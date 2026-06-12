# RawPicker Pro

A lightweight RAW + JPG picking and cleaning desktop app for photographers.

## Features

- **Picking workflow** — scan a folder of JPGs, preview, mark (Accept/Reject/Pending), and move JPGs (with their companion RAW) to a destination folder in one click.
- **Cleaning workflow** — find orphan RAW/JPG files (no matching pair) and clean them up safely.
- **Renaming workflow** — batch-rename files using a template (`{basename}`, `{seq}`, `{rating}`, `{date}`, `{camera}`).
- **Map view** — see GPS-tagged photos on OpenStreetMap, color-coded by pick state.
- **Filter by pick status** — show all, accepted, rejected, or GPS-tagged photos.
- **Keyboard-first** — every high-frequency action has a hotkey.

## Performance

- Background thumbnail decoding with thread pool and LRU cache (2048 entries, 6 parallel workers)
- PIL image cache shared between grid and lightbox — no redundant decode on resize or zoom toggle
- Speculative pre-decode of adjacent images in lightbox for instant navigation
- Debounced grid relayout (150 ms) with lazy off-screen loading via background drain

## Tech Stack

- GUI: `customtkinter`
- Image: `Pillow`
- Map: `tkintermapview` (OpenStreetMap)
- Trash: `send2trash`

## Quickstart

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```powershell
# Install dependencies (uv will provision Python automatically)
uv sync

# Run the app
uv run raw-picker-pro
```

## Project layout

```
src/
  config/         constants, raw-format list, color palette
  core/           scanners, picker/cleaner/renamer engines, EXIF reader, file ops
  models/         PhotoItem, OrphanItem, AppConfig
  ui/             main window + tabs + widgets + dialogs
  utils/          image cache, thumbnail loader, validators
  app.py          application controller
  main.py         entry point
tests/            pytest suite + headless smoke tests
```
