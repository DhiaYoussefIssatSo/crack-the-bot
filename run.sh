#!/usr/bin/env bash
# Lance Crack the Bot. Première exécution : crée l'environnement Python et installe les dépendances.
set -euo pipefail
cd "$(dirname "$0")"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "ERREUR : Python 3.10 ou plus récent est nécessaire (trouvé : $(python3 --version 2>&1))." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Création de l'environnement Python (.venv)…"
  python3 -m venv .venv
fi
# requirements.lock.txt (s'il existe) = les versions exactes testées ; sinon requirements.txt (versions minimales).
REQ=requirements.txt
[ -f requirements.lock.txt ] && REQ=requirements.lock.txt
.venv/bin/pip install -q -r "$REQ"

# ./run.sh --install : prépare seulement l'environnement (utile avant tools/redteam.py), sans lancer le jeu.
if [ "${1:-}" = "--install" ]; then
  echo "Environnement prêt (.venv). Lance le jeu avec : ./run.sh"
  exit 0
fi

# Réglages optionnels : copie .env.example en .env puis modifie-le.
# (une variable écrite devant la commande, ex. « BACKEND=mock ./run.sh », garde la priorité sur .env)
# shellcheck disable=SC1091
. ./env_loader.sh
load_dotenv_keep_terminal

echo "Adresses :  http://${HOST:-127.0.0.1}:${PORT:-8000}/  (jeu)   /board  (projecteur)   /admin"

exec .venv/bin/uvicorn --factory app.main:create_app \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --log-level warning
