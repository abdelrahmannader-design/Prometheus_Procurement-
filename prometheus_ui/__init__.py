"""Prometheus modern interface kit ("Aurora").

A small, dependency-free Tk design system: tokens, canvas primitives,
widgets, charts, a navigation shell and the CBOT Command Center screen.
Nothing in here touches business logic, the state file or the network, so
it can be imported and exercised without the application.
"""

from __future__ import annotations

from .theme import (Theme, theme_for, PALETTES, RADIUS, SPACE, TYPE_SCALE,
                    LAYOUT, mix, lighten, darken, contrast_ratio, readable_ink)
from .ttk_skin import apply_ttk_skin, FLAT_NOTEBOOK_STYLE, TREE_STYLE

__all__ = [
    "Theme", "theme_for", "PALETTES", "RADIUS", "SPACE", "TYPE_SCALE",
    "LAYOUT", "mix", "lighten", "darken", "contrast_ratio", "readable_ink",
    "apply_ttk_skin", "FLAT_NOTEBOOK_STYLE", "TREE_STYLE",
    "UI_KIT_VERSION",
]

UI_KIT_VERSION = "aurora-1.0"
