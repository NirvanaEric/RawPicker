"""Shared pytest fixtures for Tk-based UI tests.

Provides a single Tk root for tests that need a display widget. Skipped on
CI / headless environments by checking the DISPLAY / tkinter availability.
"""
from __future__ import annotations

import os
import tkinter as tk

import pytest


_HAS_TK = True
try:
    _test_root = tk.Tk()
    _test_root.withdraw()
    _test_root.destroy()
except Exception:  # noqa: BLE001
    _HAS_TK = False


_SKIP_REASON = "no display / tkinter not available in this environment"


@pytest.fixture
def tk_root():
    if not _HAS_TK:
        pytest.skip(_SKIP_REASON)
    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception:
            pass
