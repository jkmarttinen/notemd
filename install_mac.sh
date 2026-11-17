#!/bin/sh
# Installs notemd on macOS: creates ~/Applications/notemd.app (launchable from Spotlight / Launchpad).
# Needs Python 3 with Tk, e.g. the installer from https://www.python.org/downloads/macos/
# (Apple's built-in python3 ships an outdated Tk and is skipped.)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

PY=""
for cand in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
            /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
    [ -x "$cand" ] || continue
    [ "$cand" = /usr/bin/python3 ] && continue
    if "$cand" -c "import tkinter" 2>/dev/null; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "No Python 3 with Tk found."
    echo "Install Python from https://www.python.org/downloads/macos/  (or: brew install python-tk)"
    exit 1
fi

APP="$HOME/Applications/notemd.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/notemd" <<LAUNCHER
#!/bin/sh
exec "$PY" "$DIR/notemd_tk.pyw"
LAUNCHER
chmod +x "$APP/Contents/MacOS/notemd"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>notemd</string>
    <key>CFBundleDisplayName</key><string>notemd</string>
    <key>CFBundleIdentifier</key><string>local.notemd</string>
    <key>CFBundleExecutable</key><string>notemd</string>
    <key>CFBundleIconFile</key><string>notemd</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1</string>
</dict>
</plist>
PLIST

# app icon (.icns) from notemd.png
ICONSET="$(mktemp -d)/notemd.iconset"
mkdir -p "$ICONSET"
for size in 16 32 64 128 256 512; do
    sips -z $size $size "$DIR/notemd.png" --out "$ICONSET/tmp_$size.png" >/dev/null
done
cp "$ICONSET/tmp_16.png"  "$ICONSET/icon_16x16.png"
cp "$ICONSET/tmp_32.png"  "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/tmp_32.png"  "$ICONSET/icon_32x32.png"
cp "$ICONSET/tmp_64.png"  "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/tmp_128.png" "$ICONSET/icon_128x128.png"
cp "$ICONSET/tmp_256.png" "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/tmp_256.png" "$ICONSET/icon_256x256.png"
cp "$ICONSET/tmp_512.png" "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/tmp_512.png" "$ICONSET/icon_512x512.png"
rm "$ICONSET"/tmp_*.png
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/notemd.icns" || true

touch "$APP"
echo "Installed: $APP  (using $PY)"
echo
echo "Hotkey: macOS has no per-app hotkey setting, so create one:"
echo "  1. Open Automator -> New Document -> Quick Action"
echo "  2. Set 'Workflow receives' to 'no input', add the action 'Run Shell Script' with:  open -a notemd"
echo "  3. Save it as 'notemd'"
echo "  4. System Settings -> Keyboard -> Keyboard Shortcuts -> Services -> General -> notemd -> add a shortcut (e.g. Ctrl+Option+N)"
