"""Tests for the scanner."""
import os
import tempfile

import pytest

from src.core.scanner import scan_for_cleaning, scan_for_picking
from tests._fixture import make_fixture_set


def test_scan_for_picking_finds_all_jpgs():
    """The picking scanner is JPG-anchored, so it returns every JPG in the
    folder, including ones without a companion RAW. Each item's has_raw
    flag tells the UI which ones are missing their RAW twin."""
    with tempfile.TemporaryDirectory() as tmp:
        files = make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        assert len(items) == 4
        basenames = {it.basename for it in items}
        assert basenames == {"pair_01", "pair_02", "pair_03", "orphan_jpg_01"}


def test_scan_for_picking_keeps_first_matching_raw():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        by_name = {it.basename: it for it in items}
        assert by_name["pair_01"].has_raw is True
        assert by_name["pair_01"].raw_ext == "nef"
        assert by_name["pair_02"].raw_ext == "cr2"
        assert by_name["pair_03"].has_raw is False


def test_scan_for_picking_does_not_recurse():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        assert all(os.path.dirname(it.jpg_path) == tmp for it in items)


def test_scan_for_picking_invalid_folder_returns_empty():
    assert scan_for_picking("/nonexistent/abc/xyz") == []


def test_scan_for_cleaning_finds_orphans_and_pairs():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        orphans, complete = scan_for_cleaning(tmp)
        # 2 orphan RAW (dng, arw) + 2 orphan JPG (pair_03, orphan_jpg_01)
        assert len(orphans) == 4
        # 2 complete pairs (pair_01, pair_02)
        assert len(complete) == 2
        orphan_paths = {o.file_path for o in orphans}
        assert any(p.endswith("orphan_raw_01.dng") for p in orphan_paths)
        assert any(p.endswith("orphan_raw_02.arw") for p in orphan_paths)
        assert any(p.endswith("orphan_jpg_01.jpg") for p in orphan_paths)
        assert any(p.endswith("pair_03.jpg") for p in orphan_paths)
