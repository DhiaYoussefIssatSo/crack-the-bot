"""Configuration : tout vient de variables d'environnement (voir .env.example)."""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} doit être un entier (reçu : {raw!r})") from None
    if value < minimum:
        raise ValueError(f"{name} doit être >= {minimum} (reçu : {value})")
    return value


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} doit être un nombre (reçu : {raw!r})") from None
    if value < minimum:
        raise ValueError(f"{name} doit être >= {minimum} (reçu : {value})")
    return value


_DURATION = re.compile(r"-?(\d+(\.\d+)?(ns|us|µs|ms|s|m|h))+")


def _env_think() -> str:
    raw = os.environ.get("THINK", "off").strip().lower() or "off"
    if raw in ("off", "false", "0", "non", "no"):
        return "off"
    if raw in ("default", "auto", "défaut"):
        return "default"
    raise ValueError(f"THINK doit valoir 'off' ou 'default' (reçu : {raw!r})")


def _env_keep_alive(default: str) -> str:
    raw = os.environ.get("KEEP_ALIVE", "").strip() or default
    if re.fullmatch(r"-?\d+", raw) or _DURATION.fullmatch(raw):
        return raw
    raise ValueError(f"KEEP_ALIVE doit être un nombre de secondes ou une durée comme 24h ou 90m (reçu : {raw!r})")


@dataclass(frozen=True)
class Settings:
    # --- Modèle -----------------------------------------------------------
    backend: str = "ollama"  # "ollama" (vrai jeu) ou "mock" (tests / essai de l'interface)
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    temperature: float = 0.4
    max_tokens: int = 80  # longueur max d'une réponse du gardien
    # Contexte volontairement petit : plus rapide, et évite que le cache du modèle
    # déborde de la VRAM (2 Go sur ce PC). Un échange de jeu tient largement dedans.
    num_ctx: int = 1024
    request_timeout: float = 60.0
    # Réflexion des modèles « thinking » (Qwen3/3.5, Gemma 4…) : "off" envoie think=false à Ollama
    # (sinon la réflexion peut consommer tout le budget de MAX_TOKENS et le joueur ne voit que « … »).
    # "default" n'envoie rien. Si Ollama refuse think=false pour un modèle, on réessaie sans (voir llm.py).
    think: str = "off"
    # Réglages de vitesse (mesurés par tools/tune.py). 0 / -1 = « laisser Ollama décider » : rien n'est envoyé.
    num_thread: int = 0  # threads de calcul CPU
    num_gpu: int = -1  # couches envoyées au GPU (0 = CPU seulement)
    # Durée de maintien du modèle en mémoire. Un nombre de secondes ou une durée « 24h », « 90m ».
    # Un nombre négatif (-1) = jamais déchargé.
    keep_alive: str = "24h"

    # --- Règles du jeu ----------------------------------------------------
    time_limit: int = 180  # secondes par joueur
    wrong_guess_penalty: int = 10  # secondes perdues par mot faux dans « Valider »
    messages_per_level: int = 6  # messages que le joueur peut envoyer au gardien, par niveau
    # Échanges précédents renvoyés au modèle (0 = chaque message est indépendant). Par défaut (via .env) : autant que
    # MESSAGES_PER_LEVEL, donc toute la conversation du niveau est gardée, le début du prompt ne change jamais et le
    # cache du modèle sert à chaque message (une fenêtre glissante le fait perdre, voir GUIDE_TESTS.md).
    history_turns: int = 6
    max_message_chars: int = 300
    points_per_level: int = 1000

    # --- Serveur ----------------------------------------------------------
    data_dir: Path = ROOT / "data"
    admin_token: str = ""
    sweep_interval: float = 1.0

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.environ.get("BACKEND", "ollama").strip().lower()
        if backend not in ("ollama", "mock"):
            raise ValueError(f"BACKEND doit valoir 'ollama' ou 'mock' (reçu : {backend!r})")
        token = os.environ.get("ADMIN_TOKEN", "").strip() or secrets.token_urlsafe(6)
        messages = _env_int("MESSAGES_PER_LEVEL", cls.messages_per_level, minimum=1)
        return cls(
            backend=backend,
            ollama_url=os.environ.get("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            model=os.environ.get("MODEL", cls.model).strip(),
            temperature=_env_float("TEMPERATURE", cls.temperature),
            max_tokens=_env_int("MAX_TOKENS", cls.max_tokens, minimum=8),
            num_ctx=_env_int("NUM_CTX", cls.num_ctx, minimum=256),
            request_timeout=_env_float("REQUEST_TIMEOUT", cls.request_timeout, minimum=1.0),
            think=_env_think(),
            num_thread=_env_int("NUM_THREAD", cls.num_thread),
            num_gpu=_env_int("NUM_GPU", cls.num_gpu, minimum=-1),
            keep_alive=_env_keep_alive(cls.keep_alive),
            time_limit=_env_int("TIME_LIMIT", cls.time_limit, minimum=10),
            wrong_guess_penalty=_env_int("WRONG_GUESS_PENALTY", cls.wrong_guess_penalty),
            messages_per_level=messages,
            history_turns=_env_int("HISTORY_TURNS", messages),
            max_message_chars=_env_int("MAX_MESSAGE_CHARS", cls.max_message_chars, minimum=20),
            points_per_level=_env_int("POINTS_PER_LEVEL", cls.points_per_level, minimum=1),
            data_dir=Path(os.environ.get("DATA_DIR", str(cls.data_dir))),
            admin_token=token,
        )

    def warnings(self) -> list[str]:
        out = []
        if 0 < self.history_turns < self.messages_per_level:
            out.append(
                f"HISTORY_TURNS={self.history_turns} est inférieur à MESSAGES_PER_LEVEL={self.messages_per_level} : "
                "l'historique glisse et le cache du modèle est perdu (réponses plus lentes). "
                "Supprime la ligne HISTORY_TURNS du .env, ou mets-la à la même valeur."
            )
        return out
