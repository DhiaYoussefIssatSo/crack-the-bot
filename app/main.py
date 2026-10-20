"""API FastAPI + pages statiques. Lancer avec :  uvicorn --factory app.main:create_app"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from contextlib import asynccontextmanager, suppress
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ROOT, Settings
from .game import GameError, GameManager
from .leaderboard import Leaderboard
from .levels import TOTAL_LEVELS, public_levels
from .llm import Backend, make_backend

log = logging.getLogger("crackthebot")
STATIC = ROOT / "static"


class NameIn(BaseModel):
    name: str


class MessageIn(BaseModel):
    message: str


class GuessIn(BaseModel):
    word: str


class ResetIn(BaseModel):
    confirm: bool = False


def create_app(
    settings: Settings | None = None,
    backend: Backend | None = None,
    clock: Callable[[], float] = time.monotonic,
    rng: random.Random | None = None,
    background: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    backend = backend or make_backend(settings)
    leaderboard = Leaderboard(settings.data_dir / "leaderboard.json")
    game = GameManager(settings, backend, leaderboard, clock=clock, rng=rng)

    async def sweeper() -> None:
        while True:
            await asyncio.sleep(settings.sweep_interval)
            try:
                await game.sweep()
            except Exception:  # pragma: no cover - ne jamais laisser mourir la tâche
                log.exception("erreur dans la tâche d'entretien")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks: list[asyncio.Task] = []
        if background:
            tasks.append(asyncio.create_task(sweeper()))
            tasks.append(asyncio.create_task(backend.warmup()))
        print(
            f"\n  Crack the Bot  |  backend: {backend.name}  |  modèle: {settings.model}\n"
            f"  Jeu          : /\n  Projecteur   : /board\n"
            f"  Admin        : /admin   (jeton : {settings.admin_token})\n",
            flush=True,
        )
        for warning in settings.warnings():
            print(f"  ATTENTION : {warning}\n", flush=True)
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await backend.aclose()

    app = FastAPI(title="Crack the Bot", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.state.game = game
    app.state.settings = settings

    @app.exception_handler(GameError)
    async def game_error_handler(_: Request, exc: GameError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    def require_admin(x_admin_token: str = Header(default="")) -> None:
        if not secrets.compare_digest(x_admin_token.encode(), settings.admin_token.encode()):
            raise HTTPException(status_code=401, detail="Jeton admin invalide.")

    # ---------------------------------------------------------------- pages
    @app.get("/", include_in_schema=False)
    async def page_player():
        return FileResponse(STATIC / "index.html")

    @app.get("/board", include_in_schema=False)
    async def page_board():
        return FileResponse(STATIC / "board.html")

    @app.get("/admin", include_in_schema=False)
    async def page_admin():
        return FileResponse(STATIC / "admin.html")

    # ------------------------------------------------------------------ API
    @app.get("/api/health")
    async def health():
        return {"backend": backend.name, "model": settings.model, **await backend.health()}

    @app.get("/api/config")
    async def config():
        return {
            "time_limit": settings.time_limit,
            "total_levels": TOTAL_LEVELS,
            "messages_per_level": settings.messages_per_level,
            "wrong_guess_penalty": settings.wrong_guess_penalty,
            "max_message_chars": settings.max_message_chars,
            "levels": public_levels(),
        }

    @app.post("/api/session")
    async def create_session(body: NameIn):
        return await game.create_session(body.name)

    @app.get("/api/session/{session_id}")
    async def get_session(session_id: str):
        return game.state(game.get(session_id))

    @app.post("/api/session/{session_id}/chat")
    async def chat(session_id: str, body: MessageIn):
        return await game.chat(session_id, body.message)

    @app.post("/api/session/{session_id}/guess")
    async def guess(session_id: str, body: GuessIn):
        return await game.guess(session_id, body.word)

    @app.post("/api/session/{session_id}/finish")
    async def finish(session_id: str):
        return await game.finish(session_id)

    @app.get("/api/leaderboard")
    async def get_leaderboard(limit: int = 10):
        limit = max(1, min(limit, 100))
        public = ("rank", "name", "levels", "points", "time_left")
        return {"entries": [{k: e[k] for k in public} for e in leaderboard.top(limit)]}

    # ---------------------------------------------------------------- admin
    @app.get("/api/admin/entries", dependencies=[Depends(require_admin)])
    async def admin_entries():
        return {"entries": leaderboard.top()}

    @app.delete("/api/admin/entries/{entry_id}", dependencies=[Depends(require_admin)])
    async def admin_delete(entry_id: str):
        if not leaderboard.delete(entry_id):
            raise HTTPException(status_code=404, detail="Entrée introuvable.")
        return {"deleted": entry_id}

    @app.post("/api/admin/reset", dependencies=[Depends(require_admin)])
    async def admin_reset(body: ResetIn):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Ajoute confirm=true pour vider le classement.")
        return {"removed": leaderboard.reset()}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
