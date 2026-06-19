# RawPicker

A lightweight RAW + JPG picking and cleaning desktop app for photographers — keyboard-first, dark-themed, performance-optimized, and forever free & open-source.

## Features

- **Picking workflow** — scan a folder of JPGs, preview full-resolution, mark (Accept/Reject/Pending), and batch-move accepted JPGs (with companion RAWs) to destination folder while deleting rejected ones.
- **Lightbox** — full-screen viewer with 5-level stepped zoom (`Z` toggles fit/1:1, `[0.25×, 0.5×, 1×, 2×, 4×]`), click-drag pan, keyboard navigation (`←`/`→`), and adjacent-image pre-decode for instant switching.
- **Cleaning workflow** — scan paired folders for orphan RAW/JPG files, preview orphans, and delete or move them to a recovery folder.
- **Renaming workflow** — batch-rename files using a template (`{basename}`, `{seq}`, `{rating}`, `{date}`, `{camera}`).
- **Map view** — see GPS-tagged photos on OpenStreetMap, color-coded by pick state.
- **Filter by pick status** — show all, accepted, rejected, or GPS-tagged photos.
- **Keyboard-first** — every high-frequency action has a hotkey; minimal mouse reliance.
- **Dark professional theme** — neutral-gray palette inspired by Lightroom / Capture One / Darktable design principles.

## Performance

- Background thumbnail decoding with thread pool and unified LRU cache (1024 entries, 6 parallel workers)
- BILINEAR resampling for thumbnails (3–5× faster than LANCZOS, imperceptible at thumbnail scale)
- PIL image cache shared between grid and lightbox — no redundant decode on resize or zoom toggle
- Speculative pre-decode of adjacent images in lightbox for instant navigation
- Scroll-direction prediction in thumbnail grid; debounced relayout (150 ms)
- `PreviewCache` (capacity 4) for lightbox full-resolution views

## Quickstart

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```powershell
# Install dependencies (uv will provision Python automatically)
uv sync

# Run the app
uv run rawpicker
```

## Packaging

Build a standalone Windows executable with version metadata:

```powershell
uv run python build.py
```

The output is at `dist/RawPicker.exe` (version sourced from `src/__init__.py`).

## Project layout

```
src/
  config/         constants, raw-format list, dark/light color palettes
  core/           scanners, picker/cleaner/renamer engines, EXIF reader, file ops
  models/         PhotoItem, OrphanItem, AppConfig
  ui/             main window + tabs (pick, clean, rename, map) + lightbox + widgets
  utils/          image cache, thumbnail loader, config store, validators
  app.py          application controller — wires UI to engines
  main.py         entry point
tests/            pytest suite + headless smoke tests
icon.ico          application icon
```

## Tech Stack

| Module | Technology |
|--------|-----------|
| GUI framework | customtkinter |
| Image processing | Pillow |
| Online map | tkintermapview (OpenStreetMap) |
| Trash operations | send2trash |
| Window styling | pywinstyles |
| Packaging | PyInstaller |

## License

GPL-3.0
