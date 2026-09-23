"""Small reusable 'card' and category-tag widgets shared by the Intelligence and
Agent pages: a clickable icon+title+description card that can be toggled between
a plain and a selected visual state, and a row of filter chips built the same way.

Kept separate because both pages build the same visual element (previously a
plain button grid / dropdown) and duplicating the styling logic would drift.
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk


class Card:
    """A clickable card: icon on top, bold title, short description below."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        icon: str,
        title: str,
        description: str,
        on_click: Callable[[], None],
    ) -> None:
        self.frame = ttk.Frame(parent, style="CardOutline.TFrame", padding=(12, 10))
        self._icon = ttk.Label(self.frame, text=icon, style="CardIcon.TLabel")
        self._icon.pack(anchor="w")
        self._title = ttk.Label(
            self.frame, text=title, style="CardTitle.TLabel", wraplength=230
        )
        self._title.pack(anchor="w", pady=(4, 2))
        self._desc = ttk.Label(
            self.frame,
            text=description,
            style="CardDesc.TLabel",
            wraplength=230,
            justify="left",
        )
        self._desc.pack(anchor="w", fill="x")
        self.active = False
        for widget in (self.frame, self._icon, self._title, self._desc):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event: on_click())

    def set_active(self, active: bool) -> None:
        self.active = active
        suffix = "Active" if active else ""
        self.frame.configure(style=f"CardOutline{suffix}.TFrame")
        self._icon.configure(style=f"CardIcon{suffix}.TLabel")
        self._title.configure(style=f"CardTitle{suffix}.TLabel")
        self._desc.configure(style=f"CardDesc{suffix}.TLabel")


def build_tag_row(
    parent: ttk.Frame,
    options: list[str],
    *,
    active: str,
    on_select: Callable[[str], None],
) -> dict[str, ttk.Button]:
    """A row of filter chips; returns the buttons so the caller can restyle them."""
    row = ttk.Frame(parent, style="Surface.TFrame")
    row.pack(fill="x", pady=(0, 8))
    buttons: dict[str, ttk.Button] = {}
    for option in options:
        button = ttk.Button(
            row,
            text=option,
            style="TagActive.TButton" if option == active else "Tag.TButton",
            command=lambda value=option: on_select(value),
        )
        button.pack(side="left", padx=(0, 6))
        buttons[option] = button
    return buttons
