"""Renaming tab: template-based batch rename."""
from __future__ import annotations

import os
import queue
import threading
from typing import Callable, List, Optional

import customtkinter as ctk
from tkinter import filedialog

from ..config.settings import Colors
from ..core.renamer_engine import preview_renames, rename_items
from ..core.scanner import scan_for_picking
from ..models.photo_item import PhotoItem


class RenameTab(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_show_message: Callable[[str, str], None],
        on_rename_done: Callable[[], None],
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._on_show_message = on_show_message
        self._on_rename_done = on_rename_done
        self._items: List[PhotoItem] = []
        self._scope: str = "all"  # "all" | "checked"
        self._scan_q: "queue.Queue" = queue.Queue()
        self._scan_poller = None
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Folder + scope
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="文件夹:", font=ctk.CTkFont(weight="bold")
                     ).grid(row=0, column=0, padx=(12, 6), pady=12, sticky="w")
        self._folder_var = ctk.StringVar()
        self._folder_entry = ctk.CTkEntry(top, textvariable=self._folder_var, width=400,
                                           placeholder_text="选择或粘贴文件夹...")
        self._folder_entry.grid(row=0, column=1, padx=4, pady=12, sticky="ew")
        ctk.CTkButton(top, text="浏览", width=80,
                      command=self._browse).grid(row=0, column=2, padx=4, pady=12)
        ctk.CTkButton(top, text="扫描", width=80, fg_color=Colors.ACCENT,
                      command=self.scan).grid(row=0, column=3, padx=4, pady=12)
        self._folder_entry.bind("<Return>", lambda _e: self.scan())

        # Scope + template
        opt = ctk.CTkFrame(self, fg_color="transparent")
        opt.grid(row=1, column=0, sticky="ew", padx=8)
        ctk.CTkLabel(opt, text="范围:").pack(side="left", padx=(8, 4))
        self._scope_var = ctk.StringVar(value="all")
        ctk.CTkRadioButton(opt, text="全部", variable=self._scope_var, value="all",
                           command=self._refresh_preview
                           ).pack(side="left", padx=4)
        ctk.CTkRadioButton(opt, text="仅已勾选", variable=self._scope_var, value="checked",
                           command=self._refresh_preview
                           ).pack(side="left", padx=4)

        ctk.CTkLabel(opt, text="模板:").pack(side="left", padx=(20, 4))
        self._template_var = ctk.StringVar(value="{basename}_{seq:03d}")
        self._template_entry = ctk.CTkEntry(opt, textvariable=self._template_var, width=260)
        self._template_entry.pack(side="left", padx=4)
        self._template_var.trace_add("write", lambda *_: self._refresh_preview())

        # Variables cheat sheet
        ctk.CTkLabel(
            self, anchor="w", justify="left",
            text_color=Colors.TEXT_DIM,
            text=("可用变量: {basename}  {seq}  {seq:03d}  {rating}  {date}  {camera}"),
        ).grid(row=2, column=0, sticky="ew", padx=12)

        # Preview area
        preview_box = ctk.CTkFrame(self)
        preview_box.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        preview_box.grid_columnconfigure(0, weight=1)
        preview_box.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(preview_box, text="预览 (前 5 项)", anchor="w",
                     font=ctk.CTkFont(weight="bold")
                     ).grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")
        self._preview = ctk.CTkTextbox(preview_box, font=ctk.CTkFont(family="Consolas", size=12))
        self._preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Action row
        action = ctk.CTkFrame(self, fg_color="transparent")
        action.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        self._count_lbl = ctk.CTkLabel(action, text="", text_color=Colors.TEXT_DIM)
        self._count_lbl.pack(side="left", padx=8)
        ctk.CTkButton(action, text="执行重命名 (Ctrl+R)", width=180, fg_color=Colors.ACCENT,
                      command=self._execute).pack(side="right", padx=4)

    # -- public API --------------------------------------------------------
    def scan(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            self._on_show_message("扫描失败", "文件夹无效或不存在")
            return
        threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()
        if self._scan_poller is None:
            self._scan_poller = self.after(100, self._poll_scan_queue)

    def _poll_scan_queue(self) -> None:
        try:
            while True:
                kind, *payload = self._scan_q.get_nowait()
                if kind == "done":
                    self._scan_done(payload[0])
                elif kind == "error":
                    self._on_show_message("扫描错误", payload[0])
        except queue.Empty:
            pass
        self._scan_poller = self.after(100, self._poll_scan_queue)

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="选择文件夹", initialdir=self._folder_var.get() or os.getcwd())
        if path:
            self._folder_var.set(path)

    def _scan_worker(self, folder: str) -> None:
        try:
            items = scan_for_picking(folder)
            self._scan_q.put(("done", items))
        except Exception as exc:  # noqa: BLE001
            self._scan_q.put(("error", str(exc)))

    def _scan_done(self, items: List[PhotoItem]) -> None:
        self._items = items
        self._refresh_preview()
        self._count_lbl.configure(text=f"共 {len(items)} 个 JPG")

    def _active_items(self) -> List[PhotoItem]:
        if self._scope_var.get() == "checked":
            return [it for it in self._items if it.selected]
        return list(self._items)

    def _refresh_preview(self) -> None:
        template = self._template_var.get()
        items = self._active_items()
        try:
            preview = preview_renames(items, template, limit=5)
        except Exception as exc:  # noqa: BLE001
            self._preview.delete("1.0", "end")
            self._preview.insert("1.0", f"模板错误: {exc}")
            return
        body = "\n".join(f"{old}  ->  {new}" for old, new in preview) or "(无文件)"
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", body)
        self._count_lbl.configure(text=f"将处理 {len(items)} 个文件")

    def _execute(self) -> None:
        items = self._active_items()
        if not items:
            self._on_show_message("重命名", "没有可重命名的文件")
            return
        template = self._template_var.get()
        folder = self._folder_var.get().strip()
        result = rename_items(items, template, folder)
        self._on_show_message("重命名报告", result.as_text())
        self._on_rename_done()
        self._scan_done([])
        self._items = scan_for_picking(folder)
        self._refresh_preview()
