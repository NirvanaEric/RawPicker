"""EXIF and GPS metadata reader built on top of Pillow.

Designed to fail silently: callers always get a dict (possibly empty) and
Optional[float] for GPS coordinates. The reader never raises on broken EXIF.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ExifTags, ImageOps


# Human-friendly tag lookup, built once
EXIF_TAG_NAMES = {v: k for k, v in ExifTags.TAGS.items()}
GPS_INFO_TAG = EXIF_TAG_NAMES.get("GPSInfo", 0x8825)
ORIENTATION_TAG = EXIF_TAG_NAMES.get("Orientation", 0x0112)


def _rat(r: Any) -> float:
    """Convert an IFDRational (or tuple) to float. Pillow returns IFDRational."""
    try:
        return float(r)
    except (TypeError, ValueError):
        try:
            return r[0] / r[1]
        except Exception:
            return 0.0


def _dms_to_decimal(dms: Tuple[float, float, float], ref: str) -> Optional[float]:
    """Convert (degrees, minutes, seconds) + ref to signed decimal degrees."""
    try:
        d, m, s = (_rat(x) for x in dms)
    except Exception:
        return None
    if not all((d, m, s)):
        return None
    val = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        val = -val
    return val


def _extract_gps(raw_gps: Dict[int, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Pull lat/lon out of a GPSInfo IFD. Returns (lat, lon) or (None, None)."""
    try:
        lat = _dms_to_decimal(raw_gps[2], raw_gps.get(1, "N"))
        lon = _dms_to_decimal(raw_gps[4], raw_gps.get(3, "E"))
    except (KeyError, TypeError):
        return None, None
    return lat, lon


def _decode_exif(exif: Any) -> Dict[str, Any]:
    """Walk a Pillow Exif object into a human-readable dict.

    Skips large binary blobs (MakerNote etc.) to keep the dict small.
    """
    if not exif:
        return {}
    decoded: Dict[str, Any] = {}
    for tag_id, value in exif.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if isinstance(value, bytes) and len(value) > 256:
            continue
        decoded[name] = value
    return decoded


def read_exif(path: str) -> Dict[str, Any]:
    """Return a dict of human-readable EXIF tags, or {} on failure."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            return _decode_exif(exif)
    except (OSError, ValueError, AttributeError):
        return {}


def read_gps(path: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (lat, lon) in decimal degrees, or (None, None) on failure."""
    if not path or not os.path.isfile(path):
        return None, None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None, None
            gps_ifd = exif.get_ifd(GPS_INFO_TAG) if hasattr(exif, "get_ifd") else None
            if not gps_ifd:
                return None, None
            return _extract_gps(gps_ifd)
    except (OSError, ValueError, AttributeError):
        return None, None


def read_metadata(path: str) -> Tuple[Dict[str, Any], Optional[float], Optional[float]]:
    """Open the image once and return (exif_dict, lat, lon).

    The combined reader avoids opening the file twice (one for EXIF, one for
    GPS) which halves I/O on a 1000-photo folder scan. Always silent on
    failure: returns ({}, None, None) for missing / broken / unsupported files.
    """
    if not path or not os.path.isfile(path):
        return {}, None, None
    try:
        with Image.open(path) as img:
            exif = img.getexif() or None
            decoded = _decode_exif(exif) if exif is not None else {}
            lat: Optional[float] = None
            lon: Optional[float] = None
            if exif is not None and hasattr(exif, "get_ifd"):
                gps_ifd = exif.get_ifd(GPS_INFO_TAG)
                if gps_ifd:
                    lat, lon = _extract_gps(gps_ifd)
            return decoded, lat, lon
    except (OSError, ValueError, AttributeError):
        return {}, None, None


def transpose_image(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation to a Pillow image (idempotent)."""
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def format_exif_for_display(exif: Dict[str, Any]) -> Dict[str, str]:
    """Trim a raw EXIF dict down to the fields the detail panel shows."""
    wanted = [
        "Make", "Model", "LensModel", "LensMake",
        "FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength",
        "DateTimeOriginal", "DateTime",
    ]
    out: Dict[str, str] = {}
    for k in wanted:
        v = exif.get(k)
        if v is None:
            continue
        if k == "FNumber":
            out["光圈"] = f"f/{_rat(v):.1f}"
        elif k == "ExposureTime":
            t = _rat(v)
            if t >= 1:
                out["快门"] = f"{t:.1f}s"
            elif t > 0:
                out["快门"] = f"1/{int(round(1/t))}s"
        elif k == "ISOSpeedRatings":
            out["ISO"] = str(v)
        elif k == "FocalLength":
            out["焦距"] = f"{int(_rat(v))}mm"
        elif k in ("Make", "Model"):
            out["相机"] = f"{exif.get('Make','')} {exif.get('Model','')}".strip()
        elif k in ("LensModel", "LensMake"):
            out["镜头"] = str(v)
        elif k in ("DateTimeOriginal", "DateTime"):
            out["拍摄日期"] = str(v)
    # de-dupe "相机" - only set once
    if "相机" in out and "Make" in wanted:
        pass
    return out
