"""notemd for Windows – quick notes with a single hotkey (Tk, standard library only).

Enter = newline, double Enter (quickly) or Ctrl+Enter = save, Esc = hide the window.
The app stays running in the background; the global hotkey (default Win+Space) shows the
window again. Ctrl+Q quits it. Notes are stored in ~/Documents/notemd/notes.md.

Usage:  notemd_win.pyw [--hidden] [--hotkey win+space]
"""
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notemd_core import *  # noqa: E402,F401,F403  (storage functions and constants)

HERE = os.path.dirname(os.path.abspath(__file__))
BG, PANEL, PINNED_BG = "#121212", "#181818", "#1f1a16"
FG, MUTED, DIM = "#e6e6e6", "#bdbdbd", "#5c5c5c"
ORANGE, BORDER, CARD_BORDER, RED = "#d2691e", "#333333", "#262626", "#d8453b"
FONT = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_TEXT = ("Consolas", 12)

DOUBLE_ENTER_SECS = 0.4  # two Enters this quickly = save
ALL = object()           # category filter: all
DRAG_THRESHOLD = 6       # pixels before a press turns into a drag


DEFAULT_HOTKEY = "win+space"
PORT = 47613             # local port used to detect an already running instance


# ------------------------------------------------- global hotkey + single instance
def parse_hotkey(text):
    """'win+space' -> ({'win'}, 0x20). Modifiers: win, ctrl, alt, shift."""
    names = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B}
    parts = [p for p in text.lower().replace(" ", "").split("+") if p]
    mods = {p for p in parts if p in ("win", "ctrl", "alt", "shift")}
    keys = [p for p in parts if p not in mods]
    if len(keys) != 1:
        raise ValueError(f"bad hotkey: {text!r}")
    k = keys[0]
    if k in names:
        vk = names[k]
    elif len(k) == 1 and k.isalnum():
        vk = ord(k.upper())
    elif k[0] == "f" and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        vk = 0x70 + int(k[1:]) - 1
    else:
        raise ValueError(f"bad hotkey: {text!r}")
    return mods, vk


class HotkeyHook(threading.Thread):
    """Global hotkey through a low-level keyboard hook (the only way to take over Win+Space,
    which Windows reserves for switching the input language). Windows only."""

    def __init__(self, hotkey, callback):
        super().__init__(daemon=True)
        self.mods, self.vk = parse_hotkey(hotkey)
        self.callback = callback
        self.ok = threading.Event()
        self.failed = False
        self.swallowed = False

    def run(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        except Exception:
            self.failed = True
            self.ok.set()
            return

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        mod_keys = {"win": (0x5B, 0x5C), "ctrl": (0x11,), "alt": (0x12,), "shift": (0x10,)}

        def down(vk):
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)

        def mods_match():
            return all(any(down(v) for v in vks) == (m in self.mods) for m, vks in mod_keys.items())

        def proc(n_code, w_param, l_param):
            if n_code == 0:
                info = ctypes.cast(l_param, ctypes.POINTER(KBD)).contents
                if info.vkCode == self.vk and not info.flags & 0x10:  # 0x10 = injected
                    if w_param in (0x100, 0x104):                      # key down
                        if self.swallowed or mods_match():
                            if not self.swallowed:
                                self.swallowed = True
                                self.callback()
                                if "win" in self.mods:                 # keep the Start menu from opening
                                    user32.keybd_event(0xE8, 0, 0, 0)
                                    user32.keybd_event(0xE8, 0, 2, 0)
                            return 1
                    elif w_param in (0x101, 0x105) and self.swallowed:  # key up
                        self.swallowed = False
                        return 1
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)  # keep a reference so it is not garbage collected
        hook = user32.SetWindowsHookExW(13, self._proc, kernel32.GetModuleHandleW(None), 0)
        self.failed = not hook
        self.ok.set()
        if self.failed:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def signal_running(message):
    """Tell an already running instance something; True if there is one."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5) as s:
            s.sendall(message)
        return True
    except OSError:
        return False


def listen_for_signals(events):
    """Listens on a local port so a second launch can ask the running instance to show itself."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", PORT))
    srv.listen(4)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    if conn.recv(16) == b"show":
                        events.put("show")
            except OSError:
                return

    threading.Thread(target=loop, daemon=True).start()
    return srv


# ------------------------------------------------------------------ widgets
def mkbtn(parent, text, command, kind="normal", on=False, bg=None):
    """Flat console-style button. kind: normal | primary | danger | toggle."""
    b = tk.Button(parent, text=text, command=command, relief="flat", bd=0, cursor="hand2",
                  takefocus=0, font=FONT_SMALL, padx=8, pady=1, highlightthickness=1)
    b.kind, b.on = kind, on
    paint(b)

    def enter(_):
        if b.kind in ("normal", "toggle") and not b.on:
            b.configure(highlightbackground=ORANGE)
        elif b.kind == "primary":
            b.configure(bg=ORANGE, fg=BG)

    def leave(_):
        paint(b)

    b.bind("<Enter>", enter)
    b.bind("<Leave>", leave)
    return b


def paint(b):
    if b.kind == "danger":
        b.configure(bg=RED, fg=BG, activebackground=RED, activeforeground=BG,
                    highlightbackground=RED, highlightcolor=RED)
    elif b.kind == "primary":
        b.configure(bg=PANEL, fg=ORANGE, activebackground=ORANGE, activeforeground=BG,
                    highlightbackground=ORANGE, highlightcolor=ORANGE)
    elif b.kind == "toggle" and b.on:
        b.configure(bg=ORANGE, fg=BG, activebackground=ORANGE, activeforeground=BG,
                    highlightbackground=ORANGE, highlightcolor=ORANGE, font=FONT_BOLD)
    else:
        b.configure(bg=PANEL, fg=MUTED, activebackground="#222222", activeforeground=FG,
                    highlightbackground=BORDER, highlightcolor=ORANGE, font=FONT_SMALL)


def mklabel(parent, text, fg=MUTED, font=FONT, bg=BG, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


def mkentry(parent, textvariable=None, width=18):
    return tk.Entry(parent, textvariable=textvariable, width=width, bg=PANEL, fg=FG, relief="flat",
                    insertbackground=ORANGE, font=FONT, highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=ORANGE, bd=4)


def mkoptions(parent, var, values):
    om = tk.OptionMenu(parent, var, *values)
    om.configure(bg=PANEL, fg=MUTED, activebackground="#222222", activeforeground=FG, relief="flat",
                 bd=0, highlightthickness=1, highlightbackground=BORDER, font=FONT_SMALL, takefocus=0)
    try:
        om["menu"].configure(bg=PANEL, fg=MUTED, activebackground=ORANGE, activeforeground=BG,
                             bd=0, font=FONT_SMALL)
    except Exception:
        pass
    return om


def mktext(parent, height):
    t = tk.Text(parent, height=height, width=48, wrap="word", bg=PANEL, fg=FG, insertbackground=ORANGE,
                font=FONT_TEXT, relief="flat", bd=0, padx=10, pady=8, highlightthickness=1,
                highlightbackground=BORDER, highlightcolor=ORANGE, undo=True)
    return t


class Flow(tk.Frame):
    """Wraps its children into rows (like a flow layout)."""

    GAP = 6

    def __init__(self, master, **kw):
        super().__init__(master, bg=BG, **kw)
        self._last = None
        self.bind("<Configure>", lambda e: self.reflow())

    def clear(self):
        for w in self.winfo_children():
            w.destroy()
        self._last = None

    def reflow(self):
        width = self.winfo_width()
        kids = self.winfo_children()
        key = (width, len(kids))
        if key == self._last:
            return
        self._last = key
        x = y = rowh = 0
        for w in kids:
            rw, rh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x and x + rw > width:
                x, y, rowh = 0, y + rowh + self.GAP, 0
            w.place(x=x, y=y)
            x += rw + self.GAP
            rowh = max(rowh, rh)
        self.configure(height=y + rowh)


class PinIcon(tk.Canvas):
    """Push-pin icon: grey outline = unpinned, orange fill = pinned."""

    def __init__(self, master, pinned, command, bg):
        super().__init__(master, width=20, height=20, bg=bg, highlightthickness=0, cursor="hand2")
        self.pinned, self.hover = pinned, False
        self.draw()
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        self.bind("<ButtonRelease-1>", lambda e: command())

    def set_hover(self, value):
        self.hover = value
        self.draw()

    def draw(self):
        import math
        self.delete("all")
        color = ORANGE if (self.pinned or self.hover) else DIM
        a = math.radians(35)
        ca, sa = math.cos(a), math.sin(a)

        def rot(points):
            out = []
            for x, y in points:
                dx, dy = x - 10, y - 10
                out += [dx * ca - dy * sa + 10, dx * sa + dy * ca + 10]
            return out

        fill = color if self.pinned else ""
        for rect in ((7.5, 1, 12.5, 3.2), (8.4, 3.2, 11.6, 8.2), (5.8, 8.2, 14.2, 10.4)):
            x0, y0, x1, y1 = rect
            self.create_polygon(rot([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]),
                                outline=color, fill=fill, width=1.5)
        self.create_line(rot([(10, 10.4), (10, 18)]), fill=color, width=1.5)


def card(parent, note, wrap, full=False):
    """Note card. Returns (outer, header): pack buttons into the header (side='right')."""
    pinned = note["pinned"]
    cbg = PINNED_BG if pinned else PANEL
    outer = tk.Frame(parent, bg=cbg, highlightthickness=1,
                     highlightbackground=ORANGE if pinned else CARD_BORDER)
    tk.Frame(outer, width=3, bg=ORANGE).pack(side="left", fill="y")
    content = tk.Frame(outer, bg=cbg)
    content.pack(side="left", fill="both", expand=True, padx=8, pady=5)
    header = tk.Frame(content, bg=cbg)
    header.pack(fill="x")
    label = ("★ " if pinned else "") + f"[{fmt_stamp(note['stamp'])}]" + \
        (f" #{note['cat']}" if note["cat"] else "")
    mklabel(header, label, fg=ORANGE, font=FONT_SMALL, bg=cbg).pack(side="left")
    text = note["text"]
    if not full and len(text) > 160:
        text = text[:157] + "…"
    body = mklabel(content, text, fg=MUTED, font=FONT_SMALL, bg=cbg, justify="left",
                   anchor="w", wraplength=wrap)
    body.pack(fill="x", anchor="w")
    return outer, header


# --------------------------------------------------------- scrolling frame
class ScrollFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=10,
                                troughcolor=BG, bg=BORDER, relief="flat", bd=0)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))

    def scroll(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


# ----------------------------------------------------------- all-notes window
class AllNotes(tk.Toplevel):
    """All notes grouped by category, with editing, deleting, pinning, search and drag & drop."""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("notemd – all notes")
        self.configure(bg=BG)
        self.geometry("640x700")
        self.set_icon()
        self.filter_cat = ALL
        self.editing = None       # note being edited
        self.confirming = None    # note waiting for delete confirmation
        self.cat_confirm = None   # category selected for deletion
        self.editor = None
        self.edit_var = None
        self.move_var = None
        self.drag = None          # active drag state
        self.hover_zone = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14, pady=(14, 0))
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.refresh())
        self.search = mkentry(top, self.query, width=40)
        self.search.pack(fill="x")
        self.flow = Flow(self)
        self.flow.pack(fill="x", padx=14, pady=(10, 0))
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=14, pady=10)
        self.bind("<MouseWheel>", self.scroll.scroll)
        self.bind("<Escape>", self.on_escape)
        self.bind("<Destroy>", self.on_destroy)
        self.refresh()
        self.search.focus_set()

    def set_icon(self):
        self.app.set_icon(self)

    def on_destroy(self, event):
        if event.widget is self:
            self.app.all = None

    def on_escape(self, _):
        if self.cat_confirm:
            self.cat_confirm = None
            self.refresh()
        elif self.editing:
            self.cancel_edit()
        elif self.query.get():
            self.query.set("")
        else:
            self.destroy()
        return "break"

    # -- actions
    def pin(self, note):
        toggle_pin(note)
        self.app.refresh()

    def start_edit(self, note):
        self.editing, self.confirming = note, None
        self.refresh()

    def cancel_edit(self):
        self.editing = None
        self.refresh()

    def save_edit(self):
        text = self.editor.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        cat = self.edit_var.get()
        update_note(self.editing, text, None if cat == GENERAL else cat)
        self.editing = None
        self.app.refresh()
        return "break"

    def ask_delete(self, note):
        self.confirming, self.editing = note, None
        self.refresh()

    def cancel_delete(self):
        self.confirming = None
        self.refresh()

    def do_delete(self, note):
        delete_note(note)
        self.confirming = None
        self.app.refresh()

    def ask_cat_delete(self, cat):
        self.cat_confirm, self.editing, self.confirming = cat, None, None
        self.refresh()

    def cancel_cat_delete(self):
        self.cat_confirm = None
        self.refresh()

    def do_cat_delete(self, cat, action):
        target = None
        if action == "move" and self.move_var is not None:
            t = self.move_var.get()
            target = None if t == GENERAL else t
        delete_category(cat, action, target)
        self.cat_confirm = None
        self.app.refresh()

    def set_filter(self, key):
        self.filter_cat = ALL if (key is self.filter_cat or (key is not ALL and key == self.filter_cat)) else key
        self.refresh()

    # -- drawing
    @staticmethod
    def same(a, b):
        return a is not None and (a["stamp"], a["cat"], a["text"]) == (b["stamp"], b["cat"], b["text"])

    def build_filter(self, cats, notes):
        self.flow.clear()
        entries = [(ALL, f"all {len(notes)}"),
                   (None, f"{GENERAL} {sum(1 for n in notes if n['cat'] is None)}")]
        entries += [(c, f"{c} {sum(1 for n in notes if n['cat'] == c)}") for c in cats]
        for key, label in entries:
            on = key is self.filter_cat or (key is not ALL and key == self.filter_cat)
            b = mkbtn(self.flow, label, lambda k=key: self.set_filter(k), "toggle", on)
            if key is not ALL:
                b._drop = (key,)   # a dragged note can be dropped on the button
        self.flow.reflow()

    def refresh(self):
        pos = self.scroll.canvas.yview()[0]
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        cats, notes = load_data()
        all_notes = notes
        q = self.query.get().strip().lower()
        if q:
            notes = [n for n in notes
                     if q in n["text"].lower() or q in (n["cat"] or GENERAL).lower()
                     or q in fmt_stamp(n["stamp"]).lower()]
        if self.filter_cat is not ALL and self.filter_cat is not None and self.filter_cat not in cats:
            self.filter_cat = ALL
        self.build_filter(cats, notes)
        inner = self.scroll.inner
        wrap = max(300, self.scroll.canvas.winfo_width() - 80)
        if not notes:
            mklabel(inner, "No matches." if q else "No notes yet.", fg=DIM, font=FONT_SMALL).pack(anchor="w")
        for cat in [None] + cats:
            if self.filter_cat is not ALL and cat != self.filter_cat:
                continue
            group = sorted((n for n in notes if n["cat"] == cat), key=sort_key, reverse=True)
            if not group and (q or (cat is None and not all_notes)):
                continue
            zone = tk.Frame(inner, bg=BG, highlightthickness=1, highlightbackground=BG)
            zone.pack(fill="x", pady=(6, 4))
            zone._drop = (cat,)
            head = tk.Frame(zone, bg=BG)
            head.pack(fill="x", pady=(2, 4))
            mklabel(head, "#", fg=ORANGE, font=FONT_BOLD).pack(side="left")
            mklabel(head, f" {cat or GENERAL} ", fg=FG, font=FONT_BOLD).pack(side="left")
            mklabel(head, f"({len(group)})", fg=DIM, font=FONT_BOLD).pack(side="left")
            if cat is not None and self.cat_confirm != cat:
                mkbtn(head, "delete category", lambda c=cat: self.ask_cat_delete(c)).pack(side="right")
            if cat is not None and self.cat_confirm == cat:
                total = sum(1 for n in all_notes if n["cat"] == cat)
                self.build_cat_panel(zone, cat, total, cats)
            for n in group:
                self.build_note(zone, n, cats, wrap)
        self.update_idletasks()
        self.scroll.canvas.yview_moveto(pos)

    def build_cat_panel(self, parent, cat, count, cats):
        panel = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        panel.pack(fill="x", pady=3)
        if count == 0:
            q = f'Delete category "{cat}"?'
        else:
            q = f'Category "{cat}" has {count} note{"s" if count != 1 else ""}. What should happen to them?'
        mklabel(panel, q, fg=MUTED, font=FONT_SMALL, bg=PANEL, wraplength=520, justify="left").pack(
            anchor="w", padx=8, pady=(6, 4))
        row = tk.Frame(panel, bg=PANEL)
        row.pack(fill="x", padx=8, pady=(0, 6))
        self.move_var = None
        if count:
            names = [GENERAL] + [c for c in cats if c != cat]
            self.move_var = tk.StringVar(value=names[0])
            mkbtn(row, "move →", lambda: self.do_cat_delete(cat, "move")).pack(side="left")
            mkoptions(row, self.move_var, names).pack(side="left", padx=6)
            mkbtn(row, "cancel", self.cancel_cat_delete).pack(side="right")
            mkbtn(row, "delete notes too", lambda: self.do_cat_delete(cat, "delete"), "danger").pack(
                side="right", padx=6)
        else:
            mkbtn(row, "delete", lambda: self.do_cat_delete(cat, "delete"), "danger").pack(side="left")
            mkbtn(row, "cancel", self.cancel_cat_delete).pack(side="left", padx=6)

    def build_note(self, parent, n, cats, wrap):
        if self.same(self.editing, n):
            return self.build_editor(parent, n, cats)
        outer, header = card(parent, n, wrap, full=True)
        outer.pack(fill="x", pady=3)
        cbg = PINNED_BG if n["pinned"] else PANEL
        PinIcon(header, n["pinned"], lambda n=n: self.pin(n), cbg).pack(side="right")
        if self.same(self.confirming, n):
            mkbtn(header, "no", self.cancel_delete).pack(side="right", padx=(0, 6))
            mkbtn(header, "yes", lambda n=n: self.do_delete(n), "danger").pack(side="right", padx=(0, 6))
            mklabel(header, "delete?", fg=DIM, font=FONT_SMALL, bg=cbg).pack(side="right", padx=(0, 6))
        else:
            mkbtn(header, "delete", lambda n=n: self.ask_delete(n)).pack(side="right", padx=(0, 6))
            mkbtn(header, "edit", lambda n=n: self.start_edit(n)).pack(side="right", padx=(0, 6))
        self.bind_drag(outer, n)

    def build_editor(self, parent, n, cats):
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        outer.pack(fill="x", pady=3)
        mklabel(outer, f"[{fmt_stamp(n['stamp'])}] editing", fg=ORANGE, font=FONT_SMALL, bg=PANEL).pack(
            anchor="w", padx=8, pady=(5, 3))
        self.editor = mktext(outer, 4)
        self.editor.insert("1.0", n["text"])
        self.editor.pack(fill="x", padx=8)
        self.editor.bind("<Control-Return>", lambda e: self.save_edit())
        self.editor.bind("<Escape>", lambda e: (self.cancel_edit(), "break")[1])
        row = tk.Frame(outer, bg=PANEL)
        row.pack(fill="x", padx=8, pady=6)
        names = [GENERAL] + cats
        self.edit_var = tk.StringVar(value=n["cat"] if n["cat"] in names else GENERAL)
        mkoptions(row, self.edit_var, names).pack(side="left")
        mkbtn(row, "save", self.save_edit, "primary").pack(side="left", padx=6)
        mkbtn(row, "cancel", self.cancel_edit).pack(side="left")
        self.after(10, self.editor.focus_set)

    # -- drag & drop (manual: Tk has no built-in drag and drop)
    def bind_drag(self, widget, note):
        if isinstance(widget, (tk.Button, tk.Canvas)):
            return
        widget.bind("<ButtonPress-1>", lambda e, n=note: self.drag_press(e, n), add="+")
        widget.bind("<B1-Motion>", self.drag_motion, add="+")
        widget.bind("<ButtonRelease-1>", self.drag_release, add="+")
        for child in widget.winfo_children():
            self.bind_drag(child, note)

    def drag_press(self, event, note):
        self.drag = {"note": note, "x": event.x_root, "y": event.y_root, "float": None}

    def drag_motion(self, event):
        d = self.drag
        if not d:
            return
        if d["float"] is None:
            if abs(event.x_root - d["x"]) + abs(event.y_root - d["y"]) < DRAG_THRESHOLD:
                return
            f = tk.Toplevel(self)
            f.overrideredirect(True)
            f.attributes("-topmost", True)
            try:
                f.attributes("-alpha", 0.85)
            except tk.TclError:
                pass
            txt = d["note"]["text"].replace("\n", " ")
            mklabel(f, txt[:40] + ("…" if len(txt) > 40 else ""), fg=BG, bg=ORANGE,
                    font=FONT_SMALL, padx=8, pady=3).pack()
            d["float"] = f
        d["float"].geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        self.set_hover_zone(self.zone_at(event.x_root, event.y_root))

    def zone_at(self, x, y):
        w = None
        try:
            w = self.winfo_containing(x, y)
        except Exception:
            pass
        while w is not None:
            if getattr(w, "_drop", None) is not None:
                return w
            w = getattr(w, "master", None)
        return None

    def set_hover_zone(self, zone):
        if zone is self.hover_zone:
            return
        for z, color in ((self.hover_zone, BG), (zone, ORANGE)):
            if z is not None and isinstance(z, tk.Frame):
                try:
                    z.configure(highlightbackground=color)
                except tk.TclError:
                    pass
        self.hover_zone = zone

    def drag_release(self, event):
        d, self.drag = self.drag, None
        if not d:
            return
        zone = None
        if d["float"] is not None:
            d["float"].destroy()
            zone = self.zone_at(event.x_root, event.y_root)
        self.set_hover_zone(None)
        if zone is None:
            return
        (cat,) = zone._drop
        note = d["note"]
        if note["cat"] != cat:
            # update in idle: refresh destroys the dragged widgets in the middle of the event
            def move():
                update_note(note, note["text"], cat)
                self.app.refresh()
            self.after_idle(move)


# --------------------------------------------------------------- main window
class App:
    def __init__(self, hotkey=DEFAULT_HOTKEY, hidden=False):
        self.root = tk.Tk()
        self.events = queue.SimpleQueue()   # "show" requests from the hotkey / a second launch
        self.root.title("notemd")
        self.root.configure(bg=BG)
        self.set_icon(self.root)
        self.selected = None      # selected category (None = general)
        self.cats = []
        self.all = None
        self.warned = False
        self.last_enter = 0.0
        self.hint_text = ("Enter: newline · Enter Enter / Ctrl+Enter: save · "
                          "Esc: hide · Ctrl+1…9: category · Ctrl+Q: quit")

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        left = tk.Frame(outer, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self.text = mktext(left, 7)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<Return>", self.on_return)
        self.text.bind("<Control-Return>", self.on_ctrl_return)
        self.text.bind("<Key>", self.on_any_key, add="+")

        self.flow = Flow(left)
        self.flow.pack(fill="x", pady=(8, 0))
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        self.add_btn = mkbtn(row, "[+] category", self.show_new_entry)
        self.add_btn.pack(side="left")
        self.new_var = tk.StringVar()
        self.new_entry = mkentry(row, self.new_var, width=18)
        self.new_entry.bind("<Return>", self.create_category)
        self.new_entry.bind("<Escape>", lambda e: (self.hide_new_entry(), "break")[1])
        self.hint = mklabel(left, self.hint_text, fg=DIM, font=FONT_SMALL)
        self.hint.pack(anchor="w", pady=(8, 0))

        right = tk.Frame(outer, bg=BG)
        right.pack(side="left", fill="y", padx=(16, 0))
        tk.Frame(right, width=330, height=0, bg=BG).pack()  # minimum width of the column
        mkbtn(right, "> all notes", self.show_all_notes, "primary").pack(fill="x", pady=(0, 8))
        self.list = tk.Frame(right, bg=BG)
        self.list.pack(fill="both", expand=True)

        self.root.bind("<Escape>", self.on_escape)
        for i in range(1, 10):
            self.root.bind(f"<Control-Key-{i}>", lambda e, i=i: self.quick_select(i))
        self.root.bind("<Control-q>", lambda e: self.quit_app())
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.refresh()

        self.hook = None
        if os.name == "nt":
            self.hook = HotkeyHook(hotkey, lambda: self.events.put("show"))
            self.hook.start()
            self.hook.ok.wait(2)
            if self.hook.failed:
                self.hint_text = "Could not register the hotkey – start the app from the Start menu instead."
                self.hint.configure(text=self.hint_text, fg=ORANGE)
        self.root.after(50, self.poll)
        if hidden:
            self.root.withdraw()
        else:
            self.show()

    def poll(self):
        """Runs in the Tk thread: handles show requests queued by other threads."""
        try:
            while True:
                if self.events.get_nowait() == "show":
                    self.show()
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def show(self):
        self.refresh()
        self.root.deiconify()
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 3
        self.root.geometry(f"+{x}+{y}")  # position only: the height follows the content
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.text.focus_set()

    def hide(self):
        if self.all:
            self.all.destroy()
        self.text.delete("1.0", "end")
        self.warned = False
        self.hint.configure(text=self.hint_text, fg=DIM)
        self.root.withdraw()

    def quit_app(self):
        self.root.destroy()
        return "break"

    def set_icon(self, window):
        try:
            img = tk.PhotoImage(file=os.path.join(HERE, "notemd.png"))
            window.iconphoto(True, img)
            window._icon = img
        except Exception:
            pass

    # -- drawing
    def refresh(self):
        cats, notes = load_data()
        self.cats = cats
        if self.selected and self.selected not in cats:
            self.selected = None
        self.flow.clear()
        for cat in cats:
            on = cat == self.selected
            mkbtn(self.flow, cat, lambda c=cat: self.select(None if self.selected == c else c),
                  "toggle", on)
        self.flow.reflow()
        for w in self.list.winfo_children():
            w.destroy()
        for n in latest(notes):
            outer, header = card(self.list, n, wrap=270)
            outer.pack(fill="x", pady=3)
            cbg = PINNED_BG if n["pinned"] else PANEL
            PinIcon(header, n["pinned"], lambda n=n: self.toggle_pin(n), cbg).pack(side="right")
        if self.all:
            self.all.refresh()

    def toggle_pin(self, note):
        toggle_pin(note)
        self.refresh()

    def select(self, cat):
        self.selected = cat
        self.refresh()
        self.text.focus_set()

    def quick_select(self, i):
        if i <= len(self.cats):
            cat = self.cats[i - 1]
            self.select(None if self.selected == cat else cat)
        return "break"

    # -- new category
    def show_new_entry(self):
        self.add_btn.pack_forget()
        self.new_var.set("")
        self.new_entry.pack(side="left")
        self.new_entry.focus_set()
        self.new_entry.bind("<FocusOut>", lambda e: self.hide_new_entry())

    def hide_new_entry(self):
        self.new_entry.unbind("<FocusOut>")
        self.new_entry.pack_forget()
        self.add_btn.pack(side="left")
        self.text.focus_set()

    def create_category(self, _):
        name = add_category(self.new_var.get())
        if name:
            self.selected = name
            self.refresh()
        self.hide_new_entry()
        return "break"

    def show_all_notes(self):
        if self.all:
            self.all.lift()
            return
        self.all = AllNotes(self)

    # -- keys
    def draft(self):
        return self.text.get("1.0", "end-1c").strip()

    def save(self):
        text = self.draft()
        if text:
            add_note(text, self.selected)
            self.refresh()
        self.text.delete("1.0", "end")  # also removes the newline from the first Enter

    def on_return(self, event):
        now = time.monotonic()
        double = now - self.last_enter < DOUBLE_ENTER_SECS
        self.last_enter = now
        if double:
            self.last_enter = 0.0
            self.save()
            return "break"
        return None  # ordinary newline

    def on_ctrl_return(self, event):
        self.last_enter = 0.0
        self.save()
        return "break"

    def on_any_key(self, event):
        if self.warned and event.keysym not in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Escape"):
            self.warned = False
            self.hint.configure(text=self.hint_text, fg=DIM)

    def on_escape(self, _):
        # unsaved text: the first Esc warns, the second closes
        if self.draft() and not self.warned:
            self.warned = True
            self.hint.configure(text="Unsaved text! Ctrl+Enter saves, Esc again discards and closes", fg=ORANGE)
            return "break"
        self.hide()
        return "break"

    def run(self):
        self.root.mainloop()


def main():
    try:  # sharp text on high-DPI screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    argv = sys.argv[1:]
    hidden = "--hidden" in argv
    hotkey = argv[argv.index("--hotkey") + 1] if "--hotkey" in argv and argv.index("--hotkey") + 1 < len(argv) \
        else DEFAULT_HOTKEY
    # one instance only: a second launch just asks the running one to show itself
    if signal_running(b"ping" if hidden else b"show"):
        return
    app = App(hotkey, hidden)
    try:
        app.srv = listen_for_signals(app.events)
    except OSError:
        pass
    app.run()


if __name__ == "__main__":
    main()
