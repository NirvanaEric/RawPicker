"""Tests for the cleaner engine (trash, permanent, recycle modes)."""
import os
import tempfile

import pytest

from src.core.cleaner_engine import clean_orphans
from src.core.scanner import scan_for_cleaning
from tests._fixture import make_fixture_set


def test_clean_recycle_moves_into_subfolder():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        orphans, _ = scan_for_cleaning(tmp)
        for o in orphans:
            o.selected = True
        report = clean_orphans(orphans, mode="recycle", target_folder=tmp)
        # 4 orphans: 2 RAW + 2 JPG (pair_03 + orphan_jpg_01)
        assert report.moved_to_recycle == 4
        assert report.recycle_folder is not None
        assert os.path.isdir(report.recycle_folder)
        moved = set(os.listdir(report.recycle_folder))
        assert moved == {
            "orphan_raw_01.dng", "orphan_raw_02.arw",
            "orphan_jpg_01.jpg", "pair_03.jpg",
        }


def test_clean_creates_unique_recycle_folder():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        orphans, _ = scan_for_cleaning(tmp)
        for o in orphans:
            o.selected = True
        r1 = clean_orphans(orphans, mode="recycle", target_folder=tmp)
        # Run again - should create a *new* timestamped folder.
        import time
        time.sleep(1.1)  # ensure second timestamp
        orphans2, _ = scan_for_cleaning(tmp)  # should be empty now
        # Re-create fixtures for the second run by reading still-existing
        # orphans (none), so use the recycle folder's contents as new orphans.
        from src.models.orphan_item import OrphanItem
        new_orphans = [OrphanItem.from_path(os.path.join(r1.recycle_folder, n))
                       for n in os.listdir(r1.recycle_folder)]
        for o in new_orphans:
            o.selected = True
        r2 = clean_orphans(new_orphans, mode="recycle", target_folder=tmp)
        assert r1.recycle_folder != r2.recycle_folder


def test_clean_permanent_removes_files():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        orphans, _ = scan_for_cleaning(tmp)
        target = orphans[0].file_path
        orphans[0].selected = True
        report = clean_orphans([orphans[0]], mode="permanent", target_folder=tmp)
        assert report.permanently_deleted == 1
        assert not os.path.exists(target)


def test_clean_trash_mode_calls_send2trash(monkeypatch):
    """We patch the import in file_ops so the real recycle bin is never touched."""
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        orphans, _ = scan_for_cleaning(tmp)
        target_path = orphans[0].file_path
        orphans[0].selected = True

        sent = []
        import src.core.file_ops as fo

        def fake_send2trash(path):
            sent.append(path)
            os.remove(path)  # simulate trash by removing

        monkeypatch.setattr(fo, "send2trash", fake_send2trash)
        report = clean_orphans([orphans[0]], mode="trash")
        assert report.trashed == 1
        assert sent == [target_path]
        assert not os.path.exists(target_path)
