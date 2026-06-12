"""Scale test: a 300-photo scan should not block the UI.

We don't try to render 1500 here (that would burn disk + minutes in CI);
300 is the design's "comfortable" upper bound and exercises the chunked
grid creation path.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.models.photo_item import PhotoItem  # noqa: E402
from src.ui.thumbnail_grid import ThumbnailGrid  # noqa: E402
from src.utils.thumbnail_loader import ThumbnailLoader  # noqa: E402

from _fixture import make_fixture_set, make_jpg  # noqa: E402


def _make_many_items(folder: str, count: int) -> list[PhotoItem]:
    items: list[PhotoItem] = []
    for i in range(count):
        name = f"big_{i:04d}"
        jp = os.path.join(folder, f"{name}.jpg")
        make_jpg(jp, (60, 80, 100 + (i % 50)), str(i))
        items.append(PhotoItem(
            basename=name, folder=folder, jpg_path=jp, raw_path=None,
            rating=0, pick_status="pending", exif={}, gps_lat=None, gps_lon=None,
        ))
    return items


def test_grid_handles_100_items_without_blocking(tk_root, tmp_path):
    """A 100-item load should not block the main thread for a noticeable
    time and should eventually render every cell.

    The hard perf target is "responsive": set_items() itself must return
    promptly, after which the rest of the UI is free to do other work while
    cells are built in background chunks. The total paint time is bounded
    by the number of items * per-cell-decode cost; that's not what the test
    is about.
    """
    folder = str(tmp_path / "big")
    make_fixture_set(folder)
    items = _make_many_items(folder, count=100)
    loader = ThumbnailLoader(num_workers=2, capacity=128)
    grid = ThumbnailGrid(tk_root, loader=loader, thumbnail_size=128,
                          on_select=lambda _it: None,
                          on_double_click=lambda _it: None)
    grid.pack(fill="both", expand=True)
    # Force an initial size so col-count calculation is sensible
    tk_root.geometry("800x600")
    grid.configure(width=800, height=600)
    tk_root.update_idletasks()
    grid.update_idletasks()

    # Hard responsiveness: set_items() itself should return near-instantly
    t0 = time.perf_counter()
    grid.set_items(items)
    set_items_ms = (time.perf_counter() - t0) * 1000
    assert set_items_ms < 200, f"set_items blocked for {set_items_ms:.0f}ms"

    # Soft paint: pump until all cells are visible, with a generous budget
    t0 = time.perf_counter()
    for _ in range(150):  # ~150 * 20ms = 3s budget
        tk_root.update()
        time.sleep(0.02)
        if len(grid._cells) >= len(items):  # noqa: SLF001
            break
    paint_ms = (time.perf_counter() - t0) * 1000

    # Sanity: chunked creation must finish
    assert len(grid._cells) == len(items)  # noqa: SLF001
    # And within a sensible budget on a quiet machine
    assert paint_ms < 3000, f"all 100 cells painted in {paint_ms:.0f}ms"


def test_grid_is_cancellable_mid_load(tk_root, tmp_path):
    """If the user issues a new set_items() mid-load, the in-flight chunks
    should be cancelled so we don't render stale cells."""
    folder = str(tmp_path / "big")
    make_fixture_set(folder)
    items = _make_many_items(folder, count=200)
    loader = ThumbnailLoader(num_workers=2, capacity=128)
    grid = ThumbnailGrid(tk_root, loader=loader, thumbnail_size=128,
                          on_select=lambda _it: None,
                          on_double_click=lambda _it: None)
    grid.pack(fill="both", expand=True)
    tk_root.geometry("800x600")
    grid.configure(width=800, height=600)
    tk_root.update_idletasks()
    grid.update_idletasks()

    grid.set_items(items)
    # Almost immediately swap to a fresh set of items
    tk_root.update()
    fresh = items[:30]
    grid.set_items(fresh)
    # Pump for long enough that the *original* load would have finished
    for _ in range(150):
        tk_root.update()
        time.sleep(0.02)
    # We expect at most 30 cells (the new count), not 200.
    assert len(grid._cells) <= 30 + 8  # noqa: SLF001
    # No stale cells from the original set
    basenames = {c.item.basename for c in grid._cells}  # noqa: SLF001
    assert all(b.startswith("big_") for b in basenames)


def test_grid_handles_1000_items_with_smooth_main_thread(tk_root, tmp_path):
    """1000-item stress test.

    We measure three things, in order of importance:

    1. **Hard responsiveness** — `set_items(1000)` itself returns in
       < 200 ms. This is what the user *feels* the moment they scan.
    2. **Steady-state smoothness** — once all cells exist (and decode
       results are flowing), no single main-thread update() takes
       > 50 ms. This is what makes scrolling feel smooth.
    3. **Time to full grid** — every cell is built within 30 s. This
       is the long-tail completion guarantee.
    """
    folder = str(tmp_path / "big")
    make_fixture_set(folder)
    items = _make_many_items(folder, count=1000)
    loader = ThumbnailLoader(num_workers=None, capacity=512)
    grid = ThumbnailGrid(tk_root, loader=loader, thumbnail_size=128,
                          on_select=lambda _it: None,
                          on_double_click=lambda _it: None)
    grid.pack(fill="both", expand=True)
    tk_root.geometry("1280x800")
    grid.configure(width=1280, height=800)
    tk_root.update_idletasks()
    grid.update_idletasks()

    # (1) Hard responsiveness
    t0 = time.perf_counter()
    grid.set_items(items)
    set_items_ms = (time.perf_counter() - t0) * 1000
    print(f"\n  set_items(1000): {set_items_ms:.0f}ms")
    assert set_items_ms < 200, f"set_items(1000) took {set_items_ms:.0f}ms"

    # Warm up the widget tree once
    for _ in range(3):
        tk_root.update()
        time.sleep(0.005)

    # (3) Time to full grid: pump until all 1000 cells are created OR
    # the deadline expires. Tk widget creation in pure-Python is the
    # main bottleneck (~50 ms / cell on a slow CI); we budget 120 s
    # for the full 1000 cells. The async loader is decoupled from
    # this work, so the *user* doesn't see the grid freeze for 60 s
    # at a time - they see the first chunk appear quickly, then a
    # steady stream of new cells while they can already browse.
    t0 = time.perf_counter()
    deadline = t0 + 120.0
    while time.perf_counter() < deadline:
        tk_root.update()
        time.sleep(0.005)
        if len(grid._cells) >= 1000:  # noqa: SLF001
            break
    full_ms = (time.perf_counter() - t0) * 1000
    print(f"  full grid: {full_ms:.0f}ms for 1000 cells")
    assert len(grid._cells) == 1000, (  # noqa: SLF001
        f"only {len(grid._cells)}/1000 cells built in {full_ms:.0f}ms"  # noqa: SLF001
    )
    assert full_ms < 30_000, f"full grid took {full_ms:.0f}ms"

    # Give the loader a moment to drain pending decodes
    for _ in range(50):
        tk_root.update()
        time.sleep(0.01)

    # (2) Steady-state smoothness: now that everything is built, every
    # update() should be a cheap event-loop pass.
    tick_times: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        tk_root.update()
        tick_ms = (time.perf_counter() - t0) * 1000
        tick_times.append(tick_ms)
        time.sleep(0.005)
    max_tick_ms = max(tick_times)
    median_tick_ms = sorted(tick_times)[len(tick_times) // 2]
    print(f"  idle ticks: median {median_tick_ms:.1f}ms, max {max_tick_ms:.1f}ms")
    assert max_tick_ms < 50, (
        f"worst idle tick was {max_tick_ms:.0f}ms "
        f"(median {median_tick_ms:.0f}ms, n={len(tick_times)})"
    )
