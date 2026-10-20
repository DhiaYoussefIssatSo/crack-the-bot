# À « sourcer » depuis la racine du projet : . ./env_loader.sh
# Charge .env SANS écraser les variables déjà définies dans le terminal (ex. « BACKEND=mock ./run.sh » gagne sur .env),
# comme le font déjà les outils de tools/.
load_dotenv_keep_terminal() {
  [ -f .env ] || return 0
  local k keys i
  local saved_names=() saved_values=()
  keys=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | cut -d= -f1 || true)
  for k in $keys; do
    if [ -n "${!k+x}" ]; then
      saved_names+=("$k")
      saved_values+=("${!k}")
    fi
  done
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  for i in "${!saved_names[@]}"; do
    export "${saved_names[$i]}=${saved_values[$i]}"
  done
}
