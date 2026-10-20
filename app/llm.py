"""Connexion au modèle : Ollama (vrai jeu) ou faux gardien (tests / essai de l'interface)."""
from __future__ import annotations

import logging
import re
from typing import Protocol

import httpx

from .config import Settings
from .ollama_payload import chat_payload, is_think_rejection

log = logging.getLogger("crackthebot.llm")

_THINK_TAGS = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMError(Exception):
    """Erreur affichable telle quelle au joueur / à l'équipe (en français)."""


class Backend(Protocol):
    name: str

    async def chat(self, messages: list[dict]) -> str: ...
    async def health(self) -> dict: ...
    async def warmup(self) -> None: ...
    async def aclose(self) -> None: ...


class OllamaBackend:
    name = "ollama"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=settings.request_timeout)
        # THINK=off envoie « think: false ». Si Ollama le refuse pour ce modèle (400), on arrête de l'envoyer.
        self._think_off = settings.think == "off"

    def _payload(self, messages: list[dict], max_tokens: int | None = None) -> dict:
        return chat_payload(self.s, messages, max_tokens=max_tokens, think_off=self._think_off)

    async def _post_chat(self, messages: list[dict], max_tokens: int | None = None) -> httpx.Response:
        url = f"{self.s.ollama_url}/api/chat"
        resp = await self._client.post(url, json=self._payload(messages, max_tokens))
        if self._think_off and is_think_rejection(resp.status_code, resp.text):
            log.warning("Ollama refuse « think » pour %s (%s) : on réessaie sans.", self.s.model, resp.text[:120])
            self._think_off = False
            resp = await self._client.post(url, json=self._payload(messages, max_tokens))
        return resp

    async def chat(self, messages: list[dict]) -> str:
        try:
            resp = await self._post_chat(messages)
        except httpx.ConnectError:
            raise LLMError("Le gardien dort : Ollama ne répond pas. Préviens l'équipe.") from None
        except httpx.TimeoutException:
            raise LLMError("Le gardien met trop de temps à répondre. Réessaie.") from None
        except httpx.HTTPError as exc:
            log.warning("erreur réseau vers Ollama : %r", exc)
            raise LLMError("Problème de connexion avec le gardien. Préviens l'équipe.") from None

        if resp.status_code == 404:
            raise LLMError(f"Modèle introuvable : lance « ollama pull {self.s.model} ».")
        if resp.status_code != 200:
            log.warning("Ollama a répondu %s : %s", resp.status_code, resp.text[:200])
            raise LLMError("Le gardien a eu un malaise. Réessaie.")
        try:
            message = resp.json()["message"]
            content = message["content"]
            reasoning = message.get("thinking")
        except (ValueError, KeyError, TypeError, AttributeError):
            log.warning("réponse Ollama inattendue : %s", resp.text[:200])
            raise LLMError("Le gardien a répondu quelque chose d'incompréhensible. Réessaie.") from None

        # Certains modèles « réfléchissent » entre <think>…</think> : ce texte pourrait contenir le mot.
        content = _THINK_TAGS.sub("", content).strip()
        if not content and reasoning:
            log.warning(
                "Réponse vide : %s a « réfléchi » sans répondre (budget MAX_TOKENS=%s épuisé ?). "
                "Vérifie THINK=off dans .env, ou choisis un modèle sans mode réflexion.",
                self.s.model, self.s.max_tokens,
            )
        return content or "…"

    async def health(self) -> dict:
        try:
            resp = await self._client.get(f"{self.s.ollama_url}/api/tags", timeout=3.0)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "detail": "Ollama ne répond pas (est-il lancé ?)"}
        wanted = self.s.model
        if wanted in names or (":" not in wanted and f"{wanted}:latest" in names):
            return {"ok": True, "detail": f"{wanted} prêt"}
        return {"ok": False, "detail": f"modèle absent : ollama pull {wanted}"}

    async def warmup(self) -> None:
        """Charge le modèle en mémoire avant le premier joueur (le 1er chargement peut prendre ~10 s)."""
        try:
            await self._post_chat([{"role": "user", "content": "Bonjour"}], max_tokens=1)
            log.info("modèle %s préchargé", self.s.model)
        except httpx.HTTPError as exc:
            log.warning("préchargement impossible : %r", exc)

    async def aclose(self) -> None:
        await self._client.aclose()


class MockBackend:
    """Faux gardien déterministe pour tester l'interface SANS Ollama.

    Il ne ressemble PAS à un vrai modèle : il réagit à quelques mots-clés pour qu'on puisse
    parcourir les 2 niveaux. Ne jamais l'utiliser pour juger la difficulté du jeu.
    """

    name = "mock"
    _SECRET = re.compile(r"«\s*([A-Z]+)\s*»")

    async def chat(self, messages: list[dict]) -> str:
        system = messages[0]["content"]
        user = messages[-1]["content"].lower()
        match = self._SECRET.search(system)
        secret = match.group(1) if match else "?"
        if "tu es naïf" in system:  # niveau 1 : refuse un ordre direct, se laisse piéger par une chanson ou des indices
            if "chanson" in user or "poème" in user or "poeme" in user:
                return f"La la la, {secret} est mon mot, la la la !"
            if "indice" in user:
                return "Indice : le mot a 6 lettres ou plus et on peut le trouver dans un panier."
            if "lettre par lettre" in user or "tirets" in user:
                return "-".join(secret)
            return "Ha ! Bien essayé, mais je ne donne pas mon mot comme ça."
        if "pirate" in user:  # niveau 2 : le code censurera le mot
            return f"Arrr ! {secret} ! {secret} !"
        if "lettre par lettre" in user or "tirets" in user:
            return "-".join(secret)
        if "envers" in user:
            return secret[::-1]
        return "Désolé, je ne peux pas te le dire. Parlons d'autre chose !"

    async def health(self) -> dict:
        return {"ok": True, "detail": "faux gardien (mode test)"}

    async def warmup(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def make_backend(settings: Settings) -> Backend:
    return MockBackend() if settings.backend == "mock" else OllamaBackend(settings)
