#!/usr/bin/env bash
# Crée l'icône « Crack the Bot » (menu des applications + bureau) et fixe le jeton admin.
# À lancer une seule fois :  bash launcher/installer_raccourci.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
ROOT="$PWD"

if [ ! -f .env ]; then
  echo "Il n'y a pas encore de fichier .env. Crée-le d'abord :"
  echo "  cp .env.example .env"
  echo "  sed -i 's/^MODEL=[^ ]*/MODEL=gemma3:4b/' .env     (ou le modèle de ton choix)"
  exit 1
fi
chmod +x launcher/crack-the-bot.sh run.sh

# Jeton admin fixe : sinon il change à chaque lancement.
current="$( (set -a; . ./.env; echo "${ADMIN_TOKEN:-}") )"
if [ -z "$current" ]; then
  token="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 8 || true)"
  if grep -q '^ADMIN_TOKEN=' .env; then
    sed -i "s/^ADMIN_TOKEN=[^ #]*/ADMIN_TOKEN=${token}/" .env
  else
    printf '\nADMIN_TOKEN=%s\n' "$token" >>.env
  fi
  current="$token"
  echo "Jeton admin créé et enregistré dans .env."
fi

desktop_entry() {
  cat <<ENTRY
[Desktop Entry]
Type=Application
Version=1.0
Name=Crack the Bot
Comment=Lance le gardien IA et le jeu
Exec="$ROOT/launcher/crack-the-bot.sh"
Path=$ROOT
Icon=$ROOT/launcher/icon.svg
Terminal=true
Categories=Game;
Actions=Board;Admin;

[Desktop Action Board]
Name=Ouvrir le classement (projecteur)
Exec=xdg-open http://127.0.0.1:${PORT:-8000}/board

[Desktop Action Admin]
Name=Ouvrir l'admin
Exec=xdg-open http://127.0.0.1:${PORT:-8000}/admin
ENTRY
}
[ -f .env ] && PORT="$( (set -a; . ./.env; echo "${PORT:-8000}") )"

apps="$HOME/.local/share/applications"
mkdir -p "$apps"
desktop_entry >"$apps/crack-the-bot.desktop"
chmod +x "$apps/crack-the-bot.desktop"
echo "Icône ajoutée au menu des applications."

desk="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -n "$desk" ] && [ -d "$desk" ]; then
  desktop_entry >"$desk/Crack the Bot.desktop"
  chmod +x "$desk/Crack the Bot.desktop"
  gio set "$desk/Crack the Bot.desktop" metadata::trusted true 2>/dev/null || true
  echo "Icône posée sur le bureau : $desk/Crack the Bot.desktop"
  echo "Si elle apparaît avec un nom bizarre : clic droit > « Autoriser le lancement »."
fi

echo
echo "Terminé. Jeton admin : $current"
echo "Double-clique sur l'icône pour lancer le jeu."
