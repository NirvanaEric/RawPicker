"""Fullscreen lightbox opened by double-clicking a thumbnail.

Lightroom-style: black canvas, the photo centered, small chrome around it.
Reuses PreviewCache so opening a 1:1 preview doesn't decode twice.
"""
from __future__ import annotations

import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Tuple

import tkinter as tk

import customtkinter as ctk

from ..config.settings import Colors
from ..core.metadata_reader import transpose_image
from ..models.photo_item import PhotoItem
from .rating_widget import RatingWidget

from PIL import Image as PILImage
from PIL import ImageTk

_ZOOM_LEVELS = [0.25, 0.50, 1.0, 2.0, 4.0]
_DEFAULT_ZOOM_IDX = 2


class Lightbox(ctk.CTkToplevel):
    """Modal fullscreen viewer for a single PhotoItem.

    Args:
        master:   parent window.
        items:    the full filtered list; navigation wraps around.
        index:    starting position in `items`.
        cache:    PreviewCache instance (shared with the main window).
        on_close: optional callback fired when the user closes the box.
        on_pick_change / on_rating_change: optional callbacks that the user
            triggers from inside the lightbox (e.g. pressing P to mark
            accepted). Wired by the main controller.
    """

    def __init__(
        self,
        master,
        items: List[PhotoItem],
        index: int,
        cache,
        on_close: Optional[Callable[[], None]] = None,
        on_pick_change: Optional[Callable[[PhotoItem, str], None]] = None,
        on_rating_change: Optional[Callable[[PhotoItem, int], None]] = None,
    ) -> None:
        super().__init__(master)
        self._items = list(items)
        self._index = max(0, min(index, len(self._items) - 1))
        self._cache = cache
        self._on_close = on_close
        self._on_pick_change = on_pick_change
        self._on_rating_change = on_rating_change
        self._req_id = 0
        self._zoom_idx = _DEFAULT_ZOOM_IDX
        self._zoom_1_1 = False
        self._pil_image: "PILImage.Image | None" = None
        self._decode_q: "queue.Queue[Tuple[int, object]]" = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lb")
        self._configure_after_id: Optional[str] = None
        self._pil_cache: dict = {}
        self._pil_cache_lock = threading.Lock()
        self._MAX_PIL_CACHE = 5
        self._fit_size: Optional[Tuple[int, int]] = None
        self._pan_enabled = False
        self._canvas_img_id: Optional[int] = None

        # Window setup - keep the lightbox as a dark "stage" for photo
        # evaluation, regardless of the app theme.
        self.title("Lightbox")
        self.configure(fg_color=Colors.LIGHTBOX_BG)
        # Maximize the window to fill the screen
        self.after(10, lambda: self.state("zoomed"))
        self.minsize(720, 520)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self._build()
        self._bind_keys()
        self._show_current()
        self.after(50, self._poll_decode)

    # -- UI construction -------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar - transparent so the dark stage shows through
        top = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, height=44, corner_radius=0)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        top.grid_propagate(False)
        # Status badge (top-left, like the grid)
        self._status_badge = ctk.CTkLabel(
            top, text="", width=28, height=28, corner_radius=14,
            fg_color="transparent", text_color="white",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._status_badge.grid(row=0, column=0, padx=(14, 6), pady=8, sticky="w")
        self._title_lbl = ctk.CTkLabel(top, text="", anchor="w",
                                        text_color="#F5F5F7",
                                        font=ctk.CTkFont(size=15, weight="bold"))
        self._title_lbl.grid(row=0, column=1, padx=4, pady=10, sticky="w")
        ctk.CTkButton(
            top, text="\u2715  关闭 (Esc)", width=90, height=30, corner_radius=15,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
            text_color="#F5F5F7", font=ctk.CTkFont(size=11),
            command=self._on_close_request,
        ).grid(row=0, column=2, padx=10, pady=7)

        # Body: image canvas only
        body = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Image area: tk.Canvas for zoom + drag pan
        self._image_canvas = tk.Canvas(
            body, bg=Colors.LIGHTBOX_BG, highlightthickness=0, relief="flat",
        )
        self._image_canvas.grid(row=0, column=0, sticky="nsew")
        self._image_canvas.bind("<Configure>", self._on_configure)
        self._image_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._image_canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._image_canvas.bind("<B1-Motion>", self._on_drag_move)

        # Status indicator bar (thin colored line below image)
        self._status_bar = ctk.CTkFrame(self, height=2, corner_radius=0,
                                         fg_color="transparent")
        self._status_bar.grid(row=2, column=0, sticky="ew")

        # Bottom action bar - matches the dark stage
        bottom = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, height=60, corner_radius=0)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_propagate(False)

        # Left: status pills + rating
        action_row = ctk.CTkFrame(bottom, fg_color="transparent")
        action_row.pack(side="left", padx=14, pady=13)

        self._btn_accepted = ctk.CTkButton(
            action_row, text="  \u2713 接受  A  ", width=90, height=32, corner_radius=16,
            fg_color=Colors.ACCEPTED, hover_color=Colors.ACCEPTED,
            text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._emit_pick("accepted"),
        )
        self._btn_accepted.pack(side="left", padx=(0, 4))

        self._btn_rejected = ctk.CTkButton(
            action_row, text="  \u2715 删除  D  ", width=90, height=32, corner_radius=16,
            fg_color=Colors.REJECTED, hover_color=Colors.REJECTED,
            text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._emit_pick("rejected"),
        )
        self._btn_rejected.pack(side="left", padx=(4, 12))

        self._rating = RatingWidget(action_row, value=0, size=22,
                                    on_change=self._emit_rating)
        self._rating.pack(side="left", padx=4)

        # Right: counter + nav + zoom
        nav = ctk.CTkFrame(bottom, fg_color="transparent")
        nav.pack(side="right", padx=14, pady=13)

        self._counter_lbl = ctk.CTkLabel(nav, text="", anchor="e",
                                          text_color="#AEAEB2",
                                          font=ctk.CTkFont(size=12))
        self._counter_lbl.pack(side="left", padx=(0, 8))

        ctk.CTkButton(nav, text="\u25C0  上一张", width=90, height=30, corner_radius=15,
                      fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
                      text_color="#F5F5F7", font=ctk.CTkFont(size=11),
                      command=self._prev
                      ).pack(side="left", padx=2)
        ctk.CTkButton(nav, text="下一张  \u25B6", width=90, height=30, corner_radius=15,
                      fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
                      text_color="#F5F5F7", font=ctk.CTkFont(size=11),
                      command=self._next
                      ).pack(side="left", padx=2)
        self._zoom_btn = ctk.CTkButton(
            nav, text="Z  100%", width=64, height=30, corner_radius=15,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
            text_color="#F5F5F7", font=ctk.CTkFont(size=11),
            command=self._toggle_zoom,
        )
        self._zoom_btn.pack(side="left", padx=(4, 0))

    def _bind_keys(self) -> None:
        for ks in ("Escape", "Left", "Right", "a", "A", "d", "D",
                   "space", "z", "Z"):
            self.bind(f"<KeyPress-{ks}>", self._on_key)
        for d in "12345":
            self.bind(f"<KeyPress-{d}>", self._on_key)

    # -- public API ------------------------------------------------------
    def current_item(self) -> Optional[PhotoItem]:
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return None

    # -- internals -------------------------------------------------------
    def _on_key(self, event) -> None:
        ks = event.keysym
        if ks == "Escape":
            self._on_close_request()
        elif ks in ("Right", "space"):
            self._next()
        elif ks == "Left":
            self._prev()
        elif ks.lower() == "a":
            self._emit_pick("accepted")
        elif ks.lower() == "d":
            self._emit_pick("rejected")
        elif ks in ("z", "Z"):
            self._toggle_zoom()
        elif ks in ("1", "2", "3", "4", "5"):
            self._emit_rating(int(ks))

    def _prev(self) -> None:
        if not self._items:
            return
        self._index = (self._index - 1) % len(self._items)
        self._show_current()

    def _next(self) -> None:
        if not self._items:
            return
        self._index = (self._index + 1) % len(self._items)
        self._show_current()

    def _toggle_zoom(self) -> None:
        if self._zoom_1_1:
            self._zoom_1_1 = False
            self._zoom_idx = _DEFAULT_ZOOM_IDX
        else:
            self._zoom_1_1 = True
        self._refresh_image()

    def _show_current(self) -> None:
        item = self.current_item()
        if item is None:
            self._title_lbl.configure(text="(无照片)")
            self._counter_lbl.configure(text="0 / 0")
            self._image_canvas.delete("all")
            self._image_canvas.create_text(
                10, 10, text="(无照片)", fill=Colors.TEXT_DISABLED,
                font=("", 12), anchor="nw")
            return
        self._title_lbl.configure(text=item.display_name)
        self._counter_lbl.configure(text=f"{self._index + 1} / {len(self._items)}")
        self._req_id += 1
        rid = self._req_id
        self._pil_image = None
        self._zoom_idx = _DEFAULT_ZOOM_IDX
        self._zoom_1_1 = False
        self._image_canvas.delete("all")
        self._image_canvas.create_text(
            10, 10, text="加载中…", fill=Colors.TEXT_DISABLED,
            font=("", 12), anchor="nw", tags="loading")
        self._pool.submit(self._decode_worker, item, rid)
        self._rating.set_value(item.rating)
        self._update_pick_buttons(item.pick_status)
        # Pre-decode prev/next into PIL cache
        if len(self._items) > 1:
            self._preload_adjacent()

    def _update_pick_buttons(self, status: str) -> None:
        """Update status badge, status bar, and button states."""
        # Badge in top-left corner
        if status == "accepted":
            self._status_badge.configure(text="\u2713", fg_color=Colors.ACCEPTED)
            self._status_bar.configure(fg_color=Colors.ACCEPTED)
        elif status == "rejected":
            self._status_badge.configure(text="\u2715", fg_color=Colors.REJECTED)
            self._status_bar.configure(fg_color=Colors.REJECTED)
        else:
            self._status_badge.configure(text="", fg_color="transparent")
            self._status_bar.configure(fg_color="transparent")
        # Button states
        if status == "accepted":
            self._btn_accepted.configure(fg_color=Colors.ACCEPTED, text_color="white")
            self._btn_rejected.configure(fg_color="#5C3A3A", text_color="#8E8E93")
        elif status == "rejected":
            self._btn_accepted.configure(fg_color="#3A5C3A", text_color="#8E8E93")
            self._btn_rejected.configure(fg_color=Colors.REJECTED, text_color="white")
        else:
            self._btn_accepted.configure(fg_color=Colors.ACCEPTED, text_color="white")
            self._btn_rejected.configure(fg_color=Colors.REJECTED, text_color="white")

    def _decode_worker(self, item: PhotoItem, rid: int) -> None:
        """Decode full-resolution PIL image on a worker thread.

        The _refresh_image method handles all resizing on the main thread
        (BILINEAR is fast enough for interactive zoom levels).
        """
        path = item.jpg_path
        if not path or not os.path.isfile(path):
            self._decode_q.put((rid, None))
            return
        try:
            pil = self._pil_cache_get(path)
            if pil is None:
                with PILImage.open(path) as im:
                    pil = transpose_image(im)
                    pil.load()
                self._pil_cache_put(path, pil)
            self._decode_q.put((rid, pil))
        except Exception:  # noqa: BLE001
            self._decode_q.put((rid, None))

    def _pil_cache_get(self, path: str):
        with self._pil_cache_lock:
            return self._pil_cache.get(path)

    def _pil_cache_put(self, path: str, pil) -> None:
        with self._pil_cache_lock:
            if len(self._pil_cache) >= self._MAX_PIL_CACHE:
                self._pil_cache.pop(next(iter(self._pil_cache)))
            self._pil_cache[path] = pil

    def _preload_adjacent(self) -> None:
        """Pre-decode prev/next images into the PIL cache."""
        for delta in (-1, 1):
            idx = (self._index + delta) % len(self._items)
            item = self._items[idx]
            p = item.jpg_path
            if p and p not in self._pil_cache and os.path.isfile(p):
                self._pool.submit(self._cache_worker, item)

    def _cache_worker(self, item: PhotoItem) -> None:
        p = item.jpg_path
        if not p or not os.path.isfile(p):
            return
        with self._pil_cache_lock:
            if p in self._pil_cache:
                return
        try:
            with PILImage.open(p) as im:
                pil = transpose_image(im)
                pil.load()
            self._pil_cache_put(p, pil)
        except Exception:  # noqa: BLE001
            pass

    def _poll_decode(self) -> None:
        try:
            while True:
                rid, pil_img = self._decode_q.get_nowait()
                if rid != self._req_id:
                    continue
                if pil_img is not None:
                    self._pil_image = pil_img
                    self._image_canvas.delete("loading")
                    self._refresh_image()
                else:
                    self._pil_image = None
                    self._image_canvas.delete("all")
                    cw = max(self._image_canvas.winfo_width(), 100)
                    ch = max(self._image_canvas.winfo_height(), 100)
                    self._image_canvas.create_text(
                        cw // 2, ch // 2, text="(无法读取)",
                        fill=Colors.TEXT_DISABLED, font=("", 12))
        except queue.Empty:
            pass
        self.after(50, self._poll_decode)

    def _on_configure(self, _event=None) -> None:
        """Debounce <Configure> — avoid repeated resize during window drag."""
        if self._configure_after_id is not None:
            try:
                self.after_cancel(self._configure_after_id)
            except Exception:
                pass
        self._configure_after_id = self.after(100, self._configure_done)

    def _configure_done(self) -> None:
        """Re-fit image after window resize."""
        self._configure_after_id = None
        if self._pil_image is None:
            return
        if not self._zoom_1_1 and self._zoom_idx == _DEFAULT_ZOOM_IDX:
            # Fit mode: recalculate fit_size against new viewport
            self._refresh_image()
        elif self._pan_enabled:
            # Zoomed in: just re-center image in available space
            self._refresh_image()

    def _on_mousewheel(self, event) -> None:
        """Scroll wheel adjusts zoom level."""
        if self._pil_image is None:
            return
        old_idx = self._zoom_idx
        if event.delta > 0:
            self._zoom_idx = min(len(_ZOOM_LEVELS) - 1, self._zoom_idx + 1)
        else:
            self._zoom_idx = max(0, self._zoom_idx - 1)
        if self._zoom_idx != old_idx:
            self._zoom_1_1 = False
            self._refresh_image()

    def _refresh_image(self) -> None:
        """Resize cached PIL to current zoom level and display on canvas."""
        self._configure_after_id = None
        pil = self._pil_image
        if pil is None:
            return
        try:
            canvas = self._image_canvas
            vw = max(canvas.winfo_width(), 20)
            vh = max(canvas.winfo_height(), 20)
            pw, ph = pil.size

            # Compute fit size (image filling viewport while preserving aspect)
            fit_scale = min(vw / pw, vh / ph)
            fit_w = max(int(pw * fit_scale), 1)
            fit_h = max(int(ph * fit_scale), 1)
            self._fit_size = (fit_w, fit_h)

            # Determine display size
            if self._zoom_1_1:
                dw, dh = pw, ph
            else:
                factor = _ZOOM_LEVELS[self._zoom_idx]
                dw = max(int(fit_w * factor), 1)
                dh = max(int(fit_h * factor), 1)

            # Resize (cheap BILINEAR since PIL is cached in memory)
            if (dw, dh) != pil.size:
                display = pil.resize((dw, dh), PILImage.Resampling.BILINEAR)
            else:
                display = pil

            photo = ImageTk.PhotoImage(display)
            self._canvas_img_ref = photo  # prevent GC

            # Clear and rebuild canvas
            canvas.delete("all")

            if dw <= vw and dh <= vh:
                # Image fits viewport: center it
                cx = (vw - dw) // 2
                cy = (vh - dh) // 2
                self._canvas_img_id = canvas.create_image(cx, cy, image=photo, anchor="nw")
                canvas.configure(scrollregion=(0, 0, vw, vh))
                self._pan_enabled = False
            else:
                # Image larger than viewport: enable panning
                self._canvas_img_id = canvas.create_image(0, 0, image=photo, anchor="nw")
                canvas.configure(scrollregion=(0, 0, dw, dh))
                self._pan_enabled = True

            # Zoom label for Z button
            if self._zoom_1_1:
                zoom_text = "1:1"
            else:
                pct = int(_ZOOM_LEVELS[self._zoom_idx] * 100)
                zoom_text = f"{pct}%"
            self._zoom_btn.configure(text=f"Z  {zoom_text}")
        except Exception:  # noqa: BLE001
            pass

    # -- drag panning -----------------------------------------------------
    def _on_drag_start(self, event) -> None:
        if self._pan_enabled:
            self._image_canvas.scan_mark(event.x, event.y)

    def _on_drag_move(self, event) -> None:
        if self._pan_enabled:
            self._image_canvas.scan_dragto(event.x, event.y, gain=1)

    # -- pick / rating / close --------------------------------------------
    def _emit_pick(self, status: str) -> None:
        item = self.current_item()
        if item is None:
            return
        # Toggle: press same key again → revert to pending
        new_status = "pending" if item.pick_status == status else status
        item.pick_status = new_status
        self._update_pick_buttons(new_status)
        if self._on_pick_change:
            self._on_pick_change(item, new_status)

    def _emit_rating(self, value: int) -> None:
        item = self.current_item()
        if item and self._on_rating_change:
            self._on_rating_change(item, value)

    def _on_close_request(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass
        if self._on_close:
            self._on_close()
        self.destroy()
