#!/usr/bin/env bash
# Diagnostic de ce PC pour Crack the Bot (Ubuntu). LECTURE SEULE : il ne change rien.
#
#   bash tools/diagnostic_pc.sh              -> affiche l'état et les points à corriger
#   bash tools/diagnostic_pc.sh --appliquer  -> propose, une par une et avec confirmation, 2 corrections
#                                               (mode « performance » du processeur ; réglage mémoire d'Ollama)
#
# Copiez-collez le résultat complet dans la conversation : il me dit sur quel PC je règle le jeu.
set -u

APPLY=0
[ "${1:-}" = "--appliquer" ] && APPLY=1

if [ -t 1 ]; then G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[0m'; else G=""; Y=""; R=""; fi
WARNS=0
ok()    { printf '  %s✔%s %s\n' "$G" "$R" "$*"; }
warn()  { printf '  %s⚠%s %s\n' "$Y" "$R" "$*"; WARNS=$((WARNS + 1)); }
info()  { printf '    %s\n' "$*"; }
title() { printf '\n== %s ==\n' "$*"; }
have()  { command -v "$1" >/dev/null 2>&1; }
ask()   { local ans; read -r -p "  $1 [o/N] " ans </dev/tty || return 1; [ "$ans" = "o" ] || [ "$ans" = "O" ]; }

echo "Diagnostic Crack the Bot — $(date '+%Y-%m-%d %H:%M')"

# --- Processeur ---------------------------------------------------------------------------------------
title "Processeur"
if have lscpu; then
  model=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)
  sockets=$(lscpu | sed -n 's/^Socket(s):[[:space:]]*//p' | head -1)
  cores=$(lscpu | sed -n 's/^Core(s) per socket:[[:space:]]*//p' | head -1)
  tpc=$(lscpu | sed -n 's/^Thread(s) per core:[[:space:]]*//p' | head -1)
  maxmhz=$(lscpu | sed -n 's/^CPU max MHz:[[:space:]]*//p' | head -1)
  info "$model"
  if [ -n "$sockets" ] && [ -n "$cores" ] && [ -n "$tpc" ]; then
    info "$((sockets * cores)) cœurs physiques, $((sockets * cores * tpc)) threads (tools/tune.py teste ces nombres)"
  fi
  [ -n "$maxmhz" ] && info "fréquence max : ${maxmhz%.*} MHz"
else
  info "lscpu introuvable"
fi

# --- Alimentation et mode du processeur --------------------------------------------------------------
title "Alimentation et mode de performance"
found_mains=0; on_ac=0
for ps in /sys/class/power_supply/*; do
  [ -r "$ps/type" ] || continue
  if [ "$(cat "$ps/type")" = "Mains" ]; then
    found_mains=1
    [ "$(cat "$ps/online" 2>/dev/null)" = "1" ] && on_ac=1
  fi
done
if [ "$found_mains" = 1 ]; then
  if [ "$on_ac" = 1 ]; then ok "PC branché sur secteur"; else warn "PC sur batterie : branche-le, le processeur ralentit sur batterie"; fi
else
  info "pas de prise secteur détectée (PC fixe ou information indisponible)"
fi

gov_file=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
gov=""; [ -r "$gov_file" ] && gov=$(cat "$gov_file")
driver=""; [ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver ] && driver=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver)
profile=""; have powerprofilesctl && profile=$(powerprofilesctl get 2>/dev/null)
[ -n "$gov" ] && info "gouverneur CPU : $gov (pilote : ${driver:-inconnu})"
[ -n "$profile" ] && info "profil d'énergie : $profile"
if [ -z "$gov" ] && [ -z "$profile" ]; then
  info "mode du processeur : information indisponible sur ce système"
elif [ "$gov" = "performance" ] || [ "$profile" = "performance" ]; then
  ok "mode performance actif"
else
  warn "mode performance non actif : le processeur peut monter en fréquence moins vite (gain attendu : modéré, à mesurer)"
  info "pour l'activer jusqu'au prochain redémarrage : bash tools/diagnostic_pc.sh --appliquer"
fi

# --- Mémoire -------------------------------------------------------------------------------------------
title "Mémoire"
if have free; then
  total=$(free -m | awk '/^Mem:/ {print $2}')
  avail=$(free -m | awk '/^Mem:/ {print $7}')
  swap_used=$(free -m | awk '/^Swap:/ {print $3}')
  info "RAM : ${total} Mo au total, ${avail} Mo disponibles ; swap utilisé : ${swap_used:-0} Mo"
  if [ "${avail:-0}" -lt 6000 ]; then
    warn "moins de 6 Go disponibles : ferme le navigateur et les applications avant de jouer ou de mesurer"
  else
    ok "assez de mémoire libre pour un modèle de 3 à 4 Go"
  fi
  info "plus gros consommateurs :"
  ps -eo comm,rss --sort=-rss 2>/dev/null | awk 'NR>1 && NR<=6 {printf "      %-22s %6d Mo\n", $1, $2/1024}'
fi

# --- Carte graphique -----------------------------------------------------------------------------------
title "Carte graphique"
nv_pci=""
have lspci && nv_pci=$(lspci 2>/dev/null | grep -i nvidia | head -2)
[ -n "$nv_pci" ] && info "$nv_pci"
if have nvidia-smi; then
  line=""
  if raw=$(nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>/dev/null); then
    line=$(echo "$raw" | head -1)
  fi
  # Format attendu : « nom, 2048 MiB, 300 MiB, 535.183.01 ». Tout le reste (message d'erreur…) est refusé.
  if echo "$line" | grep -Eq '^.+, [0-9]+ MiB, [0-9]+ MiB, [0-9]+(\.[0-9]+)*$'; then
    info "nvidia-smi : $line"
    driver_ver=$(echo "$line" | awk -F', ' '{print $4}')
    vram_used=$(echo "$line" | awk -F', ' '{print $3}' | awk '{print $1}')
    cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1)
    echo "$cc" | grep -Eq '^[0-9]+\.[0-9]+$' || cc=""
    [ -n "$cc" ] && info "capacité de calcul CUDA : $cc"
    major=${driver_ver%%.*}
    if [ "$major" -lt 550 ] 2>/dev/null; then
      warn "pilote Nvidia $driver_ver : Ollama demande 550 ou plus (doc officielle) ; sinon il travaille sur le processeur"
    elif [ -n "$cc" ] && awk -v c="$cc" 'BEGIN{exit !(c < 6.3)}' && [ "$major" -lt 570 ]; then
      warn "carte de capacité $cc : Ollama demande un pilote 570 ou plus pour les cartes de cette génération (doc officielle)"
    else
      ok "pilote Nvidia $driver_ver (compatible avec les exigences d'Ollama indiquées dans sa doc)"
    fi
    if [ -n "$vram_used" ] && [ "$vram_used" -gt 600 ] 2>/dev/null; then
      warn "${vram_used} Mo de VRAM déjà utilisés par d'autres applications : il reste peu de place pour le modèle"
    fi
    info "avec ~2 Go de VRAM, un modèle de 3 B ou plus ne tient pas entièrement : tools/tune.py mesure si le GPU aide"
  else
    warn "la commande nvidia-smi existe mais le pilote Nvidia ne fonctionne pas : Ollama travaillera sur le processeur"
    info "(un redémarrage le règle parfois ; sinon c'est un sujet de pilote Ubuntu, à ne pas toucher juste avant l'événement)"
    info "pour comprendre : ubuntu-drivers devices ; lsmod | grep nvidia ; mokutil --sb-state (Secure Boot)"
  fi
elif [ -n "$nv_pci" ]; then
  warn "carte Nvidia détectée mais pas de pilote (nvidia-smi absent) : Ollama n'utilisera pas le GPU"
  info "pour installer le pilote recommandé :  sudo ubuntu-drivers install   (puis redémarrer)"
else
  info "aucune carte Nvidia détectée : tout se fera sur le processeur"
fi

# --- Ollama --------------------------------------------------------------------------------------------
title "Ollama"
if have ollama; then
  info "$(ollama --version 2>&1 | head -1)"
  if curl -fsS -m 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    ok "le serveur Ollama répond"
    info "modèles installés :"
    ollama list 2>/dev/null | sed 's/^/      /'
    info "modèles chargés en mémoire :"
    ollama ps 2>/dev/null | sed 's/^/      /'
  else
    warn "le serveur Ollama ne répond pas (lance « ollama serve », ou « sudo systemctl start ollama »)"
  fi
  if have systemctl && systemctl cat ollama >/dev/null 2>&1; then
    env_line=$(systemctl show ollama -p Environment --value 2>/dev/null)
    ollama_vars=$(echo "$env_line" | grep -oE 'OLLAMA_[A-Z_]+=[^ ]*' | tr '\n' ' ')
    [ -n "$ollama_vars" ] && info "réglages OLLAMA_* du service : $ollama_vars"
    case "$ollama_vars" in *OLLAMA_KV_CACHE_TYPE=q8_0*|*OLLAMA_KV_CACHE_TYPE=q4_0*)
      info "cache KV quantifié : réglage déjà présent sur ce PC, non modifié (effet sur la vitesse non mesuré)";; esac
  fi
else
  warn "Ollama n'est pas installé :  curl -fsSL https://ollama.com/install.sh | sh"
fi

# --- Température ---------------------------------------------------------------------------------------
title "Température"
if have sensors; then
  sensors 2>/dev/null | grep -E 'Package id|Tctl|Core 0' | head -3 | sed 's/^/    /'
  info "au-dessus de ~90 °C sous charge, le processeur ralentit tout seul (ventilation, surface dure, touche Cooler Boost des MSI)"
else
  info "pour surveiller la température :  sudo apt install lm-sensors  puis  watch -n2 sensors  pendant une mesure"
fi

# --- Résumé --------------------------------------------------------------------------------------------
title "Résumé"
if [ "$WARNS" = 0 ]; then ok "rien à signaler"; else warn "$WARNS point(s) à regarder, voir les ⚠ ci-dessus"; fi

# --- Corrections (seulement avec --appliquer) ------------------------------------------------------------
if [ "$APPLY" = 1 ]; then
  title "Corrections proposées"
  if { [ -n "$gov" ] || [ -n "$profile" ]; } && [ "$gov" != "performance" ] && [ "$profile" != "performance" ]; then
    if have powerprofilesctl; then
      cmd="powerprofilesctl set performance"
    elif have cpupower; then
      cmd="sudo cpupower frequency-set -g performance"
    else
      cmd="echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
    fi
    echo "  1) Mode performance du processeur (jusqu'au prochain redémarrage) :"
    echo "     $cmd"
    if ask "Exécuter ?"; then
      if bash -c "$cmd" >/dev/null; then ok "fait"; else warn "la commande a échoué : lance-la toi-même dans un terminal"; fi
    fi
  elif [ -z "$gov" ] && [ -z "$profile" ]; then
    info "1) mode du processeur : information indisponible sur ce système, rien à proposer."
  else
    ok "1) mode performance : déjà actif"
  fi

  svc_env=$(systemctl show ollama -p Environment --value 2>/dev/null)
  if have systemctl && systemctl cat ollama >/dev/null 2>&1 && echo "$svc_env" | grep -q 'OLLAMA_MAX_LOADED_MODELS=1'; then
    ok "2) Ollama : un seul modèle en mémoire, déjà réglé sur ce PC : rien à faire."
  elif have systemctl && systemctl cat ollama >/dev/null 2>&1; then
    dropin=/etc/systemd/system/ollama.service.d/crack-the-bot.conf
    echo "  2) Ollama : ne garder qu'UN modèle en mémoire à la fois (évite de saturer la RAM quand on compare plusieurs modèles)."
    echo "     Gain de vitesse : aucun. Fichier créé : $dropin"
    echo "     Pour annuler :  sudo rm $dropin && sudo systemctl daemon-reload && sudo systemctl restart ollama"
    if ask "Créer ce réglage et redémarrer Ollama ?"; then
      if sudo mkdir -p "$(dirname "$dropin")" \
        && printf '[Service]\nEnvironment="OLLAMA_MAX_LOADED_MODELS=1"\nEnvironment="OLLAMA_NUM_PARALLEL=1"\n' | sudo tee "$dropin" >/dev/null \
        && sudo systemctl daemon-reload && sudo systemctl restart ollama; then
        ok "fait"
      else
        warn "échec : rien n'a été cassé, tu peux lancer ces commandes à la main"
      fi
    fi
  else
    info "2) Ollama n'est pas géré par systemd sur ce PC : rien à régler ici."
  fi
  echo
  echo "Les autres variables Ollama connues (FLASH_ATTENTION, KV_CACHE_TYPE…) ne sont volontairement PAS touchées :"
  echo "FLASH_ATTENTION est automatique par défaut (doc officielle) et, avec un contexte de 1024 tokens, la mémoire du cache est petite."
fi
