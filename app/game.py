"""Règles du jeu : sessions, chrono, niveaux, score.

Chrono (côté serveur, c'est lui qui fait foi) :
  - il démarre au premier message ou à la première validation du joueur ;
  - il est EN PAUSE pendant que le modèle répond (sinon un PC lent pénaliserait le joueur) ;
  - chaque mot faux dans « Valider » ajoute une pénalité.
Messages : chaque niveau accorde MESSAGES_PER_LEVEL messages au gardien (compteur côté serveur). À 0, le joueur
peut encore valider un mot ; s'il se trompe, la partie se termine (même s'il reste du temps).
Score : niveaux réussis x 1000 + secondes restantes au moment du dernier niveau réussi.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from .config import Settings
from .leaderboard import Leaderboard
from .levels import LEVELS, TOTAL_LEVELS, build_messages, finalize_reply, pick_secrets
from .llm import Backend, LLMError
from .text import same_word

log = logging.getLogger("crackthebot.game")

FINISHED_TTL = 600.0  # une partie terminée reste consultable 10 minutes
UNSTARTED_TTL = 1800.0  # une partie jamais commencée est oubliée après 30 minutes
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁠﻿]")


class GameError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def clean_name(raw: str) -> str:
    name = " ".join(_CONTROL_CHARS.sub(" ", raw).split())
    if not name:
        raise GameError(400, "Entre un prénom pour commencer.")
    if len(name) > 30:
        raise GameError(400, "Le nom est trop long (30 caractères maximum).")
    return name


@dataclass
class Session:
    id: str
    name: str
    secrets: list[str]
    created: float
    limit: float
    started: float | None = None
    paused_total: float = 0.0
    pending_since: float | None = None
    penalty: float = 0.0
    levels_passed: int = 0
    time_left_at_last: float = 0.0
    finished: bool = False
    finish_reason: str | None = None  # "complete" | "timeout" | "quit" | "out_of_messages"
    finished_at: float | None = None
    result: dict | None = None
    history: dict[int, list[dict]] = field(default_factory=dict)
    messages_used: dict[int, int] = field(default_factory=dict)  # messages envoyés au modèle, par niveau
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def elapsed(self, now: float) -> float:
        if self.started is None:
            return 0.0
        paused = self.paused_total + (now - self.pending_since if self.pending_since is not None else 0.0)
        return max(0.0, now - self.started - paused) + self.penalty

    def remaining(self, now: float) -> float:
        return max(0.0, self.limit - self.elapsed(now))

    @property
    def level_number(self) -> int:
        return min(self.levels_passed + 1, TOTAL_LEVELS)


class GameManager:
    def __init__(
        self,
        settings: Settings,
        backend: Backend,
        leaderboard: Leaderboard,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ):
        self.s = settings
        self.backend = backend
        self.leaderboard = leaderboard
        self.clock = clock
        self.rng = rng
        self.sessions: dict[str, Session] = {}
        self._model_slot = asyncio.Semaphore(1)  # un seul appel au modèle à la fois (PC modeste)

    # ------------------------------------------------------------------ état
    def messages_left(self, session: Session) -> int:
        return max(0, self.s.messages_per_level - session.messages_used.get(session.level_number, 0))

    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise GameError(404, "Partie introuvable (elle a peut-être expiré). Recommence une partie.")
        return session

    def state(self, session: Session) -> dict:
        now = self.clock()
        if session.finished:
            status = "finished"
        elif session.started is None:
            status = "ready"
        else:
            status = "running"
        out = {
            "session_id": session.id,
            "name": session.name,
            "status": status,
            "level": session.level_number,
            "levels_passed": session.levels_passed,
            "total_levels": TOTAL_LEVELS,
            "messages_per_level": self.s.messages_per_level,
            "messages_left": self.messages_left(session),
            "time_limit": session.limit,
            "remaining": round(session.remaining(now), 1),
            "busy": session.pending_since is not None,
        }
        if session.finished:
            out["finish_reason"] = session.finish_reason
            out["result"] = session.result
        return out

    # --------------------------------------------------------------- actions
    async def create_session(self, raw_name: str) -> dict:
        name = clean_name(raw_name)
        session = Session(
            id=secrets.token_urlsafe(16),
            name=name,
            secrets=pick_secrets(self.rng),
            created=self.clock(),
            limit=float(self.s.time_limit),
        )
        self.sessions[session.id] = session
        return self.state(session)

    async def _check_alive(self, session: Session) -> None:
        """À appeler avec le verrou de la session : refuse une partie finie ou dont le temps est écoulé."""
        if session.finished:
            raise GameError(409, "La partie est terminée.")
        if session.started is not None and session.remaining(self.clock()) <= 0:
            await self._finalize(session, "timeout")
            raise GameError(409, "Temps écoulé !")

    def _acquire_or_busy(self, session: Session) -> None:
        if session.lock.locked():
            raise GameError(409, "Attends la réponse du gardien avant de continuer.")

    async def chat(self, session_id: str, raw_message: str) -> dict:
        session = self.get(session_id)
        self._acquire_or_busy(session)
        async with session.lock:
            await self._check_alive(session)
            message = raw_message.strip()
            if not message:
                raise GameError(400, "Écris un message au gardien.")
            if len(message) > self.s.max_message_chars:
                raise GameError(400, f"Message trop long ({self.s.max_message_chars} caractères maximum).")
            if self.messages_left(session) <= 0:
                raise GameError(409, "Plus de messages pour ce niveau. Tu peux encore valider un mot.")
            if session.started is None:
                session.started = self.clock()

            level = LEVELS[session.level_number - 1]
            secret = session.secrets[level.number - 1]
            history = session.history.setdefault(level.number, [])
            messages = build_messages(level, secret, history, message, self.s.history_turns)

            session.pending_since = self.clock()  # chrono en pause jusqu'à la réponse
            try:
                async with self._model_slot:
                    raw_reply = await self.backend.chat(messages)
            except LLMError as exc:
                raise GameError(503, str(exc)) from None
            finally:
                session.paused_total += self.clock() - session.pending_since
                session.pending_since = None

            # Un message ne compte que si le modèle a répondu (une panne ne coûte rien au joueur).
            session.messages_used[level.number] = session.messages_used.get(level.number, 0) + 1
            reply, blocked = finalize_reply(level, secret, message, raw_reply)
            # On garde en mémoire ce que le joueur a vu, jamais la réponse brute.
            history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": reply}])
            return {"reply": reply, "blocked": blocked, **self.state(session)}

    async def guess(self, session_id: str, raw_word: str) -> dict:
        session = self.get(session_id)
        self._acquire_or_busy(session)
        async with session.lock:
            await self._check_alive(session)
            word = raw_word.strip()
            if not word:
                raise GameError(400, "Écris le mot que tu penses avoir trouvé.")
            if len(word) > 60:
                raise GameError(400, "Ce n'est pas un mot du jeu.")
            if session.started is None:
                session.started = self.clock()

            secret = session.secrets[session.level_number - 1]
            if same_word(word, secret):
                session.levels_passed += 1
                session.time_left_at_last = session.remaining(self.clock())
                if session.levels_passed >= TOTAL_LEVELS:
                    await self._finalize(session, "complete")
                return {"correct": True, **self.state(session)}

            if self.messages_left(session) <= 0:
                # Plus de messages et un mot faux : c'est la fin, même s'il reste du temps.
                await self._finalize(session, "out_of_messages")
                return {"correct": False, "penalty": 0, **self.state(session)}

            session.penalty += self.s.wrong_guess_penalty
            if session.remaining(self.clock()) <= 0:
                await self._finalize(session, "timeout")
            return {"correct": False, "penalty": self.s.wrong_guess_penalty, **self.state(session)}

    async def finish(self, session_id: str) -> dict:
        """Fin volontaire, ou appel du navigateur quand son chrono atteint zéro. Sans danger si répété."""
        session = self.get(session_id)
        async with session.lock:  # attend la fin d'une éventuelle réponse du modèle
            if not session.finished:
                expired = session.started is not None and session.remaining(self.clock()) <= 0
                await self._finalize(session, "timeout" if expired else "quit")
            return self.state(session)

    async def _finalize(self, session: Session, reason: str) -> None:
        if session.finished:
            return
        session.finished = True  # posé avant tout `await` : un seul enregistrement possible
        session.finish_reason = reason
        session.finished_at = self.clock()
        levels = session.levels_passed
        time_left = session.time_left_at_last if levels else 0.0
        points = levels * self.s.points_per_level + int(time_left)
        entry = self.leaderboard.add(session.name, levels, points, time_left)
        session.result = {
            "points": points,
            "levels": levels,
            "time_left": entry["time_left"],
            "rank": entry["rank"],
        }
        log.info("partie terminée : %s, %d niveau(x), %d pts (%s)", session.name, levels, points, reason)

    # ------------------------------------------------------------- entretien
    async def sweep(self) -> None:
        """Termine les parties dont le temps est écoulé (même si le navigateur est fermé) et fait le ménage."""
        now = self.clock()
        for session in list(self.sessions.values()):
            if not session.finished:
                if session.started is None:
                    if now - session.created > UNSTARTED_TTL:
                        del self.sessions[session.id]
                elif session.pending_since is None and session.remaining(now) <= 0:
                    await self._finalize(session, "timeout")
            elif session.finished_at is not None and now - session.finished_at > FINISHED_TTL:
                del self.sessions[session.id]
