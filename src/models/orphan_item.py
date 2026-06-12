"""OrphanItem: data model for the cleaning workflow."""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..config.settings import JPG_SET, RAW_SET


@dataclass
class OrphanItem:
    basename: str
    folder: str
    file_path: str            # absolute path to the orphan file
    file_type: str            # "raw" | "jpg"
    ext: str                  # actual extension
    size_mb: float = 0.0
    selected: bool = False

    @classmethod
    def from_path(cls, file_path: str) -> "OrphanItem":
        folder, name = os.path.split(file_path)
        basename, ext = os.path.splitext(name)
        ext_lower = ext.lstrip(".").lower()
        if ext_lower in RAW_SET:
            file_type = "raw"
        elif ext_lower in JPG_SET:
            file_type = "jpg"
        else:
            # Unknown extension - treat as generic raw to keep it visible to user
            file_type = "raw"
        try:
            size = os.path.getsize(file_path) / (1024 * 1024)
        except OSError:
            size = 0.0
        return cls(
            basename=basename,
            folder=folder,
            file_path=file_path,
            file_type=file_type,
            ext=ext_lower,
            size_mb=round(size, 2),
        )

    @property
    def display_name(self) -> str:
        return os.path.basename(self.file_path)
