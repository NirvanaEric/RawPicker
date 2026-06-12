# Performance + Light Theme Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the grid, scan, preview, and lightbox operations feel snappy on 1000-photo folders, and restyle the whole app to a clean Apple Photos light theme.

**Architecture:**
- A new `ThumbnailLoader` (`ThreadPoolExecutor` of `min(4, cpu_count)` workers) does all thumbnail decoding off the main thread. Cells render a placeholder immediately and swap the image in via `after(0, ...)` when ready. A generation counter cancels in-flight work.
- A new `Colors` palette (`#FFFFFF` surface, `#0A84FF` accent, hairline borders) replaces the dark one. All widgets are restyled. The lightbox image area stays black for photography evaluation.

**Tech Stack:** Python 3.11+, customtkinter, Pillow, threading, queue, ThreadPoolExecutor. No new external deps.

---

## Task 1: New light-theme `Colors` palette

**Files:** `src/config/settings.py`, `tests/test_perf_panel.py` (any color asserts), `tests/test_lightbox.py` (color asserts).

**Step 1:** Replace `Colors` in `src/config/settings.py` with the light palette below. Keep the *legacy* aliases (`PRIMARY`, `ACCEPTED`, `REJECTED`, `PENDING`, `HIGH_RATING`, `WARNING`, `BG_DARK`, `BG_DARKER`, `BG_LIGHT`, `TEXT_DIM`) as backwards-compatible mappings to the new fields so we don't have to rewrite every call-site in one go. Add the new `BG` / `SURFACE` / `SURFACE_RAISED` / `BORDER` / `BORDER_SUBTLE` / `TEXT` / `TEXT_DISABLED` / `ACCENT` / `ACCENT_SOFT` names.

```python
class Colors:
    BG              = "#FFFFFF"
    SURFACE         = "#F2F2F7"
    SURFACE_RAISED  = "#FFFFFF"
    BORDER          = "#D1D1D6"
    BORDER_SUBTLE   = "#E5E5EA"
    TEXT            = "#1C1C1E"
    TEXT_DIM        = "#8E8E93"
    TEXT_DISABLED   = "#C7C7CC"
    ACCENT          = "#0A84FF"
    ACCENT_SOFT     = "#E5F0FF"
    ACCEPTED        = "#34C759"
    REJECTED        = "#FF3B30"
    PENDING         = "#8E8E93"
    WARNING         = "#FF9F0A"
    HIGH_RATING     = "#FFCC00"
    # Backwards compat
    PRIMARY         = ACCENT
    BG_DARK         = SURFACE
    BG_DARKER       = BG
    BG_LIGHT        = SURFACE_RAISED
```

**Step 2:** Run `uv run python -m pytest -q` — must stay green (the legacy aliases preserve the old field names).

## Task 2: New `ThumbnailLoader` utility

**Files:** `src/utils/thumbnail_loader.py` (new), `tests/test_thumbnail_loader.py` (new).

**Step 1 (TDD):** Write the tests first.

```python
# tests/test_thumbnail_loader.py
import os, sys
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
import time
import tkinter as tk
import pytest
from PIL import Image
from src.utils.thumbnail_loader import ThumbnailLoader
from _fixture import make_fixture_set, make_jpg

def _pump(seconds=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.02)

def test_loader_submits_and_fires_callback(tmp_path):
    folder = str(tmp_path)
    make_jpg(os.path.join(folder, "a.jpg"), (40, 60, 80), "A")
    received = []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.submit(os.path.join(folder, "a.jpg"), 64, lambda img: received.append(img), generation=1)
    _pump(2.0)
    loader.shutdown()
    assert len(received) == 1
    assert received[0] is not None

def test_loader_dedups_same_path_size(tmp_path):
    folder = str(tmp_path)
    make_jpg(os.path.join(folder, "b.jpg"), (40, 60, 80), "B")
    a, b = [], []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    p = os.path.join(folder, "b.jpg")
    loader.submit(p, 64, lambda img: a.append(img), generation=1)
    loader.submit(p, 64, lambda img: b.append(img), generation=1)
    _pump(2.0)
    loader.shutdown()
    assert len(a) == 1 and len(b) == 1

def test_loader_cancelled_generation_does_not_fire(tmp_path):
    folder = str(tmp_path)
    make_jpg(os.path.join(folder, "c.jpg"), (40, 60, 80), "C")
    fired = []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.cancel_generation(1)  # cancel BEFORE submit
    loader.submit(os.path.join(folder, "c.jpg"), 64, lambda img: fired.append(img), generation=1)
    _pump(1.0)
    loader.shutdown()
    assert fired == []
```

**Step 2:** Run tests — they fail (no `ThumbnailLoader`).

**Step 3:** Implement `src/utils/thumbnail_loader.py`:

```python
"""Background thumbnail decoder. Keeps the main thread free."""
from __future__ import annotations
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional, Set, Tuple

import customtkinter as ctk
from PIL import Image, ImageOps

from .image_cache import ThumbnailCache


class ThumbnailLoader:
    """Decode thumbnails off the main thread.

    The grid creates a placeholder cell synchronously, then calls
    `submit(path, size, on_ready, generation)`. Workers run
    `Image.open → exif_transpose → resize → CTkImage`; results come
    back via a `queue.Queue` that the caller polls on the main thread
    (typically with `widget.after(20, self._poll)`).

    A generation counter invalidates in-flight work: if the user
    issues a new `set_items()` while decodes are pending, call
    `cancel_generation(new_gen - 1)` so the previous batch's
    callbacks are dropped on the poller side.
    """

    def __init__(self, num_workers: Optional[int] = None, capacity: int = 1024):
        if num_workers is None:
            num_workers = max(1, min(4, (os.cpu_count() or 2)))
        self._cache = ThumbnailCache(capacity=capacity)
        self._q: "queue.Queue[Tuple[int, int, object, Callable]]" = queue.Queue()
        self._inflight: Set[Tuple[str, int]] = set()
        self._inflight_lock = threading.Lock()
        self._cancelled: Set[int] = set()
        self._cancel_lock = threading.Lock()
        self._ex = ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix="thumb")
        self._workers = num_workers

    def cache(self) -> ThumbnailCache:
        return self._cache

    def cancel_generation(self, gen: int) -> None:
        with self._cancel_lock:
            self._cancelled.add(gen)

    def submit(self, path: str, size: int,
               on_ready: Callable, generation: int) -> None:
        if not path or not os.path.isfile(path):
            on_ready(None)
            return
        with self._inflight_lock:
            key = (path, size)
            if key in self._inflight:
                # dedup: just attach our callback; the original job will
                # fan out the result to both via the cache
                return
            self._inflight.add(key)
        self._ex.submit(self._decode_job, path, size, generation, on_ready)

    def _decode_job(self, path: str, size: int, generation: int,
                    on_ready: Callable) -> None:
        try:
            ctk_img = self._cache.get_or_load(path, size)
            self._q.put((generation, id(on_ready), ctk_img, on_ready))
        except Exception:
            self._q.put((generation, id(on_ready), None, on_ready))
        finally:
            with self._inflight_lock:
                self._inflight.discard((path, size))

    def drain(self) -> list:
        """Pop all currently-available results. Call from the main thread."""
        out = []
        try:
            while True:
                out.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return out

    def is_cancelled(self, generation: int) -> bool:
        with self._cancel_lock:
            return generation in self._cancelled

    def shutdown(self) -> None:
        self._ex.shutdown(wait=False)
```

**Step 4:** Run tests — they pass.

**Step 5:** Sanity-check existing tests still pass (`uv run python -m pytest -q`).

## Task 3: Wire `ThumbnailLoader` into the app

**Files:** `src/app.py`, `src/ui/main_window.py`, `src/ui/pick_tab.py`, `src/ui/thumbnail_grid.py`, `src/ui/preview_panel.py`, `src/ui/lightbox.py`.

**Step 1:** Modify `src/app.py`:

- Import `ThumbnailLoader` from `src.utils.thumbnail_loader`.
- In `__init__`, replace `self.cache = ImageCache(...)` with `self.loader = ThumbnailLoader(num_workers=None, capacity=1024)`. (Keep `self.cache = self.loader.cache()` for any direct callers.)
- Pass `loader=self.loader` into `MainWindow`.

**Step 2:** Modify `src/ui/main_window.py`:

- `MainWindow.__init__` takes a new `loader` parameter (default `None`).
- If `loader is None`, create one (for unit tests).
- Pass `loader` to `PickTab`.

**Step 3:** Modify `src/ui/pick_tab.py`:

- `PickTab.__init__` takes `loader`; store as `self._loader`.
- Pass `loader=self._loader` into the `ThumbnailGrid`.

**Step 4:** Modify `src/ui/thumbnail_grid.py` (the big change):

- `ThumbnailGrid.__init__` takes `loader` (default: build one internally for tests).
- `_ThumbCell` is rewritten:
  - In `__init__`, `self._image_label` shows a placeholder (a `CTkFrame` 128×128 with a centred `TEXT_DIM` glyph) and does **no** decode.
  - Add `load_async(loader, generation)` which calls `loader.submit(...)`.
  - Add `apply_image(ctk_img)` which configures the label with the image.
  - On `<Destroy>`, no special action needed.
- `ThumbnailGrid.set_items(items)`:
  - Bump `self._generation`.
  - Call `loader.cancel_generation(self._generation - 1)`.
  - Build cells in chunks of 30 (existing logic).
  - Each cell: call `cell.load_async(loader, self._generation)`.
  - Start a poller: `self.after(20, self._poll_loader)` (cancel old one first).
- `ThumbnailGrid._poll_loader`:
  - Drain results from `loader.drain()`.
  - For each `(gen, _, ctk_img, on_ready)`: if gen != self._generation, skip; else call on_ready(ctk_img).
  - Each `on_ready` is a closure capturing the cell + the image.
  - Re-arm: `self.after(20, self._poll_loader)`.
- The cell's `on_ready` does: `cell.apply_image(img)` if the cell still exists (`cell.winfo_exists()`).

**Step 5:** Modify `src/ui/preview_panel.py` and `src/ui/lightbox.py`:

- These already do async decode. Add a comment / pass the loader if convenient. No required change.
- Optional simplification: route through `loader.submit()` so we have one decode path. (Skip for now if it adds risk; the existing paths are already non-blocking.)

**Step 6:** Run all tests; smoke.

## Task 4: 1000-photo perf test

**Files:** `tests/test_grid_1000_responsive.py` (new).

```python
"""1000-photo load should be smooth."""
import os, sys, time
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
import pytest
import tkinter as tk
from src.models.photo_item import PhotoItem
from src.ui.thumbnail_grid import ThumbnailGrid
from src.utils.thumbnail_loader import ThumbnailLoader
from _fixture import make_fixture_set, make_jpg


def _make_items(folder, n):
    items = []
    for i in range(n):
        name = f"x_{i:04d}"
        jp = os.path.join(folder, f"{name}.jpg")
        make_jpg(jp, (50, 70, 90), str(i))
        items.append(PhotoItem(basename=name, folder=folder, jpg_path=jp, raw_path=None,
                                rating=0, pick_status="pending", exif={}, gps_lat=None, gps_lon=None))
    return items


def test_grid_1000_responsive(tk_root, tmp_path):
    folder = str(tmp_path)
    make_fixture_set(folder)
    items = _make_items(folder, 1000)
    loader = ThumbnailLoader(num_workers=4, capacity=1024)
    grid = ThumbnailGrid(tk_root, loader=loader, thumbnail_size=128,
                          on_select=lambda _i: None, on_double_click=lambda _i: None)
    grid.pack(fill="both", expand=True)
    tk_root.geometry("900x600"); grid.configure(width=900, height=600)
    tk_root.update_idletasks(); grid.update_idletasks()

    # 1. set_items returns fast
    t = time.perf_counter()
    grid.set_items(items)
    set_ms = (time.perf_counter() - t) * 1000
    assert set_ms < 200, f"set_items blocked {set_ms:.0f}ms"

    # 2. pump + measure every tick. The MAX tick must be small.
    max_tick = 0
    painted = 0
    deadline = time.time() + 60
    while time.time() < deadline:
        t = time.perf_counter()
        try:
            tk_root.update()
        except tk.TclError:
            break
        max_tick = max(max_tick, (time.perf_counter() - t) * 1000)
        if len(grid._cells) >= 1000 and all(c._loaded for c in grid._cells):  # noqa: SLF001
            break
        time.sleep(0.01)

    # main thread never blocks > 50ms in any single tick
    assert max_tick < 50, f"a single tick took {max_tick:.0f}ms (UI would stutter)"
    # all cells are created
    assert len(grid._cells) == 1000
    loader.shutdown()
```

Run the test, debug until green.

## Task 5: Restyle sidebar, badges, dialogs to light theme

**Files:** `src/ui/sidebar.py`, `src/ui/pick_badge.py`, `src/ui/dialogs/common.py`, `src/ui/rating_widget.py`, `src/ui/main_window.py`.

For each, swap every `fg_color=Colors.BG_DARK` / `Colors.BG_DARKER` / `Colors.ACCENT_OLD` etc. for the new `Colors.BG` / `Colors.SURFACE` / `Colors.ACCENT` / `Colors.ACCENT_SOFT`. Set the segmented-button selected_colour to `ACCENT`, unselected to `BORDER_SUBTLE`. Replace big-number stats with regular-size tabular numbers.

The mapping table:

| Old | New |
|---|---|
| `BG_DARK` | `SURFACE` |
| `BG_DARKER` | `BG` |
| `BG_LIGHT` | `SURFACE_RAISED` |
| `PRIMARY` | `ACCENT` |
| text on dark bg | text on `BG` → use `TEXT` |

Run all tests after each file; smoke.

## Task 6: Restyle thumbnail cell, preview panel, lightbox chrome

**Files:** `src/ui/thumbnail_grid.py` (cell only), `src/ui/preview_panel.py`, `src/ui/lightbox.py`.

Cell: 8 px radius, 1 px BORDER, ACCENT 2 px on select + ACCENT_SOFT bg, placeholder uses SURFACE + TEXT_DISABLED.

Preview panel: BG background, SURFACE for image area, TEXT/TEXT_DIM for EXIF.

Lightbox: top bar / right rail / bottom bar all `BG`, 1 px `BORDER` between them. Image area stays `BG_DARKER` (which now aliases to `BG` — we use a separate `Colors.LIGHTBOX_BG = "#0E0E10"` constant for clarity, NOT aliased to BG).

Add `LIGHTBOX_BG = "#0E0E10"` to `Colors`.

## Task 7: Tabs + appearance mode

**Files:** `src/ui/main_window.py`, `src/ui/clean_tab.py`, `src/ui/rename_tab.py`, `src/app.py`.

- `ctk.set_appearance_mode("light")` in `app.py` at import time.
- Override the `CTkTabview` segmented-button colour to `Colors.ACCENT`.
- Restyle clean/rename tab headers/buttons to match.

## Task 8: Full smoke + regression

- Run `uv run python -m pytest -q` — all 36 + new tests pass.
- Run `uv run python smoke.py` — PICK + CLEAN + RENAME + LIGHTBOX pass.
- Add a 1000-photo smoke variant: scan 1000 fixtures, click into lightbox, verify no stutter (eyeballed by stats: max tick < 50 ms).

---

## Execution order

1 → 2 → 3 → 4 (gates on loader working) → 5 → 6 → 7 → 8

Tasks 1–4 are the perf foundation; 5–7 are pure restyle and can be done in any order; 8 is the gate.
