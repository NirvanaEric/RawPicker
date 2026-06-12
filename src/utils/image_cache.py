"""Two LRU image caches for the picking workflow.

- ThumbnailCache: small square previews, 1024-entry LRU. Decodes fast and
  applies EXIF orientation so portrait shots render right-side-up.
- PreviewCache:   larger previews for the right-hand panel + lightbox,
  small capacity (4) since they're bigger. Also applies EXIF orientation.

Both are thread-safe.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Optional, Tuple

from PIL import Image, ImageFile

# Be tolerant of truncated JPEGs so a single broken file doesn't kill a scan
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

from src.core.metadata_reader import transpose_image

try:
    from customtkinter import CTkImage
except ImportError:  # pragma: no cover - customtkinter is a hard dep
    CTkImage = None  # type: ignore[assignment]


def _make_ctk(img: Image.Image, size: Tuple[int, int]) -> "CTkImage | None":
    if CTkImage is None:
        return None
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return CTkImage(light_image=img, dark_image=img, size=size)


class _BaseLRUCache:
    """Common LRU + decode plumbing shared by thumb/preview caches."""

    def __init__(self, capacity: int) -> None:
        self._capacity = max(1, int(capacity))
        self._cache: "OrderedDict[tuple, object]" = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _key(self, path: str, size: Tuple[int, int]) -> tuple:
        return (path, int(size[0]), int(size[1]))

    def get(self, path: str, size: Tuple[int, int]):
        key = self._key(path, size)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
        return cached

    def put(self, path: str, size: Tuple[int, int], image) -> None:
        key = self._key(path, size)
        with self._lock:
            self._cache[key] = image
            self._cache.move_to_end(key)
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)


class ThumbnailCache(_BaseLRUCache):
    """Square thumbnails. Capacity ~1024 keeps memory bounded for big folders."""

    def __init__(self, capacity: int = 1024) -> None:
        super().__init__(capacity)

    def get_or_load(self, path: str, size: int):
        size_pair = (size, size)
        cached = self.get(path, size_pair)
        if cached is not None:
            return cached
        if not os.path.isfile(path):
            return None
        try:
            with Image.open(path) as im:
                im = transpose_image(im)
                im.thumbnail((size, size), Image.Resampling.LANCZOS)
                ctk = _make_ctk(im, (size, size))
        except (OSError, ValueError):
            return None
        if ctk is not None:
            self.put(path, size_pair, ctk)
        return ctk


class PreviewCache(_BaseLRUCache):
    """Larger rectangular previews. Small capacity (default 4) since each
    decoded image is much bigger than a thumbnail."""

    def __init__(self, capacity: int = 4) -> None:
        super().__init__(capacity)

    def get_or_load(self, path: str, max_size: Tuple[int, int]):
        """Decode `path` fitted into `max_size` (w, h), preserving aspect.

        `max_size` is the maximum bounding box; the resulting image is
        never larger than it on either axis.
        """
        cached = self.get(path, max_size)
        if cached is not None:
            return cached
        if not os.path.isfile(path):
            return None
        try:
            with Image.open(path) as im:
                im = transpose_image(im)
                im.thumbnail(max_size, Image.Resampling.LANCZOS)
                w, h = im.size
                ctk = _make_ctk(im, (w, h))
        except (OSError, ValueError):
            return None
        if ctk is not None:
            self.put(path, max_size, ctk)
        return ctk


# Backwards-compatible alias so legacy call sites that imported ImageCache
# (e.g. tests) keep working. New code should import ThumbnailCache / PreviewCache
# directly to make the intent explicit.
ImageCache = ThumbnailCache
