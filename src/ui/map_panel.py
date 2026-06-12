"""OpenStreetMap panel that shows photos with GPS coordinates.

Built on tkintermapview (which embeds a tkinter Canvas + tile loader).
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional

import customtkinter as ctk

try:
    from tkintermapview import TkinterMapView
except ImportError:  # pragma: no cover - hard dep
    TkinterMapView = None  # type: ignore[assignment]

from ..config.settings import Colors
from ..models.photo_item import PhotoItem


_MARKER_COLORS = {
    "accepted": Colors.ACCEPTED,
    "rejected": Colors.REJECTED,
    "pending":  Colors.PENDING,
}


class MapPanel(ctk.CTkFrame):
    def __init__(self, master, on_marker_click: Optional[Callable[[PhotoItem], None]] = None, **kw) -> None:
        super().__init__(master, **kw)
        self._on_marker_click = on_marker_click
        self._markers: list = []
        self._items: List[PhotoItem] = []
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(header, text="地图视图 (OpenStreetMap)",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="适配边界", width=100,
                      command=self.fit_bounds).pack(side="right", padx=4)

        if TkinterMapView is None:
            ctk.CTkLabel(self, text="tkintermapview 未安装，地图不可用").pack(pady=20)
            return

        self._map = TkinterMapView(self, corner_radius=0)
        self._map.pack(fill="both", expand=True, padx=8, pady=8)
        # Default view: world view
        self._map.set_zoom(2)
        self._map.set_position(20, 0)

    # -- public API -------------------------------------------------------
    def set_items(self, items: List[PhotoItem]) -> None:
        if TkinterMapView is None:
            return
        # Clear existing markers
        for m in self._markers:
            try:
                m.delete()
            except tk.TclError:
                pass
        self._markers.clear()
        self._items = [it for it in items if it.gps_lat is not None and it.gps_lon is not None]
        for it in self._items:
            color = _MARKER_COLORS.get(it.pick_status, Colors.PENDING)
            marker = self._map.set_marker(
                it.gps_lat, it.gps_lon,
                text=f"{it.basename} ({it.pick_status[0].upper()})",
                marker_color_inverted=color,
                command=lambda m=None, item=it: self._handle_click(item),
            )
            self._markers.append(marker)
        if self._items:
            self.fit_bounds()

    def set_items_by_predicate(self, items: List[PhotoItem],
                               predicate: Optional[Callable[[PhotoItem], bool]] = None) -> None:
        if predicate is None:
            self.set_items(items)
        else:
            self.set_items([it for it in items if predicate(it)])

    def fit_bounds(self) -> None:
        if TkinterMapView is None or not self._items:
            return
        lats = [it.gps_lat for it in self._items if it.gps_lat is not None]
        lons = [it.gps_lon for it in self._items if it.gps_lon is not None]
        if not lats:
            return
        self._map.fit_bounding_box((min(lats), min(lons)), (max(lats), max(lons)))

    # -- internals --------------------------------------------------------
    def _handle_click(self, item: PhotoItem) -> None:
        if self._on_marker_click:
            self._on_marker_click(item)
