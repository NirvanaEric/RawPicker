"""Thumbnail grid for the picking workflow.

A single Tk Canvas draws the entire grid as canvas items (rectangles,
images, text). One widget, regardless of photo count. The Tk Canvas is
implemented in C; drawing 1000 cells is ~50× faster than creating 1000
widget trees, and the main thread stays well under one frame.

Perf characteristics:
- One `tk.Canvas` widget holds the entire grid.
- Cell "shells" are canvas items, not widgets: no per-cell CTkFrame.
- Thumbnail decode runs on a `ThumbnailLoader` worker pool; the main
  thread only assigns the already-decoded image to an existing canvas
  image item via `itemconfig(image=...)`. Per-cell `image_ref` keeps the
  `CTkImage` alive.
- `<Configure>` debounced (150ms) so dragging the window edge doesn't
  rebuild on every pixel.
- Relayout is skipped if the column count didn't change.
- Generation counter cancels in-flight decodes when `set_items` is
  called again (the loader drops callbacks for the previous generation).

Visual style (Apple Photos light):
- 8px corner radius simulated via square cells + 1px BORDER outline.
- Selected: 2px ACCENT border + ACCENT_SOFT background.
- Hover (unselected): SURFACE_RAISED background.
- Placeholder: SURFACE solid + TEXT_DISABLED hourglass glyph.
- Pill badges: ACCENT/ACCEPTED/REJECTED, white text.

Public API (unchanged from the widget-based version, so callers don't
need to know about the rewrite):
- `set_items(items)`, `items()`, `current()`, `set_current(item)`,
  `set_thumbnail_size(size)`, `refresh()`, `set_focus_to_grid()`.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from ..config.settings import Colors
from ..models.photo_item import PhotoItem
from ..utils.thumbnail_loader import ThumbnailLoader


_DEBOUNCE_MS = 150
_POLL_INTERVAL_MS = 20
_BG_DRAIN_INTERVAL_MS = 80   # interval for background decode drain
_BG_DRAIN_BATCH = 2          # cells per background tick
_CELL_PAD = 8
_CAPTION_H = 18        # filename strip below the thumbnail
_BADGE_SIZE = 18       # size of pick / raw-missing badge
_BADGE_FONT = ("", 11, "bold")


@dataclass
class _Cell:
    """One cell's worth of canvas items, plus the data needed to refresh it."""
    index: int
    item: PhotoItem
    bg: int = 0              # background rectangle
    border: int = 0         # selection border (hidden when not selected)
    image: int = 0          # image item (state=hidden until loaded)
    image_ref: Any = None   # CTkImage; held to prevent GC
    name: int = 0           # filename text
    badge: int = 0          # pick status pill (P / X / U)
    raw_warn: int = 0       # "RAW?" pill when no companion
    rating_glyphs: List[int] = field(default_factory=list)  # 5 star shapes
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)  # bbox in canvas coords
    state: str = "placeholder"  # "placeholder" | "loaded" | "error"


class ThumbnailGrid(ctk.CTkFrame):
    """Single-canvas thumbnail grid."""

    def __init__(
        self,
        master,
        loader: ThumbnailLoader,
        on_select: Callable[[PhotoItem], None],
        on_double_click: Optional[Callable[[PhotoItem], None]] = None,
        thumbnail_size: int = 160,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._loader = loader
        self._on_select = on_select
        self._on_double_click = on_double_click
        self._size = max(64, int(thumbnail_size))
        self._items: List[PhotoItem] = []
        self._cells: List[_Cell] = []
        self._current_index: int = -1
        self._hover_index: int = -1
        self._generation = 0
        self._col_count = 1
        self._debounce_id: Optional[str] = None
        self._poll_id: Optional[str] = None
        self._bg_drain_id: Optional[str] = None
        self._pending_decode: set = set()  # indices awaiting decode submit
        self._image_cache: dict = {}  # (path, size) → PIL.Image (survives relayout)

        self._build_canvas()
        self._bind_events()

    # -- public API -------------------------------------------------------
    def set_thumbnail_size(self, size: int) -> None:
        new_size = max(64, int(size))
        if new_size == self._size:
            return
        self._size = new_size
        self._request_relayout()

    def set_items(self, items: List[PhotoItem]) -> None:
        self._items = list(items)
        self._current_index = 0 if items else -1
        self._generation += 1
        # Cancel any in-flight decodes for the previous generation so their
        # callbacks won't try to itemconfig a cell that's about to disappear.
        gen_to_cancel = self._generation - 1
        if gen_to_cancel >= 0 and hasattr(self._loader, "cancel_generation"):
            self._loader.cancel_generation(gen_to_cancel)
        # Cancel background drain from previous generation
        if self._bg_drain_id is not None:
            try:
                self.after_cancel(self._bg_drain_id)
            except Exception:
                pass
            self._bg_drain_id = None
        self._pending_decode.clear()
        self._image_cache.clear()  # new item set → invalidate cache
        self._cells.clear()  # force rebuild on _do_relayout
        self._request_relayout()

    def items(self) -> List[PhotoItem]:
        return list(self._items)

    def current(self) -> Optional[PhotoItem]:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    def set_current(self, item: PhotoItem) -> bool:
        for i, it in enumerate(self._items):
            if it is item:
                self._current_index = i
                self._refresh_selection()
                self._scroll_into_view(i)
                return True
        return False

    def refresh(self) -> None:
        """Re-apply badge / rating / selection visuals to all cells.

        Cheap: only changes canvas itemconfig for affected items, no rebuild.
        """
        for i, cell in enumerate(self._cells):
            self._apply_cell_state(cell)
        self._refresh_selection()
        self._refresh_hover()

    def set_focus_to_grid(self) -> None:
        self._canvas.focus_set()

    # -- construction -----------------------------------------------------
    def _build_canvas(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # CTkScrollbar is themed; tk.Canvas does the actual drawing.
        self._canvas = tk.Canvas(
            self, bg=Colors.BG, highlightthickness=0, borderwidth=0,
            takefocus=1,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = ctk.CTkScrollbar(self, command=self._canvas.yview)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

    def _bind_events(self) -> None:
        c = self._canvas
        c.bind("<Configure>", lambda _e: (self._request_relayout(), self._on_scroll_visible()))
        c.bind("<Button-1>", self._on_click)
        c.bind("<Double-Button-1>", self._on_double)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda _e: self._on_motion_leave())
        # Wheel: Windows / macOS use MouseWheel; X11 uses Button-4 / 5
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Button-4>", lambda _e: self._canvas.yview_scroll(-1, "units"))
        c.bind("<Button-5>", lambda _e: self._canvas.yview_scroll(1, "units"))
        # Arrow key navigation. Bind on the underlying tk canvas (CTk forbids
        # bind_all). The grid still gets the events when the canvas or any
        # descendant has focus.
        c.bind_all("<KeyPress-Up>", self._on_arrow)
        c.bind_all("<KeyPress-Down>", self._on_arrow)
        c.bind_all("<KeyPress-Left>", self._on_arrow)
        c.bind_all("<KeyPress-Right>", self._on_arrow)

    # -- relayout machinery ----------------------------------------------
    def _request_relayout(self) -> None:
        if self._debounce_id is not None:
            try:
                self.after_cancel(self._debounce_id)
            except Exception:
                pass
        self._debounce_id = self.after(_DEBOUNCE_MS, self._do_relayout)

    def _do_relayout(self) -> None:
        self._debounce_id = None
        if not self._items:
            # Nothing to show. Wipe the canvas and bail.
            self._canvas.delete("all")
            self._cells.clear()
            self._canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        cw = self._canvas.winfo_width()
        avail = max(cw - 16, self._size + _CELL_PAD * 2 + 8)
        new_cols = max(1, avail // (self._size + _CELL_PAD * 2))
        # Column count unchanged AND we still have cells -> skip rebuild.
        if new_cols == self._col_count and self._cells:
            return
        # Rebuild from scratch.
        self._canvas.delete("all")
        self._cells.clear()
        self._col_count = new_cols
        self._render_all_cells()
        self._ensure_poller()

    def _render_all_cells(self) -> None:
        """Create canvas item shells for every photo, decode only visible cells."""
        pad = _CELL_PAD
        cell_w = self._size + pad * 2
        cell_h = self._size + pad * 2 + _CAPTION_H
        for idx, item in enumerate(self._items):
            r, c = divmod(idx, self._col_count)
            x1 = c * cell_w + pad
            y1 = r * cell_h + pad
            x2 = x1 + self._size + pad
            y2 = y1 + self._size + pad

            bg = self._canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=Colors.SURFACE, outline=Colors.BORDER, width=1,
            )
            border = self._canvas.create_rectangle(
                x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                outline=Colors.ACCENT, width=2, state="hidden",
            )
            image = self._canvas.create_image(
                (x1 + x2) // 2, (y1 + y2) // 2, anchor="center",
                state="hidden",
            )
            name = self._canvas.create_text(
                x1 + pad, y2 + 4, text=item.display_name,
                fill=Colors.TEXT_DIM, font=("", 10), anchor="nw",
            )
            cell = _Cell(
                index=idx, item=item, bg=bg, border=border, image=image,
                image_ref=None, name=name, badge=0, raw_warn=0,
                rating_glyphs=[], rect=(x1, y1, x2, y2),
                state="placeholder",
            )
            self._cells.append(cell)

        # Scrollregion = total height of the grid
        rows = (len(self._items) + self._col_count - 1) // self._col_count
        total_h = rows * cell_h + pad
        self._canvas.configure(scrollregion=(0, 0, max(self._canvas.winfo_width(), 200), total_h))

        # Initial visual pass
        for cell in self._cells:
            self._apply_cell_state(cell)
        self._refresh_selection()

        # Submit decode jobs: visible cells first, rest via background drain.
        # Reuse cached images from previous relayout (e.g. window resize).
        self._pending_decode = set()
        for idx, cell in enumerate(self._cells):
            cache_key = (cell.item.jpg_path, self._size)
            cached = self._image_cache.get(cache_key)
            if cached is not None:
                # Apply cached image immediately — no worker needed.
                try:
                    photo = ImageTk.PhotoImage(cached)
                    cell.image_ref = photo
                    self._canvas.itemconfig(cell.image, image=photo, state="normal")
                    cell.state = "loaded"
                except Exception:
                    cell.state = "error"
            else:
                self._pending_decode.add(idx)
        self._submit_visible_decode()
        self._start_bg_drain()

    def _submit_visible_decode(self) -> None:
        """Submit decode jobs for cells currently visible in the viewport."""
        if not self._cells or not self._pending_decode:
            return
        yview = self._canvas.yview()
        if not yview or yview[1] - yview[0] <= 0:
            return
        total = self._canvas.bbox("all")
        if not total:
            return
        _, _, _, total_h = total
        if total_h <= 0:
            return
        top_px = yview[0] * total_h
        bot_px = yview[1] * total_h
        margin = 80
        to_submit = []
        for idx in list(self._pending_decode):
            cell = self._cells[idx]
            _, cy1, _, cy2 = cell.rect
            if cy2 >= top_px - margin and cy1 <= bot_px + margin:
                to_submit.append(idx)
        for idx in to_submit:
            self._pending_decode.discard(idx)
            cell = self._cells[idx]
            item = cell.item
            if item.jpg_path and self._loader is not None:
                self._loader.submit(
                    item.jpg_path, self._size,
                    on_ready=self._make_apply(cell),
                    generation=self._generation,
                )

    def _on_scroll_visible(self) -> None:
        """Called on scroll/resize: submit decode for newly visible cells."""
        self._submit_visible_decode()

    def _start_bg_drain(self) -> None:
        """Start background drain of remaining decode jobs (2 per tick)."""
        if self._bg_drain_id is not None:
            return
        self._bg_drain()

    def _bg_drain(self) -> None:
        """Submit a small batch of remaining decode jobs per tick."""
        if not self._pending_decode:
            self._bg_drain_id = None
            return
        batch = 0
        while self._pending_decode and batch < _BG_DRAIN_BATCH:
            idx = self._pending_decode.pop()
            cell = self._cells[idx]
            item = cell.item
            if item.jpg_path and self._loader is not None:
                self._loader.submit(
                    item.jpg_path, self._size,
                    on_ready=self._make_apply(cell),
                    generation=self._generation,
                )
            batch += 1
        if self._pending_decode:
            self._bg_drain_id = self.after(_BG_DRAIN_INTERVAL_MS, self._bg_drain)
        else:
            self._bg_drain_id = None

    def _make_apply(self, cell: _Cell) -> Callable[[Any], None]:
        """Closure for the loader to call with the decoded image.

        Captures the current generation so a stale result (after a
        `set_items()` swap) can no-op without crashing the canvas.
        """
        gen = self._generation
        cell_gen = cell.index  # also captured for paranoia
        del cell_gen

        def apply(pil_img: Optional[Image.Image]) -> None:
            if gen != self._generation:
                return  # cancelled; cell is gone or replaced
            try:
                if pil_img is None:
                    cell.state = "error"
                    # Mark the cell with a tiny ⚠ so the user knows
                    self._canvas.itemconfig(cell.bg, outline=Colors.REJECTED, width=2)
                    return
                # Cache the PIL image so relayout can reuse it instantly.
                cache_key = (cell.item.jpg_path, self._size)
                self._image_cache[cache_key] = pil_img
                # PIL image is already resized to (size, size) on the worker.
                photo = ImageTk.PhotoImage(pil_img)
                cell.image_ref = photo
                self._canvas.itemconfig(cell.image, image=photo, state="normal")
                cell.state = "loaded"
            except Exception:
                cell.state = "error"

        return apply

    # -- per-cell visual refresh ----------------------------------------
    def _apply_cell_state(self, cell: _Cell) -> None:
        """Redraw badges / rating for one cell from its current PhotoItem."""
        item = cell.item
        x1, y1, x2, y2 = cell.rect
        # Remove old badge / rating items (they were created in a previous
        # _apply_cell_state call). We don't try to update them in place —
        # the pill geometry is tiny and a fresh create is cheap.
        for old in (cell.badge, cell.raw_warn):
            if old:
                try: self._canvas.delete(old)
                except Exception: pass
        for s in cell.rating_glyphs:
            try: self._canvas.delete(s)
            except Exception: pass
        cell.badge = 0
        cell.raw_warn = 0
        cell.rating_glyphs = []

        # Pick status pill (top-left, white border for refined look)
        pill_x, pill_y = x1 + 6, y1 + 6
        status = item.pick_status
        if status == "accepted":
            cell.badge = self._canvas.create_oval(
                pill_x, pill_y, pill_x + _BADGE_SIZE, pill_y + _BADGE_SIZE,
                fill=Colors.ACCEPTED, outline="white", width=1.5,
            )
            self._canvas.create_text(
                pill_x + _BADGE_SIZE // 2, pill_y + _BADGE_SIZE // 2,
                text="\u2713", fill="white", font=_BADGE_FONT,
            )
        elif status == "rejected":
            cell.badge = self._canvas.create_oval(
                pill_x, pill_y, pill_x + _BADGE_SIZE, pill_y + _BADGE_SIZE,
                fill=Colors.REJECTED, outline="white", width=1.5,
            )
            self._canvas.create_text(
                pill_x + _BADGE_SIZE // 2, pill_y + _BADGE_SIZE // 2,
                text="\u2715", fill="white", font=_BADGE_FONT,
            )
        # 'pending' = no badge, by design (cleaner look)

        # RAW-missing warning (top-right)
        if item.has_raw is False:
            rx2 = x2 - 6
            ry2 = y1 + 6 + _BADGE_SIZE
            cell.raw_warn = self._canvas.create_rectangle(
                rx2 - 36, y1 + 6, rx2, ry2,
                fill=Colors.SURFACE_RAISED, outline=Colors.BORDER,
            )
            self._canvas.create_text(
                rx2 - 18, y1 + 6 + _BADGE_SIZE // 2,
                text="RAW?", fill=Colors.TEXT_DIM, font=("", 9, "bold"),
            )

        # Rating stars (bottom-left of the thumbnail, above caption)
        if item.rating:
            star_color = Colors.HIGH_RATING
            for i in range(item.rating):
                sx = x1 + 8 + i * 14
                sy = y2 - 4
                star = self._canvas.create_text(
                    sx, sy, text="\u2605", fill=star_color, font=("", 11),
                    anchor="sw",
                )
                cell.rating_glyphs.append(star)

    def _refresh_selection(self) -> None:
        for i, cell in enumerate(self._cells):
            if i == self._current_index:
                self._canvas.itemconfig(cell.bg, fill=Colors.ACCENT_SOFT,
                                        outline=Colors.ACCENT, width=3)
                self._canvas.itemconfig(cell.border, state="normal")
            else:
                self._canvas.itemconfig(cell.bg, fill=Colors.SURFACE,
                                        outline=Colors.BORDER, width=1)
                self._canvas.itemconfig(cell.border, state="hidden")

    def _refresh_hover(self) -> None:
        for i, cell in enumerate(self._cells):
            if i == self._current_index:
                continue  # selection overrides
            if i == self._hover_index:
                self._canvas.itemconfig(cell.bg, fill=Colors.SURFACE_RAISED,
                                        outline=Colors.ACCENT, width=1)
            else:
                self._canvas.itemconfig(cell.bg, fill=Colors.SURFACE,
                                        outline=Colors.BORDER, width=1)

    # -- hit testing & events --------------------------------------------
    def _find_cell_at(self, x: int, y: int) -> Optional[_Cell]:
        # find_overlapping returns the topmost item; we look up which cell
        # owns it. (Canvas item IDs are unique within the canvas.)
        if not self._cells:
            return None
        hits = self._canvas.find_overlapping(x, y, x, y)
        if not hits:
            return None
        # The smallest ID is drawn first (background); we want the cell
        # whose bg / image / border is in the hit set. Linear scan is fine
        # because the cell list is in index order and we stop at the first
        # match; for 1000 cells this is sub-millisecond.
        hit_set = set(hits)
        for cell in self._cells:
            if cell.bg in hit_set or cell.image in hit_set or cell.border in hit_set:
                return cell
            # any badge / name / raw-warn in this cell is also a hit
            if cell.badge in hit_set or cell.raw_warn in hit_set:
                return cell
            if any(s in hit_set for s in cell.rating_glyphs):
                return cell
        return None

    def _on_click(self, event) -> None:
        x, y = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)
        cell = self._find_cell_at(x, y)
        if cell is None:
            return
        if cell.index == self._current_index:
            return  # already selected; don't re-emit
        self._current_index = cell.index
        self._refresh_selection()
        if self._on_select:
            self._on_select(cell.item)

    def _on_double(self, event) -> None:
        x, y = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)
        cell = self._find_cell_at(x, y)
        if cell is None:
            return
        if self._on_double_click:
            self._on_double_click(cell.item)

    def _on_motion(self, event) -> None:
        x, y = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)
        cell = self._find_cell_at(x, y)
        new_hover = cell.index if cell else -1
        if new_hover == self._hover_index:
            return
        self._hover_index = new_hover
        self._refresh_hover()

    def _on_motion_leave(self) -> None:
        if self._hover_index == -1:
            return
        self._hover_index = -1
        self._refresh_hover()

    def _on_wheel(self, event) -> None:
        # Windows / macOS: event.delta is a multiple of 120 per notch
        if event.delta == 0:
            return
        delta = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(delta, "units")
        self._on_scroll_visible()

    def _on_arrow(self, event) -> None:
        if not self._items:
            return
        ks = event.keysym
        old = self._current_index
        n = len(self._items)
        if ks == "Up" and old >= self._col_count:
            self._current_index -= self._col_count
        elif ks == "Down" and old + self._col_count < n:
            self._current_index += self._col_count
        elif ks == "Left" and old > 0:
            self._current_index -= 1
        elif ks == "Right" and old < n - 1:
            self._current_index += 1
        else:
            return
        self._refresh_selection()
        self._scroll_into_view(self._current_index)
        self._on_scroll_visible()
        if self._on_select:
            self._on_select(self._items[self._current_index])

    def _scroll_into_view(self, idx: int) -> None:
        if not (0 <= idx < len(self._cells)):
            return
        x1, y1, x2, y2 = self._cells[idx].rect
        self._canvas.update_idletasks()
        # Compare to the visible y-range (canvas yview returns a 0..1 fraction)
        yview = self._canvas.yview()
        if not yview or yview[1] - yview[0] <= 0:
            return
        total = self._canvas.bbox("all")
        if not total:
            return
        _, _, _, total_h = total
        top_px = yview[0] * total_h
        bot_px = yview[1] * total_h
        margin = 20
        if y1 < top_px + margin:
            frac = max(0.0, (y1 - margin) / total_h)
            self._canvas.yview_moveto(frac)
        elif y2 > bot_px - margin:
            frac = min(1.0, (y2 + margin) / total_h)
            self._canvas.yview_moveto(frac)

    # -- loader polling --------------------------------------------------
    def _ensure_poller(self) -> None:
        if self._poll_id is None:
            self._poll_id = self.after(_POLL_INTERVAL_MS, self._poll_loader)

    def _poll_loader(self) -> None:
        try:
            if self._loader is not None:
                self._loader.dispatch()
        except Exception:
            pass
        self._poll_id = self.after(_POLL_INTERVAL_MS, self._poll_loader)
