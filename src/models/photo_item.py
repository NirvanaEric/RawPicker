"""PhotoItem: the central data model for the picking workflow."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PhotoItem:
    basename: str                       # e.g. "DSC_0001"
    folder: str                         # absolute folder
    jpg_path: Optional[str]             # absolute path to the JPG
    jpg_ext: str = ""                   # "jpg" or "jpeg"
    raw_path: Optional[str] = None      # absolute path to the companion RAW
    raw_ext: Optional[str] = None       # e.g. "nef"

    # Interaction state (in-memory only, not written to disk by default)
    selected: bool = False
    rating: int = 0                     # 0-5
    pick_status: str = "pending"        # "accepted" | "rejected" | "pending"

    # Cached metadata
    exif: Dict[str, Any] = field(default_factory=dict)
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None

    # -- derived ---------------------------------------------------------
    @property
    def has_raw(self) -> bool:
        return self.raw_path is not None

    @property
    def file_size_mb(self) -> float:
        total = 0
        for p in (self.jpg_path, self.raw_path):
            if p and os.path.isfile(p):
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
        return round(total / (1024 * 1024), 2)

    @property
    def display_name(self) -> str:
        ext = self.jpg_ext or (os.path.splitext(self.raw_path or "")[1].lstrip(".") if self.raw_path else "")
        return f"{self.basename}.{ext}" if ext else self.basename

    def to_dict(self) -> Dict[str, Any]:
        return {
            "basename": self.basename,
            "folder": self.folder,
            "jpg_path": self.jpg_path,
            "jpg_ext": self.jpg_ext,
            "raw_path": self.raw_path,
            "raw_ext": self.raw_ext,
            "selected": self.selected,
            "rating": self.rating,
            "pick_status": self.pick_status,
            "gps_lat": self.gps_lat,
            "gps_lon": self.gps_lon,
        }
