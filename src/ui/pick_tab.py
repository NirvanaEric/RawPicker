"""Picking tab: the main photographer-facing workflow.

Layout: [ left sidebar | thumbnail grid + map (toggle) | preview panel ]
"""
from __future__ import annotations

import os
import queue
import threading
from typing import Callable, List, Optional

import customtkinter as ctk

from ..config.settings import AppConfig, Colors
from ..core.metadata_reader import read_metadata
from ..core.scanner import scan_for_picking
from ..models.photo_item import PhotoItem
from ..utils.image_cache import PreviewCache
from ..utils.thumbnail_loader import ThumbnailLoader
from .map_panel import MapPanel
from .preview_panel import PreviewPanel
from .sidebar import Sidebar
from .thumbnail_grid import ThumbnailGrid


class PickTab(ctk.CTkFrame):
    def __init__(
        self,
        master,
        config: AppConfig,
        loader: ThumbnailLoader,
        preview_cache: PreviewCache,
        on_pick_to_b: Callable[[List[PhotoItem]], None],
        on_recent_pair: Callable[[str, str], None],
        on_show_message: Callable[[str, str], None],
        on_jump_to_clean: Callable[[str], None],
        on_open_lightbox: Optional[Callable[[PhotoItem], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._config = config
        self._loader = loader
        self._preview_cache = preview_cache
        self._on_pick_to_b = on_pick_to_b
        self._on_recent_pair = on_recent_pair
        self._on_show_message = on_show_message
        self._on_jump_to_clean = on_jump_to_clean
        self._on_open_lightbox = on_open_lightbox
        self._items: List[PhotoItem] = []
        self._filter: str = "all"
        self._view: str = "grid"  # "grid" | "map"
        # Thread-safe handoff: worker pushes, main thread polls via after().
        self._scan_q: "queue.Queue" = queue.Queue()
        self._scan_poller = None
        self._build()

    def _build(self) -> None:
        # 3-column grid
        self.grid_columnconfigure(0, weight=0, minsize=260)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=400)
        self.grid_rowconfigure(0, weight=1)

        self._sidebar = Sidebar(
            self, self._config,
            on_change_a=self._on_a_changed,
            on_change_b=self._on_b_changed,
            on_scan=self.scan,
            on_filter=self.set_filter,
            on_pick_to_b=self._on_pick_clicked,
            on_refresh=self.scan,
        )
        self._sidebar.grid(row=0, column=0, sticky="nsw", padx=(8, 4), pady=8)

        # Center: view switcher + grid / map
        center = ctk.CTkFrame(self)
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(center, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self._view_var = ctk.StringVar(value="缩略图")
        seg = ctk.CTkSegmentedButton(
            top, values=["缩略图", "地图"], variable=self._view_var,
            command=lambda v: self._switch_view(v),
        )
        seg.pack(side="left")
        self._status_lbl = ctk.CTkLabel(top, text="", text_color=Colors.TEXT_DIM,
                                        font=ctk.CTkFont(size=12))
        self._status_lbl.pack(side="right")

        self._grid = ThumbnailGrid(
            center, self._loader, on_select=self._on_thumb_selected,
            on_double_click=self._on_thumb_double_clicked,
            thumbnail_size=self._config.thumbnail_size,
        )
        self._grid.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

        self._map_panel = MapPanel(center, on_marker_click=self._on_map_marker)
        # Hidden initially

        # Right preview panel
        self._preview = PreviewPanel(
            self, self._preview_cache, max_height=self._config.preview_max_height,
            on_rating_change=self._on_rating,
            on_pick_change=self._on_pick_state,
            on_jump_to_map=lambda _it: self._switch_view("地图"),
            on_double_click=self._on_thumb_double_clicked,
        )
        self._preview.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)

    # -- public API --------------------------------------------------------
    def set_folders(self, folder_a: str, folder_b: str) -> None:
        self._sidebar.set_a(folder_a)
        self._sidebar.set_b(folder_b)

    def get_folders(self) -> tuple[str, str]:
        return self._sidebar.get_a(), self._sidebar.get_b()

    def current_items(self) -> List[PhotoItem]:
        return self._items

    def selected_items(self) -> List[PhotoItem]:
        return [it for it in self._items if it.selected]

    def focused_item(self) -> Optional[PhotoItem]:
        return self._grid.current()

    def set_focus_to_grid(self) -> None:
        self._grid.set_focus_to_grid()

    def refresh(self) -> None:
        self._grid.refresh()
        self._preview.show(self._grid.current())

    def scan(self) -> None:
        folder = self._sidebar.get_a()
        if not folder or not os.path.isdir(folder):
            self._on_show_message("扫描失败", "Folder A 无效或不存在")
            return
        self._status_lbl.configure(text="扫描中...")
        # Run scan + metadata enrichment on a background thread to keep UI alive.
        threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()
        # Make sure the poller is running
        if self._scan_poller is None:
            self._scan_poller = self.after(100, self._poll_scan_queue)

    def _poll_scan_queue(self) -> None:
        try:
            while True:
                kind, payload = self._scan_q.get_nowait()
                if kind == "scan_done":
                    # Phase 1: show thumbnails immediately
                    self._scan_done(payload)
                elif kind == "enriched":
                    # Phase 2: EXIF ready, refresh stats
                    self._update_stats()
                    self._status_lbl.configure(text=f"扫描完成: {len(payload)} 个 JPG")
                elif kind == "error":
                    self._on_show_message("扫描错误", payload)
        except queue.Empty:
            pass
        # Keep polling
        self._scan_poller = self.after(100, self._poll_scan_queue)

    def set_filter(self, value: str) -> None:
        self._filter = value
        self._apply_filter()

    def toggle_select_current(self) -> None:
        cur = self._grid.current()
        if cur is None:
            return
        cur.selected = not cur.selected
        self._grid.refresh()
        self._update_stats()

    def set_rating_current(self, rating: int) -> None:
        cur = self._grid.current()
        if cur is None:
            return
        cur.rating = rating
        self._grid.refresh()
        self._preview.show(cur)

    def set_pick_current(self, status: str) -> None:
        cur = self._grid.current()
        if cur is None:
            return
        cur.pick_status = status
        self._grid.refresh()
        self._update_stats()
        if self._view == "map":
            self._map_panel.set_items(self._filtered_items())

    def jump_to(self, item: PhotoItem) -> bool:
        """Highlight a specific PhotoItem in the grid; switch to grid view."""
        if self._view != "grid":
            self._switch_view("缩略图")
        return self._grid.set_current(item)

    # -- internals ---------------------------------------------------------
    def _scan_worker(self, folder: str) -> None:
        try:
            items = scan_for_picking(folder)
            # Phase 1: push items immediately so the grid shows thumbnails
            # without waiting for EXIF enrichment.
            self._scan_q.put(("scan_done", items))
            # Phase 2: enrich with EXIF + GPS (the slow part).
            for it in items:
                if it.jpg_path and os.path.isfile(it.jpg_path):
                    exif, lat, lon = read_metadata(it.jpg_path)
                    it.exif = exif
                    it.gps_lat, it.gps_lon = lat, lon
            self._scan_q.put(("enriched", items))
        except Exception as exc:  # noqa: BLE001
            self._scan_q.put(("error", str(exc)))

    def _scan_done(self, items: List[PhotoItem]) -> None:
        self._items = items
        self._apply_filter()
        self._update_stats()
        self._status_lbl.configure(text=f"已发现 {len(items)} 张 JPG, 加载 EXIF...")

    def _apply_filter(self) -> None:
        items = self._filtered_items()
        self._grid.set_items(items)
        if self._view == "map":
            self._map_panel.set_items(items)

    def _filtered_items(self) -> List[PhotoItem]:
        f = self._filter
        if f == "all":
            return list(self._items)
        if f == "checked":
            return [it for it in self._items if it.selected]
        if f in ("accepted", "rejected", "pending"):
            return [it for it in self._items if it.pick_status == f]
        if f == "gps":
            return [it for it in self._items if it.gps_lat is not None]
        return list(self._items)

    def _switch_view(self, view: str) -> None:
        self._view = "grid" if view == "缩略图" else "map"
        if self._view == "grid":
            self._map_panel.grid_forget()
            self._grid.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        else:
            self._grid.grid_forget()
            self._map_panel.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
            self._map_panel.set_items(self._filtered_items())

    def _on_thumb_selected(self, item: PhotoItem) -> None:
        self._preview.show(item)

    def _on_thumb_double_clicked(self, item: PhotoItem) -> None:
        # Make sure the preview reflects the active item, then open the lightbox.
        self._preview.show(item)
        if self._on_open_lightbox:
            self._on_open_lightbox(item)

    def _on_map_marker(self, item: PhotoItem) -> None:
        self._switch_view("缩略图")
        self.jump_to(item)
        self._preview.show(item)

    def _on_rating(self, item: PhotoItem, value: int) -> None:
        item.rating = value
        self._grid.refresh()

    def _on_pick_state(self, item: PhotoItem, status: str) -> None:
        item.pick_status = status
        self._grid.refresh()
        self._update_stats()

    def _on_a_changed(self, path: str) -> None:
        self._config.folder_a = path
        if path and self._config.folder_b:
            self._on_recent_pair(path, self._config.folder_b)

    def _on_b_changed(self, path: str) -> None:
        self._config.folder_b = path
        if path and self._config.folder_a:
            self._on_recent_pair(self._config.folder_a, path)

    def _on_pick_clicked(self) -> None:
        # Pass ALL items with a non-pending status (accepted or rejected).
        # The handler separates them and moves accepted → B, deletes rejected.
        action_items = [it for it in self._items if it.pick_status in ("accepted", "rejected")]
        if not action_items:
            self._on_show_message("执行操作", "请先标记照片：A=接受, D=删除 (再按一次取消)")
            return
        # Validate B folder only if there are accepted items
        if any(it.pick_status == "accepted" for it in action_items):
            if not (self._sidebar.get_b() and os.path.isdir(self._sidebar.get_b())):
                self._on_show_message("执行操作", "Folder B 无效或不存在")
                return
        self._on_pick_to_b(action_items)

    def _update_stats(self) -> None:
        total = len(self._items)
        accepted = sum(1 for it in self._items if it.pick_status == "accepted")
        rejected = sum(1 for it in self._items if it.pick_status == "rejected")
        with_raw = sum(1 for it in self._items if it.has_raw)
        self._sidebar.set_stats(total, accepted, rejected, with_raw)
