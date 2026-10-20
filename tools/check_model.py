#!/usr/bin/env python3
"""Mesure ce qu'un joueur vivra avec ce modèle sur CE PC : temps d'attente par réponse, GPU, mode réflexion.

Usage :  python3 tools/check_model.py [modèle]      (par défaut : MODEL du .env, sinon qwen2.5:3b)

Le test envoie de vrais prompts du jeu (dernier niveau, historique, mot secret différent à chaque essai) avec les
réglages de votre .env. Aucune dépendance : « python3 » du système suffit. Les seuils du verdict sont des
repères que j'ai choisis pour ce jeu, pas des valeurs officielles : c'est à vous de juger si l'attente vous va.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import _probe as p

RUNS = 4  # l'essai 1 charge le modèle et n'est pas compté
# Attente maximale d'un joueur (secondes) -> jugement. Repères choisis, voir ci-dessus.
VERDICTS = ((10, "confortable"), (15, "acceptable"), (25, "lent"))


def gpu_line() -> str:
    if not shutil.which("nvidia-smi"):
        return "nvidia-smi introuvable (pas de pilote Nvidia détecté : Ollama travaillera sur le processeur)"
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=15,
    )
    return out.stdout.strip() or out.stderr.strip() or "nvidia-smi n'a rien répondu"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep = "--garder" in sys.argv  # ne pas décharger le modèle à la fin
    s = p.settings_for(args[0] if args else None)
    probe = p.Probe(s, s.ollama_url)
    print(f"Serveur : {s.ollama_url}   Modèle : {s.model}")
    print(f"Réglages : num_ctx={s.num_ctx}  max_tokens={s.max_tokens}  think={s.think}  "
          f"num_thread={s.num_thread or 'auto'}  num_gpu={'auto' if s.num_gpu < 0 else s.num_gpu}")
    print("Carte graphique :", gpu_line())

    try:
        names = probe.installed()
    except p.ProbeError as exc:
        print(f"\nERREUR : {exc}. Lance-le avec « ollama serve » (ou ouvre l'application).")
        return 2
    print(f"Ollama : version {probe.version()}\n")
    if s.model not in names and f"{s.model}:latest" not in names:
        print(f"ERREUR : le modèle « {s.model} » n'est pas installé. Installés : {', '.join(names) or 'aucun'}.")
        print(f"         Installe-le avec :  ollama pull {s.model}")
        return 2

    rows: list[dict] = []
    sample = ""
    problems: list[str] = []
    for i in range(1, RUNS + 1):
        try:
            result, wall = probe.chat(p.realistic_messages(i))
        except p.ProbeError as exc:
            print(f"\nERREUR pendant l'essai {i} : {exc}")
            return 2
        t = p.timings(result, wall)
        answer = p.answer_text(result).strip()
        if i == 1:
            print(f"Essai 1 (chargement du modèle {t['load_s']:.1f} s, essai non compté) : durée totale {wall:.1f} s")
        else:
            print(f"Essai {i} : question de {t['prompt_tokens']} tokens traitée en {t['prompt_s']:.1f} s, "
                  f"réponse de {t['gen_tokens']} tokens en {t['gen_s']:.1f} s ({t['gen_rate']:.1f} tokens/s) "
                  f"=> attente {wall:.1f} s")
            rows.append(t)
        if not answer:
            problems.append("réponse VIDE" + (" : le modèle a réfléchi sans répondre (mode thinking ?)"
                                              if p.reasoning_text(result) else ""))
        elif i == 2:
            sample = answer
            warn = p.language_warning(answer)
            if warn:
                problems.append(warn)
    if probe.think_fallback_used:
        print("\nNote : Ollama a refusé « think: false » pour ce modèle (il n'a pas de mode réflexion) : "
              "le jeu enverra la requête sans ce champ, automatiquement.")
    print("\nExemple de réponse :", sample.replace("\n", " ")[:200] or "(vide)")

    share = probe.gpu_share()
    gpu_pct = 0.0
    if share and share[0]:
        size, vram = share
        pct = gpu_pct = 100 * vram / size
        print(f"\nMémoire : modèle de {size / 1e9:.2f} Go, dont {vram / 1e9:.2f} Go dans la carte graphique ({pct:.0f} %).")
        if pct < 5:
            print("  -> Le calcul se fait sur le processeur. Avec ~2 Go de VRAM c'est attendu pour un modèle de 3B ou plus.")
        elif pct < 95:
            print("  -> Modèle réparti entre carte graphique et processeur : plus lent qu'un chargement 100 % GPU.")
        else:
            print("  -> Modèle entièrement dans la carte graphique.")
    else:
        print("\nMémoire : impossible de lire /api/ps (le modèle est peut-être déjà déchargé).")

    prompt_s = p.median([r["prompt_s"] for r in rows])
    rate = p.median([r["gen_rate"] for r in rows])
    typical = p.median([r["wall_s"] for r in rows])
    worst = p.worst_case_s(prompt_s, rate, s.max_tokens)
    short = p.worst_case_s(prompt_s, rate, 50)
    print(f"\nVitesse de génération : {rate:.1f} tokens/s.   Traitement de la question : {prompt_s:.1f} s.")
    print(f"Attente typique d'un joueur : {typical:.1f} s.   Attente maximale (MAX_TOKENS={s.max_tokens}) : ~{worst:.0f} s.   "
          f"Avec MAX_TOKENS=50 : ~{short:.0f} s.")
    print("(Ollama réutilise parfois le début de la conversation déjà calculé : en partie réelle, l'attente peut être un peu plus courte.)")

    label = next((name for limit, name in VERDICTS if worst <= limit), "trop lent")
    short_verdict = "À CORRIGER" if problems else label
    if problems:
        print("\nProblèmes détectés :")
        for item in problems:
            print("  -", item)
        print("\nVerdict : À CORRIGER avant de juger la vitesse (voir ci-dessus).")
    elif label == "trop lent":
        print("\nVerdict : trop lent pour un jeu chronométré (repère : attente maximale > 25 s). Prends un modèle plus petit.")
    elif label == "lent":
        print("\nVerdict : lent (attente maximale entre 15 et 25 s). Essaie MAX_TOKENS=50, lance tools/tune.py, "
              "ou un modèle plus petit, et teste avec de vrais joueurs.")
    else:
        print(f"\nVerdict : {label} (attente maximale {worst:.0f} s ; repères : ≤ 10 s confortable, ≤ 15 s acceptable).")
    print("Rappel : cette mesure ne dit RIEN sur la qualité du gardien. Lance ensuite tools/redteam.py.")
    print(f"RÉSUMÉ | {s.model} | attente max ~{worst:.0f} s (50 tokens : ~{short:.0f} s) | {rate:.1f} tokens/s | "
          f"GPU {gpu_pct:.0f} % | {short_verdict}")

    if not keep:
        probe.unload()
        print("(Le modèle a été déchargé de la mémoire pour que la mesure suivante parte propre ; "
              "ajoute --garder pour l'éviter.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
