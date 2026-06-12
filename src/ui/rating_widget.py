"""Star rating widget. 0 = unrated, 1-5 = filled accent stars.

Bigger than the previous version (default 22px) for a more tappable,
more Lightroom-like feel. Hover preview is shown when `on_hover` is set.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from ..config.settings import Colors


STAR = "\u2605"   # filled
EMPTY = "\u2606"  # outline


class RatingWidget(ctk.CTkFrame):
    def __init__(self, master, value: int = 0,
                 on_change: Optional[Callable[[int], None]] = None,
                 size: int = 22, **kw) -> None:
        super().__init__(master, fg_color="transparent", **kw)
        self._on_change = on_change
        self._size = size
        self._value = max(0, min(5, int(value)))
        self._labels = []
        for i in range(1, 6):
            lbl = ctk.CTkLabel(self, text=EMPTY, width=size + 6, height=size,
                               text_color=Colors.ACCENT,
                               font=ctk.CTkFont(size=size, weight="bold"),
                               cursor="hand2")
            lbl.bind("<Button-1>", lambda _e, v=i: self._click(v))
            lbl.bind("<Enter>", lambda _e, v=i: self._preview(v))
            lbl.bind("<Leave>", lambda _e: self._preview(0))
            lbl.pack(side="left", padx=1)
            self._labels.append(lbl)
        self._refresh(self._value)

    # -- public API -----------------------------------------------------
    def set_value(self, value: int) -> None:
        self._value = max(0, min(5, int(value)))
        self._refresh(self._value)

    def get_value(self) -> int:
        return self._value

    # -- internals ------------------------------------------------------
    def _click(self, v: int) -> None:
        # Click an already-filled star to clear (toggle off)
        self._value = 0 if self._value == v else v
        self._refresh(self._value)
        if self._on_change:
            self._on_change(self._value)

    def _preview(self, v: int) -> None:
        # Hover preview shows the would-be value (or restores current on leave)
        self._refresh(v if v > 0 else self._value)

    def _refresh(self, fill_to: int) -> None:
        for i, lbl in enumerate(self._labels, 1):
            lbl.configure(text=STAR if i <= fill_to else EMPTY)
