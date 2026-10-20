import pytest

from app.config import Settings


def clean(monkeypatch):
    for name in ("THINK", "NUM_THREAD", "NUM_GPU", "KEEP_ALIVE", "MODEL", "ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch):
    clean(monkeypatch)
    s = Settings.from_env()
    assert (s.think, s.num_thread, s.num_gpu, s.keep_alive) == ("off", 0, -1, "24h")


def test_valid_values(monkeypatch):
    clean(monkeypatch)
    monkeypatch.setenv("THINK", "default")
    monkeypatch.setenv("NUM_THREAD", "6")
    monkeypatch.setenv("NUM_GPU", "0")
    monkeypatch.setenv("KEEP_ALIVE", "90m")
    s = Settings.from_env()
    assert (s.think, s.num_thread, s.num_gpu, s.keep_alive) == ("default", 6, 0, "90m")
    for ok in ("-1", "3600", "1h30m", "24h"):
        monkeypatch.setenv("KEEP_ALIVE", ok)
        assert Settings.from_env().keep_alive == ok


@pytest.mark.parametrize(
    "name,value",
    [("THINK", "peut-être"), ("NUM_THREAD", "-2"), ("NUM_GPU", "-5"), ("NUM_GPU", "beaucoup"),
     ("KEEP_ALIVE", "longtemps"), ("KEEP_ALIVE", "24 heures")],
)
def test_invalid_values_are_refused_with_a_clear_message(monkeypatch, name, value):
    clean(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_think_aliases(monkeypatch):
    clean(monkeypatch)
    for raw in ("off", "OFF", "false", "0", ""):
        monkeypatch.setenv("THINK", raw)
        assert Settings.from_env().think == "off"


def test_env_example_parses_the_same_in_bash_and_python_and_documents_the_real_defaults(monkeypatch, tmp_path):
    """Le fichier .env.example copié tel quel ne doit rien changer (valeurs = défauts), pour run.sh ET les outils."""
    import subprocess
    import sys
    from dataclasses import fields
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    from _probe import load_dotenv

    names = [line.split("=")[0] for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
             if "=" in line and not line.startswith("#")]
    for name in names:
        monkeypatch.delenv(name, raising=False)
    load_dotenv(root / ".env.example")
    from_python = Settings.from_env()
    defaults = Settings()
    for f in fields(Settings):
        if f.name in ("admin_token", "data_dir"):  # jeton aléatoire ; chemin relatif écrit ./data
            continue
        assert getattr(from_python, f.name) == getattr(defaults, f.name), f.name

    # Même lecture par bash (c'est ainsi que run.sh charge .env) : on compare les valeurs brutes.
    script = 'set -a; . "$1"; set +a; for n in "${@:2}"; do printf "%s=%s\\n" "$n" "${!n}"; done'
    out = subprocess.run(["bash", "-c", script, "_", str(root / ".env.example"), *names],
                         capture_output=True, text=True, check=True, env={"PATH": "/usr/bin:/bin"}).stdout
    bash_values = dict(line.split("=", 1) for line in out.splitlines())
    import os

    for name in names:
        assert bash_values[name] == os.environ[name], name


def test_history_follows_messages_per_level_unless_set(monkeypatch):
    clean(monkeypatch)
    assert Settings.from_env().messages_per_level == 6 and Settings.from_env().history_turns == 6
    monkeypatch.setenv("MESSAGES_PER_LEVEL", "4")
    assert Settings.from_env().history_turns == 4
    monkeypatch.setenv("HISTORY_TURNS", "2")
    assert Settings.from_env().history_turns == 2
    monkeypatch.setenv("HISTORY_TURNS", "")
    assert Settings.from_env().history_turns == 4  # ligne vide = comme si elle n'existait pas


def test_messages_per_level_validation(monkeypatch):
    clean(monkeypatch)
    for bad in ("0", "-1", "six"):
        monkeypatch.setenv("MESSAGES_PER_LEVEL", bad)
        with pytest.raises(ValueError, match="MESSAGES_PER_LEVEL"):
            Settings.from_env()


def test_warning_when_history_window_is_shorter_than_the_cap():
    assert Settings(messages_per_level=6, history_turns=2).warnings()
    assert not Settings(messages_per_level=6, history_turns=6).warnings()
    assert not Settings(messages_per_level=6, history_turns=0).warnings()  # 0 = choix explicite : messages indépendants
    assert not Settings(messages_per_level=6, history_turns=10).warnings()
