"""notemd core: note storage shared by the GTK (Linux) and Tk (Windows) front ends.

Notes live in ~/Documents/notemd/notes.md, grouped by category:

    # General          <- notes without a category
    ## Tue 17.11.2026 17:41:57
    text
    # Work             <- category (kept in the file even when empty)
    ## Tue 17.11.2026 18:02:10
    text
"""
import os
import re
import tempfile
from datetime import datetime

NOTES_DIR = os.path.expanduser("~/Documents/notemd")
NOTES_FILE = os.path.join(NOTES_DIR, "notes.md")
# Earlier (Finnish) versions stored notes here; moved to the new location on first start
OLD_NOTES_FILE = os.path.expanduser("~/Documents/InstaNote/muistiinpanot.md")
GENERAL = "General"
LEGACY_GENERAL = "Yleinen"  # the group name used by the Finnish version
CAT_HEADING = re.compile(r"^# (.+?)\s*$")
PIN = "📌"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Heading: "## Tue 17.11.2026 17:50:59" (the ISO form 2026-11-17 and Finnish weekdays are read too)
NOTE_HEADING = re.compile(
    r"^## (?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|ma|ti|ke|to|pe|la|su) )?(?:(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.(\d{1,2})\.(\d{4})) (\d{2}:\d{2}:\d{2})(\s+" + PIN + r")?\s*$")
NEEDS_ESCAPE = re.compile(r"^#{1,2}\s")


# ---------------------------------------------------------------- storage
def parse_heading(m):
    """From a heading match: (ISO timestamp for sorting, pinned)."""
    if m.group(1):
        y, mo, d = m.group(1), m.group(2), m.group(3)
    else:
        d, mo, y = m.group(4), m.group(5), m.group(6)
    return f"{y}-{int(mo):02d}-{int(d):02d} {m.group(7)}", bool(m.group(8))


def fmt_stamp(stamp):
    """2026-11-17 17:50:59 -> ti 17.11.2026 17:50:59"""
    day, time = stamp.split(" ")
    y, mo, d = (int(x) for x in day.split("-"))
    return f"{WEEKDAYS[datetime(y, mo, d).weekday()]} {d}.{mo}.{y} {time}"


def unescape(line):
    return line[1:] if line.startswith("\\") and NEEDS_ESCAPE.match(line[1:]) else line


def migrate_old_file():
    """Moves the notes file of an earlier version to the new location (once)."""
    if not os.path.exists(NOTES_FILE) and os.path.exists(OLD_NOTES_FILE):
        os.makedirs(NOTES_DIR, exist_ok=True)
        os.replace(OLD_NOTES_FILE, NOTES_FILE)


def load_data():
    """Returns (categories, notes).

    categories: list of names in creation order (without 'General').
    notes: list of dicts {stamp, cat (None = general), text, order}.
    """
    migrate_old_file()
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return [], []

    cats, notes = [], []
    cur_cat, cur = None, None

    def flush():
        if cur is not None:
            cur["text"] = "\n".join(cur["body"]).strip()
            del cur["body"]
            cur["order"] = len(notes)
            notes.append(cur)

    for line in lines:
        m = NOTE_HEADING.match(line)
        if m:
            flush()
            stamp, pinned = parse_heading(m)
            cur = {"stamp": stamp, "cat": cur_cat, "pinned": pinned, "body": []}
            continue
        m = CAT_HEADING.match(line)
        if m:
            flush()
            cur = None
            name = m.group(1)
            cur_cat = None if name in (GENERAL, LEGACY_GENERAL) else name
            if cur_cat and cur_cat not in cats:
                cats.append(cur_cat)
            continue
        if cur is not None:
            cur["body"].append(unescape(line))
    flush()
    return cats, notes


def write_data(cats, notes):
    """Writes the whole file grouped by category (atomically)."""
    os.makedirs(NOTES_DIR, exist_ok=True)
    out = []
    for cat in [None] + cats:
        out.append(f"# {cat or GENERAL}\n")
        for n in sorted((n for n in notes if n["cat"] == cat), key=lambda n: (n["stamp"], n["order"])):
            safe = "\n".join(("\\" + l) if NEEDS_ESCAPE.match(l) else l for l in n["text"].splitlines())
            out.append(f"## {fmt_stamp(n['stamp'])}{' ' + PIN if n.get('pinned') else ''}\n\n{safe}\n")
    fd, tmp = tempfile.mkstemp(dir=NOTES_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    os.replace(tmp, NOTES_FILE)


def add_note(text, cat):
    cats, notes = load_data()
    if cat and cat not in cats:
        cats.append(cat)
    notes.append({
        "stamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cat": cat, "pinned": False, "text": text, "order": len(notes),
    })
    write_data(cats, notes)


def add_category(name):
    """Palauttaa siistityn nimen tai None jos nimi ei kelpaa."""
    name = re.sub(r"\s+", " ", name).strip().lstrip("#").strip()[:40]
    if not name or name.lower() in (GENERAL.lower(), LEGACY_GENERAL.lower()):
        return None
    cats, notes = load_data()
    existing = next((c for c in cats if c.lower() == name.lower()), None)
    if existing:
        return existing
    cats.append(name)
    write_data(cats, notes)
    return name


def _find(notes, target):
    for n in notes:
        if (n["stamp"], n["cat"], n["text"]) == (target["stamp"], target["cat"], target["text"]):
            return n
    return None


def delete_note(target):
    cats, notes = load_data()
    n = _find(notes, target)
    if n:
        notes.remove(n)
        write_data(cats, notes)


def toggle_pin(target):
    cats, notes = load_data()
    n = _find(notes, target)
    if n:
        n["pinned"] = not n["pinned"]
        write_data(cats, notes)


def delete_category(name, action, target=None):
    """action 'move': move the notes to category target (None = General); 'delete': delete them."""
    cats, notes = load_data()
    if name in cats:
        cats.remove(name)
    if action == "delete":
        notes = [n for n in notes if n["cat"] != name]
    else:
        for n in notes:
            if n["cat"] == name:
                n["cat"] = target
    write_data(cats, notes)


def sort_key(n):
    """Pinned first, then newest first (use with reverse=True)."""
    return (n["pinned"], n["stamp"], n["order"])


def update_note(target, text, cat):
    cats, notes = load_data()
    n = _find(notes, target)
    if n:
        n["text"], n["cat"] = text, cat
        write_data(cats, notes)


def latest(notes, limit=5):
    return sorted(notes, key=sort_key, reverse=True)[:limit]
