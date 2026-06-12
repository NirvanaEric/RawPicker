"""Right-hand detail panel: large preview + EXIF + GPS + action buttons.

The preview image is decoded asynchronously (T9) on a worker thread to keep
the UI responsive when the user scrubs through 1500+ photos. Each call to
`show()` increments a request id; only the result matching the latest id
is applied, so a fast A→B click sequence never shows a stale B-image.
"""
from __future__ import annotations

import os
import queue
import threading
from typing import Callable, Optional, Tuple

import customtkinter as ctk

from ..config.settings import Colors
from ..core.metadata_reader import format_exif_for_display
from ..models.photo_item import PhotoItem
from ..utils.image_cache import PreviewCache
from .rating_widget import RatingWidget


class PreviewPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        cache: PreviewCache,
        max_height: int = 600,
        on_rating_change: Optional[Callable[[PhotoItem, int], None]] = None,
        on_pick_change: Optional[Callable[[PhotoItem, str], None]] = None,
        on_jump_to_map: Optional[Callable[[PhotoItem], None]] = None,
        on_double_click: Optional[Callable[[PhotoItem], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._cache = cache
        self._max_h = max_height
        self._on_rating_change = on_rating_change
        self._on_pick_change = on_pick_change
        self._on_jump_to_map = on_jump_to_map
        self._on_double_click = on_double_click
        self._item: Optional[PhotoItem] = None
        self._req_id = 0
        self._decode_q: "queue.Queue[Tuple[int, object]]" = queue.Queue()
        self._build()
        self.after(50, self._poll_decode)

    def _build(self) -> None:
        # Big image preview — surface-coloured canvas with rounded corners,
        # double-click to open the lightbox.
        # Wrapped in a frame with pack_propagate(False) so the image area
        # stays at a fixed height regardless of the loaded photo's aspect.
        self._img_frame = ctk.CTkFrame(
            self, fg_color=Colors.SURFACE, corner_radius=8,
            height=self._max_h,
        )
        self._img_frame.pack(padx=12, pady=(12, 8), fill="x")
        self._img_frame.pack_propagate(False)

        self._image_label = ctk.CTkLabel(
            self._img_frame, text="点击照片查看预览",
            fg_color=Colors.SURFACE,
            text_color=Colors.TEXT_DISABLED,
            font=ctk.CTkFont(size=14),
        )
        self._image_label.pack(fill="both", expand=True)
        self._image_label.bind("<Double-Button-1>", self._handle_image_double)

        # Filename
        self._name_lbl = ctk.CTkLabel(self, text="", anchor="w",
                                      font=ctk.CTkFont(size=15, weight="bold"),
                                      text_color=Colors.TEXT)
        self._name_lbl.pack(padx=14, pady=(0, 6), anchor="w")

        # EXIF key/value table with section header
        self._exif_frame = ctk.CTkFrame(self, fg_color=Colors.SURFACE,
                                         corner_radius=8)
        self._exif_frame.pack(padx=12, pady=4, fill="x")
        header = ctk.CTkLabel(self._exif_frame, text="拍摄信息",
                              anchor="w", text_color=Colors.TEXT_DIM,
                              font=ctk.CTkFont(size=10, weight="bold"))
        header.grid(row=0, column=0, columnspan=4, sticky="ew",
                     padx=10, pady=(8, 2))
        sep = ctk.CTkFrame(self._exif_frame, height=1,
                           fg_color=Colors.BORDER_SUBTLE)
        sep.grid(row=1, column=0, columnspan=4, sticky="ew",
                  padx=10, pady=(0, 4))
        self._exif_rows: list[tuple[ctk.CTkLabel, ctk.CTkLabel]] = []
        for _ in range(8):
            k = ctk.CTkLabel(self._exif_frame, text="", anchor="w",
                             text_color=Colors.TEXT_DIM,
                             font=ctk.CTkFont(size=11))
            v = ctk.CTkLabel(self._exif_frame, text="", anchor="w",
                             text_color=Colors.TEXT,
                             font=ctk.CTkFont(size=11))
            self._exif_rows.append((k, v))
        # Lay out as 2 columns x 8 rows inside the frame
        for idx, (k, v) in enumerate(self._exif_rows):
            r, c = divmod(idx, 2)
            k.grid(row=r + 2, column=2 * c, sticky="w", padx=(10, 4), pady=1)
            v.grid(row=r + 2, column=2 * c + 1, sticky="w", padx=(0, 10), pady=1)
        self._exif_frame.grid_columnconfigure(0, weight=0)
        self._exif_frame.grid_columnconfigure(2, weight=0)
        self._exif_frame.grid_columnconfigure(1, weight=1)
        self._exif_frame.grid_columnconfigure(3, weight=1)

        # GPS / file size info
        self._gps_lbl = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                     text_color=Colors.TEXT_DIM,
                                     font=ctk.CTkFont(size=11))
        self._gps_lbl.pack(padx=14, pady=(4, 2), anchor="w")

        # Action row: pick state pills + rating
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(padx=12, pady=8, fill="x")

        self._btn_accepted = ctk.CTkButton(
            actions, text="  \u2713 接受  A  ", height=30, corner_radius=15,
            fg_color=Colors.ACCEPTED, hover_color=Colors.ACCEPTED,
            text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._emit_pick("accepted"),
        )
        self._btn_rejected = ctk.CTkButton(
            actions, text="  \u2715 删除  D  ", height=30, corner_radius=15,
            fg_color=Colors.REJECTED, hover_color=Colors.REJECTED,
            text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._emit_pick("rejected"),
        )
        self._btn_accepted.pack(side="left", padx=(0, 4), expand=True, fill="x")
        self._btn_rejected.pack(side="left", padx=(4, 0), expand=True, fill="x")

        # Rating row + map jump
        rate_row = ctk.CTkFrame(self, fg_color="transparent")
        rate_row.pack(padx=12, pady=(4, 12), fill="x")
        ctk.CTkLabel(rate_row, text="评分", text_color=Colors.TEXT_DIM,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self._rating = RatingWidget(rate_row, value=0,
                                    on_change=self._emit_rating, size=22)
        self._rating.pack(side="left")
        self._btn_map = ctk.CTkButton(rate_row, text="地图  M", width=84, height=30,
                                      corner_radius=15,
                                      fg_color=Colors.SURFACE_RAISED,
                                      hover_color=Colors.BORDER,
                                      text_color=Colors.TEXT,
                                      state="disabled", command=self._emit_map)
        self._btn_map.pack(side="right")

    # -- public API -----------------------------------------------------
    def show(self, item: Optional[PhotoItem]) -> None:
        self._item = item
        if item is None:
            self._image_label.configure(image=None, text="(未选择)")
            self._name_lbl.configure(text="")
            self._set_exif_rows({})
            self._gps_lbl.configure(text="")
            self._rating.set_value(0)
            self._btn_map.configure(state="disabled")
            return

        # Bump request id so any in-flight decode from a previous selection
        # is discarded when it returns.
        self._req_id += 1
        req_id = self._req_id
        self._image_label.configure(image=None, text="加载中…")
        threading.Thread(target=self._decode_worker,
                         args=(item, req_id), daemon=True).start()

        # Synchronous metadata (cheap, no I/O since we already read EXIF in scan)
        self._name_lbl.configure(text=item.display_name)
        self._set_exif_rows(format_exif_for_display(item.exif))
        size = item.file_size_mb
        if item.gps_lat is not None and item.gps_lon is not None:
            gps = f"GPS  {item.gps_lat:.5f}, {item.gps_lon:.5f}"
            self._btn_map.configure(state="normal")
        else:
            gps = "GPS  无"
            self._btn_map.configure(state="disabled")
        raw_tag = f"  ·  RAW: {item.raw_ext}" if item.has_raw else "  ·  无伴随 RAW"
        self._gps_lbl.configure(text=f"{size} MB{raw_tag}\n{gps}")
        self._rating.set_value(item.rating)

    def refresh_actions(self) -> None:
        """Update only the action button colours when the pick state changes."""
        if not self._item:
            return
        # The pick state is also reflected on the cell badge; nothing to do here.

    # -- internals ------------------------------------------------------
    def _decode_worker(self, item: PhotoItem, req_id: int) -> None:
        if not item.jpg_path or not os.path.isfile(item.jpg_path):
            self._decode_q.put((req_id, None, "(无法读取)"))
            return
        try:
            max_w = max(self.winfo_width() - 24, 200)
            ctk_img = self._cache.get_or_load(item.jpg_path, (max_w, self._max_h))
            self._decode_q.put((req_id, ctk_img, ""))
        except Exception:  # noqa: BLE001
            self._decode_q.put((req_id, None, "(无法读取)"))

    def _poll_decode(self) -> None:
        try:
            while True:
                req_id, ctk_img, fallback_text = self._decode_q.get_nowait()
                if req_id != self._req_id:
                    # Stale result; a newer show() is now in flight.
                    continue
                if ctk_img is not None:
                    self._image_label.configure(image=ctk_img, text="")
                else:
                    self._image_label.configure(image=None, text=fallback_text)
        except queue.Empty:
            pass
        self.after(50, self._poll_decode)

    def _set_exif_rows(self, exif: dict) -> None:
        # Fill the key/value table in display order. Up to 8 rows = 16 fields
        # shown in a 2-col grid.
        items = list(exif.items())[: 2 * len(self._exif_rows)]
        for idx, (k_lbl, v_lbl) in enumerate(self._exif_rows):
            if idx < len(items):
                k, v = items[idx]
                k_lbl.configure(text=k + "  ")
                v_lbl.configure(text=str(v))
            else:
                k_lbl.configure(text="")
                v_lbl.configure(text="")

    def _handle_image_double(self, _event=None) -> None:
        if self._item and self._on_double_click:
            self._on_double_click(self._item)

    def _emit_rating(self, value: int) -> None:
        if self._item and self._on_rating_change:
            self._on_rating_change(self._item, value)

    def _emit_pick(self, status: str) -> None:
        if not self._item or not self._on_pick_change:
            return
        # Toggle: press same status again → revert to pending
        new_status = "pending" if self._item.pick_status == status else status
        self._on_pick_change(self._item, new_status)

    def _emit_map(self) -> None:
        if self._item and self._on_jump_to_map:
            self._on_jump_to_map(self._item)
