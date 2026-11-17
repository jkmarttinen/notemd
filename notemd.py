#!/usr/bin/env python3
"""notemd – quick notes with a single hotkey.

Enter = newline, double Enter (quickly) or Ctrl+Enter = save, Esc = close.
Notes are stored in ~/Documents/notemd/notes.md

File structure:
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

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from notemd_core import *  # noqa: E402,F401,F403  (storage functions and constants)

# Wayland app id: lets KDE match the window to notemd.desktop (icon)
GLib.set_prgname("notemd")
GLib.set_application_name("notemd")
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notemd.svg")


CSS = b"""
* { font-family: "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", monospace; }
window, .root { background-color: #121212; }
scrolledwindow { background-color: transparent; border: none; border-radius: 0; }
textview, textview text { background-color: #181818; color: #e6e6e6; font-size: 11.5pt; }
textview { padding: 10px; }
scrolledwindow.input { border: 1px solid #333333; border-radius: 0; }
scrolledwindow.input:focus-within { border-color: #d2691e; }
.note {
    background-color: #181818; border-radius: 0; padding: 6px 10px;
    border: 1px solid #262626; border-left: 3px solid #d2691e;
}
.note.pinned { border: 1px solid #d2691e; border-left: 3px solid #d2691e; background-color: #1f1a16; }
.stamp { color: #d2691e; font-size: 8.5pt; }
.body { color: #bdbdbd; font-size: 9.5pt; }
.hint { color: #5c5c5c; font-size: 8.5pt; }
.group { color: #e6e6e6; font-weight: bold; font-size: 11pt; }
button.cat, button.side {
    background-image: none; background-color: #181818; color: #bdbdbd;
    border: 1px solid #333333; border-radius: 0; padding: 2px 10px; box-shadow: none;
    text-shadow: none;
}
button.cat:hover, button.side:hover { background-color: #222222; border-color: #d2691e; }
button.cat:checked { background-color: #d2691e; border-color: #d2691e; color: #121212; font-weight: bold; }
button.side.primary { color: #d2691e; border-color: #d2691e; }
button.side.primary:hover { background-color: #d2691e; color: #121212; }
button.pinbtn { background: transparent; background-image: none; border: none; box-shadow: none; padding: 2px; min-height: 0; min-width: 0; }
button.pinbtn:hover { background: transparent; }
.dropzone { border: 1px dashed transparent; padding: 4px; }
.dropzone.dropover { border-color: #d2691e; background-color: #1a1612; }
calendar { background-color: #181818; color: #bdbdbd; border: 1px solid #333333;
    border-radius: 0; padding: 4px; }
calendar:selected { background-color: #d2691e; color: #121212; }
calendar:indeterminate { color: #4a4a4a; }
calendar.highlight { color: #d2691e; }
calendar.header { color: #e6e6e6; background-color: transparent; border: none; }
calendar.button { background-image: none; background-color: transparent; color: #d2691e;
    border: none; box-shadow: none; }
button.side.small { padding: 0 8px; font-size: 8.5pt; }
button.side.danger { color: #121212; background-color: #d8453b; border-color: #d8453b; }
combobox button { background-image: none; background-color: #181818; color: #bdbdbd;
    border: 1px solid #333333; border-radius: 0; box-shadow: none; padding: 0 6px; }
entry.newcat {
    background-image: none; background-color: #181818; color: #e6e6e6;
    border: 1px solid #d2691e; border-radius: 0; padding: 2px 8px; box-shadow: none;
}
scrollbar slider { background-color: #333333; border-radius: 0; min-width: 6px; }
scrollbar trough, scrollbar { background: transparent; border: none; }
"""


# --------------------------------------------------------------------- UI
def make_card(note, full=False):
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    card.get_style_context().add_class("note")
    label = ("★ " if note["pinned"] else "") + f"[{fmt_stamp(note['stamp'])}]" + (f" #{note['cat']}" if note["cat"] else "")
    if note["pinned"]:
        card.get_style_context().add_class("pinned")
    s = Gtk.Label(label=label)
    s.get_style_context().add_class("stamp")
    s.set_xalign(0)
    text = note["text"]
    if not full and len(text) > 160:
        text = text[:157] + "…"
    b = Gtk.Label(label=text)
    b.get_style_context().add_class("body")
    b.set_xalign(0)
    b.set_line_wrap(True)
    b.set_max_width_chars(40 if not full else 80)
    b.set_selectable(False)  # drag & drop requires that the text is not selectable
    b.set_can_focus(False)  # keeps the text from being highlighted when the window opens
    card.pack_start(s, False, False, 0)
    card.pack_start(b, False, False, 0)
    return card


def _pin_svg(color, filled):
    fill = color if filled else "none"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">'
        '<g transform="rotate(35 10 10)" stroke="%s" stroke-width="1.5" stroke-linejoin="round" '
        'stroke-linecap="round" fill="%s">'
        '<rect x="7.5" y="1" width="5" height="2.2"/>'
        '<path d="M8.4 3.2 V8.2 H11.6 V3.2 Z"/>'
        '<path d="M5.8 8.2 H14.2 V10.4 H5.8 Z"/>'
        '<path d="M10 10.4 V18" fill="none"/>'
        '</g></svg>' % (color, fill)
    )


_PIN_CACHE = {}


def pin_pixbuf(color, filled):
    key = (color, filled)
    if key not in _PIN_CACHE:
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.write(_pin_svg(color, filled).encode())
        loader.close()
        _PIN_CACHE[key] = loader.get_pixbuf()
    return _PIN_CACHE[key]


class PinButton(Gtk.Button):
    """Push-pin icon: grey outline = unpinned, orange fill = pinned."""

    def __init__(self, pinned, callback):
        super().__init__()
        self.pinned = pinned
        self.get_style_context().add_class("pinbtn")
        self.set_can_focus(False)
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_tooltip_text("Unpin" if pinned else "Pin to top")
        self.image = Gtk.Image()
        self.add(self.image)
        self.update_icon()
        self.connect("state-flags-changed", lambda *_: self.update_icon())
        self.connect("clicked", lambda *_: callback())

    def update_icon(self):
        hover = bool(self.get_state_flags() & Gtk.StateFlags.PRELIGHT)
        color = "#d2691e" if (self.pinned or hover) else "#6a6d73"
        self.image.set_from_pixbuf(pin_pixbuf(color, self.pinned))


def add_pin_header(card, note, callback, extras=()):
    """Turns the card's timestamp row into a header row with the pin icon on the right."""
    stamp = card.get_children()[0]
    card.remove(stamp)
    header = Gtk.Box(spacing=6)
    header.pack_start(stamp, True, True, 0)
    header.pack_end(PinButton(note["pinned"], callback), False, False, 0)
    for w in extras:  # pack_end: the first extra is the one closest to the pin
        header.pack_end(w, False, False, 0)
    card.pack_start(header, False, False, 0)
    card.reorder_child(header, 0)


def clear(container):
    for child in container.get_children():
        container.remove(child)


DOUBLE_ENTER_SECS = 0.4  # two Enters this quickly = save
ALL = object()  # category filter: all
DND_TAG = "notemd-note"
DND_TARGETS = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]


class AllNotesWindow(Gtk.Window):
    """All notes grouped by category, with editing and deleting."""

    def __init__(self, parent):
        super().__init__(title="notemd – all notes")
        self.main = parent
        self.set_default_size(600, 660)
        self.set_transient_for(parent)
        self.get_style_context().add_class("root")
        self.connect("key-press-event", self.on_key)
        self.editing = None          # note being edited
        self.confirming = None       # note waiting for delete confirmation
        self.cat_confirm = None      # category selected for deletion
        self.drag_note = None        # note being dragged
        self.move_combo = None
        self.editor = None
        self.combo = None
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("search (text or category)_")
        self.search.get_style_context().add_class("newcat")
        self.search.set_margin_start(14)
        self.search.set_margin_end(14)
        self.search.set_margin_top(14)
        self.search.connect("search-changed", lambda *_: self.refresh())
        outer.pack_start(self.search, False, False, 0)
        self.filter_cat = ALL
        self._syncing = False
        self.filter_flow = Gtk.FlowBox()
        self.filter_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.filter_flow.set_homogeneous(False)
        self.filter_flow.set_max_children_per_line(30)
        self.filter_flow.set_column_spacing(6)
        self.filter_flow.set_row_spacing(6)
        self.filter_flow.set_margin_start(14)
        self.filter_flow.set_margin_end(14)
        self.filter_flow.set_margin_top(10)
        outer.pack_start(self.filter_flow, False, False, 0)
        self.scroll = Gtk.ScrolledWindow()
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_border_width(14)
        self.scroll.add(self.box)
        outer.pack_start(self.scroll, True, True, 0)
        self.add(outer)
        self.refresh()
        self.show_all()
        self.search.grab_focus()

    def on_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.cat_confirm:
                self.cancel_cat_delete()
            elif self.editing:
                self.cancel_edit()
            elif self.search.get_text():
                self.search.set_text("")
            else:
                self.destroy()
            return True
        return False

    @staticmethod
    def same(a, b):
        return a is not None and (a["stamp"], a["cat"], a["text"]) == (b["stamp"], b["cat"], b["text"])

    def small_button(self, label, callback, cls=None):
        btn = Gtk.Button(label=label)
        ctx = btn.get_style_context()
        ctx.add_class("side")
        ctx.add_class("small")
        if cls:
            ctx.add_class(cls)
        btn.set_can_focus(False)
        btn.connect("clicked", lambda *_: callback())
        return btn

    # -- toiminnot
    def build_filter(self, cats, notes):
        """Category buttons at the top of the window: one click shows only that category."""
        clear(self.filter_flow)
        entries = [(ALL, f"all {len(notes)}")]
        entries.append((None, f"{GENERAL} {sum(1 for n in notes if n['cat'] is None)}"))
        for c in cats:
            entries.append((c, f"{c} {sum(1 for n in notes if n['cat'] == c)}"))
        self._syncing = True
        for key, label in entries:
            b = Gtk.ToggleButton(label=label)
            b.get_style_context().add_class("cat")
            b.set_can_focus(False)
            b.set_active(key is self.filter_cat or (key is not ALL and key == self.filter_cat))
            b.connect("toggled", self.on_filter_toggled, key)
            if key is not ALL:  # a dragged note can be dropped on the button
                b.drag_dest_set(Gtk.DestDefaults.ALL, DND_TARGETS, Gdk.DragAction.MOVE)
                b.connect("drag-data-received", self.on_drag_received, key)
            self.filter_flow.add(b)
        self._syncing = False
        self.filter_flow.show_all()

    def on_filter_toggled(self, button, key):
        if self._syncing:
            return
        # button toggled off -> back to "all"
        self.filter_cat = key if button.get_active() else ALL
        self.refresh()

    def ask_cat_delete(self, cat):
        self.cat_confirm, self.editing, self.confirming = cat, None, None
        self.refresh()

    def cancel_cat_delete(self):
        self.cat_confirm = None
        self.refresh()

    def do_cat_delete(self, cat, action):
        target = None
        if action == "move" and self.move_combo is not None:
            t = self.move_combo.get_active_text()
            target = None if t == GENERAL else t
        delete_category(cat, action, target)
        self.cat_confirm = None
        self.main.refresh()

    def build_cat_panel(self, cat, count, cats):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        panel.get_style_context().add_class("note")
        if count == 0:
            q = f"Delete category \"{cat}\"?"
        else:
            q = f"Category \"{cat}\" has {count} note{'s' if count != 1 else ''}. What should happen to them?"
        lbl = Gtk.Label(label=q)
        lbl.get_style_context().add_class("body")
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)
        panel.pack_start(lbl, False, False, 0)
        row = Gtk.Box(spacing=6)
        self.move_combo = None
        if count:
            names = [GENERAL] + [c for c in cats if c != cat]
            self.move_combo = Gtk.ComboBoxText()
            self.move_combo.set_can_focus(False)
            for name in names:
                self.move_combo.append_text(name)
            self.move_combo.set_active(0)
            row.pack_start(self.small_button("move →", lambda: self.do_cat_delete(cat, "move")), False, False, 0)
            row.pack_start(self.move_combo, False, False, 0)
            row.pack_end(self.small_button("cancel", self.cancel_cat_delete), False, False, 0)
            row.pack_end(self.small_button("delete notes too", lambda: self.do_cat_delete(cat, "delete"), "danger"), False, False, 0)
        else:
            row.pack_start(self.small_button("delete", lambda: self.do_cat_delete(cat, "delete"), "danger"), False, False, 0)
            row.pack_start(self.small_button("cancel", self.cancel_cat_delete), False, False, 0)
        panel.pack_start(row, False, False, 0)
        return panel

    def pin(self, note):
        toggle_pin(note)
        self.main.refresh()

    def start_edit(self, note):
        self.editing, self.confirming = note, None
        self.refresh()

    def cancel_edit(self):
        self.editing = None
        self.refresh()

    def save_edit(self):
        buf = self.editor.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
        if not text:
            return
        cat = self.combo.get_active_text()
        update_note(self.editing, text, None if cat == GENERAL else cat)
        self.editing = None
        self.main.refresh()

    def ask_delete(self, note):
        self.confirming, self.editing = note, None
        self.refresh()

    def cancel_delete(self):
        self.confirming = None
        self.refresh()

    def do_delete(self, note):
        delete_note(note)
        self.confirming = None
        self.main.refresh()

    def on_editor_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.cancel_edit()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.save_edit()
            return True
        return False

    # -- piirto
    def build_card(self, n, cats):
        if self.same(self.editing, n):
            return self.build_editor(n, cats)
        card = make_card(n, full=True)
        if self.same(self.confirming, n):
            lbl = Gtk.Label(label="delete?")
            lbl.get_style_context().add_class("hint")
            extras = [self.small_button("no", self.cancel_delete),
                      self.small_button("yes", lambda: self.do_delete(n), "danger"), lbl]
        else:
            extras = [self.small_button("delete", lambda: self.ask_delete(n)),
                      self.small_button("edit", lambda: self.start_edit(n))]
        add_pin_header(card, n, lambda: self.pin(n), extras)
        return self.make_draggable(card, n)

    # -- drag & drop
    def make_draggable(self, card, note):
        eb = Gtk.EventBox()
        eb.set_visible_window(True)
        eb.add(card)
        eb.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, DND_TARGETS, Gdk.DragAction.MOVE)
        eb.connect("drag-begin", self.on_drag_begin, note)
        eb.connect("drag-data-get", lambda w, ctx, sel, info, t: sel.set_text(DND_TAG, -1))
        eb.connect("drag-end", lambda *_: setattr(self, "drag_note", None))
        return eb

    def on_drag_begin(self, widget, context, note):
        self.drag_note = note
        try:
            alloc = widget.get_allocation()
            pb = Gdk.pixbuf_get_from_window(widget.get_window(), 0, 0, alloc.width, alloc.height)
            if pb:
                Gtk.drag_set_icon_pixbuf(context, pb, 12, 12)
        except Exception:
            pass

    def on_drag_motion(self, widget, context, x, y, time, grp):
        if self.drag_note is not None:
            grp.get_style_context().add_class("dropover")
        return False

    def on_drag_received(self, widget, context, x, y, data, info, time, cat):
        note = self.drag_note
        Gtk.drag_finish(context, note is not None, False, time)
        if note is None or note["cat"] == cat:
            return
        # update in idle: refresh destroys the dragged widget in the middle of the event
        def move():
            update_note(note, note["text"], cat)
            self.main.refresh()
            return False
        GLib.idle_add(move)

    def build_editor(self, n, cats):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("note")
        s = Gtk.Label(label=f"[{fmt_stamp(n['stamp'])}] editing")
        s.get_style_context().add_class("stamp")
        s.set_xalign(0)
        card.pack_start(s, False, False, 0)

        self.editor = Gtk.TextView()
        self.editor.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.editor.get_buffer().set_text(n["text"])
        self.editor.connect("key-press-event", self.on_editor_key)
        frame = Gtk.ScrolledWindow()
        frame.get_style_context().add_class("input")
        frame.set_min_content_height(80)
        frame.add(self.editor)
        card.pack_start(frame, False, False, 0)

        row = Gtk.Box(spacing=6)
        self.combo = Gtk.ComboBoxText()
        self.combo.set_can_focus(False)
        names = [GENERAL] + cats
        for name in names:
            self.combo.append_text(name)
        self.combo.set_active(names.index(n["cat"]) if n["cat"] in names else 0)
        row.pack_start(self.combo, False, False, 0)
        row.pack_start(self.small_button("save", self.save_edit, "primary"), False, False, 0)
        row.pack_start(self.small_button("cancel", self.cancel_edit), False, False, 0)
        card.pack_start(row, False, False, 0)
        GLib.idle_add(self.editor.grab_focus)
        return card

    def refresh(self):
        adj = self.scroll.get_vadjustment()
        pos = adj.get_value()
        clear(self.box)
        cats, notes = load_data()
        all_notes = notes
        query = self.search.get_text().strip().lower()
        date = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", query)
        if date:  # a plain date (from the calendar) matches that day exactly
            iso = f"{date.group(3)}-{int(date.group(2)):02d}-{int(date.group(1)):02d}"
            notes = [n for n in notes if n["stamp"].startswith(iso)]
        elif query:
            notes = [n for n in notes
                     if query in n["text"].lower() or query in (n["cat"] or GENERAL).lower()
                     or query in fmt_stamp(n["stamp"]).lower()]
        if self.filter_cat is not ALL and self.filter_cat is not None and self.filter_cat not in cats:
            self.filter_cat = ALL
        self.build_filter(cats, notes)
        if not notes:
            lbl = Gtk.Label(label="No matches." if query else "No notes yet.")
            lbl.get_style_context().add_class("hint")
            self.box.pack_start(lbl, False, False, 0)
        for cat in [None] + cats:
            if self.filter_cat is not ALL and cat != self.filter_cat:
                continue
            group = sorted((n for n in notes if n["cat"] == cat), key=sort_key, reverse=True)
            if not group and (query or (cat is None and not all_notes)):
                continue
            h = Gtk.Label()
            h.set_markup(f"<span foreground='#d2691e'>#</span> {GLib.markup_escape_text(cat or GENERAL)}  "
                         f"<span foreground='#5c5c5c'>({len(group)})</span>")
            h.get_style_context().add_class("group")
            h.set_xalign(0)
            grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            grp.get_style_context().add_class("dropzone")
            zone = Gtk.EventBox()
            zone.add(grp)
            zone.drag_dest_set(Gtk.DestDefaults.ALL, DND_TARGETS, Gdk.DragAction.MOVE)
            zone.connect("drag-motion", self.on_drag_motion, grp)
            zone.connect("drag-leave", lambda w, c, t, g=grp: g.get_style_context().remove_class("dropover"))
            zone.connect("drag-data-received", self.on_drag_received, cat)
            head = Gtk.Box(spacing=6)
            head.set_margin_top(4)
            head.pack_start(h, True, True, 0)
            if cat is not None and self.cat_confirm != cat:
                head.pack_end(self.small_button("delete category", lambda c=cat: self.ask_cat_delete(c)), False, False, 0)
            grp.pack_start(head, False, False, 0)
            if cat is not None and self.cat_confirm == cat:
                total = sum(1 for n in all_notes if n["cat"] == cat)
                grp.pack_start(self.build_cat_panel(cat, total, cats), False, False, 0)
            for n in group:
                grp.pack_start(self.build_card(n, cats), False, False, 0)
            self.box.pack_start(zone, False, False, 0)
        self.box.show_all()
        GLib.idle_add(adj.set_value, pos)


class NoteMD(Gtk.Window):
    def __init__(self):
        super().__init__(title="notemd")
        self.set_default_size(1080, -1)  # height follows the content
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.get_style_context().add_class("root")
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_window_key)

        self.selected = None      # selected category (None = general)
        self.note_days = set()
        self.cat_buttons = {}
        self.warned = False
        self.last_enter = 0.0
        self.all_window = None
        self._syncing = False

        Gtk.Settings.get_default().set_property("gtk-entry-select-on-focus", False)  # no auto-selected text
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        box = Gtk.Box(spacing=16)
        box.set_border_width(16)
        self.add(box)

        # Far left: small calendar (days with notes are marked, double-click a day to see its notes)
        cal_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.calendar = Gtk.Calendar()
        self.calendar.set_can_focus(False)
        self.calendar.connect("month-changed", lambda *_: self.mark_calendar())
        self.calendar.connect("day-selected-double-click", self.on_calendar_day)
        cal_col.pack_start(self.calendar, False, False, 0)
        cal_hint = Gtk.Label(label="double-click a day\nto show its notes")
        cal_hint.get_style_context().add_class("hint")
        cal_hint.set_xalign(0)
        cal_col.pack_start(cal_hint, False, False, 0)
        box.pack_start(cal_col, False, False, 0)

        # Left: writing area + categories
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.connect("key-press-event", self.on_key)
        scroll = Gtk.ScrolledWindow()
        scroll.get_style_context().add_class("input")
        scroll.set_min_content_height(140)
        scroll.add(self.view)
        left.pack_start(scroll, True, True, 0)

        cat_row = Gtk.Box(spacing=6)
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_homogeneous(False)
        self.flow.set_max_children_per_line(30)
        self.flow.set_column_spacing(6)
        self.flow.set_row_spacing(6)
        cat_row.pack_start(self.flow, True, True, 0)

        self.new_entry = Gtk.Entry()
        self.new_entry.set_placeholder_text("new category_")
        self.new_entry.set_width_chars(16)
        self.new_entry.get_style_context().add_class("newcat")
        self.new_entry.set_no_show_all(True)
        self.new_entry.connect("key-press-event", self.on_entry_key)
        self.new_entry.connect("focus-out-event", lambda *a: self.hide_new_entry())
        cat_row.pack_start(self.new_entry, False, False, 0)

        self.add_btn = self.side_button("[+] category", self.show_new_entry)
        cat_row.pack_start(self.add_btn, False, False, 0)
        left.pack_start(cat_row, False, False, 0)

        self.hint_text = "Enter: newline · Enter Enter / Ctrl+Enter: save · Esc: close · Ctrl+1…9: category"
        hint = self.hint = Gtk.Label(label=self.hint_text)
        hint.get_style_context().add_class("hint")
        hint.set_xalign(0)
        left.pack_start(hint, False, False, 0)
        box.pack_start(left, True, True, 0)

        # Right: button + the 5 latest
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        all_btn = self.side_button("> all notes", self.show_all_notes)
        all_btn.get_style_context().add_class("primary")
        right_col.pack_start(all_btn, False, False, 0)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right = Gtk.ScrolledWindow()
        right.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        right.set_propagate_natural_height(True)  # window grows with the list -> no scrollbar
        right.set_max_content_height(self.max_height())
        right.add(self.list_box)
        right_col.pack_start(right, True, True, 0)
        right_col.set_size_request(320, -1)
        box.pack_start(right_col, False, True, 0)

        self.refresh()
        self.show_all()
        self.view.grab_focus()

    # -- apurit
    def max_height(self):
        try:
            mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
            return int(mon.get_workarea().height * 0.8)
        except Exception:
            return 700

    def fit_height(self):
        """Grow the window if needed so the list fits without a scrollbar."""
        width, height = self.get_size()
        _, natural = self.get_preferred_height()
        target = min(natural, self.max_height() + 120)
        if target > height:
            self.resize(width, target)
        return False

    def side_button(self, label, callback):
        btn = Gtk.Button(label=label)
        btn.get_style_context().add_class("side")
        btn.set_can_focus(False)  # focus stays in the text area
        btn.connect("clicked", lambda *_: callback())
        return btn

    def refresh(self):
        cats, notes = load_data()
        # category buttons
        clear(self.flow)
        self.cat_buttons = {}
        if self.selected and self.selected not in cats:
            self.selected = None
        for cat in cats:
            b = Gtk.ToggleButton(label=cat)
            b.get_style_context().add_class("cat")
            b.set_can_focus(False)
            b.set_active(cat == self.selected)
            b.connect("toggled", self.on_cat_toggled, cat)
            self.cat_buttons[cat] = b
            self.flow.add(b)
        self.flow.show_all()
        self.cats = cats
        self.note_days = {n["stamp"][:10] for n in notes}
        self.mark_calendar()
        # latest notes
        clear(self.list_box)
        for n in latest(notes):
            card = make_card(n)
            add_pin_header(card, n, lambda n=n: self.toggle_pin(n))
            self.list_box.pack_start(card, False, False, 0)
        self.list_box.show_all()
        GLib.idle_add(self.fit_height)
        if self.all_window:
            self.all_window.refresh()

    # -- calendar
    def mark_calendar(self):
        """Mark the days of the shown month that have notes."""
        year, month, _ = self.calendar.get_date()   # month is 0-based
        self.calendar.clear_marks()
        prefix = f"{year}-{month + 1:02d}-"
        for day in self.note_days:
            if day.startswith(prefix):
                self.calendar.mark_day(int(day[8:10]))

    def on_calendar_day(self, calendar):
        year, month, day = calendar.get_date()
        self.show_all_notes()
        search = self.all_window.search
        search.set_text(f"{day}.{month + 1}.{year}")
        search.select_region(0, 0)   # no highlighted text
        search.set_position(-1)

    def toggle_pin(self, note):
        toggle_pin(note)
        self.refresh()

    def select(self, cat):
        self._syncing = True
        self.selected = cat
        for name, b in self.cat_buttons.items():
            b.set_active(name == cat)
        self._syncing = False

    def on_cat_toggled(self, button, cat):
        if self._syncing:
            return
        self.select(cat if button.get_active() else None)

    # -- new category
    def show_new_entry(self):
        self.add_btn.hide()
        self.new_entry.set_text("")
        self.new_entry.show()
        self.new_entry.grab_focus()

    def hide_new_entry(self):
        self.new_entry.hide()
        self.add_btn.show()
        self.view.grab_focus()

    def on_entry_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide_new_entry()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            name = add_category(self.new_entry.get_text())
            if name:
                self.selected = name
                self.refresh()
            self.hide_new_entry()
            return True
        return False

    # -- all notes
    def show_all_notes(self):
        if self.all_window:
            self.all_window.present()
            return
        self.all_window = AllNotesWindow(self)
        self.all_window.connect("destroy", lambda *_: setattr(self, "all_window", None))

    # -- keys
    def on_key(self, widget, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            now = GLib.get_monotonic_time() / 1e6
            double = now - self.last_enter < DOUBLE_ENTER_SECS
            self.last_enter = now
            if not (event.state & Gdk.ModifierType.CONTROL_MASK or double):
                return False  # ordinary newline
            self.last_enter = 0.0
            text = self.draft()
            if text:
                add_note(text, self.selected)
                self.refresh()
            self.view.get_buffer().set_text("")  # also removes the newline from the first Enter
            return True
        if event.state & Gdk.ModifierType.CONTROL_MASK and Gdk.KEY_1 <= event.keyval <= Gdk.KEY_9:
            i = event.keyval - Gdk.KEY_1
            if i < len(self.cats):
                cat = self.cats[i]
                self.select(None if self.selected == cat else cat)
            return True
        return False

    def draft(self):
        buf = self.view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()

    def on_window_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.new_entry.has_focus():
                return False  # the category entry handles Esc itself
            # unsaved text: the first Esc warns, the second closes
            if self.draft() and not self.warned:
                self.warned = True
                self.hint.set_markup("<span foreground='#d2691e'>Unsaved text! Ctrl+Enter saves, Esc again discards and closes</span>")
                return True
            self.close()
            return True
        if self.warned and event.keyval not in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R):
            self.warned = False
            self.hint.set_text(self.hint_text)
        return False


if __name__ == "__main__":
    if os.path.exists(ICON_FILE):
        Gtk.Window.set_default_icon_from_file(ICON_FILE)
    NoteMD()
    Gtk.main()
