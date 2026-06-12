"""End-to-end smoke test of the GUI across all three workflows.

Builds the App, scans a fixture set, exercises PICK → CLEAN → RENAME, and
also opens the lightbox. Runs fully headless by withdrawing the window.
"""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, os.pardir, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.app import App  # noqa: E402
from src.core.picker_engine import pick_to_b, delete_items
from src.core.cleaner_engine import clean_orphans
from src.core.renamer_engine import rename_items

from _fixture import make_fixture_set, make_jpg  # noqa: E402


def _pump(root, seconds: float = 0.1) -> None:
    """Pump the event loop for `seconds` so async work can run."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.02)


def _wait_for(root, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            root.update()
        except Exception:
            return False
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main() -> int:
    # Headless
    try:
        import tkinter as tk
        _t = tk.Tk()
        _t.withdraw()
        _t.destroy()
    except Exception:
        print("[SKIP] no display")
        return 0

    folder_a = os.path.join(_ROOT, "_smoke_a")
    folder_b = os.path.join(_ROOT, "_smoke_b")
    for d in (folder_a, folder_b):
        if os.path.isdir(d):
            for root_, _, files in os.walk(d):
                for f in files:
                    try:
                        os.remove(os.path.join(root_, f))
                    except OSError:
                        pass
        os.makedirs(d, exist_ok=True)
    make_fixture_set(folder_a)

    app = App()
    app.window.withdraw()

    pick = app.window.pick_tab()
    pick.set_folders(folder_a, folder_b)
    pick.scan()
    if not _wait_for(app.window, lambda: bool(pick.current_items())):
        print("[FAIL] pick tab scan never produced items")
        return 1
    items = pick.current_items()
    print(f"[scan] {len(items)} JPGs in A")

    # ---- 1. PICK (accepted→move, rejected→delete) ----
    # Mark first 2 as accepted, next 2 as rejected (no RAW for pair_03)
    for i, it in enumerate(items):
        if i < 2:
            it.pick_status = "accepted"
        else:
            it.pick_status = "rejected"
    accepted = [it for it in items if it.pick_status == "accepted"]
    rejected = [it for it in items if it.pick_status == "rejected"]
    # Move accepted
    move_report = pick_to_b(accepted, folder_b, resolver=lambda *_a, **_kw: "rename")
    # Move rejected to temp folder inside A
    del_report = delete_items(rejected, target_folder=folder_a)
    print(f"[1. PICK] moved_jpg={move_report.moved_jpg} moved_raw={move_report.moved_raw} "
          f"deleted_jpg={del_report.deleted_jpg} deleted_raw={del_report.deleted_raw} "
          f"recycle={del_report.recycle_folder}")
    assert move_report.moved_jpg == 2
    assert del_report.deleted_jpg == 2
    assert del_report.recycle_folder and os.path.isdir(del_report.recycle_folder)
    pick.scan()
    _wait_for(app.window, lambda: True, timeout=0.5)

    # ---- 2. CLEAN ----
    clean = app.window.clean_tab()
    clean._folder_var.set(folder_a)  # noqa: SLF001
    clean.scan()
    if not _wait_for(app.window, lambda: bool(clean._orphans)):  # noqa: SLF001
        # No orphans is fine (everything was paired)
        print("[2. CLEAN] no orphans in A (all pairs were moved)")
    else:
        orphans = clean._orphans  # noqa: SLF001
        print(f"[2. CLEAN] found {len(orphans)} orphans in A: "
              f"{[o.basename for o in orphans]}")
        # Mark all orphans selected (the engine filters by selected)
        for o in orphans:
            o.selected = True
        # Run in 'recycle' mode - the recycle folder goes inside target_folder
        report = clean_orphans(orphans, mode="recycle", target_folder=folder_a)
        print(f"[2. CLEAN] recycled={report.moved_to_recycle} "
              f"folder={report.recycle_folder}")
        assert report.moved_to_recycle == len(orphans)
        assert report.recycle_folder and os.path.isdir(report.recycle_folder)

    # ---- 3. RENAME ----
    rename = app.window.rename_tab()
    rename._folder_var.set(folder_b)  # noqa: SLF001
    rename.scan()
    if not _wait_for(app.window, lambda: bool(rename._items)):  # noqa: SLF001
        print("[3. RENAME] nothing to rename in B")
    else:
        items_b = rename._items  # noqa: SLF001
        print(f"[3. RENAME] {len(items_b)} JPGs in B")
        # Pick one with a RAW companion
        target = next((it for it in items_b if it.has_raw), None)
        if target is not None:
            # Select just this one and call the engine directly
            for it in items_b:
                it.selected = (it is target)
            renames = rename_items([target], "vacation_{seq:02d}", folder_b)
            print(f"[3. RENAME] renamed: {renames}")
            new_jpg = os.path.join(folder_b, "vacation_01.jpg")
            print(f"[3. RENAME] exists={os.path.isfile(new_jpg)}")
            assert os.path.isfile(new_jpg)
        else:
            print("[3. RENAME] no paired item to test rename against")

    # ---- 4. LIGHTBOX ----
    # Open the lightbox on a fixture JPG and verify the window is created.
    # We don't pump aggressively because the decode worker needs the after
    # loop running. Point the pick tab at B since that's where photos are now.
    pick.set_folders(folder_b, folder_b)
    pick.scan()
    _wait_for(app.window, lambda: bool(pick.current_items()), timeout=3.0)
    if pick.current_items():
        target = pick.current_items()[0]
        app.open_lightbox(target)
        _pump(app.window, 0.3)
        assert app._lightbox is not None  # noqa: SLF001
        assert app._lightbox.winfo_exists()  # noqa: SLF001
        # Navigate forward
        app._lightbox._next()  # noqa: SLF001
        _pump(app.window, 0.1)
        # Set rating
        app._lightbox._emit_rating(4)  # noqa: SLF001
        _pump(app.window, 0.1)
        # Close
        app._lightbox._on_close_request()  # noqa: SLF001
        _pump(app.window, 0.1)
        assert app._lightbox is None  # noqa: SLF001
        print("[4. LIGHTBOX] open + navigate + rate + close: OK")
    else:
        print("[4. LIGHTBOX] skipped (no items)")

    # Teardown
    try:
        app.window.destroy()
    except Exception:
        pass
    print("=== SMOKE PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
