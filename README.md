# notemd

A quick-note app for Linux (Python + GTK3). Open a small dark window with a hotkey, type a note, and it is saved with a timestamp to a Markdown file, organised by category.

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

## Requirements
Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), and SVG support for GdkPixbuf (`librsvg2-common`).

On Debian/Ubuntu:
```sh
sudo apt install python3-gi gir1.2-gtk-3.0 librsvg2-common
```

## Install
```sh
git clone https://github.com/jkmarttinen/notemd.git
cd notemd
./install.sh
```
This adds a launcher and icon to your application menu. Set the hotkey in your desktop environment's settings (KDE: System Settings → Shortcuts → Add Command) with the command `/path/to/notemd.py`. Global hotkeys cannot be registered by the app itself on Wayland.

## Storage
Notes are stored in `~/Documents/notemd/notes.md`:

```
# General

## Tue 17.11.2026 17:50:59

note text

# Work
...
```
The file is plain Markdown. A pinned note has 📌 after its heading, and empty categories are kept as headings.

If you used an earlier (Finnish) version, `~/Documents/InstaNote/muistiinpanot.md` is moved to the new location on first start, and the old `Yleinen` group becomes `General`.
