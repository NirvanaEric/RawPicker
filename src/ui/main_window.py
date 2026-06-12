"""Top-level main window: TabView + global keyboard routing."""
from __future__ import annotations

from typing import Optional

import customtkinter as ctk
from tkinter import StringVar

from ..config.settings import AppConfig, Colors
from ..utils.image_cache import ImageCache, PreviewCache
from ..utils.thumbnail_loader import ThumbnailLoader
from .clean_tab import CleanTab
from .pick_tab import PickTab
from .rename_tab import RenameTab


class MainWindow(ctk.CTk):
    def __init__(self, config: AppConfig, loader: ThumbnailLoader,
                 preview_cache: PreviewCache, **controller_callbacks) -> None:
        super().__init__()
        self._config = config
        self._loader = loader
        # Kept for back-compat with any code that might still reference it
        self._cache: Optional[ImageCache] = None
        self._preview_cache = preview_cache
        self._cbs = controller_callbacks
        self.title("RawPicker Pro")
        self.geometry("1400x900")
        self.minsize(1100, 700)

        # Apply theme
        ctk.set_appearance_mode("light" if config.theme != "dark" else "dark")
        ctk.set_default_color_theme("blue")

        # Root window colour: must match theme. The default CTk dark grey is
        # very visible at the tab bar edges if we don't override.
        self.configure(fg_color=Colors.BG)

        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Tabs at the top
        self._tabview = ctk.CTkTabview(self, height=40)
        self._tabview.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        self._tabview.add("挑选 (Ctrl+1)")
        self._tabview.add("清理 (Ctrl+2)")
        self._tabview.add("重命名 (Ctrl+3)")

        self._pick_tab = PickTab(
            self._tabview.tab("挑选 (Ctrl+1)"), self._config,
            self._loader, self._preview_cache,
            on_pick_to_b=self._cbs["on_pick_to_b"],
            on_recent_pair=self._cbs["on_recent_pair"],
            on_show_message=self._cbs["on_show_message"],
            on_jump_to_clean=self._cbs["on_jump_to_clean"],
            on_open_lightbox=self._cbs.get("on_open_lightbox"),
        )
        self._pick_tab.pack(fill="both", expand=True)

        self._clean_tab = CleanTab(
            self._tabview.tab("清理 (Ctrl+2)"), self._config,
            on_clean=self._cbs["on_clean"],
            on_show_message=self._cbs["on_show_message"],
        )
        self._clean_tab.pack(fill="both", expand=True)

        self._rename_tab = RenameTab(
            self._tabview.tab("重命名 (Ctrl+3)"),
            on_show_message=self._cbs["on_show_message"],
            on_rename_done=self._cbs["on_rename_done"],
        )
        self._rename_tab.pack(fill="both", expand=True)

        # Tab switching via Ctrl+1/2/3
        self.bind_all("<Control-Key-1>", lambda _e: self._select_tab(0))
        self.bind_all("<Control-Key-2>", lambda _e: self._select_tab(1))
        self.bind_all("<Control-Key-3>", lambda _e: self._select_tab(2))
        # F5 -> scan pick tab
        self.bind_all("<F5>", lambda _e: self._pick_tab.scan())

        # Tab-level shortcuts (only when in pick tab)
        self.bind_all("<Key>", self._on_key)

    # -- public API --------------------------------------------------------
    def pick_tab(self) -> PickTab:
        return self._pick_tab

    def clean_tab(self) -> CleanTab:
        return self._clean_tab

    def rename_tab(self) -> RenameTab:
        return self._rename_tab

    def select_tab(self, name: str) -> None:
        self._tabview.set(name)

    # -- internals ---------------------------------------------------------
    def _select_tab(self, index: int) -> None:
        mapping = {0: "挑选 (Ctrl+1)", 1: "清理 (Ctrl+2)", 2: "重命名 (Ctrl+3)"}
        self._tabview.set(mapping[index])

    def _on_key(self, event) -> None:
        # Skip if user is typing in an Entry
        try:
            widget_class = event.widget.winfo_class()
        except AttributeError:
            return  # event.widget can be a str in rare Tk edge cases
        if widget_class in ("TEntry", "Entry", "CTkEntry", "Text", "CTkTextbox"):
            return
        # Skip if the key event originates from a Toplevel other than
        # the main window (e.g. the Lightbox).  Those windows handle
        # their own keyboard shortcuts; we must not double-process.
        try:
            if event.widget.winfo_toplevel() is not self:
                return
        except Exception:
            pass
        # Active tab
        active = self._tabview.get()
        if active.startswith("挑选"):
            self._handle_pick_key(event)
        # other tabs handle their own keys via focused widgets

    def _handle_pick_key(self, event) -> None:
        ks = event.keysym
        if ks == "space":
            self._pick_tab.toggle_select_current()
            return
        if ks in ("a", "A"):
            cur = self._pick_tab.focused_item()
            if cur:
                new = "pending" if cur.pick_status == "accepted" else "accepted"
                self._pick_tab.set_pick_current(new)
            return
        if ks in ("d", "D"):
            cur = self._pick_tab.focused_item()
            if cur:
                new = "pending" if cur.pick_status == "rejected" else "rejected"
                self._pick_tab.set_pick_current(new)
            return
        if ks in ("1", "2", "3", "4", "5"):
            self._pick_tab.set_rating_current(int(ks)); return
        if ks.lower() == "m" and (event.state & 0x4):  # Ctrl+M
            self._cbs["on_pick_to_b"](self._pick_tab.selected_items())
            return
