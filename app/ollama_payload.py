"""Construction de la requête /api/chat d'Ollama. Bibliothèque standard seulement.

Le jeu (app/llm.py) ET les outils de mesure (tools/) passent par cette fonction : ce que l'on mesure est
donc exactement ce que le jeu envoie. Les réglages « laisser Ollama décider » (0 / -1) ne sont pas envoyés :
Ollama recharge le modèle quand certaines options changent, donc deux outils qui n'enverraient pas les
mêmes options se feraient recharger le modèle l'un l'autre.
"""
from __future__ import annotations

import re
from typing import Any

from .config import Settings


def keep_alive_value(raw: str) -> int | str:
    """« 3600 » et « -1 » → nombre (secondes) ; « 24h » → texte. Un « -1 » sans unité en texte serait refusé."""
    raw = raw.strip()
    return int(raw) if re.fullmatch(r"-?\d+", raw) else raw


def chat_payload(
    s: Settings,
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    think_off: bool | None = None,
    num_thread: int | None = None,
    num_gpu: int | None = None,
    keep_alive: str | None = None,
) -> dict[str, Any]:
    """Les arguments nommés remplacent les réglages de `s` (utile pour tools/tune.py)."""
    threads = s.num_thread if num_thread is None else num_thread
    gpu = s.num_gpu if num_gpu is None else num_gpu
    options: dict[str, Any] = {
        "temperature": s.temperature,
        "num_predict": max_tokens or s.max_tokens,
        "num_ctx": s.num_ctx,
    }
    if threads > 0:
        options["num_thread"] = threads
    if gpu >= 0:
        options["num_gpu"] = gpu
    payload: dict[str, Any] = {
        "model": s.model,
        "messages": messages,
        "stream": False,
        "keep_alive": keep_alive_value(s.keep_alive if keep_alive is None else keep_alive),
        "options": options,
    }
    if (s.think == "off") if think_off is None else think_off:
        payload["think"] = False
    return payload


def is_think_rejection(status: int, body_text: str) -> bool:
    """Ollama a-t-il refusé la requête à cause du champ « think » ? (ex. « … does not support thinking »)"""
    return status == 400 and "think" in body_text.lower()
