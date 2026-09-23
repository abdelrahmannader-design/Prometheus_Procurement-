"""The application shell: sidebar rail, top bar, content host, palette.

The shell is a *chrome replacement*, not a rewrite. It hosts whatever the
application already builds — in Prometheus that is the existing
``ttk.Notebook`` — and drives it from a modern rail, so every legacy screen
keeps working while the navigation, search and status chrome around it
become the new interface.

Nothing here knows about procurement: it takes a list of destinations and
a callback. That keeps the shell testable on its own and reusable for any
other screen the app grows later.
"""

from __future__ import annotations

import tkinter as tk

from . import primitives as pr
from .theme import Theme, mix
from .widgets import Chip, IconBubble, SearchField, ToggleSwitch, parent_bg

__all__ = ["NavItem", "Sidebar", "TopBar", "ModernShell", "CommandPalette"]


class NavItem(tk.Canvas):
    """One rail destination: active pill, glyph, label and optional badge."""

    def __init__(self, master, theme: Theme, key, label, glyph="•",
                 command=None, ground=None, collapsed=False, height=42, **kw):
        self.theme = theme
        self.key = key
        self.label = label
        self.glyph = glyph
        self._ground = ground or parent_bg(master, theme.c("rail"))
        self._command = command
        self._active = False
        self._hover = False
        self._collapsed = collapsed
        self._badge = ""
        super().__init__(master, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Button-1>", self._on_click)

    # -- state ----------------------------------------------------------
    def set_active(self, active: bool):
        if bool(active) != self._active:
            self._active = bool(active)
            self._draw()

    def set_badge(self, text=""):
        text = "" if text in (None, 0, "0") else str(text)
        if text != self._badge:
            self._badge = text
            self._draw()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = bool(collapsed)
        self._draw()

    def _set_hover(self, hover):
        self._hover = hover
        self._draw()

    def _on_click(self, _event=None):
        if callable(self._command):
            self._command(self.key)

    # -- paint ----------------------------------------------------------
    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        t = self.theme
        pad = 6
        if self._active:
            fill = t.c("brand_soft")
            ink = t.c("brand_ink")
        elif self._hover:
            fill = mix(self._ground, t.c("brand"), 0.07)
            ink = t.c("ink")
        else:
            fill = None
            ink = t.c("rail_ink")
        if fill:
            pr.round_rect(self, pad, 3, w - pad, h - 3, radius=t.r("sm"), fill=fill)
        if self._active:
            # A short accent bar marks the current destination at a glance.
            pr.round_rect(self, pad - 3, h / 2 - 9, pad, h / 2 + 9, radius=2,
                          fill=t.c("brand"))
        gx = pad + 15
        self.create_text(gx, h / 2, text=self.glyph, fill=ink,
                         font=(t.family, t.size("subtitle")))
        if not self._collapsed:
            self.create_text(gx + 20, h / 2, anchor="w", text=self.label,
                             fill=ink,
                             font=t.font("body", "bold" if self._active else "regular"))
            if self._badge:
                bw = pr.chip_text_width(t.size("micro"), self._badge, pad=7)
                bh = t.size("micro") + 9
                pr.pill(self, w - pad - 8 - bw, h / 2 - bh / 2, w - pad - 8,
                        h / 2 + bh / 2, fill=t.c("rose"))
                self.create_text(w - pad - 8 - bw / 2, h / 2, text=self._badge,
                                 fill="#ffffff", font=t.font("micro", "bold"))
        elif self._badge:
            pr.dot(self, w - pad - 6, h / 2 - 8, 4, fill=t.c("rose"))


class Sidebar(tk.Frame):
    """Brand mark, grouped destinations, and a footer slot."""

    def __init__(self, master, theme: Theme, destinations, on_navigate=None,
                 brand="Prometheus", brand_sub="Procurement", brand_mark="◈",
                 collapsed=False, **kw):
        self.theme = theme
        self._bg = theme.c("rail")
        super().__init__(master, bg=self._bg, **kw)
        self._on_navigate = on_navigate
        self._collapsed = bool(collapsed)
        self._items = {}
        self._section_labels = []
        self._active = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # -- brand -------------------------------------------------------
        head = tk.Frame(self, bg=self._bg)
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 6))
        head.columnconfigure(1, weight=1)
        self._mark = IconBubble(head, theme, brand_mark, tone="brand", size=36,
                                ground=self._bg)
        self._mark.grid(row=0, column=0, rowspan=2)
        self._brand_lbl = tk.Label(head, text=brand, bg=self._bg,
                                   fg=theme.c("ink"), font=theme.font("body_lg", "bold"),
                                   anchor="w")
        self._brand_lbl.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._brand_sub = tk.Label(head, text=brand_sub, bg=self._bg,
                                   fg=theme.c("rail_ink_soft"),
                                   font=theme.font("micro"), anchor="w")
        self._brand_sub.grid(row=1, column=1, sticky="w", padx=(10, 0))
        self._head = head

        # -- destinations -------------------------------------------------
        self.nav = tk.Frame(self, bg=self._bg)
        self.nav.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.nav.columnconfigure(0, weight=1)
        self._build_items(destinations)

        # -- footer -------------------------------------------------------
        self.footer = tk.Frame(self, bg=self._bg)
        self.footer.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        self.footer.columnconfigure(0, weight=1)

    def _build_items(self, destinations):
        for child in self.nav.winfo_children():
            child.destroy()
        self._items.clear()
        self._section_labels.clear()
        row = 0
        seen_sections = set()
        for dest in destinations:
            section = dest.get("section") or ""
            if section and section not in seen_sections:
                seen_sections.add(section)
                lbl = tk.Label(self.nav, text=section.upper(), bg=self._bg,
                               fg=self.theme.c("rail_ink_soft"),
                               font=self.theme.font("micro", "bold"), anchor="w")
                lbl.grid(row=row, column=0, sticky="ew", padx=20,
                         pady=(14 if row else 2, 4))
                self._section_labels.append(lbl)
                row += 1
            item = NavItem(self.nav, self.theme, dest["key"], dest["label"],
                           glyph=dest.get("glyph", "•"),
                           command=self._navigate, ground=self._bg,
                           collapsed=self._collapsed)
            item.grid(row=row, column=0, sticky="ew", padx=6)
            self._items[dest["key"]] = item
            row += 1

    def _navigate(self, key):
        self.set_active(key)
        if callable(self._on_navigate):
            self._on_navigate(key)

    # -- api -------------------------------------------------------------
    def set_active(self, key):
        self._active = key
        for item_key, item in self._items.items():
            item.set_active(item_key == key)

    @property
    def active(self):
        return self._active

    def set_badge(self, key, text=""):
        item = self._items.get(key)
        if item is not None:
            item.set_badge(text)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = bool(collapsed)
        for item in self._items.values():
            item.set_collapsed(self._collapsed)
        for lbl in self._section_labels:
            if self._collapsed:
                lbl.grid_remove()
            else:
                lbl.grid()
        if self._collapsed:
            self._brand_lbl.grid_remove()
            self._brand_sub.grid_remove()
        else:
            self._brand_lbl.grid()
            self._brand_sub.grid()

    def keys(self):
        return list(self._items.keys())


class TopBar(tk.Frame):
    """Page title, live market chips, search and quick actions."""

    def __init__(self, master, theme: Theme, on_search=None, on_toggle_rail=None,
                 on_toggle_theme=None, dark=False, **kw):
        self.theme = theme
        self._bg = theme.c("bg")
        super().__init__(master, bg=self._bg, **kw)
        self.columnconfigure(2, weight=1)

        self.rail_btn = tk.Canvas(self, width=34, height=34, bg=self._bg,
                                  highlightthickness=0, bd=0, cursor="hand2")
        self.rail_btn.grid(row=0, column=0, padx=(4, 8), pady=10)
        self._draw_rail_btn()
        if callable(on_toggle_rail):
            self.rail_btn.bind("<Button-1>", lambda _e: on_toggle_rail())

        titles = tk.Frame(self, bg=self._bg)
        titles.grid(row=0, column=1, sticky="w")
        self.title_var = tk.StringVar(value="")
        self.sub_var = tk.StringVar(value="")
        tk.Label(titles, textvariable=self.title_var, bg=self._bg,
                 fg=theme.c("ink"), font=theme.font("subtitle", "bold"),
                 anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(titles, textvariable=self.sub_var, bg=self._bg,
                 fg=theme.c("ink_3"), font=theme.font("micro"),
                 anchor="w").grid(row=1, column=0, sticky="w")

        self.chips = tk.Frame(self, bg=self._bg)
        self.chips.grid(row=0, column=2, sticky="e", padx=8)
        self._chip_cache = {}

        self.search = SearchField(self, theme, placeholder="Search or jump to…  Ctrl+K",
                                  command=on_search, ground=self._bg, width=250)
        self.search.grid(row=0, column=3, padx=(6, 8))

        self.actions = tk.Frame(self, bg=self._bg)
        self.actions.grid(row=0, column=4, sticky="e", padx=(0, 6))

        self.theme_toggle = ToggleSwitch(self, theme, value=dark,
                                         command=on_toggle_theme, ground=self._bg)
        self.theme_toggle.grid(row=0, column=5, padx=(4, 10))

    def _draw_rail_btn(self):
        cv = self.rail_btn
        cv.delete("all")
        t = self.theme
        pr.round_rect(cv, 2, 2, 32, 32, radius=t.r("sm"), fill=t.c("surface"),
                      outline=t.c("stroke"), width=1)
        for i, y in enumerate((12, 17, 22)):
            cv.create_line(11, y, 23 if i != 1 else 19, y, fill=t.c("ink_2"),
                           width=2, capstyle="round")

    def set_page(self, title, subtitle=""):
        self.title_var.set(title)
        self.sub_var.set(subtitle)

    def set_chip(self, key, text, tone="sky"):
        """Create-or-update a live market chip (FX, CBOT, data quality)."""
        chip = self._chip_cache.get(key)
        if chip is None:
            chip = Chip(self.chips, self.theme, text, tone=tone, ground=self._bg)
            chip.pack(side="left", padx=4)
            self._chip_cache[key] = chip
        else:
            chip.set(text, tone)
        return chip

    def remove_chip(self, key):
        chip = self._chip_cache.pop(key, None)
        if chip is not None:
            chip.destroy()


class CommandPalette(tk.Toplevel):
    """Ctrl+K jump list over every destination and registered action."""

    def __init__(self, master, theme: Theme, entries, on_choose):
        super().__init__(master)
        self.theme = theme
        self._entries = list(entries)
        self._filtered = list(entries)
        self._on_choose = on_choose
        self._index = 0

        self.overrideredirect(True)
        self.configure(bg=theme.c("stroke"))
        self.transient(master)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        width, height = 520, 360
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 90
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        wrap = tk.Frame(self, bg=theme.c("surface"))
        wrap.pack(fill="both", expand=True, padx=1, pady=1)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)

        self.search = SearchField(wrap, theme, placeholder="Jump to a screen…",
                                  ground=theme.c("surface"), width=width - 24,
                                  on_change=self._on_query)
        self.search.grid(row=0, column=0, sticky="ew", padx=12, pady=12)

        self.list_frame = tk.Frame(wrap, bg=theme.c("surface"))
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.list_frame.columnconfigure(0, weight=1)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", self._choose)
        self.bind("<Down>", lambda _e: self._move(1))
        self.bind("<Up>", lambda _e: self._move(-1))
        for seq in ("<Escape>", "<Return>", "<Down>", "<Up>"):
            self.search.entry.bind(seq, getattr(self, "_key_" + seq.strip("<>").lower()))
        self._render()
        # The palette can be dismissed before this fires, and Tk complains
        # about the orphaned callback, so cancel it on destroy.
        self._focus_job = self.after(30, self._focus_search_if_alive)
        self.bind("<Destroy>", self._cancel_focus_job, add="+")

    def _cancel_focus_job(self, _event=None):
        job, self._focus_job = getattr(self, "_focus_job", None), None
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _focus_search_if_alive(self):
        self._focus_job = None
        try:
            if self.winfo_exists():
                self.search.focus_input()
        except Exception:
            pass

    # -- keys ------------------------------------------------------------
    def _key_escape(self, _e=None):
        self.destroy()
        return "break"

    def _key_return(self, _e=None):
        self._choose()
        return "break"

    def _key_down(self, _e=None):
        self._move(1)
        return "break"

    def _key_up(self, _e=None):
        self._move(-1)
        return "break"

    def _move(self, delta):
        if not self._filtered:
            return
        self._index = (self._index + delta) % len(self._filtered)
        self._render()

    def _choose(self, _e=None):
        if not self._filtered:
            return
        entry = self._filtered[self._index]
        self.destroy()
        if callable(self._on_choose):
            self._on_choose(entry)

    def _on_query(self, text):
        q = (text or "").strip().lower()
        if not q:
            self._filtered = list(self._entries)
        else:
            self._filtered = [e for e in self._entries
                              if q in e["label"].lower()
                              or q in (e.get("hint") or "").lower()]
        self._index = 0
        self._render()

    def _render(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        t = self.theme
        if not self._filtered:
            tk.Label(self.list_frame, text="No matching screen", bg=t.c("surface"),
                     fg=t.c("ink_3"), font=t.font("body")).grid(row=0, column=0,
                                                                pady=24)
            return
        for i, entry in enumerate(self._filtered[:9]):
            active = i == self._index
            bg = t.c("brand_soft") if active else t.c("surface")
            row = tk.Frame(self.list_frame, bg=bg, cursor="hand2")
            row.grid(row=i, column=0, sticky="ew", pady=1, padx=4)
            row.columnconfigure(1, weight=1)
            tk.Label(row, text=entry.get("glyph", "•"), bg=bg,
                     fg=t.c("brand_ink") if active else t.c("ink_3"),
                     font=t.font("body_lg")).grid(row=0, column=0, padx=(10, 8), pady=7)
            tk.Label(row, text=entry["label"], bg=bg,
                     fg=t.c("brand_ink") if active else t.c("ink"),
                     font=t.font("body", "bold"), anchor="w").grid(
                         row=0, column=1, sticky="w")
            if entry.get("hint"):
                tk.Label(row, text=entry["hint"], bg=bg, fg=t.c("ink_3"),
                         font=t.font("micro"), anchor="e").grid(
                             row=0, column=2, sticky="e", padx=10)
            for widget in (row,) + tuple(row.winfo_children()):
                widget.bind("<Button-1>",
                            lambda _e, idx=i: (setattr(self, "_index", idx),
                                               self._choose()))


class ModernShell(tk.Frame):
    """Rail + top bar + content host. Hosts the app's existing container."""

    def __init__(self, master, theme: Theme, destinations, on_navigate=None,
                 brand="Prometheus", brand_sub="Procurement",
                 on_toggle_theme=None, on_search=None, **kw):
        self.theme = theme
        super().__init__(master, bg=theme.c("bg"), **kw)
        self._destinations = list(destinations)
        self._on_navigate = on_navigate
        self._collapsed = False

        # Only the content row grows: the top bar, the hosted legacy
        # toolbar and the status bar each keep their requested height.
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        self.sidebar = Sidebar(self, theme, self._destinations,
                               on_navigate=self._navigate, brand=brand,
                               brand_sub=brand_sub)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="ns")
        self.sidebar.configure(width=theme.layout["rail_width"])
        self.sidebar.grid_propagate(False)

        tk.Frame(self, bg=theme.c("stroke"), width=1).grid(
            row=0, column=0, rowspan=3, sticky="nse")

        self.topbar = TopBar(self, theme, on_search=on_search,
                             on_toggle_rail=self.toggle_rail,
                             on_toggle_theme=on_toggle_theme,
                             dark=theme.is_dark)
        self.topbar.grid(row=0, column=1, sticky="ew", padx=(10, 6))

        #: Legacy toolbars are re-parented here so they keep working.
        self.toolbar_host = tk.Frame(self, bg=theme.c("bg"))
        self.toolbar_host.grid(row=1, column=1, sticky="ew", padx=10)
        self.toolbar_host.grid_remove()

        self.body = tk.Frame(self, bg=theme.c("bg"))
        self.body.grid(row=2, column=1, sticky="nsew", padx=10, pady=(4, 0))

        self.statusbar_host = tk.Frame(self, bg=theme.c("bg"))
        self.statusbar_host.grid(row=3, column=0, columnspan=2, sticky="ew")

    # -- navigation ------------------------------------------------------
    def _navigate(self, key):
        if callable(self._on_navigate):
            self._on_navigate(key)

    def select(self, key):
        self.sidebar.set_active(key)
        dest = next((d for d in self._destinations if d["key"] == key), None)
        if dest:
            self.topbar.set_page(dest.get("title") or dest["label"],
                                 dest.get("subtitle", ""))

    def show_toolbar(self, visible=True):
        if visible:
            self.toolbar_host.grid()
        else:
            self.toolbar_host.grid_remove()

    def toggle_rail(self):
        self._collapsed = not self._collapsed
        width = (self.theme.layout["rail_width_collapsed"] if self._collapsed
                 else self.theme.layout["rail_width"])
        self.sidebar.configure(width=width)
        self.sidebar.set_collapsed(self._collapsed)

    def open_palette(self, extra_entries=()):
        entries = [{"key": d["key"], "label": d["label"],
                    "glyph": d.get("glyph", "•"),
                    "hint": d.get("section", "")} for d in self._destinations]
        entries.extend(extra_entries)

        def _choose(entry):
            if entry.get("command"):
                entry["command"]()
            else:
                self.sidebar.set_active(entry["key"])
                self._navigate(entry["key"])

        return CommandPalette(self.winfo_toplevel(), self.theme, entries, _choose)
