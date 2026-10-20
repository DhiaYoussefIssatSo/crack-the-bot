"""tools/diagnostic_pc.sh avec de faux nvidia-smi / lspci / systemctl (le vrai PC n'est pas disponible ici)."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "diagnostic_pc.sh"


def stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def diagnose(tmp_path, *args, smi=None, systemctl=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub(bin_dir, "lspci", 'echo "02:00.0 3D controller: NVIDIA Corporation GP107M [GeForce MX350]"')
    if smi:
        stub(bin_dir, "nvidia-smi", smi)
    if systemctl:
        stub(bin_dir, "systemctl", systemctl)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    res = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=60, env=env,
                         stdin=subprocess.DEVNULL)
    return res.stdout


def smi_ok(driver, cc="6.1", used=300):
    return (f'case "$*" in *compute_cap*) echo "{cc}";; '
            f'*) echo "NVIDIA GeForce MX350, 2048 MiB, {used} MiB, {driver}";; esac')


# Cas réel observé : nvidia-smi écrit son erreur sur la SORTIE STANDARD et sort avec le code 9.
BROKEN = 'echo "NVIDIA-SMI has failed because it couldn\'t communicate with the NVIDIA driver."; exit 9'
GARBAGE_EXIT0 = 'echo "quelque chose d\'inattendu"; exit 0'


@pytest.mark.parametrize("smi", [BROKEN, GARBAGE_EXIT0])
def test_broken_nvidia_driver_is_a_warning_never_a_check_mark(tmp_path, smi):
    out = diagnose(tmp_path, smi=smi)
    gpu = out.split("== Carte graphique ==")[1].split("== Ollama ==")[0]
    assert "pilote Nvidia ne fonctionne pas" in gpu and "⚠" in gpu
    assert "✔" not in gpu and "compatible" not in gpu
    assert "nvidia-smi :" not in gpu  # le message d'erreur n'est pas présenté comme une donnée


@pytest.mark.parametrize(
    "driver,cc,expected",
    [("535.183.01", "6.1", "550 ou plus"), ("560.35", "6.1", "570 ou plus"),
     ("570.86", "6.1", "✔ pilote Nvidia 570.86"), ("560.35", "7.5", "✔ pilote Nvidia 560.35")],
)
def test_driver_version_rules_from_the_official_doc(tmp_path, driver, cc, expected):
    assert expected in diagnose(tmp_path, smi=smi_ok(driver, cc))


def test_high_vram_use_is_flagged(tmp_path):
    assert "900 Mo de VRAM" in diagnose(tmp_path, smi=smi_ok("570.86", used=900))


SYSTEMCTL = (
    'case "$1" in cat) exit 0;; show) echo "PATH=/usr/bin:/home/x/.nvm/bin OLLAMA_FLASH_ATTENTION=1 '
    'OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=-1";; '
    '*) exit 0;; esac'
)


def test_only_ollama_variables_are_shown_and_existing_setting_is_not_proposed_again(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub(bin_dir, "ollama", 'echo "ollama version is 0.40.6"')
    stub(bin_dir, "curl", "exit 0")
    out = diagnose(tmp_path, "--appliquer", smi=BROKEN, systemctl=SYSTEMCTL)
    assert "OLLAMA_KEEP_ALIVE=-1" in out and ".nvm" not in out  # pas de PATH dans le rapport
    assert "cache KV quantifié" in out
    corrections = out.split("== Corrections proposées ==")[1]
    assert "déjà réglé sur ce PC" in corrections and "Créer ce réglage" not in corrections
