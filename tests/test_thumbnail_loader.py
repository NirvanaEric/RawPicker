"""Tests for the background thumbnail loader."""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
_TESTS = _ROOT
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.utils.thumbnail_loader import ThumbnailLoader  # noqa: E402

from _fixture import make_jpg  # noqa: E402


def _pump_and_dispatch(loader: ThumbnailLoader, seconds: float = 1.5) -> None:
    """Simulate the main-thread poller for `seconds`."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        loader.dispatch()
        time.sleep(0.02)


def test_loader_submits_and_fires_callback(tmp_path):
    p = os.path.join(str(tmp_path), "a.jpg")
    make_jpg(p, (40, 60, 80), "A")
    received: list = []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.submit(p, 64, lambda img: received.append(img), generation=1)
    _pump_and_dispatch(loader, 3.0)
    loader.shutdown()
    assert len(received) == 1
    assert received[0] is not None


def test_loader_fires_none_for_missing_file(tmp_path):
    received: list = []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.submit(os.path.join(str(tmp_path), "nope.jpg"), 64,
                  lambda img: received.append(img), generation=1)
    _pump_and_dispatch(loader, 0.5)
    loader.shutdown()
    assert received == [None]


def test_loader_cancelled_generation_does_not_fire(tmp_path):
    p = os.path.join(str(tmp_path), "c.jpg")
    make_jpg(p, (40, 60, 80), "C")
    fired: list = []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.cancel_generation(7)  # cancel BEFORE submit
    loader.submit(p, 64, lambda img: fired.append(img), generation=7)
    _pump_and_dispatch(loader, 1.5)
    loader.shutdown()
    assert fired == []


def test_loader_dedups_inflight(tmp_path):
    p = os.path.join(str(tmp_path), "d.jpg")
    make_jpg(p, (40, 60, 80), "D")
    a, b = [], []
    loader = ThumbnailLoader(num_workers=1, capacity=64)
    loader.submit(p, 64, lambda img: a.append(img), generation=1)
    loader.submit(p, 64, lambda img: b.append(img), generation=1)
    _pump_and_dispatch(loader, 3.0)
    loader.shutdown()
    # Both callbacks fire (dedup still notifies the second submitter
    # via a small re-decode job).
    assert len(a) == 1 and len(b) == 1


def test_loader_processes_many_jobs(tmp_path):
    paths = []
    for i in range(20):
        p = os.path.join(str(tmp_path), f"m_{i}.jpg")
        make_jpg(p, (40, 60, 80 + i), str(i))
        paths.append(p)
    received: list = []
    loader = ThumbnailLoader(num_workers=2, capacity=64)
    for p in paths:
        loader.submit(p, 64, lambda img, _p=p: received.append(_p), generation=1)
    _pump_and_dispatch(loader, 8.0)
    loader.shutdown()
    assert sorted(received) == sorted(paths)


def test_loader_dispatch_returns_zero_when_no_jobs(tmp_path):
    loader = ThumbnailLoader(num_workers=1, capacity=8)
    n = loader.dispatch()
    loader.shutdown()
    assert n == 0


def test_loader_is_cancelled_query(tmp_path):
    loader = ThumbnailLoader(num_workers=1, capacity=8)
    loader.cancel_generation(42)
    assert loader.is_cancelled(42) is True
    assert loader.is_cancelled(43) is False
    loader.shutdown()
