"""Tests for the renamer engine (template parsing, format widths, sync rename)."""
import os
import tempfile

import pytest

from src.core.renamer_engine import preview_renames, rename_items
from src.core.scanner import scan_for_picking
from tests._fixture import make_fixture_set


def test_template_seq_padding():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        preview = preview_renames(items, "{basename}_{seq:03d}", limit=5)
        # Every preview entry should end with _NNN.jpg
        for old, new in preview:
            assert new.endswith(".jpg")
            assert "_" in new
            # The seq component should be 3 digits
            seq_part = new.split("_")[-1].split(".")[0]
            assert len(seq_part) == 3
            assert seq_part.isdigit()


def test_rename_keeps_jpg_and_raw_in_sync():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        # Pick the first item that actually has a companion RAW
        target = next(it for it in items if it.has_raw)
        result = rename_items([target], "renamed_{seq:02d}", tmp)
        assert len(result.renamed) >= 1
        # Both files should exist with the new basename
        assert os.path.isfile(os.path.join(tmp, "renamed_01.jpg"))
        assert os.path.isfile(os.path.join(tmp, "renamed_01.nef"))
        # And old basenames are gone
        assert not os.path.isfile(os.path.join(tmp, "pair_01.jpg"))
        assert not os.path.isfile(os.path.join(tmp, "pair_01.nef"))


def test_rename_skip_when_already_target_name():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        # Template produces the same name -> should be skipped, not failed
        result = rename_items(items, "{basename}", tmp)
        # No actual renames performed
        assert result.renamed == []
        assert result.failed == []


def test_rename_handles_unknown_variable_gracefully():
    with tempfile.TemporaryDirectory() as tmp:
        make_fixture_set(tmp)
        items = scan_for_picking(tmp)
        preview = preview_renames(items, "{unknown}_{seq}", limit=2)
        # Unknown var should pass through as-is
        for old, new in preview:
            assert "{unknown}" in new or "unknown" in new
