"""Low-level canvas drawing used by every modern widget.

Tk's canvas has no rounded rectangles, no gradients and no alpha channel.
Everything the interface needs is therefore reconstructed here from
polygons, scanlines and pre-blended colours:

``round_rect``          smooth-splined rounded rectangle
``round_rect_gradient`` a real rounded gradient — each scanline is inset by
                        the corner circle, so the gradient itself is clipped
                        to the rounded shape instead of being masked
``soft_shadow``         stacked, progressively lighter rounded rects that
                        read as a diffuse drop shadow on an opaque ground
``ring``                donut arc with rounded caps
``smooth_path``         Catmull-Rom-ish smoothing for chart lines

All helpers take an explicit ``ground`` colour where blending is needed,
because a Tk canvas item can never be genuinely translucent.
"""

from __future__ import annotations

import math

from .theme import mix

__all__ = [
    "round_rect_points", "round_rect", "round_rect_gradient", "soft_shadow",
    "ring", "pill", "smooth_path", "chip_text_width", "inset_for_row",
    "dot", "vertical_gradient",
]


def _clamp_radius(x1, y1, x2, y2, r) -> float:
    return max(0.0, min(float(r), abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0))


def round_rect_points(x1, y1, x2, y2, r):
    """Point list for a rounded rectangle drawn with ``smooth=True``.

    The doubled corner points are what make Tk's spline hug the corner
    instead of rounding the whole outline into a blob.
    """
    r = _clamp_radius(x1, y1, x2, y2, r)
    return [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
        x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r,
        x1, y1,
    ]


def round_rect(canvas, x1, y1, x2, y2, radius=16, fill="", outline="",
               width=1, tags=(), **kw):
    """Draw a rounded rectangle and return its canvas item id."""
    pts = round_rect_points(x1, y1, x2, y2, radius)
    return canvas.create_polygon(
        pts, smooth=True, splinesteps=24, fill=fill or "",
        outline=outline or "", width=width if outline else 0,
        tags=tags, **kw)


def inset_for_row(y, y1, y2, radius) -> float:
    """Horizontal inset of a rounded rect at scanline ``y``.

    Solving the corner circle gives the exact inset, so a scanline gradient
    can be clipped to the rounded silhouette without a mask.
    """
    r = _clamp_radius(0, y1, 2 * radius, y2, radius)
    if r <= 0:
        return 0.0
    inset = 0.0
    d_top = y - y1
    if d_top < r:
        inset = max(inset, r - math.sqrt(max(0.0, r * r - (r - d_top) ** 2)))
    d_bot = y2 - y
    if d_bot < r:
        inset = max(inset, r - math.sqrt(max(0.0, r * r - (r - d_bot) ** 2)))
    return inset


def round_rect_gradient(canvas, x1, y1, x2, y2, color_from, color_to,
                        radius=20, direction="vertical", tags=(), steps=None):
    """Fill a rounded rectangle with a two-stop gradient.

    ``direction`` is ``"vertical"`` or ``"horizontal"``. Returns the list of
    item ids so callers can delete or raise the whole fill at once.
    """
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    h, w = int(round(y2 - y1)), int(round(x2 - x1))
    if h <= 0 or w <= 0:
        return []
    items = []
    if direction == "horizontal":
        n = max(1, steps or w)
        for i in range(n):
            x = x1 + (w * i / n)
            xn = x1 + (w * (i + 1) / n)
            inset = inset_for_row(x, x1, x2, radius)
            items.append(canvas.create_rectangle(
                x, y1 + inset, xn + 1, y2 - inset, width=0,
                fill=mix(color_from, color_to, i / max(1, n - 1)), tags=tags))
        return items
    n = max(1, steps or h)
    for i in range(n):
        y = y1 + (h * i / n)
        yn = y1 + (h * (i + 1) / n)
        inset = inset_for_row(y, y1, y2, radius)
        items.append(canvas.create_rectangle(
            x1 + inset, y, x2 - inset, yn + 1, width=0,
            fill=mix(color_from, color_to, i / max(1, n - 1)), tags=tags))
    return items


def vertical_gradient(canvas, x1, y1, x2, y2, color_from, color_to, tags=()):
    """Square-cornered vertical gradient (chart fills, sheet headers)."""
    return round_rect_gradient(canvas, x1, y1, x2, y2, color_from, color_to,
                               radius=0, direction="vertical", tags=tags)


def soft_shadow(canvas, x1, y1, x2, y2, radius=20, ground="#ffffff",
                color="#243056", layers=5, spread=5, offset=2,
                strength=0.13, tags=()):
    """Diffuse drop shadow built from stacked pre-blended rounded rects."""
    items = []
    for i in range(layers, 0, -1):
        grow = spread * i / layers
        # Quadratic falloff: the outermost ring is nearly the ground colour,
        # the innermost carries most of the tint. That reads as diffusion.
        alpha = strength * ((layers - i + 1) / layers) ** 2.2
        items.append(round_rect(
            canvas, x1 - grow, y1 - grow + offset, x2 + grow, y2 + grow + offset,
            radius=radius + grow, fill=mix(ground, color, alpha), outline="",
            tags=tags))
    return items


def ring(canvas, cx, cy, outer_r, thickness, start=90, extent=-270,
         color="#5646e5", tags=(), rounded=True):
    """Donut arc. Tk arcs have square ends, so caps are drawn as dots."""
    items = []
    inset = thickness / 2.0
    r = outer_r - inset
    items.append(canvas.create_arc(
        cx - r, cy - r, cx + r, cy + r, start=start, extent=extent,
        style="arc", outline=color, width=thickness, tags=tags))
    if rounded and abs(extent) > 0.5:
        for ang in (start, start + extent):
            a = math.radians(ang)
            px, py = cx + r * math.cos(a), cy - r * math.sin(a)
            items.append(canvas.create_oval(
                px - inset, py - inset, px + inset, py + inset,
                fill=color, outline="", tags=tags))
    return items


def dot(canvas, cx, cy, r, fill, outline="", width=0, tags=()):
    return canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill,
                              outline=outline, width=width, tags=tags)


def pill(canvas, x1, y1, x2, y2, fill="", outline="", width=1, tags=(), **kw):
    return round_rect(canvas, x1, y1, x2, y2, radius=(y2 - y1) / 2.0,
                      fill=fill, outline=outline, width=width, tags=tags, **kw)


def smooth_path(points, tension=0.35, samples=12):
    """Return a denser, smoothed point list for a polyline.

    Tk's ``smooth=True`` over-rounds sharp market data; sampling a
    Catmull-Rom spline ourselves keeps peaks honest while removing the
    hard elbows that make a chart look unfinished.
    """
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 3:
        return [c for p in pts for c in p]
    ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            m1x = tension * (p2[0] - p0[0])
            m1y = tension * (p2[1] - p0[1])
            m2x = tension * (p3[0] - p1[0])
            m2y = tension * (p3[1] - p1[1])
            h1 = 2 * t3 - 3 * t2 + 1
            h2 = -2 * t3 + 3 * t2
            h3 = t3 - 2 * t2 + t
            h4 = t3 - t2
            out.append(h1 * p1[0] + h2 * p2[0] + h3 * m1x + h4 * m2x)
            out.append(h1 * p1[1] + h2 * p2[1] + h3 * m1y + h4 * m2y)
    out.extend(pts[-1])
    return out


def chip_text_width(font_size, text, pad=10) -> int:
    """Cheap width estimate for canvas-drawn chips before layout runs."""
    return int(len(str(text)) * font_size * 0.62) + pad * 2
