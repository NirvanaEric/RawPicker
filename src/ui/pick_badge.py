"""Pill-shaped badges that decorate a thumbnail: pick status + RAW indicator.

Lightroom-inspired: filled coloured pills, white text, rounded.
"""
from __future__ import annotations

import customtkinter as ctk

from ..config.settings import Colors


class _Pill(ctk.CTkLabel):
    """Base pill: small rounded label with translucent fill."""

    def __init__(self, master, text: str = "", padx: int = 8, pady: int = 2,
                 size: int = 11, **kw) -> None:
        super().__init__(master, text=text,
                         fg_color=Colors.SURFACE_RAISED,
                         text_color=Colors.TEXT,
                         font=ctk.CTkFont(size=size, weight="bold"),
                         corner_radius=10,
                         padx=padx, pady=pady, **kw)


class PickBadge(_Pill):
    """Top-left pill: ✓ for accepted, ✕ for rejected, hidden for pending."""

    def __init__(self, master, **kw) -> None:
        super().__init__(master, text="", **kw)
        self.set_status("pending")

    def set_status(self, status: str) -> None:
        if status == "accepted":
            self.configure(text="\u2713", fg_color=Colors.ACCEPTED, text_color="white")
        elif status == "rejected":
            self.configure(text="\u2715", fg_color=Colors.REJECTED, text_color="white")
        else:
            # Hidden (no badge for pending)
            self.configure(text="", fg_color="transparent")


class RawBadge(_Pill):
    """Top-right pill: shown only when there's no companion RAW."""

    def __init__(self, master, **kw) -> None:
        super().__init__(master, text="", padx=7, **kw)
        self.set_present(True)

    def set_present(self, has_raw: bool) -> None:
        if has_raw:
            self.configure(text="", fg_color="transparent")
        else:
            self.configure(text="RAW?", fg_color=Colors.WARNING, text_color="#1A1A1A")
