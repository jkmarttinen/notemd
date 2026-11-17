#!/bin/sh
# Installs notemd into the application menu (icon + launcher) from this folder.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/notemd.py"
mkdir -p "$HOME/.local/share/applications"
sed "s#@DIR@#$DIR#g" "$DIR/notemd.desktop.in" > "$HOME/.local/share/applications/notemd.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Installed. Set your hotkey to run: $DIR/notemd.py"
