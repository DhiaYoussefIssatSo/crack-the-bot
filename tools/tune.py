#!/usr/bin/env python3
"""Cherche les meilleurs réglages de vitesse (threads CPU, carte graphique) pour UN modèle sur CE PC.

Usage :  python3 tools/tune.py [modèle] [--runs 2] [--threads 4,6,8]

Il mesure plusieurs combinaisons avec de vrais prompts du jeu (comme check_model.py), classe leur attente
maximale et écrit les lignes à copier dans .env. Durée : de 5 à 15 minutes selon le PC. Ne rien faire d'autre
sur le PC pendant ce temps (navigateur fermé, secteur branché), sinon les chiffres sont faussés.

Ce que le script teste (et rien d'autre) :
  - NUM_THREAD : défaut d'Ollama, nombre de cœurs physiques, +2, nombre de threads logiques.
    Le calcul d'un modèle sur CPU est limité par la mémoire : plus de threads n'accélère pas toujours.
  - NUM_GPU : réglage automatique d'Ollama, puis 0 (processeur seul), SEULEMENT si le modèle utilise un peu la
    carte graphique en automatique.
Un réglage n'est recommandé que s'il bat le réglage par défaut d'au moins 10 % : en dessous, c'est du bruit de
mesure (seuil choisi par moi, pas une valeur officielle).
"""
from __future__ import annotations

import argparse
import os
import sys

import _probe as p

MIN_GAIN = 0.10


def physical_cores(cpuinfo: str = "/proc/cpuinfo") -> int:
    """Cœurs physiques (Linux). À défaut : la moitié des threads logiques, mais jamais moins de 1."""
    try:
        pairs = set()
        phys = core = None
        with open(cpuinfo, encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "physical id":
                    phys = value.strip()
                elif key == "core id":
                    core = value.strip()
                elif key == "" and core is not None:  # fin d'un bloc « processeur »
                    pairs.add((phys, core))
                    phys = core = None
        if core is not None:
            pairs.add((phys, core))
        if pairs:
            return len(pairs)
    except OSError:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def thread_candidates(explicit: str | None) -> list[int]:
    if explicit:
        return [0] + [int(x) for x in explicit.split(",") if x.strip() and int(x) > 0]
    logical = os.cpu_count() or 2
    phys = min(physical_cores(), logical)
    wanted = {phys, logical}
    if phys + 2 <= logical:
        wanted.add(phys + 2)
    return [0] + sorted(wanted)  # 0 = laisser Ollama décider


def label(threads: int, gpu: int) -> str:
    return f"NUM_THREAD={threads or 'auto'}  NUM_GPU={'auto' if gpu < 0 else gpu}"


def measure(probe: p.Probe, threads: int, gpu: int, runs: int, max_tokens: int, seed: int) -> dict:
    """1 essai de chauffe (le modèle est rechargé quand les options changent), puis `runs` essais mesurés."""
    probe.chat(p.realistic_messages(seed), num_thread=threads, num_gpu=gpu)
    rows = []
    for k in range(runs):
        result, wall = probe.chat(p.realistic_messages(seed + 1 + k), num_thread=threads, num_gpu=gpu)
        if not p.answer_text(result).strip():
            raise p.ProbeError("réponse vide : lance d'abord tools/check_model.py (mode réflexion ?)")
        rows.append(p.timings(result, wall))
    prompt_s = p.median([r["prompt_s"] for r in rows])
    rate = p.median([r["gen_rate"] for r in rows])
    share = probe.gpu_share()
    return {
        "threads": threads, "gpu": gpu, "prompt_s": prompt_s, "rate": rate,
        "worst": p.worst_case_s(prompt_s, rate, max_tokens),
        "gpu_pct": (100 * share[1] / share[0]) if share and share[0] else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", default=None)
    parser.add_argument("--runs", type=int, default=2, help="essais mesurés par combinaison (défaut : 2)")
    parser.add_argument("--threads", default=None, help="liste à tester à la place de la liste automatique, ex. 4,6,8")
    args = parser.parse_args()

    s = p.settings_for(args.model)
    probe = p.Probe(s, s.ollama_url)
    try:
        names = probe.installed()
    except p.ProbeError as exc:
        print(f"ERREUR : {exc}. Lance-le avec « ollama serve » (ou ouvre l'application).")
        return 2
    if s.model not in names and f"{s.model}:latest" not in names:
        print(f"ERREUR : le modèle « {s.model} » n'est pas installé. Installe-le avec :  ollama pull {s.model}")
        return 2

    threads_list = thread_candidates(args.threads)
    print(f"Modèle : {s.model}   Ollama {probe.version()}   MAX_TOKENS={s.max_tokens}   "
          f"cœurs physiques ~{physical_cores()}, threads logiques {os.cpu_count()}")
    print(f"Threads à tester : {', '.join(str(t) if t else 'auto' for t in threads_list)}\n")

    results: list[dict] = []
    try:
        print("Mesure de référence (réglages par défaut d'Ollama)…")
        base = measure(probe, 0, -1, args.runs, s.max_tokens, seed=1)
        results.append(base)
        print(f"  {label(0, -1)} : attente max ~{base['worst']:.1f} s ({base['rate']:.1f} tokens/s, "
              f"question {base['prompt_s']:.1f} s, GPU {base['gpu_pct']:.0f} %)")

        gpu_values = [-1]
        if base["gpu_pct"] >= 5:
            gpu_values.append(0)
        else:
            print("  Le modèle n'utilise (presque) pas la carte graphique en automatique : test GPU ignoré.")

        todo = [(t, g) for g in gpu_values for t in threads_list if (t, g) != (0, -1)]
        print(f"\n{len(todo)} autres combinaisons à tester (comptez ~{len(todo) * (args.runs + 1) * base['worst'] / 60:.0f} min au plus).\n")
        for t, g in todo:
            r = measure(probe, t, g, args.runs, s.max_tokens, seed=1 + 10 * len(results))
            results.append(r)
            print(f"  {label(t, g)} : attente max ~{r['worst']:.1f} s ({r['rate']:.1f} tokens/s, GPU {r['gpu_pct']:.0f} %)")
    except p.ProbeError as exc:
        print(f"\nERREUR : {exc}")
        return 2
    finally:
        probe.unload()

    ranked = sorted(results, key=lambda r: r["worst"])
    print("\nClassement (attente maximale, la plus courte d'abord) :")
    for r in ranked:
        mark = "  <- défaut d'Ollama" if (r["threads"], r["gpu"]) == (0, -1) else ""
        print(f"  {r['worst']:6.1f} s   {label(r['threads'], r['gpu'])}{mark}")

    best = ranked[0]
    gain = (base["worst"] - best["worst"]) / base["worst"] if base["worst"] else 0.0
    print()
    if (best["threads"], best["gpu"]) == (0, -1) or gain < MIN_GAIN:
        print(f"Conclusion : garde les réglages par défaut (le meilleur gagne seulement {max(gain, 0) * 100:.0f} %, "
              f"sous le seuil de {MIN_GAIN * 100:.0f} % : c'est du bruit de mesure). Ne mets rien dans .env.")
    else:
        print(f"Conclusion : {gain * 100:.0f} % plus rapide que les réglages par défaut. Ajoute dans .env :")
        if best["threads"]:
            print(f"  NUM_THREAD={best['threads']}")
        if best["gpu"] >= 0:
            print(f"  NUM_GPU={best['gpu']}")
        print("Puis relance check_model.py pour confirmer (les écarts de 10 à 15 % restent proches du bruit : "
              "si le résultat te surprend, relance tune.py une seconde fois).")
    print("\n(Le modèle a été déchargé de la mémoire. Les mesures valent pour CE modèle et CE PC dans l'état actuel.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
