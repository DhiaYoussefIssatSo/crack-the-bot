#!/usr/bin/env bash
# Lance tout Crack the Bot : Ollama (s'il ne tourne pas), le jeu, puis ouvre le navigateur.
# Fait pour être lancé par l'icône (Terminal=true : la fenêtre du terminal EST le jeu ; la fermer l'arrête).
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1

pause_on_error() {  # empêche la fenêtre de se fermer avant d'avoir lu l'erreur
  echo
  echo "ERREUR : $1"
  echo "(Appuie sur Entrée pour fermer cette fenêtre.)"
  read -r _
  exit 1
}

# shellcheck disable=SC1091
. ./env_loader.sh
load_dotenv_keep_terminal
PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"
OLLAMA="${OLLAMA_URL:-http://127.0.0.1:11434}"
BACKEND="${BACKEND:-ollama}"
MODEL="${MODEL:-qwen2.5:3b}"

echo "=== Crack the Bot ==="

# 1. Déjà lancé ? On ouvre seulement le navigateur.
if curl -fs --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
  echo "Le jeu tourne déjà : j'ouvre la page."
  xdg-open "$URL/" >/dev/null 2>&1 &
  sleep 2
  exit 0
fi

# 2. Ollama + modèle (sauf avec BACKEND=mock, le faux gardien de test)
if [ "$BACKEND" = "ollama" ]; then
  if ! curl -fs --max-time 2 "$OLLAMA/api/version" >/dev/null 2>&1; then
    command -v ollama >/dev/null 2>&1 || pause_on_error "Ollama n'est pas installé."
    echo "Ollama ne répond pas : je le démarre…"
    mkdir -p data
    nohup ollama serve >data/ollama.log 2>&1 &
    for _ in $(seq 1 30); do
      curl -fs --max-time 2 "$OLLAMA/api/version" >/dev/null 2>&1 && break
      sleep 1
    done
    curl -fs --max-time 2 "$OLLAMA/api/version" >/dev/null 2>&1 \
      || pause_on_error "Ollama ne démarre pas (voir data/ollama.log). Essaie : sudo systemctl restart ollama"
  fi
  if command -v ollama >/dev/null 2>&1 && ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qxF -e "$MODEL" -e "$MODEL:latest"; then
    pause_on_error "Le modèle « $MODEL » n'est pas installé. Lance :  ollama pull $MODEL   (ou corrige MODEL dans .env)"
  fi
  echo "Ollama : prêt. Modèle : $MODEL"
fi

# 3. Ouvre le navigateur dès que le jeu répond
(
  for _ in $(seq 1 90); do
    if curl -fs --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
      xdg-open "$URL/" >/dev/null 2>&1
      exit 0
    fi
    sleep 1
  done
) &

cat <<MSG

Jeu         : $URL/
Projecteur  : $URL/board   (F11 pour le plein écran)
Admin       : $URL/admin   (jeton : ${ADMIN_TOKEN:-affiché ci-dessous, il change à chaque lancement})

Pour ARRÊTER le jeu : Ctrl+C, ou ferme cette fenêtre.
------------------------------------------------------------
MSG

./run.sh
code=$?
[ "$code" -eq 0 ] || [ "$code" -eq 130 ] || pause_on_error "le jeu s'est arrêté (code $code). Lance ./run.sh dans un terminal pour voir le détail."
