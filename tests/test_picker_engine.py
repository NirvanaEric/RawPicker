"""Tests for the picker engine (move accepted JPG+RAW, delete rejected, conflicts)."""
import os
import tempfile

import pytest

from src.core.picker_engine import pick_to_b, delete_items
from src.core.scanner import scan_for_picking
from tests._fixture import make_fixture_set


def test_pick_moves_jpg_and_raw():
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        make_fixture_set(tmp_a)
        items = scan_for_picking(tmp_a)
        for it in items:
            it.pick_status = "accepted"

        report = pick_to_b(items, tmp_b)

        # 4 JPGs total: pair_01, pair_02, pair_03, orphan_jpg_01
        # pair_01 & pair_02 have RAW; pair_03 & orphan_jpg_01 do not.
        assert report.moved_jpg == 4
        assert report.moved_raw == 2
        assert report.missing_raw == 2
        # Source folder emptied of moved items
        remaining = set(os.listdir(tmp_a))
        assert "pair_01.jpg" not in remaining
        assert "pair_01.nef" not in remaining
        assert "pair_02.jpg" not in remaining
        assert "pair_02.cr2" not in remaining
        assert "pair_03.jpg" not in remaining
        assert "orphan_jpg_01.jpg" not in remaining
        # Target has all moved files
        assert set(os.listdir(tmp_b)) == {
            "pair_01.jpg", "pair_01.nef",
            "pair_02.jpg", "pair_02.cr2",
            "pair_03.jpg", "orphan_jpg_01.jpg",
        }


def test_pick_skips_unselected_items():
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        make_fixture_set(tmp_a)
        items = scan_for_picking(tmp_a)
        # Only pick pair_01
        for it in items:
            it.pick_status = "accepted" if it.basename == "pair_01" else "pending"
        report = pick_to_b(items, tmp_b)
        assert report.moved_jpg == 1
        assert report.moved_raw == 1
        assert set(os.listdir(tmp_b)) == {"pair_01.jpg", "pair_01.nef"}


def test_pick_uses_resolver_for_conflicts():
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        make_fixture_set(tmp_a)
        # Pre-populate destination with conflicting files for pair_01 (jpg + raw)
        for name in ("pair_01.jpg", "pair_01.nef"):
            with open(os.path.join(tmp_b, name), "wb") as f:
                f.write(b"existing")
        items = scan_for_picking(tmp_a)
        for it in items:
            it.pick_status = "accepted"
        # First two conflicts: rename jpg, skip raw
        decisions = iter(["rename", "skip"])
        report = pick_to_b(items, tmp_b, resolver=lambda _dst: next(decisions, "skip"))
        assert report.moved_jpg == 4
        assert report.moved_raw == 1  # pair_01 raw skipped, pair_02 raw moved
        assert len(report.skipped) == 1
        # Renamed jpg exists, raw didn't move
        assert os.path.isfile(os.path.join(tmp_b, "pair_01_1.jpg"))
        assert not os.path.isfile(os.path.join(tmp_b, "pair_01.nef")) or \
               open(os.path.join(tmp_b, "pair_01.nef"), "rb").read() == b"existing"


def test_pick_default_skips_conflicts_silently():
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        make_fixture_set(tmp_a)
        with open(os.path.join(tmp_b, "pair_01.jpg"), "wb") as f:
            f.write(b"x")
        items = scan_for_picking(tmp_a)
        for it in items:
            it.pick_status = "accepted"
        report = pick_to_b(items, tmp_b)  # no resolver -> default skip
        assert len(report.skipped) >= 1
        assert "pair_01.jpg" not in {os.path.basename(p) for p in os.listdir(tmp_b) if p != "pair_01.jpg"}


def test_delete_removes_jpg_and_raw():
    """delete_items moves JPG + companion RAW to a _Orphaned_ temp folder."""
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        # Pick only pair_01 (has RAW) and pair_03 (no RAW)
        rejected = [it for it in items if it.basename in ("pair_01", "pair_03")]
        report = delete_items(rejected, target_folder=tmp)
        assert report.deleted_jpg == 2
        assert report.deleted_raw == 1  # pair_01 has .nef, pair_03 has no RAW
        assert report.recycle_folder is not None
        assert os.path.isdir(report.recycle_folder)
        # Original files removed from source
        remaining = set(os.listdir(tmp)) - {os.path.basename(report.recycle_folder)}
        assert "pair_01.jpg" not in remaining
        assert "pair_01.nef" not in remaining
        assert "pair_03.jpg" not in remaining
        # Files exist in recycle folder
        recycle_contents = set(os.listdir(report.recycle_folder))
        assert "pair_01.jpg" in recycle_contents
        assert "pair_01.nef" in recycle_contents
        assert "pair_03.jpg" in recycle_contents


def test_delete_skips_missing_files():
    """delete_items counts missing files as failed, not as deleted."""
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        # Remove a file before deleting
        os.remove(os.path.join(tmp, "pair_01.jpg"))
        rejected = [it for it in items if it.basename == "pair_01"]
        report = delete_items(rejected, target_folder=tmp)
        assert report.deleted_jpg == 0
        assert report.deleted_raw == 1  # .nef still exists, moved to recycle
        assert len(report.failed) >= 1
