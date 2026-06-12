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

import customtkinter as ctk

from ..config.settings import Colors
from ..core.metadata_reader import transpose_image
from ..models.photo_item import PhotoItem
from .rating_widget import RatingWidget

from PIL import Image as PILImage


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
        self._zoom = "fit"   # "fit" | "1:1"
        self._pil_image: "PILImage.Image | None" = None
        self._decode_q: "queue.Queue[Tuple[int, object]]" = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lb")
        self._configure_after_id: Optional[str] = None

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
        top.grid_columnconfigure(2, weight=1)
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
                                       font=ctk.CTkFont(size=13, weight="bold"))
        self._title_lbl.grid(row=0, column=1, padx=4, pady=10, sticky="w")
        self._counter_lbl = ctk.CTkLabel(top, text="", anchor="e",
                                          text_color="#AEAEB2",
                                          font=ctk.CTkFont(size=12))
        self._counter_lbl.grid(row=0, column=2, padx=14, pady=10, sticky="e")
        ctk.CTkButton(
            top, text="\u2715", width=32, height=32, corner_radius=16,
            fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
            text_color=Colors.TEXT, command=self._on_close_request,
        ).grid(row=0, column=3, padx=10, pady=6)

        # Body: image canvas only
        body = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Image area: a CTkLabel that resizes with the window
        self._image_label = ctk.CTkLabel(
            body, text="", fg_color=Colors.LIGHTBOX_BG, text_color=Colors.TEXT_DISABLED,
        )
        self._image_label.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._image_label.bind("<Configure>", self._on_configure)
        self._image_label.bind("<MouseWheel>", self._on_mousewheel)

        # Bottom action bar - matches the dark stage; pill buttons keep
        # their colored backgrounds for action affordance.
        bottom = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, height=72, corner_radius=0)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_propagate(False)

        # Center row: status pills + rating, all packed left in a centred frame
        center_row = ctk.CTkFrame(bottom, fg_color="transparent")
        center_row.pack(expand=True)

        self._btn_accepted = ctk.CTkButton(
            center_row, text="\u2713  A", width=80, height=34, corner_radius=17,
            fg_color=Colors.ACCEPTED, hover_color=Colors.ACCEPTED,
            text_color="white", font=ctk.CTkFont(weight="bold"),
            command=lambda: self._emit_pick("accepted"),
        )
        self._btn_accepted.pack(side="left", padx=(0, 4))

        self._btn_rejected = ctk.CTkButton(
            center_row, text="\u2715  D", width=80, height=34, corner_radius=17,
            fg_color=Colors.REJECTED, hover_color=Colors.REJECTED,
            text_color="white", font=ctk.CTkFont(weight="bold"),
            command=lambda: self._emit_pick("rejected"),
        )
        self._btn_rejected.pack(side="left", padx=(4, 12))

        self._rating = RatingWidget(center_row, value=0, size=22,
                                    on_change=self._emit_rating)
        self._rating.pack(side="left", padx=4)

        # Nav on the right
        nav = ctk.CTkFrame(bottom, fg_color="transparent")
        nav.pack(side="right", padx=14, pady=18)
        ctk.CTkButton(nav, text="\u2190", width=40, height=34, corner_radius=17,
                      fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
                      text_color=Colors.TEXT, command=self._prev
                      ).pack(side="left", padx=2)
        ctk.CTkButton(nav, text="\u2192", width=40, height=34, corner_radius=17,
                      fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
                      text_color=Colors.TEXT, command=self._next
                      ).pack(side="left", padx=2)
        ctk.CTkButton(nav, text="Z  1:1", width=64, height=34, corner_radius=17,
                      fg_color=Colors.SURFACE_RAISED, hover_color=Colors.BORDER,
                      text_color=Colors.TEXT, command=self._toggle_zoom
                      ).pack(side="left", padx=(8, 0))

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
        self._zoom = "1:1" if self._zoom == "fit" else "fit"
        # Re-decode at the appropriate size (worker does the resize for fit)
        self._show_current()

    def _show_current(self) -> None:
        item = self.current_item()
        if item is None:
            self._title_lbl.configure(text="(无照片)")
            self._counter_lbl.configure(text="0 / 0")
            self._image_label.configure(image=None, text="(无照片)")
            return
        self._title_lbl.configure(text=item.display_name)
        self._counter_lbl.configure(text=f"{self._index + 1} / {len(self._items)}")
        self._req_id += 1
        rid = self._req_id
        self._pil_image = None
        self._image_label.configure(image=None, text="加载中…")
        # Compute target size now (main thread) so worker doesn't touch Tk
        iw = max(self._image_label.winfo_width(), 200)
        ih = max(self._image_label.winfo_height(), 200)
        self._pool.submit(self._decode_worker, item, rid, iw, ih, self._zoom)
        self._rating.set_value(item.rating)
        self._update_pick_buttons(item.pick_status)

    def _update_pick_buttons(self, status: str) -> None:
        """Update status badge and button states."""
        # Badge in top-left corner
        if status == "accepted":
            self._status_badge.configure(text="\u2713", fg_color=Colors.ACCEPTED)
        elif status == "rejected":
            self._status_badge.configure(text="\u2715", fg_color=Colors.REJECTED)
        else:
            self._status_badge.configure(text="", fg_color="transparent")
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

    def _decode_worker(self, item: PhotoItem, rid: int,
                       target_w: int, target_h: int, zoom_mode: str) -> None:
        """Decode image at target size on a worker thread.

        In "fit" mode, the image is resized to fit the target area
        (preserving aspect ratio) before being sent to the main thread.
        This moves the expensive LANCZOS resize off the main thread,
        eliminating the primary stutter source.
        """
        if not item.jpg_path or not os.path.isfile(item.jpg_path):
            self._decode_q.put((rid, None))
            return
        try:
            with PILImage.open(item.jpg_path) as im:
                im = transpose_image(im)
                if zoom_mode == "fit":
                    pil_w, pil_h = im.size
                    scale = min(target_w / pil_w, target_h / pil_h)
                    if scale < 1.0:
                        new_w = max(int(pil_w * scale), 1)
                        new_h = max(int(pil_h * scale), 1)
                        im = im.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                # Force full pixel decode while still on worker thread
                im.load()
            self._decode_q.put((rid, im))
        except Exception:  # noqa: BLE001
            self._decode_q.put((rid, None))

    def _poll_decode(self) -> None:
        try:
            while True:
                rid, pil_img = self._decode_q.get_nowait()
                if rid != self._req_id:
                    continue
                if pil_img is not None:
                    self._pil_image = pil_img
                    self._refresh_image()
                else:
                    self._pil_image = None
                    self._image_label.configure(image=None, text="(无法读取)")
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
        """Fire after debounce: re-decode at new size in fit mode."""
        self._configure_after_id = None
        if self._pil_image is None:
            return
        if self._zoom == "fit":
            # Re-decode at the new label size
            self._show_current()
        else:
            # 1:1 mode — just re-wrap, no re-decode needed
            self._refresh_image()

    def _on_mousewheel(self, event) -> None:
        """Scroll wheel toggles fit/1:1 zoom."""
        self._toggle_zoom()

    def _refresh_image(self) -> None:
        """Re-create CTkImage from the stored PIL image at the current size.

        In "fit" mode the image has already been resized by the worker
        thread, so this just wraps it in a CTkImage (cheap). In "1:1"
        mode the image is shown at native resolution.
        """
        self._configure_after_id = None
        if self._pil_image is None:
            return
        try:
            w, h = self._pil_image.size
            from customtkinter import CTkImage
            ctk_img = CTkImage(light_image=self._pil_image, dark_image=self._pil_image, size=(w, h))
            self._image_label.configure(image=ctk_img, text="")
            # prevent GC of the CTkImage
            self._current_ctk_img = ctk_img
        except Exception:  # noqa: BLE001
            pass

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
