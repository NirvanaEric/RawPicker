"""Reusable confirmation / info dialogs with the modern colour palette."""
from __future__ import annotations

import customtkinter as ctk

from ...config.settings import Colors


class _DialogShell(ctk.CTkToplevel):
    """Common shell: centred, grab_set, ESC closes, dark surface."""

    def __init__(self, master, *, title: str, width: int = 460, height: int = 220) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.configure(fg_color=Colors.BG)
        self.grab_set()
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self._result = None

    def _on_cancel(self) -> None:
        self.destroy()

    def get_result(self):
        return self._result


class ConfirmDialog(_DialogShell):
    """Yes/No confirmation. Returns True if confirmed, False otherwise."""

    def __init__(self, master, *, title: str, message: str, confirm_text: str = "确定",
                 cancel_text: str = "取消", danger: bool = False) -> None:
        super().__init__(master, title=title, width=460, height=220)
        self._result = False
        fg = Colors.REJECTED if danger else Colors.ACCENT
        fg_text = "white" if not danger else "white"

        # Body card
        body = ctk.CTkFrame(self, fg_color=Colors.SURFACE, corner_radius=12)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        ctk.CTkLabel(
            body, text=message, wraplength=400, justify="left",
            text_color=Colors.TEXT,
            font=ctk.CTkFont(size=13),
        ).pack(padx=16, pady=16, anchor="w")

        # Buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            btns, text=cancel_text, width=96, height=34, corner_radius=17,
            fg_color="transparent", border_width=1, border_color=Colors.BORDER,
            text_color=Colors.TEXT_DIM, hover_color=Colors.SURFACE,
            command=self._on_cancel,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btns, text=confirm_text, width=120, height=34, corner_radius=17,
            fg_color=fg, hover_color=fg, text_color=fg_text,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_ok,
        ).pack(side="right")

    def _on_ok(self) -> None:
        self._result = True
        self.destroy()


class ConflictDialog(_DialogShell):
    """Three-way conflict resolution: overwrite / rename / skip.

    Returns one of: 'overwrite' | 'rename' | 'skip'
    """

    def __init__(self, master, *, dst: str) -> None:
        super().__init__(master, title="文件冲突", width=520, height=240)
        self._result = "skip"

        body = ctk.CTkFrame(self, fg_color=Colors.SURFACE, corner_radius=12)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        ctk.CTkLabel(
            body, text="目标已存在同名文件", anchor="w",
            text_color=Colors.TEXT_DIM,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=16, pady=(16, 4), anchor="w")
        ctk.CTkLabel(
            body, text=dst, wraplength=460, justify="left",
            text_color=Colors.TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).pack(padx=16, pady=(0, 16), anchor="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            btns, text="跳过", width=88, height=34, corner_radius=17,
            fg_color="transparent", border_width=1, border_color=Colors.BORDER,
            text_color=Colors.TEXT_DIM, hover_color=Colors.SURFACE,
            command=lambda: self._finish("skip"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btns, text="重命名", width=96, height=34, corner_radius=17,
            fg_color=Colors.ACCENT, text_color="#1A1A1A", hover_color=Colors.ACCENT,
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._finish("rename"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btns, text="覆盖", width=88, height=34, corner_radius=17,
            fg_color=Colors.REJECTED, text_color="white", hover_color=Colors.REJECTED,
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._finish("overwrite"),
        ).pack(side="right")

    def _finish(self, value: str) -> None:
        self._result = value
        self.destroy()


class ReportDialog(_DialogShell):
    """Read-only report viewer. Shows a scrollable text block."""

    def __init__(self, master, *, title: str, body: str) -> None:
        super().__init__(master, title=title, width=600, height=460)
        self.resizable(True, True)

        ctk.CTkLabel(self, text=title, anchor="w",
                     text_color=Colors.TEXT,
                     font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(padx=16, pady=(16, 4), anchor="w")
        text = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=Colors.SURFACE, border_width=0, corner_radius=8,
            text_color=Colors.TEXT,
        )
        text.pack(fill="both", expand=True, padx=16, pady=8)
        text.insert("1.0", body)
        text.configure(state="disabled")

        ctk.CTkButton(
            self, text="关闭", width=100, height=34, corner_radius=17,
            fg_color=Colors.ACCENT, text_color="#1A1A1A", hover_color=Colors.ACCENT,
            font=ctk.CTkFont(weight="bold"),
            command=self.destroy,
        ).pack(pady=(0, 16))
