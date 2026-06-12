"""Cleaning tab: orphan-only view with safe deletion."""
from __future__ import annotations

import os
import queue
import threading
from typing import Callable, List, Optional

import customtkinter as ctk
from tkinter import filedialog

from ..config.settings import AppConfig, Colors
from ..core.scanner import scan_for_cleaning
from ..models.orphan_item import OrphanItem
from ..utils.image_cache import ImageCache
from ..utils.validators import is_valid_folder, normalize


class CleanTab(ctk.CTkFrame):
    def __init__(
        self,
        master,
        config: AppConfig,
        on_clean: Callable[[List[OrphanItem], str, Optional[str]], object],
        on_show_message: Callable[[str, str], None],
        cache: Optional[ImageCache] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._config = config
        self._cache = cache
        self._on_clean = on_clean
        self._on_show_message = on_show_message
        self._orphans: List[OrphanItem] = []
        self._filter: str = "all"
        self._scan_q: "queue.Queue" = queue.Queue()
        self._scan_poller = None
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top: target folder + scan
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="目标文件夹:", font=ctk.CTkFont(weight="bold")
                     ).grid(row=0, column=0, padx=(12, 6), pady=12, sticky="w")
        self._folder_var = ctk.StringVar()
        self._folder_entry = ctk.CTkEntry(top, textvariable=self._folder_var, width=400,
                                           placeholder_text="选择或粘贴任意文件夹...")
        self._folder_entry.grid(row=0, column=1, padx=4, pady=12, sticky="ew")
        ctk.CTkButton(top, text="浏览", width=80,
                      command=self._browse).grid(row=0, column=2, padx=4, pady=12)
        ctk.CTkButton(top, text="扫描", width=80, fg_color=Colors.ACCENT,
                      command=self.scan).grid(row=0, column=3, padx=4, pady=12)
        self._folder_entry.bind("<Return>", lambda _e: self.scan())
        self._folder_var.trace_add("write", lambda *_: self._update_status())

        # Mode + filter row
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        ctk.CTkLabel(opts, text="模式:").pack(side="left", padx=(8, 4))
        self._mode_var = ctk.StringVar(value=self._config.delete_mode)
        for label, value in (("移到回收 (trash)", "trash"), ("永久删除", "permanent"),
                              ("自建回收文件夹", "recycle")):
            ctk.CTkRadioButton(opts, text=label, variable=self._mode_var, value=value
                               ).pack(side="left", padx=6)

        ctk.CTkLabel(opts, text="筛选:").pack(side="left", padx=(20, 4))
        self._filter_var = ctk.StringVar(value="all")
        for label, value in (("全部孤件", "all"), ("仅 RAW", "raw"), ("仅 JPG", "jpg")):
            ctk.CTkRadioButton(opts, text=label, variable=self._filter_var, value=value,
                               command=self._apply_filter
                               ).pack(side="left", padx=4)

        # Center: orphan list
        self._list = ctk.CTkScrollableFrame(self)
        self._list.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self._list.grid_columnconfigure(0, weight=1)

        # Bottom: action buttons + stats
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(bottom, text="全选", width=80,
                      command=lambda: self._set_selection(True)).pack(side="left", padx=4)
        ctk.CTkButton(bottom, text="全不选", width=80,
                      command=lambda: self._set_selection(False)).pack(side="left", padx=4)
        self._count_lbl = ctk.CTkLabel(bottom, text="", text_color=Colors.TEXT_DIM)
        self._count_lbl.pack(side="left", padx=12)
        ctk.CTkButton(bottom, text="执行清理 (Delete)", width=160,
                      fg_color=Colors.REJECTED,
                      command=self._execute).pack(side="right", padx=4)

        self._status_lbl = ctk.CTkLabel(self, text="", text_color=Colors.TEXT_DIM)
        self._status_lbl.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))
        self._update_status()

    # -- public API --------------------------------------------------------
    def scan(self) -> None:
        folder = self._folder_var.get().strip()
        if not is_valid_folder(folder):
            self._on_show_message("扫描失败", "目标文件夹无效或不存在")
            return
        self._status_lbl.configure(text="扫描中...")
        threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()
        if self._scan_poller is None:
            self._scan_poller = self.after(100, self._poll_scan_queue)

    def _poll_scan_queue(self) -> None:
        try:
            while True:
                kind, *payload = self._scan_q.get_nowait()
                if kind == "done":
                    orphans, folder = payload
                    self._scan_done(orphans, folder)
                elif kind == "error":
                    self._on_show_message("扫描错误", payload[0])
        except queue.Empty:
            pass
        self._scan_poller = self.after(100, self._poll_scan_queue)

    def get_target_folder(self) -> str:
        return normalize(self._folder_var.get())

    def set_focus_to_list(self) -> None:
        if hasattr(self, "_list"):
            self._list.focus_set()

    # -- internals ---------------------------------------------------------
    def _browse(self) -> None:
        path = filedialog.askdirectory(title="选择要清理的文件夹",
                                        initialdir=self.get_target_folder() or os.getcwd())
        if path:
            self._folder_var.set(path)

    def _scan_worker(self, folder: str) -> None:
        try:
            orphans, _ = scan_for_cleaning(folder)
            self._scan_q.put(("done", orphans, folder))
        except Exception as exc:  # noqa: BLE001
            self._scan_q.put(("error", str(exc)))

    def _scan_done(self, orphans: List[OrphanItem], folder: str) -> None:
        self._orphans = orphans
        self._apply_filter()
        self._status_lbl.configure(text=f"扫描完成: {len(orphans)} 个孤件 (folder: {folder})")

    def _apply_filter(self) -> None:
        for w in self._list.winfo_children():
            w.destroy()
        f = self._filter_var.get()
        items = self._orphans if f == "all" else [o for o in self._orphans if o.file_type == f]
        for o in items:
            row = _OrphanRow(self._list, o, on_toggle=self._refresh_count)
            row.pack(fill="x", padx=4, pady=2)
        self._refresh_count()

    def _set_selection(self, value: bool) -> None:
        f = self._filter_var.get()
        for o in self._orphans:
            if f == "all" or o.file_type == f:
                o.selected = value
        self._apply_filter()

    def _refresh_count(self) -> None:
        n = sum(1 for o in self._orphans if o.selected)
        total_mb = sum(o.size_mb for o in self._orphans if o.selected)
        self._count_lbl.configure(text=f"已选 {n} / {len(self._orphans)} 个  ·  共 {total_mb:.1f} MB")

    def _update_status(self) -> None:
        # nothing to do for now; placeholder for inline validation
        pass

    def _execute(self) -> None:
        targets = [o for o in self._orphans if o.selected]
        if not targets:
            self._on_show_message("清理", "未选择任何文件")
            return
        mode = self._mode_var.get()
        target_folder = self.get_target_folder() if mode == "recycle" else None
        self._on_clean(targets, mode, target_folder)


class _OrphanRow(ctk.CTkFrame):
    def __init__(self, master, item: OrphanItem, on_toggle=None) -> None:
        super().__init__(master, fg_color=Colors.SURFACE, corner_radius=4, height=28)
        self.pack_propagate(False)
        self._item = item
        self._on_toggle = on_toggle
        self._var = ctk.BooleanVar(value=item.selected)
        color = Colors.REJECTED if item.file_type == "raw" else Colors.ACCENT
        text = f"[{item.file_type.upper()}]  {item.display_name}   ({item.size_mb} MB)"
        ctk.CTkCheckBox(self, text=text, variable=self._var,
                        text_color=color,
                        command=self._toggle).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(self, text=item.folder, text_color=Colors.TEXT_DIM,
                     font=ctk.CTkFont(size=11), anchor="e").pack(side="right", padx=8)

    def _toggle(self) -> None:
        self._item.selected = self._var.get()
        if self._on_toggle:
            self._on_toggle()
