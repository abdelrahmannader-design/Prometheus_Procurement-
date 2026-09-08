"""Design tokens for the Prometheus modern interface ("Aurora").

This module is deliberately dependency-free and Tk-free so the token set can
be imported, diffed and unit-tested without a display. Every colour, radius,
spacing step and font size used by :mod:`prometheus_ui` resolves here — no
screen is allowed to hardcode a hex value.

The palette follows the soft-surface style the interface brief asked for:
generous corner radii, a light airy ground, one confident violet-indigo
brand ramp, and semantic ramps (mint / amber / rose / sky) that each ship a
strong tone for text and a tinted "soft" tone for chip and bubble fills.
"""

from __future__ import annotations

import math

# ── colour maths ─────────────────────────────────────────────────────────


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(color_a: str, color_b: str, t: float) -> str:
    """Blend ``color_a`` toward ``color_b``. ``t=0`` is a, ``t=1`` is b."""
    t = max(0.0, min(1.0, float(t)))
    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    return rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def lighten(color: str, amount: float = 0.12) -> str:
    return mix(color, "#ffffff", amount)


def darken(color: str, amount: float = 0.12) -> str:
    return mix(color, "#000000", amount)


def alpha_over(fg: str, bg: str, alpha: float) -> str:
    """Tk canvases have no alpha channel; pre-blend instead."""
    return mix(bg, fg, alpha)


def relative_luminance(color: str) -> float:
    def _chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_chan(c) for c in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a: str, color_b: str) -> float:
    la, lb = relative_luminance(color_a), relative_luminance(color_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_ink(background: str, dark: str = "#101828", light: str = "#ffffff") -> str:
    """Pick whichever of ``dark``/``light`` reads better on ``background``."""
    return dark if contrast_ratio(background, dark) >= contrast_ratio(background, light) else light


# ── palettes ─────────────────────────────────────────────────────────────

AURORA_DAY: dict[str, str] = {
    "mode":          "light",
    # grounds
    "bg":            "#f3f5fc",
    "bg_alt":        "#eaeef8",
    "surface":       "#ffffff",
    "surface_2":     "#f7f9fd",
    "surface_3":     "#eef2fa",
    "rail":          "#ffffff",
    "rail_ink":      "#475467",
    "rail_ink_soft": "#6d768d",
    # strokes
    "stroke":        "#e3e8f2",
    "stroke_soft":   "#eef1f8",
    "stroke_strong": "#cfd7e6",
    # ink
    "ink":           "#101828",
    "ink_2":         "#48536b",
    "ink_3":         "#68738b",
    "on_brand":      "#ffffff",
    # brand ramp
    "brand":         "#5646e5",
    "brand_2":       "#8b6df3",
    "brand_3":       "#b48bf7",
    "brand_deep":    "#33249c",
    "brand_soft":    "#ecebfe",
    "brand_ink":     "#4034bd",
    # semantic ramps
    "mint":          "#067153",
    "mint_soft":     "#e0f5ee",
    "amber":         "#8f5606",
    "amber_soft":    "#fdf1de",
    "rose":          "#b81c44",
    "rose_soft":     "#fde8ed",
    "sky":           "#08699c",
    "sky_soft":      "#e2f1fb",
    "violet":        "#6a29d6",
    "violet_soft":   "#f1ebfe",
    # chart ink
    "grid":          "#e7ebf4",
    "axis":          "#98a2b3",
    "shadow":        "#243056",
}

AURORA_NIGHT: dict[str, str] = {
    "mode":          "dark",
    "bg":            "#080c17",
    "bg_alt":        "#050810",
    "surface":       "#111827",
    "surface_2":     "#161f33",
    "surface_3":     "#1d2941",
    "rail":          "#0d1421",
    "rail_ink":      "#a9b8d4",
    "rail_ink_soft": "#7d8ba8",
    "stroke":        "#222e47",
    "stroke_soft":   "#1a2438",
    "stroke_strong": "#33415e",
    "ink":           "#eef2fb",
    "ink_2":         "#a7b4cd",
    "ink_3":         "#8695b2",
    "on_brand":      "#ffffff",
    "brand":         "#6d5cf0",
    "brand_2":       "#9b8bff",
    "brand_3":       "#c0aeff",
    "brand_deep":    "#241a63",
    "brand_soft":    "#1e1c46",
    "brand_ink":     "#bcb0ff",
    "mint":          "#34d6a4",
    "mint_soft":     "#102c25",
    "amber":         "#f6b545",
    "amber_soft":    "#2e2314",
    "rose":          "#fb7191",
    "rose_soft":     "#2f1622",
    "sky":           "#48b6ef",
    "sky_soft":      "#0f2537",
    "violet":        "#a78bfa",
    "violet_soft":   "#211a3e",
    "grid":          "#1c2740",
    "axis":          "#5c6a86",
    "shadow":        "#000000",
}

PALETTES = {"day": AURORA_DAY, "night": AURORA_NIGHT}

# ── geometry ─────────────────────────────────────────────────────────────

RADIUS = {
    "xs":   8,
    "sm":  12,
    "md":  16,
    "lg":  20,
    "xl":  26,
    "2xl": 32,
    "pill": 999,
}

SPACE = {
    "0":  0,
    "1":  4,
    "2":  6,
    "3":  8,
    "4": 12,
    "5": 16,
    "6": 20,
    "7": 24,
    "8": 32,
    "9": 40,
}

# Base font sizes in points, before the user's font-scale multiplier.
TYPE_SCALE = {
    "micro":     8,
    "caption":   9,
    "body":     10,
    "body_lg":  11,
    "subtitle": 12,
    "title":    15,
    "headline": 19,
    "display":  26,
    "metric":   22,
    "metric_lg": 30,
}

WEIGHTS = {"regular": "normal", "medium": "bold", "bold": "bold"}

# Sidebar / chrome geometry.
LAYOUT = {
    "rail_width":          232,
    "rail_width_collapsed": 68,
    "topbar_height":        60,
    "card_pad":             16,
    "gutter":               14,
}


class Theme:
    """Resolved token set: a palette plus a font scale.

    Instances are cheap and immutable in practice; screens hold a reference
    and read ``theme.c("brand")`` / ``theme.font("title", "bold")`` rather
    than importing palette dicts directly, so a runtime theme switch is a
    matter of rebuilding with a different palette name.
    """

    def __init__(self, palette: str = "day", font_scale: float = 1.0,
                 family: str = "Segoe UI"):
        if palette not in PALETTES:
            palette = "day"
        self.name = palette
        self.palette = dict(PALETTES[palette])
        self.font_scale = max(0.8, min(1.6, float(font_scale or 1.0)))
        self.family = family or "Segoe UI"
        self.radius = dict(RADIUS)
        self.space = dict(SPACE)
        self.layout = dict(LAYOUT)

    # -- colours ---------------------------------------------------------
    @property
    def is_dark(self) -> bool:
        return self.palette.get("mode") == "dark"

    def c(self, token: str, fallback: str | None = None) -> str:
        """Resolve a colour token; a literal ``#rrggbb`` passes through."""
        if token and token.startswith("#"):
            return token
        value = self.palette.get(token)
        if value is None:
            if fallback is not None:
                return self.c(fallback)
            raise KeyError(f"unknown colour token: {token!r}")
        return value

    def soft(self, token: str) -> str:
        """The tinted companion of a semantic token ('mint' -> 'mint_soft')."""
        return self.c(f"{token}_soft", fallback=token)

    def shadow_tint(self, ground: str, strength: float = 0.10) -> str:
        return alpha_over(self.c("shadow"), self.c(ground), strength)

    # -- type ------------------------------------------------------------
    def size(self, token: str) -> int:
        base = TYPE_SCALE.get(token, TYPE_SCALE["body"])
        return max(7, int(round(base * self.font_scale)))

    def font(self, token: str = "body", weight: str = "regular"):
        w = WEIGHTS.get(weight, "normal")
        if w == "normal":
            return (self.family, self.size(token))
        return (self.family, self.size(token), w)

    # -- geometry --------------------------------------------------------
    def r(self, token: str) -> int:
        return int(RADIUS.get(token, RADIUS["md"]))

    def s(self, token) -> int:
        if isinstance(token, (int, float)):
            return int(token)
        return int(SPACE.get(str(token), SPACE["4"]))

    # -- semantics -------------------------------------------------------
    def tone(self, kind: str) -> tuple[str, str]:
        """Return ``(strong, soft)`` for a semantic tone name."""
        kind = (kind or "brand").lower()
        aliases = {
            "positive": "mint", "success": "mint", "good": "mint", "up": "mint",
            "warning": "amber", "caution": "amber", "watch": "amber",
            "negative": "rose", "danger": "rose", "bad": "rose", "down": "rose",
            "info": "sky", "neutral": "sky",
            "accent": "violet",
        }
        key = aliases.get(kind, kind)
        if key not in ("mint", "amber", "rose", "sky", "violet", "brand"):
            key = "brand"
        return self.c(key), self.soft(key)

    def delta_tone(self, value, positive_is_good: bool = True) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "sky"
        if abs(v) < 1e-12:
            return "sky"
        good = (v > 0) if positive_is_good else (v < 0)
        return "mint" if good else "rose"

    # -- gradients -------------------------------------------------------
    def brand_gradient(self) -> tuple[str, str]:
        return self.c("brand_deep") if self.is_dark else self.c("brand"), self.c("brand_2")

    def gradient(self, token: str) -> tuple[str, str]:
        strong, _soft = self.tone(token)
        return darken(strong, 0.22), lighten(strong, 0.18)

    def ramp(self, steps: int = 5) -> list[str]:
        """A categorical ramp for series colouring, brand-led."""
        anchors = [self.c("brand"), self.c("sky"), self.c("mint"),
                   self.c("amber"), self.c("violet"), self.c("rose")]
        if steps <= len(anchors):
            return anchors[:steps]
        out = []
        for i in range(steps):
            pos = i / max(1, steps - 1) * (len(anchors) - 1)
            lo = int(math.floor(pos))
            hi = min(lo + 1, len(anchors) - 1)
            out.append(mix(anchors[lo], anchors[hi], pos - lo))
        return out


def theme_for(palette: str = "day", font_scale: float = 1.0, family: str = "Segoe UI") -> Theme:
    return Theme(palette=palette, font_scale=font_scale, family=family)
