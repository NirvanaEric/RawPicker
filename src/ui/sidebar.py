"""Left sidebar: Folder A / Folder B inputs, scan button, filters, stats.

Lightroom-inspired compact panel with:
- Card-based folder rows (status dot + path)
- Segmented filter buttons
- Stats card with big tabular numbers
"""
from __future__ import annotations

import os
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import filedialog

from ..config.settings import AppConfig, Colors
from ..utils.validators import is_valid_folder, normalize


class _FolderCard(ctk.CTkFrame):
    """One folder row: label + path entry + browse/scan + status dot."""

    def __init__(self, master, title: str, initial: str,
                 browse_text: str, primary_text: str,
                 primary_color: str,
                 on_browse: Callable[[], None],
                 on_commit: Callable[[str], None],
                 on_primary: Optional[Callable[[], None]] = None,
                 **kw) -> None:
        super().__init__(master, fg_color=Colors.SURFACE, corner_radius=12, **kw)
        # Bottom accent line for depth
        self._accent = ctk.CTkFrame(self, height=1, fg_color=Colors.BORDER)
        self._accent.pack(side="bottom", fill="x", padx=12, pady=(0, 1))
        # Title row
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.pack(fill="x", padx=12, pady=(10, 4))
        self._dot = ctk.CTkLabel(title_row, text="●", width=14,
                                 text_color=Colors.TEXT_DIM,
                                 font=ctk.CTkFont(size=14))
        self._dot.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(title_row, text=title, anchor="w",
                     text_color=Colors.TEXT,
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).pack(side="left")
        # Path entry
        self._var = ctk.StringVar(value=initial)
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var, height=30, corner_radius=6,
            fg_color=Colors.BG, border_width=1, border_color=Colors.BORDER_SUBTLE,
            text_color=Colors.TEXT, placeholder_text="选择文件夹...",
        )
        self._entry.pack(fill="x", padx=12, pady=2)
        self._entry.bind("<FocusOut>", lambda _e: on_commit(self.get()))
        self._entry.bind("<Return>", lambda _e: on_commit(self.get()))
        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 4))
        ctk.CTkButton(btn_row, text=browse_text, width=72, height=28,
                      corner_radius=8, fg_color=Colors.SURFACE_RAISED,
                      hover_color=Colors.BORDER, text_color=Colors.TEXT,
                      command=on_browse).pack(side="left", padx=(0, 4))
        if on_primary:
            ctk.CTkButton(btn_row, text=primary_text, width=0, height=28,
                          corner_radius=8, fg_color=primary_color,
                          hover_color=Colors.ACCENT_HOVER,
                          text_color="white", font=ctk.CTkFont(weight="bold"),
                          command=on_primary
                          ).pack(side="left", expand=True, fill="x")
        # Status line
        self._status = ctk.CTkLabel(self, text="", anchor="w",
                                    text_color=Colors.TEXT_DIM,
                                    font=ctk.CTkFont(size=11))
        self._status.pack(padx=12, pady=(0, 10), anchor="w")

    def get(self) -> str:
        return normalize(self._var.get())

    def set(self, path: str) -> None:
        self._var.set(path)
        self._update()

    def _update(self) -> None:
        path = self.get()
        if path and is_valid_folder(path):
            self._dot.configure(text_color=Colors.ACCEPTED)
            self._status.configure(text=f"✓ {path}", text_color=Colors.ACCEPTED)
        else:
            self._dot.configure(text_color=Colors.REJECTED)
            self._status.configure(text="✗ 路径无效或为空", text_color=Colors.REJECTED)

    def refresh(self) -> None:
        self._update()


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        master,
        config: AppConfig,
        on_change_a: Callable[[str], None],
        on_change_b: Callable[[str], None],
        on_scan: Callable[[], None],
        on_filter: Callable[[str], None],
        on_pick_to_b: Callable[[], None],
        on_refresh: Callable[[], None],
        **kw,
    ) -> None:
        super().__init__(master, width=260, fg_color="transparent", **kw)
        self._config = config
        self._on_change_a = on_change_a
        self._on_change_b = on_change_b
        self._on_scan = on_scan
        self._on_filter = on_filter
        self._on_pick_to_b = on_pick_to_b
        self._on_refresh = on_refresh
        self._build()

    def _build(self) -> None:
        # Folder A
        self._a_card = _FolderCard(
            self, title="素材库  A", initial=self._config.folder_a,
            browse_text="浏览", primary_text="扫描  F5",
            primary_color=Colors.ACCENT,
            on_browse=self._browse_a, on_commit=self._commit_a,
            on_primary=self._on_scan,
        )
        self._a_card.pack(fill="x", padx=12, pady=(12, 8))

        # Folder B
        self._b_card = _FolderCard(
            self, title="结果  B", initial=self._config.folder_b,
            browse_text="浏览", primary_text="执行操作  Ctrl+M",
            primary_color=Colors.ACCENT,
            on_browse=self._browse_b, on_commit=self._commit_b,
            on_primary=self._on_pick_to_b,
        )
        self._b_card.pack(fill="x", padx=12, pady=(0, 8))

        # Refresh button (subtle)
        ctk.CTkButton(
            self, text="刷新  R", width=0, height=30, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=Colors.BORDER,
            text_color=Colors.TEXT_DIM, hover_color=Colors.SURFACE,
            command=self._on_refresh,
        ).pack(fill="x", padx=12, pady=(0, 12))

        # Filter as segmented control
        ctk.CTkLabel(self, text="筛选", anchor="w",
                     text_color=Colors.TEXT_DIM,
                     font=ctk.CTkFont(size=11, weight="bold")
                     ).pack(padx=16, pady=(4, 2), anchor="w")
        self._filter_var = ctk.StringVar(value="all")
        self._filter_seg = ctk.CTkSegmentedButton(
            self, values=["全部", "A", "D", "GPS"],
            command=self._on_seg_filter,
            height=28, corner_radius=14,
            selected_color=Colors.ACCENT,
            selected_hover_color=Colors.ACCENT_HOVER,
            unselected_color=Colors.SURFACE,
            unselected_hover_color=Colors.SURFACE_RAISED,
            text_color=Colors.TEXT,
        )
        self._filter_seg.set("全部")
        self._filter_seg.pack(fill="x", padx=12, pady=(0, 12))

        # Stats card
        stats_card = ctk.CTkFrame(self, fg_color=Colors.SURFACE, corner_radius=12)
        stats_card.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(stats_card, text="统计", anchor="w",
                     text_color=Colors.TEXT_DIM,
                     font=ctk.CTkFont(size=11, weight="bold")
                     ).pack(padx=14, pady=(10, 4), anchor="w")
        self._stats_frames: list[ctk.CTkFrame] = []
        for label, color in [("总文件", Colors.TEXT),
                              ("接受 (A)", Colors.ACCEPTED),
                              ("删除 (D)", Colors.REJECTED),
                              ("伴随 RAW", Colors.ACCENT)]:
            row = ctk.CTkFrame(stats_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            dot = ctk.CTkLabel(row, text="●", width=12,
                               text_color=color, font=ctk.CTkFont(size=9))
            dot.pack(side="left", padx=(0, 4))
            ctk.CTkLabel(row, text=label, anchor="w",
                         text_color=Colors.TEXT_DIM,
                         font=ctk.CTkFont(size=11)).pack(side="left")
            val = ctk.CTkLabel(row, text="—", anchor="e",
                               text_color=Colors.TEXT,
                               font=ctk.CTkFont(size=14, weight="bold"))
            val.pack(side="right")
            self._stats_frames.append(val)
        self._stats_extra = ctk.CTkLabel(
            stats_card, text="", anchor="w",
            text_color=Colors.TEXT_DIM, font=ctk.CTkFont(size=10))
        self._stats_extra.pack(padx=14, pady=(2, 10), anchor="w")

        # Recent
        if self._config.recent_paths:
            ctk.CTkLabel(self, text="最近", anchor="w",
                         text_color=Colors.TEXT_DIM,
                         font=ctk.CTkFont(size=11, weight="bold")
                         ).pack(padx=16, pady=(12, 2), anchor="w")
            for a, b in self._config.recent_paths[:3]:
                short = f"{os.path.basename(a.rstrip('/\\\\')) or a}  →  {os.path.basename(b.rstrip('/\\\\')) or b}"
                ctk.CTkButton(
                    self, text=short[:34], anchor="w", height=28,
                    corner_radius=8, fg_color="transparent",
                    border_width=1, border_color=Colors.BORDER,
                    text_color=Colors.TEXT_DIM,
                    hover_color=Colors.SURFACE,
                    command=lambda A=a, B=b: self._apply_recent(A, B),
                ).pack(fill="x", padx=12, pady=1)

    # -- public API -------------------------------------------------------
    def get_a(self) -> str:
        return self._a_card.get()

    def get_b(self) -> str:
        return self._b_card.get()

    def set_a(self, path: str) -> None:
        self._a_card.set(path)

    def set_b(self, path: str) -> None:
        self._b_card.set(path)

    def set_stats(self, total: int, accepted: int, rejected: int,
                  with_raw: int) -> None:
        values = [str(total), str(accepted), str(rejected), str(with_raw)]
        for lbl, v in zip(self._stats_frames, values):
            lbl.configure(text=v)
        pending = total - accepted - rejected
        self._stats_extra.configure(text=f"待处理 {pending}")

    # -- internals --------------------------------------------------------
    def _on_seg_filter(self, label: str) -> None:
        mapping = {"全部": "all", "A": "accepted",
                   "D": "rejected", "GPS": "gps"}
        value = mapping.get(label, "all")
        self._on_filter(value)

    def _browse_a(self) -> None:
        path = filedialog.askdirectory(title="选择 Folder A", initialdir=self.get_a() or os.getcwd())
        if path:
            self._a_card.set(path)
            self._commit_a()

    def _browse_b(self) -> None:
        path = filedialog.askdirectory(title="选择 Folder B", initialdir=self.get_b() or os.getcwd())
        if path:
            self._b_card.set(path)
            self._commit_b()

    def _commit_a(self) -> None:
        path = self.get_a()
        self._on_change_a(path)

    def _commit_b(self) -> None:
        path = self.get_b()
        self._on_change_b(path)

    def _apply_recent(self, a: str, b: str) -> None:
        self._a_card.set(a)
        self._b_card.set(b)
        self._commit_a()
        self._commit_b()
