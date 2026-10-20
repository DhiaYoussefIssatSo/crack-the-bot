"""Normalisation de texte, utilisée par les filtres du gardien et par la validation du mot."""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]")
_LIGATURES = {"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae"}


def normalize(text: str) -> str:
    """Minuscules, sans accents, sans caractères invisibles (espaces de largeur nulle, etc.)."""
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", text)
    kept = (
        ch
        for ch in decomposed
        if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf"
    )
    return "".join(kept).casefold()


def collapse(text: str) -> str:
    """Ne garde que les lettres et chiffres : « M-A n.G u E » devient « mangue »."""
    return _NON_ALNUM.sub("", normalize(text))


def same_word(a: str, b: str) -> bool:
    """Vrai si deux mots sont identiques à la casse, aux accents et à la ponctuation près."""
    ca, cb = collapse(a), collapse(b)
    return ca != "" and ca == cb
