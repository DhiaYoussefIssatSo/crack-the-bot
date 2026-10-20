"""env_loader.sh : .env est chargé, mais une variable déjà définie dans le terminal garde la priorité."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_loader(tmp_path, env_file: str, terminal_env: dict[str, str], names: list[str]) -> dict[str, str]:
    (tmp_path / ".env").write_text(env_file, encoding="utf-8")
    script = f'. "{ROOT}/env_loader.sh"; load_dotenv_keep_terminal; ' + "; ".join(
        f'printf "%s=%s\\n" {n} "${{{n}-<absent>}}"' for n in names
    )
    out = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", **terminal_env},
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines())


def test_env_file_is_loaded_with_inline_comments(tmp_path):
    got = run_loader(tmp_path, "MODEL=gemma3:4b   # le modèle\nPORT=8123\n", {}, ["MODEL", "PORT"])
    assert got == {"MODEL": "gemma3:4b", "PORT": "8123"}


def test_terminal_value_wins_over_env_file(tmp_path):
    got = run_loader(tmp_path, "BACKEND=ollama\nMODEL=gemma3:4b\n", {"BACKEND": "mock"}, ["BACKEND", "MODEL"])
    assert got == {"BACKEND": "mock", "MODEL": "gemma3:4b"}


def test_no_env_file_is_fine(tmp_path):
    out = subprocess.run(
        ["bash", "-c", f'. "{ROOT}/env_loader.sh"; load_dotenv_keep_terminal; echo ok'],
        cwd=tmp_path, capture_output=True, text=True, check=True, env={"PATH": "/usr/bin:/bin"},
    ).stdout
    assert out.strip() == "ok"


def test_run_script_uses_the_loader():
    assert "load_dotenv_keep_terminal" in (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "load_dotenv_keep_terminal" in (ROOT / "launcher" / "crack-the-bot.sh").read_text(encoding="utf-8")
