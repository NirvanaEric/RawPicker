"""Tests for the perf-related ThumbnailGrid and PreviewPanel wiring.

We exercise the parts that can be tested without a real display:
- ThumbnailGrid: debounced relayout, column-count skip, generation cancels
- PreviewPanel: request_id based stale result rejection
"""
from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock

from PIL import Image

from src.config.settings import AppConfig
from src.models.photo_item import PhotoItem
from src.ui.preview_panel import PreviewPanel
from src.ui.thumbnail_grid import ThumbnailGrid
from src.utils.image_cache import PreviewCache
from src.utils.thumbnail_loader import ThumbnailLoader


# ----- Test fixtures -----------------------------------------------------


def _make_jpg(path: Path, color=(120, 140, 200)) -> None:
    Image.new("RGB", (64, 48), color=color).save(path, "JPEG")


def _make_item(folder: Path, name: str) -> PhotoItem:
    return PhotoItem(
        basename=name,
        folder=str(folder),
        jpg_path=str(folder / f"{name}.jpg"),
        jpg_ext="jpg",
        raw_path=None,
        raw_ext=None,
    )


def _make_items(folder: Path, n: int) -> List[PhotoItem]:
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        _make_jpg(folder / f"img_{i:04d}.jpg")
    return [_make_item(folder, f"img_{i:04d}") for i in range(n)]


# ----- ThumbnailGrid behaviour -------------------------------------------


def _build_grid(master, items=None) -> ThumbnailGrid:
    return ThumbnailGrid(
        master,
        loader=ThumbnailLoader(num_workers=1, capacity=4),
        on_select=lambda _it: None,
        on_double_click=None,
    )


def test_relayout_skips_when_col_count_unchanged(tk_root, tmp_path: Path) -> None:
    items = _make_items(tmp_path, 4)
    grid = _build_grid(tk_root)
    grid.set_items(items)
    tk_root.update_idletasks()
    # Force the relayout once at the current width.
    grid._do_relayout()  # type: ignore[attr-defined]
    cells_after_first = list(grid._cells)  # type: ignore[attr-defined]
    assert cells_after_first, "expected cells to be created"
    # Second call at same width: should not destroy and recreate.
    grid._do_relayout()  # type: ignore[attr-defined]
    assert len(grid._cells) == len(cells_after_first)  # type: ignore[attr-defined]
    assert all(a is b for a, b in zip(grid._cells, cells_after_first))  # type: ignore[attr-defined]


def test_set_items_bumps_generation_and_cancels(tk_root, tmp_path: Path) -> None:
    items = _make_items(tmp_path, 3)
    grid = _build_grid(tk_root)
    grid.set_items(items)
    tk_root.update_idletasks()
    g1 = grid._generation  # type: ignore[attr-defined]
    grid.set_items(items[:1])
    assert grid._generation == g1 + 1  # type: ignore[attr-defined]


def test_thumbnail_grid_chunk_creates_all_cells(tk_root, tmp_path: Path) -> None:
    """Even with chunked creation, all cells eventually exist after pumping."""
    items = _make_items(tmp_path, 25)
    grid = _build_grid(tk_root)
    grid.set_items(items)
    # Bypass the debounce and trigger relayout directly.
    grid._do_relayout()  # type: ignore[attr-defined]
    # Pump the event loop so the 16ms after() chunks fire.
    for _ in range(40):
        tk_root.update()
    assert len(grid._cells) == 25  # type: ignore[attr-defined]


# ----- PreviewPanel async request_id -------------------------------------


def test_preview_panel_drops_stale_results(tk_root, tmp_path: Path) -> None:
    cache = PreviewCache(capacity=2)
    panel = PreviewPanel(tk_root, cache=cache, max_height=200)
    a = _make_item(tmp_path, "a")
    b = _make_item(tmp_path, "b")
    (tmp_path / "a.jpg").write_bytes(b"")
    (tmp_path / "b.jpg").write_bytes(b"")
    panel.show(a)
    rid_a = panel._req_id  # type: ignore[attr-defined]
    panel.show(b)
    rid_b = panel._req_id  # type: ignore[attr-defined]
    assert rid_b > rid_a
    # Stale result for a - the poller must NOT apply it.
    panel._decode_q.put((rid_a, None, "stale"))  # type: ignore[attr-defined]
    tk_root.update()
    label_text = str(panel._image_label.cget("text"))  # type: ignore[attr-defined]
    assert "stale" not in label_text


def test_preview_panel_applies_matching_result(tk_root, tmp_path: Path) -> None:
    cache = PreviewCache(capacity=2)
    panel = PreviewPanel(tk_root, cache=cache, max_height=200)
    _make_jpg(tmp_path / "x.jpg")
    item = _make_item(tmp_path, "x")
    panel.show(item)
    rid = panel._req_id  # type: ignore[attr-defined]
    # Replace configure with a plain mock so we can capture the call without
    # CTkLabel trying to actually install the fake image into Tk.
    panel._image_label.configure = MagicMock()  # type: ignore[attr-defined]
    fake_img = MagicMock(name="ctk_image")
    panel._decode_q.put((rid, fake_img, ""))  # type: ignore[attr-defined]
    # Drive the poller directly (avoids depending on the 50ms after() timer).
    panel._poll_decode()  # type: ignore[attr-defined]
    image_calls = [
        call for call in panel._image_label.configure.call_args_list  # type: ignore[attr-defined]
        if call.kwargs.get("image") is fake_img
    ]
    assert image_calls, (
        f"expected configure(image=fake_img) call, "
        f"got {panel._image_label.configure.call_args_list}"  # type: ignore[attr-defined]
    )
