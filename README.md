# notemd

A quick-note app for Linux (Python + GTK3) and Windows (Python + Tk). Open a small dark window with a hotkey, type a note, and it is saved with a timestamp to a Markdown file, organised by category.

## Features
- Small console-style window showing your 5 latest notes
- Categories (create with a button, quick-select with Ctrl+1…9)
- Pinning (📌), editing, deleting, search, category filter buttons, and drag & drop between categories in the "all notes" window
- Timestamps with weekday: `Tue 17.11.2026 17:50:59`

## Keys
| Key | Action |
|---|---|
| Enter | newline |
| Enter Enter (quickly) / Ctrl+Enter | save |
| Esc | close (warns first if there is unsaved text) |

## Requirements (Linux)
Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), and SVG support for GdkPixbuf (`librsvg2-common`).

On Debian/Ubuntu:
```sh
sudo apt install python3-gi gir1.2-gtk-3.0 librsvg2-common
```

## Install (Linux)
```sh
git clone https://github.com/jkmarttinen/notemd.git
cd notemd
./install.sh
```
This adds a launcher and icon to your application menu. Set the hotkey in your desktop environment's settings (KDE: System Settings → Shortcuts → Add Command) with the command `/path/to/notemd.py`. Global hotkeys cannot be registered by the app itself on Wayland.

## Windows
The Windows version (`notemd_win.pyw`) uses Tk, which ships with the standard Python installer, so there is nothing extra to install.

1. Install Python 3 from <https://www.python.org/downloads/> (tick "Add python.exe to PATH").
2. Download or clone this repository.
3. Run in PowerShell, in the repository folder:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```

This creates a Start Menu shortcut and a Startup shortcut, and starts notemd in the background. Press **Win+Space** to open it.

- The app stays running in the background; **Esc** (or the window's close button) only hides the window, **Ctrl+Q** quits the app completely.
- Win+Space is normally Windows' input-language switch. notemd takes it over with a low-level keyboard hook while it is running (quit the app to get the language switch back). Some antivirus tools are suspicious of keyboard hooks.
- Another hotkey: `.\install.ps1 -Hotkey "ctrl+alt+n"` (modifiers `win`, `ctrl`, `alt`, `shift` plus a letter, digit, `space` or `F1`–`F24`). Add `-NoAutostart` to skip the Startup shortcut.
- Starting the app again (Start menu, or double-clicking `notemd_win.pyw`) just brings up the running instance.

Features, keys and the notes file format are the same as on Linux.

## Storage
Notes are stored in `~/Documents/notemd/notes.md` (on Windows: `Documents\notemd\notes.md` in your user folder):

```
# General

## Tue 17.11.2026 17:50:59

note text

# Work
...
```
The file is plain Markdown. A pinned note has 📌 after its heading, and empty categories are kept as headings.

## Code layout
| File | Purpose |
|---|---|
| `notemd_core.py` | note storage and the Markdown format (shared) |
| `notemd.py` | Linux front end (GTK3) |
| `notemd_win.pyw` | Windows front end (Tk) |
