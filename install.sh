#!/bin/sh
# Asentaa notemd:n sovellusvalikkoon (kuvake + launcher) tästä kansiosta.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/notemd.py"
mkdir -p "$HOME/.local/share/applications"
sed "s#@DIR@#$DIR#g" "$DIR/notemd.desktop.in" > "$HOME/.local/share/applications/notemd.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Asennettu. Aseta pikanäppäimeksi komento: $DIR/notemd.py"
