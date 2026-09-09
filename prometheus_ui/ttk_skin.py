"""Apply the Aurora tokens to ttk, so existing screens modernise too.

The app has thousands of lines of ttk widgets that predate this interface.
Rather than rewrite each screen, this module restyles ttk itself: entries,
combos, buttons, notebooks, tables and scrollbars all pick up the new
palette, radii-adjacent padding and type scale the moment it is applied.

``apply_ttk_skin`` is idempotent and never raises — a styling failure must
never stop the application from starting.
"""

from __future__ import annotations

from tkinter import ttk

from .theme import Theme, mix

__all__ = ["apply_ttk_skin", "TREE_STYLE", "FLAT_NOTEBOOK_STYLE"]

TREE_STYLE = "Aurora.Treeview"
FLAT_NOTEBOOK_STYLE = "AuroraFlat.TNotebook"


def apply_ttk_skin(root, theme: Theme, row_height: int | None = None) -> bool:
    """Restyle ttk for ``root`` using ``theme``. Returns True on success."""
    try:
        style = ttk.Style(root)
        try:
            style.theme_use("clam")   # the only built-in that honours colours
        except Exception:
            pass

        ink = theme.c("ink")
        ink_2 = theme.c("ink_2")
        ink_3 = theme.c("ink_3")
        surface = theme.c("surface")
        surface_2 = theme.c("surface_2")
        surface_3 = theme.c("surface_3")
        stroke = theme.c("stroke")
        brand = theme.c("brand")
        bg = theme.c("bg")
        body = theme.font("body")
        body_bold = theme.font("body", "bold")

        style.configure(".", font=body, background=bg, foreground=ink,
                        bordercolor=stroke, focuscolor=brand,
                        troughcolor=surface_3, relief="flat")
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink, font=body)
        style.configure("TLabelframe", background=bg, bordercolor=stroke,
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=bg,
                        foreground=theme.c("brand_ink"), font=body_bold)
        style.configure("TCheckbutton", background=bg, foreground=ink_2, font=body)
        style.configure("TRadiobutton", background=bg, foreground=ink_2, font=body)
        style.map("TCheckbutton", foreground=[("active", ink)])

        # -- buttons ------------------------------------------------------
        style.configure("TButton", font=body_bold, padding=(14, 7),
                        background=surface_3, foreground=ink,
                        borderwidth=1, bordercolor=stroke, relief="flat")
        style.map("TButton",
                  background=[("pressed", mix(surface_3, brand, 0.24)),
                              ("active", mix(surface_3, brand, 0.12)),
                              ("disabled", surface_2)],
                  foreground=[("disabled", ink_3),
                              ("active", theme.c("brand_ink"))],
                  bordercolor=[("active", brand)])

        style.configure("Accent.TButton", background=brand,
                        foreground=theme.c("on_brand"), bordercolor=brand)
        style.map("Accent.TButton",
                  background=[("pressed", mix(brand, "#000000", 0.18)),
                              ("active", mix(brand, "#000000", 0.08)),
                              ("disabled", surface_3)],
                  foreground=[("disabled", ink_3)])

        style.configure("Ghost.TButton", background=bg, foreground=ink_2,
                        bordercolor=stroke)
        style.map("Ghost.TButton",
                  background=[("active", surface_3)],
                  foreground=[("active", ink)])

        # -- inputs -------------------------------------------------------
        for name in ("TEntry", "TSpinbox"):
            style.configure(name, fieldbackground=surface, background=surface,
                            foreground=ink, bordercolor=stroke,
                            lightcolor=stroke, darkcolor=stroke,
                            insertcolor=ink, padding=6, relief="flat",
                            arrowcolor=ink_2)
            style.map(name,
                      bordercolor=[("focus", brand)],
                      lightcolor=[("focus", brand)],
                      darkcolor=[("focus", brand)],
                      fieldbackground=[("disabled", surface_3)],
                      foreground=[("disabled", ink_3)])

        style.configure("TCombobox", fieldbackground=surface, background=surface,
                        foreground=ink, bordercolor=stroke, lightcolor=stroke,
                        darkcolor=stroke, arrowcolor=ink_2, padding=5)
        style.map("TCombobox",
                  bordercolor=[("focus", brand)],
                  lightcolor=[("focus", brand)],
                  darkcolor=[("focus", brand)],
                  fieldbackground=[("readonly", surface), ("disabled", surface_3)],
                  foreground=[("disabled", ink_3)],
                  arrowcolor=[("active", brand)])
        try:
            root.option_add("*TCombobox*Listbox.background", surface)
            root.option_add("*TCombobox*Listbox.foreground", ink)
            root.option_add("*TCombobox*Listbox.selectBackground", theme.c("brand_soft"))
            root.option_add("*TCombobox*Listbox.selectForeground", theme.c("brand_ink"))
            root.option_add("*TCombobox*Listbox.font", body)
        except Exception:
            pass

        # -- tables -------------------------------------------------------
        rh = row_height or max(26, theme.size("body") + 16)
        for name in ("Treeview", TREE_STYLE):
            style.configure(name, background=surface, fieldbackground=surface,
                            foreground=ink, rowheight=rh, font=body,
                            borderwidth=0, relief="flat")
            style.map(name,
                      background=[("selected", theme.c("brand_soft"))],
                      foreground=[("selected", theme.c("brand_ink"))])
        for name in ("Treeview.Heading", f"{TREE_STYLE}.Heading"):
            style.configure(name, background=surface_2, foreground=ink_2,
                            font=theme.font("caption", "bold"),
                            relief="flat", padding=(8, 8), borderwidth=0)
            style.map(name, background=[("active", surface_3)])

        # -- notebooks ----------------------------------------------------
        style.configure("TNotebook", background=bg, borderwidth=0,
                        tabmargins=(4, 6, 4, 0))
        # Analysis carries ten sub-tabs. Padding generous enough for a
        # two-tab notebook truncates every label there, so tabs stay on the
        # caption size: bold keeps them legible, compact keeps them whole.
        style.configure("TNotebook.Tab", font=theme.font("caption"),
                        padding=(10, 8), background=surface_3,
                        foreground=ink_2, borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", surface), ("active", surface_2)],
                  foreground=[("selected", theme.c("brand_ink"))],
                  padding=[("selected", (16, 9))])

        # A notebook whose own tab strip is hidden: the modern shell's rail
        # navigates it instead. Zero padding plus a zero-size tab element
        # keeps the strip from reserving vertical space.
        style.configure(FLAT_NOTEBOOK_STYLE, background=bg, borderwidth=0,
                        tabmargins=0)
        style.layout(FLAT_NOTEBOOK_STYLE, [
            ("Notebook.client", {"sticky": "nswe"})])
        style.configure(f"{FLAT_NOTEBOOK_STYLE}.Tab", padding=0, borderwidth=0)
        style.layout(f"{FLAT_NOTEBOOK_STYLE}.Tab", [])

        # -- misc ---------------------------------------------------------
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=surface_3,
                            troughcolor=bg, bordercolor=bg, arrowcolor=ink_3,
                            relief="flat", borderwidth=0)
            style.map(f"{orient}.TScrollbar",
                      background=[("active", theme.c("stroke_strong"))])
        style.configure("TSeparator", background=stroke)
        style.configure("TProgressbar", background=brand, troughcolor=surface_3,
                        bordercolor=surface_3, lightcolor=brand, darkcolor=brand)
        style.configure("TPanedwindow", background=bg)
        return True
    except Exception:
        return False
