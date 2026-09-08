"""Composable widgets for the Prometheus modern interface.

Every widget here is plain ``tkinter`` (no ttk theming quirks, no third
party dependency) and takes a :class:`~prometheus_ui.theme.Theme` so a
palette switch redraws the whole app consistently.

The recurring pattern is a ``tk.Frame`` with a ``place``-managed background
canvas behind a ``grid``-managed ``body`` frame: ``place`` contributes no
requested size, so the card still sizes itself to its content while the
canvas paints rounded corners and a soft shadow underneath.
"""

from __future__ import annotations

import tkinter as tk

from tkinter import font as tkfont

from . import primitives as pr
from .theme import Theme, mix

__all__ = [
    "line_height", "bind_wraplength", "Surface", "Card", "SectionTitle", "PillButton", "IconBubble", "Chip",
    "StatTile", "SegmentedControl", "SearchField", "ToggleSwitch",
    "MetricRow", "ListRow", "Divider", "HeroBanner", "EmptyState",
    "ProgressTrack", "parent_bg",
]


def line_height(widget, font) -> int:
    """Rendered height of one line in ``font`` — point sizes are not pixels,
    so vertical rhythm on a canvas has to come from real font metrics."""
    try:
        return int(tkfont.Font(root=widget, font=font).metrics("linespace"))
    except Exception:
        size = font[1] if isinstance(font, (tuple, list)) and len(font) > 1 else 10
        return int(size * 1.45)


def bind_wraplength(label, container=None, pad=8):
    """Keep a Label's wraplength equal to its container's live width.

    Fixed wraplengths either waste horizontal space or push a paragraph into
    more lines than the panel has room for; binding it to the actual width
    keeps text panels honest at every window size.
    """
    target = container if container is not None else label.master

    def _sync(event=None):
        # The container outlives labels that are rebuilt on refresh, and a
        # "+"-added binding cannot be removed individually — so a stale
        # callback must simply do nothing rather than raise.
        try:
            if not label.winfo_exists():
                return
        except Exception:
            return
        width = (event.width if event is not None else target.winfo_width()) - pad * 2
        if width > 40:
            label.configure(wraplength=width)

    target.bind("<Configure>", _sync, add="+")
    _sync()
    return label


def parent_bg(widget, fallback="#ffffff") -> str:
    """Best-effort background of a widget's parent, for seamless canvases."""
    try:
        return widget.cget("bg")
    except Exception:
        try:
            return widget.cget("background")
        except Exception:
            return fallback


class Surface(tk.Frame):
    """A plain themed frame — the base every screen section sits on."""

    def __init__(self, master, theme: Theme, bg="bg", **kw):
        self.theme = theme
        super().__init__(master, bg=theme.c(bg), **kw)


class Card(tk.Frame):
    """Rounded, softly shadowed container. Add children to ``card.body``."""

    def __init__(self, master, theme: Theme, radius="lg", fill="surface",
                 pad=16, shadow=True, border=False, ground=None,
                 accent=None, accent_width=4, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("bg"))
        super().__init__(master, bg=self._ground, **kw)
        self._radius = theme.r(radius) if isinstance(radius, str) else int(radius)
        self._fill = theme.c(fill)
        self._shadow = bool(shadow)
        self._border = bool(border)
        self._accent = theme.c(accent) if accent else None
        self._accent_width = accent_width
        self._margin = 6 if shadow else 0

        self._bgcv = tk.Canvas(self, bg=self._ground, highlightthickness=0, bd=0)
        self._bgcv.place(x=0, y=0, relwidth=1, relheight=1)

        self.body = tk.Frame(self, bg=self._fill)
        self.body.grid(row=0, column=0, sticky="nsew",
                       padx=self._margin + pad, pady=self._margin + pad)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # Canvas.lower is tag_lower (canvas items), so raise the body over
        # the background canvas instead of lowering the canvas.
        self.body.lift(self._bgcv)
        self.bind("<Configure>", self._redraw)

    @property
    def fill(self) -> str:
        return self._fill

    def _redraw(self, _event=None):
        cv = self._bgcv
        cv.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        m = self._margin
        x1, y1, x2, y2 = m, m, w - m, h - m
        if self._shadow:
            pr.soft_shadow(cv, x1, y1, x2, y2, radius=self._radius,
                           ground=self._ground, color=self.theme.c("shadow"),
                           strength=0.30 if not self.theme.is_dark else 0.62,
                           layers=5, spread=m, offset=3)
        pr.round_rect(cv, x1, y1, x2, y2, radius=self._radius, fill=self._fill,
                      outline=self.theme.c("stroke") if self._border else "",
                      width=1)
        if self._accent:
            # A colour bar hugging the card's left edge, clipped to the radius.
            cv.create_rectangle(x1, y1 + self._radius, x1 + self._accent_width,
                                y2 - self._radius, fill=self._accent, width=0)
            pr.round_rect(cv, x1, y1, x1 + self._radius * 2, y1 + self._radius * 2,
                          radius=self._radius, fill="", outline="")

    def set_fill(self, fill: str):
        self._fill = self.theme.c(fill)
        self.body.configure(bg=self._fill)
        self._redraw()


class SectionTitle(tk.Frame):
    """Screen-section heading with optional subtitle and right-hand slot."""

    def __init__(self, master, theme: Theme, title, subtitle="", ground=None, **kw):
        self.theme = theme
        bg = ground or parent_bg(master, theme.c("bg"))
        super().__init__(master, bg=bg, **kw)
        self.columnconfigure(0, weight=1)
        self.title_var = tk.StringVar(value=title)
        self.subtitle_var = tk.StringVar(value=subtitle)
        tk.Label(self, textvariable=self.title_var, bg=bg, fg=theme.c("ink"),
                 font=theme.font("title", "bold"), anchor="w").grid(
                     row=0, column=0, sticky="w")
        if subtitle:
            tk.Label(self, textvariable=self.subtitle_var, bg=bg,
                     fg=theme.c("ink_2"), font=theme.font("body"),
                     anchor="w").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.actions = tk.Frame(self, bg=bg)
        self.actions.grid(row=0, column=1, rowspan=2, sticky="e")


class PillButton(tk.Canvas):
    """Fully rounded button with hover/press states, drawn on a canvas."""

    #: variant -> (fill token or None, ink token or None, border token or None)
    #: an ink of ``None`` means "pick whichever of dark/white reads on the
    #: fill", which is what keeps bright dark-palette fills legible.
    VARIANTS = {
        "primary": ("brand", None, None),
        "soft":    ("brand_soft", "brand_ink", None),
        "ghost":   (None, "ink_2", "stroke"),
        "quiet":   (None, "ink_2", None),
        "mint":    ("mint", None, None),
        "rose":    ("rose", None, None),
        "amber":   ("amber", None, None),
    }

    def __init__(self, master, theme: Theme, text, command=None, icon="",
                 variant="primary", size="body", pad_x=16, pad_y=9,
                 ground=None, min_width=0, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        self._text = text
        self._icon = icon
        self._command = command
        self._variant = variant if variant in self.VARIANTS else "primary"
        self._size = size
        self._pad_x, self._pad_y = pad_x, pad_y
        self._state = "normal"
        self._enabled = True

        font = theme.font(size, "bold")
        label = f"{icon}  {text}".strip() if icon else text
        probe = tk.Label(master, text=label, font=font)
        w = probe.winfo_reqwidth() + pad_x * 2
        h = probe.winfo_reqheight() + pad_y * 2
        probe.destroy()
        super().__init__(master, width=max(w, min_width), height=h,
                         bg=self._ground, highlightthickness=0, bd=0,
                         cursor="hand2", **kw)
        self._label = label
        self._font = font
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", lambda _e: self._set_state("hover"))
        self.bind("<Leave>", lambda _e: self._set_state("normal"))
        self.bind("<ButtonPress-1>", lambda _e: self._set_state("press"))
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    # -- state ----------------------------------------------------------
    def _set_state(self, state):
        if not self._enabled:
            return
        self._state = state
        self._draw()

    def _on_release(self, event):
        self._set_state("hover")
        if not self._enabled:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if inside and callable(self._command):
            self._command()

    def configure_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._state = "normal"
        self._draw()

    def set_text(self, text, icon=None):
        self._text = text
        if icon is not None:
            self._icon = icon
        self._label = f"{self._icon}  {self._text}".strip() if self._icon else self._text
        self._draw()

    # -- paint ----------------------------------------------------------
    def _colors(self):
        t = self.theme
        from .theme import readable_ink
        fill_tok, ink_tok, border_tok = self.VARIANTS[self._variant]
        fill = t.c(fill_tok) if fill_tok else self._ground
        ink = t.c(ink_tok) if ink_tok else readable_ink(fill)
        border = t.c(border_tok) if border_tok else ""
        if not self._enabled:
            return mix(self._ground, t.c("stroke"), 0.6), t.c("ink_3"), border
        if self._state == "hover":
            fill = mix(fill, "#000000" if not t.is_dark else "#ffffff", 0.08)
            if border:
                border = t.c("brand")
                ink = t.c("brand_ink")
        elif self._state == "press":
            fill = mix(fill, "#000000" if not t.is_dark else "#ffffff", 0.16)
        return fill, ink, border

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width() or int(self["width"]), self.winfo_height() or int(self["height"])
        if w <= 2 or h <= 2:
            return
        fill, ink, border = self._colors()
        pr.pill(self, 1, 1, w - 1, h - 1, fill=fill, outline=border,
                width=1 if border else 0)
        self.create_text(w / 2, h / 2 + (1 if self._state == "press" else 0),
                         text=self._label, fill=ink, font=self._font)


class IconBubble(tk.Canvas):
    """Rounded tinted square holding a glyph — the card iconography."""

    def __init__(self, master, theme: Theme, glyph, tone="brand", size=38,
                 ground=None, radius=None, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        super().__init__(master, width=size, height=size, bg=self._ground,
                         highlightthickness=0, bd=0, **kw)
        self._glyph, self._tone, self._size = glyph, tone, size
        self._radius = radius if radius is not None else max(10, size // 3)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def set_tone(self, tone):
        self._tone = tone
        self._draw()

    def set_glyph(self, glyph):
        self._glyph = glyph
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        _strong, soft = self.theme.tone(self._tone)
        pr.round_rect(self, 0, 0, s, s, radius=self._radius, fill=soft)
        self.create_text(s / 2, s / 2 + 1, text=self._glyph,
                         fill=self.theme.tone_ink(self._tone),
                         font=(self.theme.family, max(10, int(s * 0.44))))


class Chip(tk.Canvas):
    """Small pill for statuses, deltas and filters."""

    def __init__(self, master, theme: Theme, text="", tone="sky", ground=None,
                 size="caption", solid=False, pad_x=10, pad_y=5, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        self._tone, self._solid = tone, solid
        self._size, self._pad_x, self._pad_y = size, pad_x, pad_y
        self._font = theme.font(size, "bold")
        super().__init__(master, bg=self._ground, highlightthickness=0, bd=0,
                         height=theme.size(size) + pad_y * 2 + 4, **kw)
        self._text = text
        self._resize()
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, text, tone=None):
        self._text = text
        if tone:
            self._tone = tone
        self._resize()
        self._draw()

    def _resize(self):
        probe = tk.Label(self.master, text=self._text or " ", font=self._font)
        w = probe.winfo_reqwidth() + self._pad_x * 2
        h = probe.winfo_reqheight() + self._pad_y * 2
        probe.destroy()
        self.configure(width=w, height=h)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        strong, soft = self.theme.tone(self._tone)
        fill = strong if self._solid else soft
        ink = (self.theme.on_tone(self._tone) if self._solid
               else self.theme.tone_ink(self._tone))
        pr.pill(self, 0, 0, w, h, fill=fill)
        self.create_text(w / 2, h / 2, text=self._text, fill=ink, font=self._font)


class ProgressTrack(tk.Canvas):
    """Rounded progress/allocation bar; supports stacked segments."""

    def __init__(self, master, theme: Theme, height=10, ground=None,
                 track="surface_3", **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        self._track = track
        self._segments = []
        super().__init__(master, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", lambda _e: self._draw())

    def set_segments(self, segments):
        """``segments`` is a list of ``(fraction, tone)`` in draw order."""
        self._segments = [(max(0.0, float(f)), t) for f, t in segments]
        self._draw()

    def set_value(self, fraction, tone="brand"):
        self.set_segments([(fraction, tone)])

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        pr.pill(self, 0, 0, w, h, fill=self.theme.c(self._track))
        total = sum(f for f, _ in self._segments) or 1.0
        scale = min(1.0, total) / total if total > 1.0 else 1.0
        x = 0.0
        for frac, tone in self._segments:
            seg_w = w * frac * scale
            if seg_w < 1:
                continue
            strong, _ = self.theme.tone(tone)
            pr.pill(self, x, 0, min(w, x + max(seg_w, h)), h, fill=strong)
            x += seg_w


class StatTile(Card):
    """Headline metric: icon bubble, caption, value, delta chip, sparkline."""

    def __init__(self, master, theme: Theme, caption="", value="—", glyph="",
                 tone="brand", hint="", spark=None, on_click=None, **kw):
        super().__init__(master, theme, radius="lg", pad=16, **kw)
        bg = self.fill
        b = self.body
        b.columnconfigure(0, weight=1)

        head = tk.Frame(b, bg=bg)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        self.bubble = IconBubble(head, theme, glyph or "◆", tone=tone, size=36, ground=bg)
        self.bubble.grid(row=0, column=0, sticky="w")
        self.caption_var = tk.StringVar(value=caption)
        tk.Label(head, textvariable=self.caption_var, bg=bg, fg=theme.c("ink_2"),
                 font=theme.font("caption", "bold"), anchor="w").grid(
                     row=0, column=1, sticky="w", padx=(10, 0))
        self.chip = Chip(head, theme, "", tone="sky", ground=bg)
        self.chip.grid(row=0, column=2, sticky="e")
        self.chip.grid_remove()

        self.value_var = tk.StringVar(value=value)
        tk.Label(b, textvariable=self.value_var, bg=bg, fg=theme.c("ink"),
                 font=theme.font("metric", "bold"), anchor="w").grid(
                     row=1, column=0, sticky="w", pady=(12, 0))

        self.hint_var = tk.StringVar(value=hint)
        tk.Label(b, textvariable=self.hint_var, bg=bg, fg=theme.c("ink_3"),
                 font=theme.font("caption"), anchor="w").grid(
                     row=2, column=0, sticky="w", pady=(3, 0))

        self.spark = None
        if spark is not False:
            from .charts import Sparkline  # local import: charts imports widgets
            self.spark = Sparkline(b, theme, tone=tone, ground=bg, height=34)
            self.spark.grid(row=3, column=0, sticky="ew", pady=(10, 0))
            if spark:
                self.spark.set_values(spark)

        if callable(on_click):
            self._bind_click(self, on_click)

    def _bind_click(self, widget, command):
        widget.configure(cursor="hand2")
        widget.bind("<Button-1>", lambda _e: command())
        for child in widget.winfo_children():
            self._bind_click(child, command)

    def set(self, value=None, caption=None, hint=None, delta=None,
            delta_tone=None, glyph=None, tone=None, spark=None):
        if value is not None:
            self.value_var.set(value)
        if caption is not None:
            self.caption_var.set(caption)
        if hint is not None:
            self.hint_var.set(hint)
        if glyph is not None:
            self.bubble.set_glyph(glyph)
        if tone is not None:
            self.bubble.set_tone(tone)
        if delta is None or delta == "":
            self.chip.grid_remove()
        else:
            self.chip.set(delta, delta_tone or "sky")
            self.chip.grid()
        if spark is not None and self.spark is not None:
            values = [v for v in spark if v is not None]
            self.spark.set_values(values, tone=delta_tone or tone)
            if len(values) < 2:
                self.spark.grid_remove()
            else:
                self.spark.grid()


class SegmentedControl(tk.Canvas):
    """iOS-style pill switch — the range/commodity pickers."""

    def __init__(self, master, theme: Theme, options, command=None, value=None,
                 ground=None, size="caption", pad_x=14, height=32, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        self._items = list(options)
        self._command = command
        self._value = value if value in self._items else (self._items[0] if self._items else None)
        self._font = theme.font(size, "bold")
        self._pad_x = pad_x
        probe = tk.Label(master, text="".join(self._items), font=self._font)
        est = probe.winfo_reqwidth() + pad_x * 2 * max(1, len(self._items)) + 8
        probe.destroy()
        super().__init__(master, width=est, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._hover = None
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self._draw()

    @property
    def value(self):
        return self._value

    def set_value(self, value, notify=False):
        if value in self._items and value != self._value:
            self._value = value
            self._draw()
            if notify and callable(self._command):
                self._command(value)

    def _slots(self):
        w, h = self.winfo_width(), self.winfo_height()
        n = max(1, len(self._items))
        step = (w - 8) / n
        return [(4 + i * step, 4, 4 + (i + 1) * step, h - 4) for i in range(n)]

    def _index_at(self, x):
        for i, (x1, _y1, x2, _y2) in enumerate(self._slots()):
            if x1 <= x <= x2:
                return i
        return None

    def _on_click(self, event):
        idx = self._index_at(event.x)
        if idx is None:
            return
        self._value = self._items[idx]
        self._draw()
        if callable(self._command):
            self._command(self._value)

    def _on_motion(self, event):
        self._set_hover(self._index_at(event.x))

    def _set_hover(self, idx):
        if idx != self._hover:
            self._hover = idx
            self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        t = self.theme
        pr.pill(self, 0, 0, w, h, fill=t.c("surface_3"))
        for i, (x1, y1, x2, y2) in enumerate(self._slots()):
            option = self._items[i]
            active = option == self._value
            if active:
                pr.pill(self, x1, y1, x2, y2, fill=t.c("surface"))
                ink = t.c("brand_ink")
            elif self._hover == i:
                ink = t.c("ink")
            else:
                ink = t.c("ink_2")
            self.create_text((x1 + x2) / 2, h / 2, text=option, fill=ink,
                             font=self._font)


class ToggleSwitch(tk.Canvas):
    """Rounded on/off switch used for the theme and density toggles."""

    def __init__(self, master, theme: Theme, value=False, command=None,
                 ground=None, width=44, height=24, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        self._value = bool(value)
        self._command = command
        super().__init__(master, width=width, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.bind("<Button-1>", self._toggle)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    @property
    def value(self) -> bool:
        return self._value

    def set_value(self, value, notify=False):
        self._value = bool(value)
        self._draw()
        if notify and callable(self._command):
            self._command(self._value)

    def _toggle(self, _event=None):
        self.set_value(not self._value, notify=True)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        t = self.theme
        pr.pill(self, 0, 0, w, h,
                fill=t.c("brand") if self._value else t.c("stroke_strong"))
        r = h / 2 - 3
        cx = (w - h / 2) if self._value else h / 2
        pr.dot(self, cx, h / 2, r, fill="#ffffff")


class SearchField(tk.Frame):
    """Rounded search input with a leading glyph and a real placeholder.

    The entry sits on top of the rounded canvas, so the placeholder has to
    live inside the entry itself rather than being painted underneath it.
    """

    def __init__(self, master, theme: Theme, placeholder="Search",
                 command=None, width=260, ground=None, glyph="⌕",
                 on_change=None, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("surface"))
        super().__init__(master, bg=self._ground, **kw)
        self._placeholder = placeholder
        self._command = command
        self._on_change = on_change
        self._showing_placeholder = False
        height = theme.size("body") + 22

        self._cv = tk.Canvas(self, width=width, height=height, bg=self._ground,
                             highlightthickness=0, bd=0)
        self._cv.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)

        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, bd=0, relief="flat",
                              bg=theme.c("surface_3"), fg=theme.c("ink"),
                              insertbackground=theme.c("ink"),
                              font=theme.font("body"), highlightthickness=0)
        self.entry.place(x=34, y=height / 2, height=height - 12, relwidth=1,
                         width=-46, anchor="w")
        self._glyph = glyph
        self._focused = False
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", lambda _e: self.clear())
        self.var.trace_add("write", self._on_write)
        self.bind("<Configure>", lambda _e: self._draw())
        self._show_placeholder()
        self._draw()

    # -- value ----------------------------------------------------------
    def get(self) -> str:
        return "" if self._showing_placeholder else self.var.get()

    def clear(self):
        self.var.set("")
        if not self._focused:
            self._show_placeholder()

    def focus_input(self):
        self.entry.focus_set()

    def _show_placeholder(self):
        if self._placeholder and not self.var.get():
            self._showing_placeholder = True
            self.entry.configure(fg=self.theme.c("ink_3"))
            self.var.set(self._placeholder)

    def _hide_placeholder(self):
        if self._showing_placeholder:
            self._showing_placeholder = False
            self.var.set("")
        self.entry.configure(fg=self.theme.c("ink"))

    def _on_focus_in(self, _event=None):
        self._focused = True
        self._hide_placeholder()
        self._draw()

    def _on_focus_out(self, _event=None):
        self._focused = False
        self._show_placeholder()
        self._draw()

    def _on_write(self, *_args):
        if not self._showing_placeholder and callable(self._on_change):
            self._on_change(self.var.get())

    def _submit(self, _event=None):
        if callable(self._command):
            self._command(self.get())

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        # Before the first layout pass winfo_width() is 1; fall back to the
        # requested width so the field never collapses to a sliver.
        w = self.winfo_width()
        if w <= 10:
            w = int(cv["width"])
        else:
            cv.configure(width=w)
        h = int(cv["height"])
        t = self.theme
        pr.pill(cv, 1, 1, w - 1, h - 1, fill=t.c("surface_3"),
                outline=t.c("brand") if self._focused else t.c("stroke"),
                width=1)
        cv.create_text(18, h / 2, text=self._glyph, fill=t.c("ink_3"),
                       font=(t.family, t.size("subtitle")))


class Divider(tk.Frame):
    def __init__(self, master, theme: Theme, ground=None, pad=0, **kw):
        bg = ground or parent_bg(master, theme.c("surface"))
        super().__init__(master, bg=bg, **kw)
        tk.Frame(self, bg=theme.c("stroke"), height=1).pack(
            fill="x", pady=pad)


class MetricRow(tk.Frame):
    """Label/value pair with an optional tone dot — used inside panels."""

    def __init__(self, master, theme: Theme, label="", value="—", tone=None,
                 ground=None, label_width=0, **kw):
        self.theme = theme
        bg = ground or parent_bg(master, theme.c("surface"))
        super().__init__(master, bg=bg, **kw)
        self.columnconfigure(1, weight=1)
        col = 0
        self._dot = None
        if tone:
            self._dot = tk.Canvas(self, width=10, height=10, bg=bg,
                                  highlightthickness=0, bd=0)
            pr.dot(self._dot, 5, 5, 4, fill=theme.tone(tone)[0])
            self._dot.grid(row=0, column=0, padx=(0, 8))
            col = 1
        self.label_var = tk.StringVar(value=label)
        tk.Label(self, textvariable=self.label_var, bg=bg, fg=theme.c("ink_2"),
                 font=theme.font("body"), anchor="w",
                 width=label_width or 0).grid(row=0, column=col, sticky="w")
        self.value_var = tk.StringVar(value=value)
        tk.Label(self, textvariable=self.value_var, bg=bg, fg=theme.c("ink"),
                 font=theme.font("body", "bold"), anchor="e").grid(
                     row=0, column=col + 1, sticky="e")

    def set(self, value=None, label=None, tone=None):
        if value is not None:
            self.value_var.set(value)
        if label is not None:
            self.label_var.set(label)
        if tone and self._dot is not None:
            self._dot.delete("all")
            pr.dot(self._dot, 5, 5, 4, fill=self.theme.tone(tone)[0])


class ListRow(tk.Frame):
    """Hoverable record row: glyph bubble, title/subtitle, value, status chip."""

    def __init__(self, master, theme: Theme, ground=None, on_click=None,
                 glyph="▪", tone="brand", **kw):
        self.theme = theme
        self._bg = ground or parent_bg(master, theme.c("surface"))
        self._hover_bg = mix(self._bg, theme.c("brand"), 0.06)
        super().__init__(master, bg=self._bg, **kw)
        self.columnconfigure(1, weight=1)
        self._on_click = on_click

        self.bubble = IconBubble(self, theme, glyph, tone=tone, size=32,
                                 ground=self._bg)
        self.bubble.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=8)

        self.title_var = tk.StringVar(value="—")
        self.sub_var = tk.StringVar(value="")
        self._title = tk.Label(self, textvariable=self.title_var, bg=self._bg,
                               fg=theme.c("ink"), font=theme.font("body", "bold"),
                               anchor="w")
        self._title.grid(row=0, column=1, sticky="w", pady=(8, 0))
        self._sub = tk.Label(self, textvariable=self.sub_var, bg=self._bg,
                             fg=theme.c("ink_3"), font=theme.font("caption"),
                             anchor="w")
        self._sub.grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.value_var = tk.StringVar(value="")
        self._value = tk.Label(self, textvariable=self.value_var, bg=self._bg,
                               fg=theme.c("ink"), font=theme.font("body", "bold"),
                               anchor="e")
        self._value.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 8))

        self.chip = Chip(self, theme, "", tone="sky", ground=self._bg)
        self.chip.grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, 10))
        self.chip.grid_remove()

        for widget in (self, self._title, self._sub, self._value, self.bubble):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            if callable(on_click):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e: on_click())

    def _paint(self, bg):
        self.configure(bg=bg)
        for widget in (self._title, self._sub, self._value):
            widget.configure(bg=bg)

    def _enter(self, _e=None):
        self._paint(self._hover_bg)

    def _leave(self, _e=None):
        self._paint(self._bg)

    def set(self, title=None, subtitle=None, value=None, chip=None,
            chip_tone="sky", glyph=None, tone=None):
        if title is not None:
            self.title_var.set(title)
        if subtitle is not None:
            self.sub_var.set(subtitle)
        if value is not None:
            self.value_var.set(value)
        if glyph is not None:
            self.bubble.set_glyph(glyph)
        if tone is not None:
            self.bubble.set_tone(tone)
        if chip is None or chip == "":
            self.chip.grid_remove()
        else:
            self.chip.set(chip, chip_tone)
            self.chip.grid()


class EmptyState(tk.Frame):
    """Friendly placeholder shown instead of a blank panel."""

    def __init__(self, master, theme: Theme, glyph="◌", title="Nothing yet",
                 body="", ground=None, **kw):
        bg = ground or parent_bg(master, theme.c("surface"))
        super().__init__(master, bg=bg, **kw)
        self.columnconfigure(0, weight=1)
        IconBubble(self, theme, glyph, tone="sky", size=44, ground=bg).grid(
            row=0, column=0, pady=(18, 10))
        tk.Label(self, text=title, bg=bg, fg=theme.c("ink"),
                 font=theme.font("body_lg", "bold")).grid(row=1, column=0)
        if body:
            tk.Label(self, text=body, bg=bg, fg=theme.c("ink_3"),
                     font=theme.font("caption"), wraplength=260,
                     justify="center").grid(row=2, column=0, pady=(4, 18))


class HeroBanner(tk.Canvas):
    """Full-width gradient hero: eyebrow, headline, live metric, actions.

    Everything is painted on one canvas — text, decorative blobs and the
    action pills — because a gradient ground has no single flat colour a
    child widget could match.
    """

    def __init__(self, master, theme: Theme, height=176, ground=None,
                 radius="2xl", tone=None, **kw):
        self.theme = theme
        self._ground = ground or parent_bg(master, theme.c("bg"))
        self._radius = theme.r(radius) if isinstance(radius, str) else int(radius)
        self._tone = tone
        super().__init__(master, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, **kw)
        self.eyebrow = ""
        self.headline = ""
        self.support = ""
        self.metric_label = ""
        self.metric_value = ""
        self.metric_delta = ""
        self.metric_delta_tone = "mint"
        self.footnote = ""
        self._actions = []
        self._action_hits = {}
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Leave>", lambda _e: self._set_hot(None))
        self._hot = None

    def set_content(self, eyebrow=None, headline=None, support=None,
                    metric_label=None, metric_value=None, metric_delta=None,
                    metric_delta_tone=None, footnote=None):
        for name, value in (("eyebrow", eyebrow), ("headline", headline),
                            ("support", support), ("metric_label", metric_label),
                            ("metric_value", metric_value),
                            ("metric_delta", metric_delta),
                            ("metric_delta_tone", metric_delta_tone),
                            ("footnote", footnote)):
            if value is not None:
                setattr(self, name, value)
        self.redraw()

    def set_actions(self, actions):
        """``actions`` is a list of ``(label, callback)`` pairs."""
        self._actions = list(actions or [])
        self.redraw()

    # -- interaction ----------------------------------------------------
    def _hit(self, x, y):
        for key, (x1, y1, x2, y2) in self._action_hits.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                return key
        return None

    def _set_hot(self, key):
        if key != self._hot:
            self._hot = key
            self.configure(cursor="hand2" if key is not None else "")
            self.redraw()

    def _on_motion(self, event):
        self._set_hot(self._hit(event.x, event.y))

    def _on_click(self, event):
        key = self._hit(event.x, event.y)
        if key is None:
            return
        _label, callback = self._actions[key]
        if callable(callback):
            callback()

    # -- paint ----------------------------------------------------------
    def redraw(self):
        self.delete("all")
        self._action_hits = {}
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        t = self.theme
        c1, c2 = t.gradient(self._tone) if self._tone else t.brand_gradient()
        pr.round_rect_gradient(self, 0, 0, w, h, c1, c2, radius=self._radius,
                               direction="horizontal")
        # Decorative blobs: pre-blended toward white so they read as light.
        pr.dot(self, w - 90, -30, 120, fill=mix(c2, "#ffffff", 0.12))
        pr.dot(self, w - 190, h + 40, 110, fill=mix(c2, "#ffffff", 0.07))
        pr.dot(self, 40, h + 60, 90, fill=mix(c1, "#ffffff", 0.05))

        ink = "#ffffff"
        ink_soft = mix(c2, "#ffffff", 0.72)
        pad = 26
        f_eyebrow = t.font("caption", "bold")
        f_headline = t.font("headline", "bold")
        f_support = t.font("body")
        f_metric = t.font("metric_lg", "bold")
        f_chip = t.font("caption", "bold")

        y = pad
        if self.eyebrow:
            self.create_text(pad, y, anchor="nw", text=self.eyebrow.upper(),
                             fill=ink_soft, font=f_eyebrow)
            y += line_height(self, f_eyebrow) + 8
        if self.headline:
            self.create_text(pad, y, anchor="nw", text=self.headline, fill=ink,
                             font=f_headline)
            y += line_height(self, f_headline) + 4
        if self.support:
            self.create_text(pad, y, anchor="nw", text=self.support,
                             fill=ink_soft, font=f_support,
                             width=max(200, w * 0.46))

        # Live metric block, right-aligned.
        if self.metric_value:
            mx = w - pad
            my = pad
            if self.metric_label:
                self.create_text(mx, my, anchor="ne", text=self.metric_label.upper(),
                                 fill=ink_soft, font=f_eyebrow)
                my += line_height(self, f_eyebrow) + 6
            self.create_text(mx, my, anchor="ne", text=self.metric_value,
                             fill=ink, font=f_metric)
            my += line_height(self, f_metric) + 8
            if self.metric_delta:
                from .theme import readable_ink
                strong, _soft = t.tone(self.metric_delta_tone)
                chip_fill = mix(c2, strong, 0.85)
                chip_h = line_height(self, f_chip) + 8
                tw = pr.chip_text_width(t.size("caption"), self.metric_delta, pad=12)
                pr.pill(self, mx - tw, my, mx, my + chip_h, fill=chip_fill)
                self.create_text(mx - tw / 2, my + chip_h / 2,
                                 text=self.metric_delta,
                                 fill=readable_ink(chip_fill),
                                 font=f_chip)

        # Action pills along the bottom-left.
        if self._actions:
            ay2 = h - pad + 4
            ay1 = ay2 - (line_height(self, t.font("body", "bold")) + 16)
            ax = pad
            for idx, (label, _cb) in enumerate(self._actions):
                tw = pr.chip_text_width(t.size("body"), label, pad=18)
                hot = self._hot == idx
                if idx == 0:
                    fill = "#ffffff" if not hot else mix("#ffffff", c1, 0.12)
                    fg = c1
                else:
                    fill = mix(c2, "#ffffff", 0.26 if hot else 0.16)
                    fg = "#ffffff"
                pr.pill(self, ax, ay1, ax + tw, ay2, fill=fill)
                self.create_text(ax + tw / 2, (ay1 + ay2) / 2, text=label,
                                 fill=fg, font=t.font("body", "bold"))
                self._action_hits[idx] = (ax, ay1, ax + tw, ay2)
                ax += tw + 10

        if self.footnote:
            self.create_text(w - pad, h - pad + 4, anchor="se",
                             text=self.footnote, fill=ink_soft,
                             font=t.font("caption"))
