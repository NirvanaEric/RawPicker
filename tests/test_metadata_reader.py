"""Tests for EXIF / GPS reader graceful failure modes."""
import os
import tempfile

import pytest
from PIL import Image

from src.core.metadata_reader import read_exif, read_gps
from tests._fixture import make_jpg


def test_read_exif_on_missing_file_returns_empty():
    assert read_exif("/nonexistent/file.jpg") == {}
    assert read_gps("/nonexistent/file.jpg") == (None, None)


def test_read_exif_on_plain_jpg_returns_dict():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "plain.jpg")
        make_jpg(p)
        exif = read_exif(p)
        # A plain JPG has no EXIF; the function should return {} (not raise)
        assert isinstance(exif, dict)


def test_read_gps_on_plain_jpg_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "plain.jpg")
        make_jpg(p)
        lat, lon = read_gps(p)
        assert lat is None and lon is None
