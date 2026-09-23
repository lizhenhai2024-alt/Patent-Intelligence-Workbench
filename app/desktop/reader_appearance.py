"""Shared, persisted typography controls for Reader text (not figure zoom)."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

DEFAULT_FONT = "默认（原文 / 译文）"
MIN_SIZE, MAX_SIZE = 8, 32
MIN_SPACING, MAX_SPACING = 0, 20


class ReaderAppearance:
    def __init__(self, parent, path: Path, on_error):
        self.path = path
        self.on_error = on_error
        self.widgets: tuple[tk.Text, ...] = ()
        self.fonts = (DEFAULT_FONT, *sorted(
            {name for name in tkfont.families(parent) if not name.startswith("@")},
            key=str.casefold,
        ))
        settings = self._load()
        family = settings.get("family", DEFAULT_FONT)
        self.family = tk.StringVar(parent, value=family if family in self.fonts else DEFAULT_FONT)
        self.size = self._number(settings.get("size"), 11, MIN_SIZE, MAX_SIZE)
        self.spacing = self._number(settings.get("spacing"), 1, MIN_SPACING, MAX_SPACING)
        self.size_label = tk.StringVar(parent)
        self.spacing_label = tk.StringVar(parent)
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="阅读设置 · 字体").pack(side="left")
        self.font_box = ttk.Combobox(
            row, textvariable=self.family, values=self.fonts, state="readonly", width=24,
        )
        self.font_box.pack(side="left", padx=(6, 12))
        self.font_box.bind("<<ComboboxSelected>>", lambda _event: self.apply())
        self.smaller = self._button(row, "字号 −", lambda: self.change_size(-1))
        ttk.Label(row, textvariable=self.size_label, width=6, anchor="center").pack(side="left")
        self.larger = self._button(row, "字号 +", lambda: self.change_size(1))
        self.tighter = self._button(row, "行距 −", lambda: self.change_spacing(-1))
        ttk.Label(row, textvariable=self.spacing_label, width=8, anchor="center").pack(side="left")
        self.looser = self._button(row, "行距 +", lambda: self.change_spacing(1))
        self.reset_button = self._button(row, "恢复默认", self.reset)
        ttk.Label(row, text="同时应用于原文和译文", style="Subtle.TLabel").pack(
            side="left", padx=(8, 0),
        )

    @staticmethod
    def _button(parent, text, command):
        button = ttk.Button(parent, text=text, command=command, width=9)
        button.pack(side="left", padx=2)
        return button

    @staticmethod
    def _number(value, default, minimum, maximum):
        return min(maximum, max(minimum, value)) if type(value) is int else default

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def attach(self, source: tk.Text, translation: tk.Text) -> None:
        self.widgets = (source, translation)
        self.apply(save=False)

    def change_size(self, delta: int) -> None:
        self.size = min(MAX_SIZE, max(MIN_SIZE, self.size + delta))
        self.apply()

    def change_spacing(self, delta: int) -> None:
        self.spacing = min(MAX_SPACING, max(MIN_SPACING, self.spacing + delta))
        self.apply()

    def reset(self) -> None:
        self.family.set(DEFAULT_FONT)
        self.size, self.spacing = 11, 1
        self.apply()

    def apply(self, *, save: bool = True) -> None:
        for widget, default in zip(self.widgets, ("Cambria", "Microsoft YaHei UI"), strict=False):
            family = default if self.family.get() == DEFAULT_FONT else self.family.get()
            widget.configure(
                font=(family, self.size),
                spacing1=self.spacing + 1,
                spacing2=self.spacing,
                spacing3=self.spacing + 6,
            )
        self.size_label.set(f"{self.size} pt")
        self.spacing_label.set(f"{self.spacing} px")
        for button, enabled in (
            (self.smaller, self.size > MIN_SIZE), (self.larger, self.size < MAX_SIZE),
            (self.tighter, self.spacing > MIN_SPACING),
            (self.looser, self.spacing < MAX_SPACING),
        ):
            button.state(["!disabled" if enabled else "disabled"])
        if save:
            self._save()

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps({
                "family": self.family.get(), "size": self.size, "spacing": self.spacing,
            }, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            self.on_error("阅读设置已应用，但保存失败；下次启动可能恢复默认。")
