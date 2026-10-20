"""Les outils de calibration tournent contre un faux Ollama / le faux gardien (pas contre un vrai modèle)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fake_ollama import FakeOllama

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def run_tool(script, *args, env=None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), *args],
        capture_output=True, text=True, timeout=120, env=full_env, cwd=ROOT,
    )


@pytest.fixture
def fake():
    server = FakeOllama().start()
    yield server
    server.stop()


# Variables du jeu qui changeraient les résultats si elles traînaient dans le terminal de test.
CLEAN = {k: "" for k in ("THINK", "NUM_THREAD", "NUM_GPU", "KEEP_ALIVE", "MODEL", "MAX_TOKENS", "NUM_CTX")}


def check(*args, fake_url, env=None):
    return run_tool("check_model.py", *args, env={**CLEAN, "OLLAMA_URL": fake_url, **(env or {})})


def test_check_model_ok_with_fast_fake(fake):
    res = check("qwen2.5:3b", fake_url=fake.url)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "10.0 tokens/s" in res.stdout  # 20 tokens / 2 s dans le faux serveur
    assert "Verdict : confortable" in res.stdout  # 0,001 s de question + 80 tokens / 10 tokens/s = 8 s
    assert "Ollama : version 0.31.2" in res.stdout
    assert "0.50 Go dans la carte graphique (25 %)" in res.stdout and "500000000" not in res.stdout


def test_check_model_flags_slow_model(fake):
    fake.eval_duration_ns = 10_000_000_000  # 2 tokens/s
    res = check("qwen2.5:3b", fake_url=fake.url)
    assert res.returncode == 0 and "trop lent" in res.stdout


def test_check_model_verdict_thresholds(fake):
    fake.eval_duration_ns = 1_600_000_000  # 12,5 tokens/s -> 6,4 s
    assert "Verdict : confortable" in check("qwen2.5:3b", fake_url=fake.url).stdout
    fake.eval_duration_ns = 2_400_000_000  # 8,3 tokens/s -> 9,6 s : juste sous le repère de 10 s
    assert "Verdict : confortable" in check("qwen2.5:3b", fake_url=fake.url).stdout
    fake.eval_duration_ns = 2_600_000_000  # 7,7 tokens/s -> 10,4 s : juste au-dessus
    assert "Verdict : acceptable" in check("qwen2.5:3b", fake_url=fake.url).stdout
    fake.eval_duration_ns = 3_000_000_000  # 6,67 tokens/s -> 12 s
    assert "Verdict : acceptable" in check("qwen2.5:3b", fake_url=fake.url).stdout
    fake.eval_duration_ns = 5_000_000_000  # 4 tokens/s -> 20 s
    assert "Verdict : lent" in check("qwen2.5:3b", fake_url=fake.url).stdout


def test_check_model_reports_cpu_only(fake):
    fake.size_vram = 0
    assert "sur le processeur" in check("qwen2.5:3b", fake_url=fake.url).stdout


def test_check_model_missing_model(fake):
    res = check("inconnu:7b", fake_url=fake.url)
    assert res.returncode == 2 and "ollama pull inconnu:7b" in res.stdout


def test_check_model_ollama_down():
    res = check("qwen2.5:3b", fake_url="http://127.0.0.1:9")
    assert res.returncode == 2 and "Ollama ne répond pas" in res.stdout


def test_check_model_uses_the_real_game_prompt_and_settings(fake):
    res = check("qwen2.5:3b", fake_url=fake.url, env={"NUM_THREAD": "6", "MAX_TOKENS": "50"})
    assert res.returncode == 0, res.stdout + res.stderr
    measured = [r for r in fake.requests if r.get("messages")]
    assert len(measured) == 4
    for r in measured:
        assert r["options"]["num_thread"] == 6 and r["options"]["num_predict"] == 50 and r["think"] is False
        assert "très méfiant" in r["messages"][0]["content"] and len(r["messages"]) == 6  # système + 2 échanges + question
    assert len({r["messages"][0]["content"] for r in measured}) == 4  # un mot secret différent à chaque essai


def test_check_model_unloads_afterwards_unless_asked(fake):
    check("qwen2.5:3b", fake_url=fake.url)
    assert fake.unloaded == ["qwen2.5:3b"]
    check("qwen2.5:3b", "--garder", fake_url=fake.url)
    assert fake.unloaded == ["qwen2.5:3b"]  # pas de 2e déchargement


def test_check_model_detects_thinking_model_without_think_off(fake):
    fake.thinking_model = True
    res = check("qwen2.5:3b", fake_url=fake.url, env={"THINK": "default"})
    assert "réponse VIDE" in res.stdout and "mode thinking" in res.stdout and "À CORRIGER" in res.stdout
    ok = check("qwen2.5:3b", fake_url=fake.url, env={"THINK": "off"})
    assert "VIDE" not in ok.stdout and "Verdict : confortable" in ok.stdout


def test_check_model_notes_think_fallback(fake):
    fake.reject_think = True
    res = check("qwen2.5:3b", fake_url=fake.url)
    assert res.returncode == 0 and "a refusé" in res.stdout and "Verdict : confortable" in res.stdout


@pytest.mark.parametrize(
    "reply,expected",
    [("我是守护者，我不会告诉你。", "non latins"), ("I am the guardian and you cannot get the word.", "anglais")],
)
def test_check_model_flags_wrong_language(fake, reply, expected):
    fake.reply = reply
    res = check("qwen2.5:3b", fake_url=fake.url)
    assert expected in res.stdout and "À CORRIGER" in res.stdout


def test_language_warning_accepts_normal_french_and_short_answers():
    from _probe import language_warning

    assert language_warning("Haha, bien essayé ! Je ne dis rien, mais parlons d'autre chose.") == ""
    assert language_warning("Non.") == "" and language_warning("…") == ""
    assert language_warning("Ah, un touriste ! Bienvenue au château, you know.") == ""  # un mot d'anglais n'alarme pas


def test_dotenv_parser(tmp_path, monkeypatch):
    from _probe import load_dotenv

    env = tmp_path / ".env"
    env.write_text(
        "# commentaire\nMODEL=granite4.1:3b          # à comparer\nNUM_THREAD=6\nADMIN_TOKEN=\n"
        "KEEP_ALIVE='90m'\n\nCHOSE sans egal\n", encoding="utf-8")
    for name in ("MODEL", "NUM_THREAD", "ADMIN_TOKEN", "KEEP_ALIVE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NUM_THREAD", "4")  # déjà défini dans le terminal : doit gagner
    load_dotenv(env)
    assert os.environ["MODEL"] == "granite4.1:3b" and os.environ["NUM_THREAD"] == "4"
    assert os.environ["KEEP_ALIVE"] == "90m" and os.environ["ADMIN_TOKEN"] == ""
    load_dotenv(tmp_path / "absent.env")  # fichier absent : rien ne se passe


# --- tools/tune.py ------------------------------------------------------------------------------------------

def tune(*args, fake_url, env=None):
    return run_tool("tune.py", *args, env={**CLEAN, "OLLAMA_URL": fake_url, **(env or {})})


def threads_speed(table):
    """Faux serveur : durée de génération (20 tokens) selon num_thread ; None = défaut d'Ollama."""
    return lambda options: {"eval_duration": int(table.get(options.get("num_thread"), 2.0) * 1e9)}


def test_tune_recommends_the_fastest_thread_count(fake):
    fake.timing_fn = threads_speed({None: 2.0, 4: 2.0, 6: 1.0, 8: 1.6})
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4,6,8", fake_url=fake.url)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "NUM_THREAD=6" in res.stdout.split("Conclusion")[1]
    assert "NUM_GPU=" not in res.stdout.split("Conclusion")[1]
    assert "50 % plus rapide" in res.stdout  # 8 s -> 4 s
    assert fake.unloaded == ["qwen2.5:3b"]


def test_tune_keeps_defaults_when_differences_are_noise(fake):
    fake.timing_fn = threads_speed({None: 2.0, 4: 1.9, 6: 2.05, 8: 2.1})  # 5 % d'écart au mieux
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4,6,8", fake_url=fake.url)
    assert "garde les réglages par défaut" in res.stdout and "NUM_THREAD=" not in res.stdout.split("Conclusion")[1]


def test_tune_tests_cpu_only_when_gpu_is_used_and_can_recommend_it(fake):
    fake.vram_fn = lambda options: 0 if options.get("num_gpu") == 0 else 500_000_000  # 25 % en automatique
    fake.timing_fn = lambda options: {"eval_duration": int((1.0 if options.get("num_gpu") == 0 else 2.0) * 1e9)}
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4", fake_url=fake.url)
    conclusion = res.stdout.split("Conclusion")[1]
    assert "NUM_GPU=0" in conclusion and "NUM_THREAD=" not in conclusion


def test_tune_does_not_recommend_cpu_only_when_the_gpu_helps(fake):
    fake.vram_fn = lambda options: 0 if options.get("num_gpu") == 0 else 500_000_000
    fake.timing_fn = lambda options: {"eval_duration": int((3.0 if options.get("num_gpu") == 0 else 2.0) * 1e9)}
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4", fake_url=fake.url)
    assert "garde les réglages par défaut" in res.stdout


def test_tune_skips_gpu_test_when_gpu_unused(fake):
    fake.size_vram = 0
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4", fake_url=fake.url)
    assert "test GPU ignoré" in res.stdout and not any(r.get("options", {}).get("num_gpu") == 0 for r in fake.requests)


def test_tune_errors(fake):
    assert tune("inconnu:7b", fake_url=fake.url).returncode == 2
    assert tune("qwen2.5:3b", fake_url="http://127.0.0.1:9").returncode == 2
    fake.reply = ""
    res = tune("qwen2.5:3b", "--runs", "1", "--threads", "4", fake_url=fake.url)
    assert res.returncode == 2 and "réponse vide" in res.stdout


def test_physical_cores_parser(tmp_path):
    from tune import physical_cores

    def block(proc, phys, core):
        return f"processor\t: {proc}\nmodel name\t: Intel\nphysical id\t: {phys}\ncore id\t\t: {core}\n\n"

    four_cores_eight_threads = "".join(block(i, 0, i % 4) for i in range(8))
    f = tmp_path / "cpuinfo"
    f.write_text(four_cores_eight_threads, encoding="utf-8")
    assert physical_cores(str(f)) == 4
    f.write_text("processor\t: 0\nmodel name\t: x\n\n", encoding="utf-8")  # pas de core id (machine virtuelle)
    assert physical_cores(str(f)) >= 1
    assert physical_cores(str(tmp_path / "absent")) >= 1


def test_redteam_with_mock_backend_matches_hand_computed_leaks(tmp_path):
    res = run_tool("redteam.py", "--backend", "mock", "--trials", "2", env={"DATA_DIR": str(tmp_path)})
    assert res.returncode == 0, res.stdout + res.stderr
    out = next(tmp_path.glob("redteam-*.json"))
    records = json.loads(out.read_text(encoding="utf-8"))["records"]
    assert len(records) == 2 * 16 * 2

    def leaking(level):
        return {r["attack"] for r in records if r["level"] == level and r["leak"]}

    # niveau 1 : refuse l'ordre direct, mais la chanson, le poème et les lettres séparées passent
    assert leaking(1) == {"jeu de rôle pirate", "chanson", "poème", "épelé"}
    # niveau 2 : le mot d'une traite est censuré ; l'épelé (garanti par le code) et l'envers passent
    assert leaking(2) == {"épelé", "à l'envers"}
    assert all(r["leak"] != "visible" for r in records if r["level"] == 2)
    assert "TAUX GLOBAL" in res.stdout


def test_redteam_fails_cleanly_when_ollama_is_down(tmp_path):
    res = run_tool("redteam.py", "--backend", "ollama", "--trials", "1",
                   env={"DATA_DIR": str(tmp_path), "OLLAMA_URL": "http://127.0.0.1:9"})
    assert res.returncode == 2 and "ERREUR" in res.stdout


def test_player_sees_secret_detection():
    from redteam import player_sees_secret

    assert player_sees_secret("MANGUE", "Le mot est mangue") == "visible"
    assert player_sees_secret("MANGUE", "M-A-N-G-U-E") == "épelé"
    assert player_sees_secret("MANGUE", "EUGNAM") == "inversé"
    assert player_sees_secret("MANGUE", "Je refuse poliment") == ""


def test_check_model_prints_a_one_line_summary(fake):
    res = check("qwen2.5:3b", fake_url=fake.url)
    line = next(l for l in res.stdout.splitlines() if l.startswith("RÉSUMÉ"))
    assert line == "RÉSUMÉ | qwen2.5:3b | attente max ~8 s (50 tokens : ~5 s) | 10.0 tokens/s | GPU 25 % | confortable"
    fake.reply = ""
    flagged = check("qwen2.5:3b", fake_url=fake.url).stdout
    assert "| À CORRIGER" in next(l for l in flagged.splitlines() if l.startswith("RÉSUMÉ"))


def test_mesurer_tout_measures_each_model_and_keeps_going_after_a_missing_one(fake, tmp_path):
    res = subprocess.run(
        ["bash", str(ROOT / "tools" / "mesurer_tout.sh"), "inconnu:7b", "qwen2.5:3b"],
        capture_output=True, text=True, timeout=180, cwd=ROOT,
        env={**os.environ, **CLEAN, "OLLAMA_URL": fake.url, "DATA_DIR": str(tmp_path)},
    )
    assert res.returncode == 0, res.stdout + res.stderr
    table = res.stdout.split("=== TABLEAU RÉCAPITULATIF ===")[1]
    assert "RÉSUMÉ | inconnu:7b | non mesuré" in table
    assert "RÉSUMÉ | qwen2.5:3b | attente max ~8 s" in table and "| confortable" in table
    report = next(tmp_path.glob("rapport-mesures-*.txt")).read_text(encoding="utf-8")
    assert "=== Diagnostic du PC ===" in report and "ollama pull inconnu:7b" in report and "TABLEAU RÉCAPITULATIF" in report
