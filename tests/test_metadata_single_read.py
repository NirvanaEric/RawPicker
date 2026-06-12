"""Tests for the single-pass read_metadata() helper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.core.metadata_reader import read_metadata, read_exif, read_gps


def _make_jpg(path: Path, color=(120, 140, 200)) -> None:
    Image.new("RGB", (64, 48), color=color).save(path, "JPEG")


def test_read_metadata_missing_file(tmp_path: Path) -> None:
    exif, lat, lon = read_metadata(str(tmp_path / "nope.jpg"))
    assert exif == {}
    assert lat is None
    assert lon is None


def test_read_metadata_plain_jpg(tmp_path: Path) -> None:
    p = tmp_path / "plain.jpg"
    _make_jpg(p)
    exif, lat, lon = read_metadata(str(p))
    assert isinstance(exif, dict)
    assert lat is None and lon is None


def test_read_metadata_opens_image_only_once(tmp_path: Path) -> None:
    """read_metadata must not call Image.open twice (the whole point of merging)."""
    p = tmp_path / "x.jpg"
    _make_jpg(p)
    from src.core import metadata_reader as mod
    real_open = Image.open
    calls: list[str] = []

    def counting_open(path, *a, **kw):
        calls.append(str(path))
        return real_open(path, *a, **kw)

    with patch.object(mod.Image, "open", staticmethod(counting_open)):
        exif, lat, lon = read_metadata(str(p))
    assert exif == exif  # no exception
    assert calls == [str(p)], f"expected 1 Image.open call, got {len(calls)}: {calls}"


def test_read_metadata_matches_split_readers(tmp_path: Path) -> None:
    """The merged result should equal calling the two split readers."""
    p = tmp_path / "y.jpg"
    _make_jpg(p)
    merged_exif, merged_lat, merged_lon = read_metadata(str(p))
    assert merged_exif == read_exif(str(p))
    assert (merged_lat, merged_lon) == read_gps(str(p))
