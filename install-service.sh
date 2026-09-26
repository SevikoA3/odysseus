#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
venv_python="$repo_dir/venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "Missing executable venv Python: $venv_python" >&2
  exit 1
fi

for template in "$repo_dir/systemd/odysseus-ui.service.in" "$repo_dir/systemd/odysseus-update.service.in"; do
  if [[ ! -f "$template" ]]; then
    echo "Missing service template: $template" >&2
    exit 1
  fi
done

escape_sed_replacement() {
  sed 's/[\\&|]/\\&/g'
}

render_unit() {
  local template="$1"
  local target="$2"
  local escaped_repo escaped_python
  escaped_repo="$(printf '%s' "$repo_dir" | escape_sed_replacement)"
  escaped_python="$(printf '%s' "$venv_python" | escape_sed_replacement)"
  sed -e "s|@REPOSITORY@|$escaped_repo|g" -e "s|@VENV_PYTHON@|$escaped_python|g" "$template" > "$target"
}

mkdir -p "$unit_dir"
render_unit "$repo_dir/systemd/odysseus-ui.service.in" "$unit_dir/odysseus-ui.service"
render_unit "$repo_dir/systemd/odysseus-update.service.in" "$unit_dir/odysseus-update.service"

systemctl --user daemon-reload
if [[ "${1:-}" == "--no-start" ]]; then
  systemctl --user enable odysseus-ui.service
else
  systemctl --user enable --now odysseus-ui.service
  echo "Odysseus is running as a user service."
fi
