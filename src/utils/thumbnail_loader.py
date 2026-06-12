"""Background thumbnail decoder.

Decoupling image decoding from the main thread is the single biggest perf
win in a 1000-photo grid: per-cell `Image.open → transpose → resize →
Tk PhotoImage` runs ~25 ms per cell, and doing 30 of those per chunk on
the main thread blocks the UI for ~750 ms at a time.

The loader returns **PIL.Image** objects (already decoded, EXIF-rotated,
and resized to the requested `size`×`size`). The caller wraps them into
whatever Tk format its widget needs (CTkImage for CTk widgets,
ImageTk.PhotoImage for raw tk.Canvas). The heavy decode work stays on
the worker; the cheap format-wrap happens on the main thread per cell.

This module owns:
- a `ThreadPoolExecutor` of `min(4, cpu_count)` workers
- a thread-safe PIL-image LRU cache (keyed by `(path, size)`)
- a FIFO result queue
- a generation counter that lets callers cancel in-flight work
- a callback registry so the main thread can dispatch results

Expected pattern from a UI cell:

    loader = ThumbnailLoader()
    loader.submit(path, size, lambda pil: cell.apply_image(pil), generation=1)
    # ...later, in widget.after(20, self._poll):
    loader.dispatch()   # invokes queued on_ready callbacks on main thread
"""
from __future__ import annotations

import os
import queue
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Set, Tuple

from PIL import Image, ImageOps


def _decode_to_pil(path: str, size: int) -> Optional[Image.Image]:
    """Open, EXIF-rotate, and resize to (size, size). Worker-side helper."""
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            return img.resize((size, size), Image.Resampling.LANCZOS)
    except Exception:
        return None


class _PilLru:
    """Thread-safe LRU for (path, size) → PIL.Image."""

    def __init__(self, capacity: int = 1024):
        self._d: "OrderedDict[Tuple[str, int], Image.Image]" = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def get_or_load(self, path: str, size: int) -> Optional[Image.Image]:
        key = (path, size)
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
        pil = _decode_to_pil(path, size)
        if pil is None:
            return None
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
            self._d[key] = pil
            while len(self._d) > self._capacity:
                self._d.popitem(last=False)
        return pil


class ThumbnailLoader:
    """Decode thumbnails off the main thread; return PIL images."""

    def __init__(self, num_workers: Optional[int] = None, capacity: int = 1024):
        if num_workers is None:
            cpu = os.cpu_count() or 2
            num_workers = max(1, min(4, cpu))
        self._num_workers = num_workers
        self._cache = _PilLru(capacity=capacity)
        self._q: "queue.Queue[Tuple[int, Optional[Image.Image]]]" = queue.Queue()
        self._inflight: Set[Tuple[str, int]] = set()
        self._inflight_lock = threading.Lock()
        self._cancelled: Set[int] = set()
        self._cancel_lock = threading.Lock()
        # callback_id -> (generation, on_ready, path, size)
        self._callbacks: dict = {}
        self._cb_lock = threading.Lock()
        self._next_cb_id = 1
        self._ex = ThreadPoolExecutor(
            max_workers=num_workers, thread_name_prefix="thumb")
        self._closed = False

    # -- public API --------------------------------------------------------
    @property
    def num_workers(self) -> int:
        return self._num_workers

    def submit(self, path: str, size: int,
               on_ready: Callable[[Optional[Image.Image]], None],
               generation: int) -> None:
        """Schedule a decode. The on_ready callback receives a PIL.Image
        (already resized to `size`×`size`) and is invoked on the main
        thread by `dispatch()`. On failure, the callback gets `None`."""
        if self._closed:
            return
        if not path or not os.path.isfile(path):
            try:
                on_ready(None)
            except Exception:
                pass
            return
        with self._cb_lock:
            cbid = self._next_cb_id
            self._next_cb_id += 1
            self._callbacks[cbid] = (generation, on_ready, path, size)
        with self._inflight_lock:
            key = (path, size)
            if key in self._inflight:
                try:
                    self._ex.submit(self._redecode_job, path, size, cbid)
                except RuntimeError:
                    pass
                return
            self._inflight.add(key)
        try:
            self._ex.submit(self._decode_job, path, size, cbid)
        except RuntimeError:
            with self._inflight_lock:
                self._inflight.discard(key)
            with self._cb_lock:
                self._callbacks.pop(cbid, None)

    def dispatch(self, max_callbacks: int = 8) -> int:
        """Drain the result queue and invoke registered callbacks.

        Call from the main thread. `max_callbacks` caps how many on_ready
        callbacks fire in a single dispatch — this keeps the main thread
        responsive when hundreds of decodes complete in the same poll
        cycle. Returns the number of callbacks invoked (useful for tests).
        """
        invoked = 0
        with self._cancel_lock:
            cancelled = set(self._cancelled)
        try:
            while invoked < max_callbacks:
                cbid, pil = self._q.get_nowait()
                with self._cb_lock:
                    entry = self._callbacks.pop(cbid, None)
                if entry is None:
                    continue
                gen, on_ready, _path, _size = entry
                if gen in cancelled:
                    continue
                try:
                    on_ready(pil)
                    invoked += 1
                except Exception:
                    pass
        except queue.Empty:
            pass
        return invoked

    def cancel_generation(self, generation: int) -> None:
        with self._cancel_lock:
            self._cancelled.add(generation)
        with self._cb_lock:
            stale = [cbid for cbid, (gen, *_rest) in self._callbacks.items()
                     if gen == generation]
            for cbid in stale:
                self._callbacks.pop(cbid, None)

    def is_cancelled(self, generation: int) -> bool:
        with self._cancel_lock:
            return generation in self._cancelled

    def pending_count(self) -> int:
        with self._cb_lock:
            return len(self._callbacks)

    def shutdown(self) -> None:
        self._closed = True
        try:
            self._ex.shutdown(wait=False)
        except Exception:
            pass

    # -- internals ---------------------------------------------------------
    def _decode_job(self, path: str, size: int, cbid: int) -> None:
        try:
            pil = self._cache.get_or_load(path, size)
            self._q.put((cbid, pil))
        except Exception:
            self._q.put((cbid, None))
        finally:
            with self._inflight_lock:
                self._inflight.discard((path, size))

    def _redecode_job(self, path: str, size: int, cbid: int) -> None:
        try:
            pil = self._cache.get_or_load(path, size)
            self._q.put((cbid, pil))
        except Exception:
            self._q.put((cbid, None))
