#!/usr/bin/env bash
# Mesure d'un coup le PC et tous les modèles candidats, puis écrit un rapport à m'envoyer.
#
#   bash tools/mesurer_tout.sh                              -> les 4 modèles du guide
#   bash tools/mesurer_tout.sh granite4.1:3b gemma3:4b      -> ceux que tu choisis
#
# Durée : environ 2 à 4 minutes par modèle. Rien d'autre ne doit tourner sur le PC pendant ce temps.
# Un modèle non téléchargé est signalé (« ollama pull … ») et le script continue avec les suivants.
set -u
cd "$(dirname "$0")/.."

MODELS=("$@")
[ ${#MODELS[@]} -eq 0 ] && MODELS=(qwen2.5:3b granite4.1:3b ministral-3:3b gemma3:4b)
OUT_DIR="${DATA_DIR:-data}"
mkdir -p "$OUT_DIR"
REPORT="$OUT_DIR/rapport-mesures-$(date +%Y%m%d-%H%M).txt"

{
  echo "=== Diagnostic du PC ==="
  bash tools/diagnostic_pc.sh

  SUMMARY=()
  for m in "${MODELS[@]}"; do
    echo
    echo "=== Modèle $m ==="
    tmp=$(mktemp)
    python3 -u tools/check_model.py "$m" 2>&1 | tee "$tmp"
    line=$(grep '^RÉSUMÉ' "$tmp" || true)
    [ -z "$line" ] && line="RÉSUMÉ | $m | non mesuré (voir les erreurs ci-dessus)"
    SUMMARY+=("$line")
    rm -f "$tmp"
  done

  echo
  echo "=== TABLEAU RÉCAPITULATIF ==="
  for line in "${SUMMARY[@]}"; do echo "$line"; done
} 2>&1 | tee "$REPORT"

echo
echo "Rapport enregistré dans : $REPORT"
echo "Envoie-moi ce fichier (ou copie-colle tout le texte ci-dessus)."
