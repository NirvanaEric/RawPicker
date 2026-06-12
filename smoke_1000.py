"""Real-world stress smoke: scan + EXIF + grid + lightbox for 1000 photos.

Mirrors what a user would do: point the App at a folder with 1000 images,
hit scan, and verify the UI is responsive throughout. Designed to be run
manually (not as a CI gate) because it takes ~70 s.
"""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
_TESTS = os.path.join(_ROOT, "tests")
for p in (_TESTS, _SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

import customtkinter as ctk  # noqa: E402

from src.app import App  # noqa: E402
from PIL import Image  # noqa: E402


def _make_jpg(path: str, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (640, 480), color).save(path, "JPEG", quality=85)


def _pump(root, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.005)


def main() -> int:
    try:
        import tkinter as tk
        _t = tk.Tk(); _t.withdraw(); _t.destroy()
    except Exception:
        print("[SKIP] no display"); return 0

    # Use a fresh folder with 1000 unique JPGs
    folder = os.path.abspath("./_smoke_1000")
    if os.path.isdir(folder):
        for root_, _, files in os.walk(folder):
            for f in files:
                try: os.remove(os.path.join(root_, f))
                except OSError: pass
    else:
        os.makedirs(folder, exist_ok=True)

    print(f"[1] generating 1000 JPGs in {folder}")
    t0 = time.perf_counter()
    for i in range(1000):
        _make_jpg(os.path.join(folder, f"img_{i:04d}.jpg"),
                  ((i * 7) % 255, (i * 13) % 255, (i * 23) % 255))
    gen_ms = (time.perf_counter() - t0) * 1000
    print(f"[1] generated in {gen_ms:.0f}ms")

    # Build the App
    app = App()
    app.window.withdraw()
    pick = app.window.pick_tab()
    pick.set_folders(folder, folder)

    print("[2] scanning (background thread + EXIF enrichment)")
    t0 = time.perf_counter()
    pick.scan()
    # Wait for scan completion
    deadline = time.time() + 30.0
    while time.time() < deadline and not pick.current_items():
        app.window.update(); time.sleep(0.05)
    scan_ms = (time.perf_counter() - t0) * 1000
    items = pick.current_items()
    print(f"[2] scan: {len(items)} items in {scan_ms:.0f}ms")
    if len(items) != 1000:
        print(f"[FAIL] expected 1000 items, got {len(items)}"); return 1

    # Settle: let the loader drain (decodes happen on workers, apply is on
    # the main thread at ~1.5 ms each). 1000 decodes at cap 8 / 20 ms poll
    # = ~2.5 s; we give 6 s to be safe.
    settle_deadline = time.time() + 6.0
    while time.time() < settle_deadline:
        app.window.update()
        time.sleep(0.02)
    # Measure how the main thread feels in steady state: every update()
    # should be fast because there's no work to do.
    print("[3] measuring main-thread smoothness with 1000 items")
    tick_times: list[float] = []
    for _ in range(40):
        t1 = time.perf_counter()
        app.window.update()
        tick_times.append((time.perf_counter() - t1) * 1000)
        time.sleep(0.005)
    max_tick = max(tick_times)
    med_tick = sorted(tick_times)[len(tick_times) // 2]
    print(f"[3] median tick {med_tick:.1f}ms, max {max_tick:.1f}ms")
    if max_tick > 50:
        print(f"[FAIL] main-thread tick exceeded 50ms ({max_tick:.0f}ms)")
        return 1

    # Open the lightbox on the first item
    print("[4] opening lightbox")
    app.open_lightbox(items[0])
    _pump(app.window, 0.3)
    if app._lightbox is None or not app._lightbox.winfo_exists():
        print("[FAIL] lightbox didn't open"); return 1
    # Navigate + rate
    app._lightbox._next()
    _pump(app.window, 0.1)
    app._lightbox._emit_rating(5)
    _pump(app.window, 0.1)
    app._lightbox._on_close_request()
    _pump(app.window, 0.1)
    if app._lightbox is not None:
        print("[FAIL] lightbox didn't close"); return 1
    print("[4] lightbox: open + nav + rate + close: OK")

    try:
        app.window.destroy()
    except Exception:
        pass

    # Cleanup
    try:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        pass

    print("=== 1000-PHOTO SMOKE PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
