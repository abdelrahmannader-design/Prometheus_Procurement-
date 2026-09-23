"""Charts for the modern interface, drawn directly on a Tk canvas.

Matplotlib stays an optional extra for the Basis Tracker's "Pro chart";
these are the always-available in-app visuals, so they are deliberately
dependency-free. Each chart is responsive (redraws on ``<Configure>``),
theme-aware and reports hover values through a crosshair readout rather
than a floating tooltip window, which keeps them usable inside scrollable
tabs.
"""

from __future__ import annotations

import math
import tkinter as tk

from . import primitives as pr
from .theme import Theme, mix

#: Peak tint of an area fill directly under the line, before it fades out.
FILL_ALPHA = 0.26

__all__ = ["Sparkline", "AreaChart", "BarChart", "DonutGauge", "RangeMeter",
           "nice_ticks", "compact_number"]


def nice_ticks(lo, hi, count=4):
    """Human-friendly axis ticks covering ``[lo, hi]``."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(1, count)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        step = mag * mult
        if step >= raw:
            break
    start = math.floor(lo / step) * step
    ticks = []
    value = start
    while value <= hi + step * 0.5:
        if value >= lo - step * 0.5:
            ticks.append(round(value, 10))
        value += step
    return ticks or [lo, hi]


def compact_number(value, decimals=1):
    """1_234_567 -> '1.2M'. Used for axis labels and tight KPI slots."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= limit:
            return f"{sign}{v / limit:.{decimals}f}{suffix}"
    if v >= 100:
        return f"{sign}{v:,.0f}"
    return f"{sign}{v:,.{decimals}f}"


class _ChartBase(tk.Canvas):
    def __init__(self, master, theme: Theme, ground=None, height=180, **kw):
        self.theme = theme
        self._ground = ground or self._parent_bg(master)
        super().__init__(master, height=height, bg=self._ground,
                         highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", lambda _e: self.redraw())

    @staticmethod
    def _parent_bg(master):
        try:
            return master.cget("bg")
        except Exception:
            return "#ffffff"

    def redraw(self):  # pragma: no cover - overridden
        pass


class Sparkline(_ChartBase):
    """Tiny trend line with a soft fill — lives inside stat tiles."""

    def __init__(self, master, theme: Theme, values=None, tone="brand",
                 ground=None, height=34, **kw):
        super().__init__(master, theme, ground=ground, height=height, **kw)
        self._values = list(values or [])
        self._tone = tone

    def set_values(self, values, tone=None):
        self._values = [v for v in (values or []) if v is not None]
        if tone:
            self._tone = tone
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 4 or h <= 4:
            return
        vals = self._values
        if len(vals) < 2:
            # A tile with no series should read as empty space, not as an
            # error; the tile's own hint line explains why there is no data.
            return
        strong, _soft = self.theme.tone(self._tone)
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        pad = 3
        step = (w - pad * 2) / (len(vals) - 1)
        pts = [(pad + i * step, h - pad - (v - lo) / span * (h - pad * 2))
               for i, v in enumerate(vals)]
        fill_pts = pr.smooth_path(pts, tension=0.3, samples=8)
        poly = list(fill_pts) + [w - pad, h, pad, h]
        self.create_polygon(poly, fill=mix(self._ground, strong, 0.16),
                            outline="", smooth=False)
        self.create_line(fill_pts, fill=strong, width=2, capstyle="round",
                         joinstyle="round", smooth=False)
        pr.dot(self, pts[-1][0], pts[-1][1], 3, fill=strong,
               outline=self._ground, width=2)


class AreaChart(_ChartBase):
    """Time-series area chart with grid, axis labels and hover crosshair."""

    def __init__(self, master, theme: Theme, ground=None, height=240,
                 tone="brand", value_format=None, show_axis=True,
                 on_hover=None, **kw):
        super().__init__(master, theme, ground=ground, height=height, **kw)
        self._points = []          # list of (label, value)
        self._tone = tone
        self._fmt = value_format or (lambda v: f"{v:,.2f}")
        self._show_axis = show_axis
        self._on_hover = on_hover
        self._hover_idx = None
        self._plot = None
        self._series2 = None
        self._series2_tone = "sky"
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))

    def set_series(self, points, tone=None, secondary=None, secondary_tone=None):
        """``points`` is a list of ``(label, value)``; ``secondary`` overlays."""
        self._points = [(str(l), float(v)) for l, v in (points or [])
                        if v is not None]
        if tone:
            self._tone = tone
        self._series2 = [(str(l), float(v)) for l, v in (secondary or [])
                         if v is not None] or None
        if secondary_tone:
            self._series2_tone = secondary_tone
        self._hover_idx = None
        self.redraw()

    # -- hover ----------------------------------------------------------
    def _set_hover(self, idx):
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.redraw()
            if callable(self._on_hover):
                point = self._points[idx] if idx is not None and idx < len(self._points) else None
                self._on_hover(point)

    def _on_motion(self, event):
        if not self._plot or len(self._points) < 2:
            return
        x1, _y1, x2, _y2 = self._plot
        if not (x1 - 6 <= event.x <= x2 + 6):
            self._set_hover(None)
            return
        step = (x2 - x1) / max(1, len(self._points) - 1)
        idx = int(round((event.x - x1) / step)) if step else 0
        self._set_hover(max(0, min(len(self._points) - 1, idx)))

    # -- paint ----------------------------------------------------------
    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 8 or h <= 8:
            return
        t = self.theme
        if len(self._points) < 2:
            self.create_text(w / 2, h / 2, text="Not enough history to chart",
                             fill=t.c("ink_3"), font=t.font("body"))
            self._plot = None
            return

        values = [v for _l, v in self._points]
        series = [values]
        if self._series2:
            series.append([v for _l, v in self._series2])
        lo = min(min(s) for s in series)
        hi = max(max(s) for s in series)
        if hi == lo:
            lo, hi = lo - 1, hi + 1
        pad_v = (hi - lo) * 0.12
        lo, hi = lo - pad_v, hi + pad_v

        left = 54 if self._show_axis else 8
        right = w - 12
        top = 12
        bottom = h - (26 if self._show_axis else 8)
        self._plot = (left, top, right, bottom)

        def y_of(v):
            return bottom - (v - lo) / (hi - lo) * (bottom - top)

        # Grid + y labels
        for tick in nice_ticks(lo, hi, 4):
            y = y_of(tick)
            if not (top - 1 <= y <= bottom + 1):
                continue
            self.create_line(left, y, right, y, fill=t.c("grid"))
            if self._show_axis:
                self.create_text(left - 8, y, anchor="e", text=compact_number(tick),
                                 fill=t.c("axis"), font=t.font("micro"))

        step = (right - left) / (len(self._points) - 1)

        def draw_series(vals, tone, filled):
            strong, _soft = t.tone(tone)
            pts = [(left + i * step, y_of(v)) for i, v in enumerate(vals)]
            path = pr.smooth_path(pts, tension=0.3, samples=8)
            if filled:
                # Fade-to-baseline fill. Each band is the same area polygon
                # with its top clamped one band lower and a lighter tint;
                # painting them in order leaves a smooth vertical fade that
                # still follows the curve exactly.
                bands = 16
                for b in range(bands):
                    y_cut = top + (bottom - top) * b / bands
                    alpha = FILL_ALPHA * (1.0 - b / bands) ** 1.15
                    clipped = [c for x, y in zip(path[0::2], path[1::2])
                               for c in (x, max(y, y_cut))]
                    self.create_polygon(
                        clipped + [right, bottom, left, bottom],
                        fill=mix(self._ground, strong, alpha), outline="")
            self.create_line(path, fill=strong, width=2.4, capstyle="round",
                             joinstyle="round")
            return pts

        pts = draw_series(values, self._tone, filled=True)
        if self._series2:
            draw_series([v for _l, v in self._series2], self._series2_tone, filled=False)

        # X labels: first, middle, last only — dense dates are unreadable.
        if self._show_axis:
            for idx in {0, len(self._points) // 2, len(self._points) - 1}:
                label = self._points[idx][0]
                x = left + idx * step
                anchor = "w" if idx == 0 else ("e" if idx == len(self._points) - 1 else "center")
                self.create_text(x, bottom + 14, anchor=anchor, text=label,
                                 fill=t.c("axis"), font=t.font("micro"))

        # Last point marker
        strong, _ = t.tone(self._tone)
        pr.dot(self, pts[-1][0], pts[-1][1], 4.5, fill=strong,
               outline=self._ground, width=2)

        if self._hover_idx is not None and self._hover_idx < len(pts):
            hx, hy = pts[self._hover_idx]
            label, value = self._points[self._hover_idx]
            self.create_line(hx, top, hx, bottom, fill=t.c("stroke_strong"), dash=(3, 3))
            pr.dot(self, hx, hy, 5, fill=strong, outline=self._ground, width=2)
            text = f"{label}   {self._fmt(value)}"
            tw = pr.chip_text_width(t.size("caption"), text, pad=10)
            bx = min(max(hx - tw / 2, left), right - tw)
            pr.round_rect(self, bx, top, bx + tw, top + t.size("caption") + 14,
                          radius=8, fill=t.c("ink"))
            self.create_text(bx + tw / 2, top + (t.size("caption") + 14) / 2,
                             text=text, fill=t.c("surface") if not t.is_dark else t.c("ink"),
                             font=t.font("caption", "bold"))


class BarChart(_ChartBase):
    """Rounded vertical bars with value labels and hover highlight."""

    def __init__(self, master, theme: Theme, ground=None, height=200,
                 tone="brand", value_format=None, **kw):
        super().__init__(master, theme, ground=ground, height=height, **kw)
        self._bars = []            # list of (label, value, tone|None)
        self._tone = tone
        self._fmt = value_format or (lambda v: compact_number(v))
        self._hover = None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))

    def set_bars(self, bars, tone=None):
        self._bars = [(str(b[0]), float(b[1]), b[2] if len(b) > 2 else None)
                      for b in (bars or []) if b[1] is not None]
        if tone:
            self._tone = tone
        self.redraw()

    def _slot_at(self, x):
        if not self._bars:
            return None
        w = self.winfo_width()
        left, right = 8, w - 8
        step = (right - left) / len(self._bars)
        idx = int((x - left) // step) if step else 0
        return idx if 0 <= idx < len(self._bars) else None

    def _set_hover(self, idx):
        if idx != self._hover:
            self._hover = idx
            self.redraw()

    def _on_motion(self, event):
        self._set_hover(self._slot_at(event.x))

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 8 or h <= 8:
            return
        t = self.theme
        if not self._bars:
            self.create_text(w / 2, h / 2, text="No data for this period",
                             fill=t.c("ink_3"), font=t.font("body"))
            return
        values = [v for _l, v, _t in self._bars]
        hi = max(values + [0.0])
        lo = min(values + [0.0])
        span = (hi - lo) or 1.0
        left, right = 8, w - 8
        top, bottom = 24, h - 22
        zero_y = bottom - (0 - lo) / span * (bottom - top)
        step = (right - left) / len(self._bars)
        bar_w = min(38, step * 0.56)

        self.create_line(left, zero_y, right, zero_y, fill=t.c("grid"))
        for i, (label, value, bar_tone) in enumerate(self._bars):
            cx = left + step * (i + 0.5)
            y = bottom - (value - lo) / span * (bottom - top)
            strong, soft = t.tone(bar_tone or self._tone)
            fill = strong if self._hover == i else mix(self._ground, strong, 0.82)
            y1, y2 = (min(y, zero_y), max(y, zero_y))
            if abs(y2 - y1) < 2:
                y1 = y2 - 2
            pr.round_rect(self, cx - bar_w / 2, y1, cx + bar_w / 2, y2,
                          radius=min(8, bar_w / 2), fill=fill)
            self.create_text(cx, bottom + 11, text=label, fill=t.c("axis"),
                             font=t.font("micro"))
            if self._hover == i:
                self.create_text(cx, y1 - 10, text=self._fmt(value),
                                 fill=t.c("ink"), font=t.font("caption", "bold"))


class DonutGauge(_ChartBase):
    """Ring gauge with a centred readout — coverage, share, utilisation."""

    def __init__(self, master, theme: Theme, ground=None, size=150,
                 thickness=16, tone="brand", **kw):
        super().__init__(master, theme, ground=ground, height=size,
                         width=size, **kw)
        self._size = size
        self._thickness = thickness
        self._tone = tone
        self._segments = []
        self._center = ("—", "")

    def set(self, segments, center_value="—", center_label="", tone=None):
        """``segments`` is a list of ``(fraction, tone)`` summing to <= 1."""
        self._segments = [(max(0.0, float(f)), t) for f, t in (segments or [])]
        self._center = (center_value, center_label)
        if tone:
            self._tone = tone
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 8 or h <= 8:
            return
        t = self.theme
        cx, cy = w / 2, h / 2
        outer = min(w, h) / 2 - 4
        pr.ring(self, cx, cy, outer, self._thickness, start=90, extent=-359.9,
                color=t.c("surface_3"), rounded=False)
        total = sum(f for f, _ in self._segments)
        scale = 1.0 / total if total > 1.0 else 1.0
        angle = 90.0
        for frac, tone in self._segments:
            extent = -359.9 * min(1.0, frac * scale)
            if abs(extent) < 0.4:
                continue
            strong, _soft = t.tone(tone)
            pr.ring(self, cx, cy, outer, self._thickness, start=angle,
                    extent=extent, color=strong)
            angle += extent
        value, label = self._center
        self.create_text(cx, cy - (6 if label else 0), text=value, fill=t.c("ink"),
                         font=t.font("title", "bold"))
        if label:
            self.create_text(cx, cy + 14, text=label, fill=t.c("ink_3"),
                             font=t.font("micro"))


class RangeMeter(_ChartBase):
    """Where today's value sits inside a low/high band (52-week style)."""

    def __init__(self, master, theme: Theme, ground=None, height=64,
                 tone="brand", value_format=None, **kw):
        super().__init__(master, theme, ground=ground, height=height, **kw)
        self._lo = self._hi = self._value = None
        self._labels = ("Low", "High")
        self._tone = tone
        self._fmt = value_format or (lambda v: f"{v:,.2f}")

    def set(self, low, high, value, labels=None, tone=None):
        self._lo, self._hi, self._value = low, high, value
        if labels:
            self._labels = labels
        if tone:
            self._tone = tone
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 8 or h <= 8:
            return
        t = self.theme
        if None in (self._lo, self._hi, self._value) or self._hi <= self._lo:
            self.create_text(w / 2, h / 2, text="Range unavailable",
                             fill=t.c("ink_3"), font=t.font("caption"))
            return
        strong, _soft = t.tone(self._tone)
        pad = 10
        track_y = h / 2
        track_h = 10
        pr.pill(self, pad, track_y - track_h / 2, w - pad, track_y + track_h / 2,
                fill=t.c("surface_3"))
        frac = (self._value - self._lo) / (self._hi - self._lo)
        frac = max(0.0, min(1.0, frac))
        x = pad + (w - pad * 2) * frac
        pr.pill(self, pad, track_y - track_h / 2, max(pad + track_h, x),
                track_y + track_h / 2, fill=strong)
        pr.dot(self, x, track_y, 8, fill=self._ground, outline=strong, width=3)
        self.create_text(pad, track_y + 18, anchor="nw",
                         text=f"{self._labels[0]}  {self._fmt(self._lo)}",
                         fill=t.c("ink_3"), font=t.font("micro"))
        self.create_text(w - pad, track_y + 18, anchor="ne",
                         text=f"{self._labels[1]}  {self._fmt(self._hi)}",
                         fill=t.c("ink_3"), font=t.font("micro"))
        self.create_text(min(max(x, pad + 20), w - pad - 20), track_y - 16,
                         text=self._fmt(self._value), fill=t.c("ink"),
                         font=t.font("caption", "bold"))
