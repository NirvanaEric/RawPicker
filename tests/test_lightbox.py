"""Lightbox behavior: navigation, status / rating emissions, callbacks, lifecycle."""
from __future__ import annotations

import os
import sys

import pytest

# Ensure the package is importable when running this file directly.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import customtkinter as ctk  # noqa: E402

from src.core.metadata_reader import read_exif, read_gps  # noqa: E402
from src.models.photo_item import PhotoItem  # noqa: E402
from src.ui.lightbox import Lightbox  # noqa: E402
from src.utils.image_cache import PreviewCache  # noqa: E402

from PIL import Image  # noqa: E402

from _fixture import make_fixture_set, make_jpg  # noqa: E402


def _make_items(folder, names=("pair_01", "pair_02", "pair_03")):
    items = []
    for n in names:
        jp = os.path.join(folder, f"{n}.jpg")
        if os.path.isfile(jp):
            exif = read_exif(jp)
            lat, lon = read_gps(jp)
            # Find the first existing raw companion, if any
            raw = None
            for ext in (".nef", ".cr2", ".arw", ".dng"):
                p = os.path.join(folder, n + ext)
                if os.path.isfile(p):
                    raw = p
                    break
            items.append(PhotoItem(
                basename=n, folder=folder, jpg_path=jp, raw_path=raw,
                rating=0, pick_status="pending", exif=exif, gps_lat=lat, gps_lon=lon,
            ))
    return items


def test_lightbox_starts_at_index_and_shows_title(tk_root, tmp_path):
    folder = str(tmp_path / "set")
    make_fixture_set(folder)
    items = _make_items(folder)

    lb = Lightbox(tk_root, items=items, index=1, cache=PreviewCache())
    try:
        title = lb._title_lbl.cget("text")
        counter = lb._counter_lbl.cget("text")
        assert title == items[1].display_name
        assert counter == f"2 / {len(items)}"
    finally:
        lb.destroy()


def test_lightbox_navigation_wraps(tk_root, tmp_path):
    folder = str(tmp_path / "set")
    make_fixture_set(folder)
    items = _make_items(folder)
    assert len(items) >= 3

    lb = Lightbox(tk_root, items=items, index=0, cache=PreviewCache())
    try:
        # prev from index 0 wraps to last
        lb._prev()
        assert lb.current_item() is items[-1]
        # next wraps back to first
        lb._next()
        assert lb.current_item() is items[0]
        # forward nav
        lb._next()
        assert lb.current_item() is items[1]
    finally:
        lb.destroy()


def test_lightbox_pick_emits_callback(tk_root, tmp_path):
    folder = str(tmp_path / "set")
    make_fixture_set(folder)
    items = _make_items(folder)

    picks: list[tuple[PhotoItem, str]] = []
    lb = Lightbox(tk_root, items=items, index=0, cache=PreviewCache(),
                  on_pick_change=lambda it, st: picks.append((it, st)))
    try:
        lb._emit_pick("accepted")
        lb._emit_pick("rejected")
        assert len(picks) == 2
        assert picks[0][0] is items[0]
        assert picks[0][1] == "accepted"
        assert picks[1][1] == "rejected"
    finally:
        lb.destroy()


def test_lightbox_rating_emits_callback(tk_root, tmp_path):
    folder = str(tmp_path / "set")
    make_fixture_set(folder)
    items = _make_items(folder)

    ratings: list[tuple[PhotoItem, int]] = []
    lb = Lightbox(tk_root, items=items, index=0, cache=PreviewCache(),
                  on_rating_change=lambda it, v: ratings.append((it, v)))
    try:
        lb._emit_rating(4)
        lb._emit_rating(0)
        assert ratings == [(items[0], 4), (items[0], 0)]
    finally:
        lb.destroy()


def test_lightbox_close_invokes_callback(tk_root, tmp_path):
    folder = str(tmp_path / "set")
    make_fixture_set(folder)
    items = _make_items(folder)

    closed = {"n": 0}
    lb = Lightbox(tk_root, items=items, index=0, cache=PreviewCache(),
                  on_close=lambda: closed.__setitem__("n", closed["n"] + 1))
    lb._on_close_request()
    assert closed["n"] == 1
    # Toplevel should be destroyed
    assert not lb.winfo_exists()
