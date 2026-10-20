"""Classement persistant (un petit fichier JSON, écrit de façon atomique).

Toutes les modifications se font dans la boucle asyncio sans `await` entre la modification
et l'écriture : pas besoin de verrou.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path

log = logging.getLogger("crackthebot.leaderboard")

_FIELDS = {"id": str, "name": str, "levels": int, "points": int, "time_left": (int, float), "at": (int, float)}


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


class Leaderboard:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: list[dict] = []
        self._load()

    # --- persistance --------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data["entries"]
            for e in entries:
                for key, typ in _FIELDS.items():
                    if not isinstance(e[key], typ):
                        raise TypeError(key)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{_stamp()}{self.path.suffix}")
            log.error("classement illisible (%r) : copie conservée dans %s, on repart de zéro", exc, backup)
            try:
                os.replace(self.path, backup)
            except OSError:
                log.exception("impossible de sauvegarder le fichier corrompu")
            return
        self.entries = entries

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "entries": self.entries}, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    # --- lecture ------------------------------------------------------------
    def _ranked(self) -> list[dict]:
        # Plus de niveaux d'abord, puis plus de temps restant, puis le premier arrivé.
        return sorted(self.entries, key=lambda e: (-e["levels"], -e["time_left"], e["at"]))

    def top(self, limit: int | None = None) -> list[dict]:
        ranked = [{**e, "rank": i} for i, e in enumerate(self._ranked(), start=1)]
        return ranked[:limit] if limit else ranked

    def rank_of(self, entry_id: str) -> int | None:
        for item in self.top():
            if item["id"] == entry_id:
                return item["rank"]
        return None

    # --- écriture -----------------------------------------------------------
    def add(self, name: str, levels: int, points: int, time_left: float) -> dict:
        entry = {
            "id": secrets.token_hex(6),
            "name": name,
            "levels": levels,
            "points": points,
            "time_left": round(time_left, 1),
            "at": time.time(),
        }
        self.entries.append(entry)
        self._save()
        return {**entry, "rank": self.rank_of(entry["id"])}

    def delete(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        if len(self.entries) == before:
            return False
        self._save()
        return True

    def reset(self) -> int:
        """Vide le classement ; l'ancien fichier est gardé en copie de sécurité."""
        count = len(self.entries)
        if self.path.exists():
            suffix = secrets.token_hex(2)  # évite d'écraser une sauvegarde faite dans la même seconde
            backup = self.path.with_name(f"{self.path.stem}.backup-{_stamp()}-{suffix}{self.path.suffix}")
            os.replace(self.path, backup)
        self.entries = []
        self._save()
        return count
