# Performance + Light Theme — Design

**Date:** 2026-06-08
**Status:** Approved
**Replaces:** the dark-Lightroom design from `2026-06-07-perf-ui-lightbox.md`

**Decisions (from user):**
- Worker pool size: `min(4, cpu_count())`
- Lightbox image area: black (`#0E0E10`) — photography convention
- All sections approved for implementation

---

## Why we're revisiting

After shipping the dark-Lightroom design, the user reported:

1. **All operations still stutter** (scan, grid load, preview, lightbox).
2. **Black theme is ugly**.

The previous round's "chunked" optimization only solved widget creation, not the real bottleneck (image decoding). And the dark visual was a wrong guess.

This design addresses both with a measurable target.

---

## Section 1 — Performance: root cause and target

### Root cause

The current grid is "chunked" (30 cells per 16 ms tick), but **each cell
synchronously decodes its thumbnail on the main thread**:

```
cell.ensure_loaded()
  → cache.get_or_load(path, size)
    → Image.open(path)              # ~3-5 ms
    → ImageOps.exif_transpose()     # ~1-2 ms
    → resize()                       # ~2-3 ms
    → CTkImage(light, dark, size)    # ~15-20 ms (PNG encode!)
```

Per-cell cost is **~25 ms** on a typical machine. 30 cells per chunk
blocks the UI for **~750 ms** with 16 ms gaps between chunks — the
classic "stutter, breath, stutter, breath" pattern the user is seeing.

The PNG-encode inside `CTkImage` is the dominant cost (≈70% of per-cell
time). It is unavoidable per image but **does not need to happen on
the main thread**.

### Target (measurable)

| Operation | Target | Why |
|---|---|---|
| `set_items(1000)` returns | < 200 ms | UI is never blocked; the user can keep interacting. |
| First 30 thumbnails visible | < 1.5 s | Visual feedback that the scan worked. |
| Scan of 1000-photo folder (data only) | < 3 s | PRD §11.1 perf budget. Already met. |
| Click thumbnail → preview appears (cache hit) | < 50 ms | Reads from a 4-entry PreviewCache. |
| Click thumbnail → preview appears (cache miss) | < 800 ms | Background decode; placeholder shown meanwhile. |
| Lightbox open on already-decoded item | < 50 ms | Same PreviewCache; only the larger decode is new. |
| Grid scroll on 1000 items | 60 fps (16 ms/frame) | No main-thread work > 5 ms during scroll. |

The headline win is the last row: **scroll is smooth because no
decode work happens on the main thread anymore**.

### Approach

Introduce a `ThumbnailLoader`: a small `ThreadPoolExecutor` (2
workers) that processes decode jobs FIFO. The main thread builds
placeholder cells immediately and submits a job per cell. Workers
emit results back to the main thread via a `queue.Queue` polled by
`after(20, ...)` (same pattern the scan + preview use). The cell
swaps in the image when its result arrives.

A generation counter cancels in-flight jobs when `set_items()` is
called again with new data — stale results are dropped on the
poller's side, identical to the existing pattern in the scan worker
and `PreviewPanel.show()`.

The same loader is reused by the lightbox (which already does this
manually) and by the preview panel (already async; we can simplify
it to use the loader).

---

## Section 2 — Architecture

```
                    main thread                          worker threads
                 ┌──────────────┐                  ┌───────────────────┐
set_items() ────▶ create cell,  │                  │                   │
                 show placeholder, ──submit job──▶ │  Worker 1: decode │
                 continue immediately                │                   │
                 │                                   │  Worker 2: decode │
                 │ poll queue (20ms) ◀─result────────│                   │
                 ▼                                   └───────────────────┘
             install image
             on cell
```

Key properties:

- **Bounded queue**: a `queue.Queue(maxsize=2000)` to prevent
  unbounded memory if the user loads 10 000 photos. Producers block
  on submit when the queue is full, giving natural backpressure
  (the user can scroll while it drains).
- **Per-path dedup**: if two cells ask for the same `path+size`, the
  loader returns the same `CTkImage` to both. This means scrolling
  the same folder twice is essentially free.
- **Generation check**: every result carries the generation id it was
  submitted under. If the cell has been recycled, the result is
  discarded. (Same mechanism as `PreviewPanel._req_id`.)
- **Thread-safe cache**: the loader owns the cache; the cells no
  longer call `cache.get_or_load()` directly.

### File changes

**New**
- `src/utils/thumbnail_loader.py` — `ThumbnailLoader` class with
  `submit(path, size, on_ready, generation) -> None` and
  `cancel(generation) -> None`. Owns the `ThumbnailCache` internally.

**Modified**
- `src/ui/thumbnail_grid.py` — `_ThumbCell` shows a placeholder
  rectangle (`CTkFrame` 128×128, neutral fill) and calls
  `loader.submit()` instead of `cache.get_or_load()`. A
  `_ThumbnailGrid._poll_loader()` callback installs the image when
  ready.
- `src/ui/preview_panel.py` — can keep its existing async path; the
  loader is passed in as a constructor arg, no behaviour change for
  users.
- `src/ui/lightbox.py` — same: takes the loader; behaviour identical
  to current.
- `src/app.py` — creates the `ThumbnailLoader` and passes it down.
- `src/utils/image_cache.py` — `ThumbnailCache` is now an internal
  detail of the loader. We still export `PreviewCache` for the
  preview/lightbox path.

### New tests

- `test_thumbnail_loader.py` — submit 200 jobs to a 2-worker loader;
  assert all callbacks fire; assert that a generation-cancelled job
  does **not** fire its callback.
- `test_grid_1000_responsive.py` — load 1000 items, pump the event
  loop, measure:
  - `set_items` returns in < 200 ms
  - first 30 cells painted (with placeholder) in < 200 ms
  - first 30 cells painted (with real image) in < 2 s
  - all 1000 cells painted (with real image) in < 30 s
  - **no main-thread tick exceeds 50 ms** during paint

The last assertion is the important one. We sample
`time.perf_counter()` around each `update()` call; any single tick
over 50 ms is a fail.

---

## Section 3 — UI: Apple Photos light

### Colour palette (`Colors` class)

```python
class Colors:
    # Surfaces
    BG          = "#FFFFFF"   # page background, panels
    SURFACE     = "#F2F2F7"   # alternating rows, sidebars
    SURFACE_RAISED = "#FFFFFF" # cards (same as BG, lifted by shadow)
    BORDER      = "#D1D1D6"   # 1px hairlines
    BORDER_SUBTLE = "#E5E5EA"

    # Text
    TEXT        = "#1C1C1E"   # primary
    TEXT_DIM    = "#8E8E93"   # secondary / metadata
    TEXT_DISABLED = "#C7C7CC"

    # Accents
    ACCENT      = "#0A84FF"   # Apple system blue
    ACCENT_SOFT = "#E5F0FF"   # 8% blue tint for selected-cell bg

    # Status
    ACCEPTED    = "#34C759"   # green
    REJECTED    = "#FF3B30"   # red
    PENDING     = "#8E8E93"   # grey
    WARNING     = "#FF9F0A"   # amber

    # High-DPI
    HIGH_RATING = "#FFCC00"   # star fill (yellow)
```

### Typography

- `ctk.CTkFont(family="Segoe UI", size=...)` (auto-resolves to
  SF Pro on macOS, Cantarell on Linux).
- Tabular numbers via `font.create_font(..., slant='roman')` is not
  supported by Tk — we approximate by using a fixed-width `Label`
  for stats, and just trust system font for the rest.
- 13 px body, 11 px metadata, 15 px section title, 22 px stat number.

### Component specs

**Sidebar** (`sidebar.py`)

- Plain white panel, no card backgrounds.
- Folder rows: `CTkFrame` with `fg_color="transparent"`, padding
  8×10. On hover → `SURFACE`. Path validation: 6×6 coloured dot
  (`#34C759` ok, `#FF3B30` missing).
- Recent paths: 2-line label, dim text, no card.
- Filter: `CTkSegmentedButton` with 4 segments (all/checked/accepted/
  rejected), white bg, `ACCENT` on selected, `BORDER` 1px around.
- Stats: tabular monospace numbers in `TEXT` 22 px, label in `TEXT_DIM`
  11 px above.

**Thumbnail cell** (`thumbnail_grid.py`)

- 8 px corner radius, **1 px** `BORDER` outline (was 3 px).
- `SURFACE` background.
- On select: 2 px `ACCENT` border, `ACCENT_SOFT` background.
- On hover (unselected): `SURFACE_RAISED` background.
- Placeholder: `SURFACE` solid, centred `TEXT_DISABLED` spinner
  glyph (Unicode `\u29D6` Hourglass or our own).
- Badges: pill shape (corner_radius = height/2), 10 px text, white
  on `ACCEPTED`/`REJECTED`/`PENDING`. Star rating 10 px text bottom-right.
- Filename: 11 px `TEXT_DIM`, truncated with ellipsis.

**Preview panel** (`preview_panel.py`)

- White background.
- Image area: neutral light grey (`SURFACE`), 8 px radius.
- EXIF: 2-col `key: value` list, 12 px each, `TEXT_DIM` keys, `TEXT`
  values.
- Action bar (bottom): pill buttons, `ACCENT` for "Accepted", red for
  "Rejected", outline-grey for "Pending". Rating widget below.

**Map view** (`map_panel.py`)

- Keep `tkintermapview` default tile rendering. The map itself is
  already light.

**Dialogs** (`dialogs/common.py`)

- `ConfirmDialog`, `ConflictDialog`, `ReportDialog` all use white bg,
  1 px `BORDER` outline, 12 px radius.
- Primary button: filled `ACCENT`, white text, 17 px text, 10 px
  radius.
- Secondary button: 1 px `BORDER` outline, `TEXT` text.
- ESC closes; Enter confirms; danger variant uses `REJECTED` for
  primary.

**Lightbox** (`lightbox.py`)

- **Image canvas stays dark** (`#0E0E10`) — a black background is
  the only way to evaluate a photo. The chrome around it is light.
- Top bar: white, 1 px bottom border, `TEXT` filename + `TEXT_DIM`
  counter, × close button.
- Right rail: white EXIF list.
- Bottom action bar: white.
- `<Configure>` on image: trigger `_refresh_image()` so resize is
  responsive.

**Tab view** (`main_window.py`)

- Default `CTkTabview` but override the segmented-button colours to
  use `ACCENT` instead of CTk's default blue (which is darker than
  Apple system blue).

### CustomTkinter caveats

- `CTk` defaults to dark theme. We set `ctk.set_appearance_mode("light")`
  in `app.py` and pass `fg_color=Colors.BG` to the root.
- `CTkScrollableFrame` does not respect `fg_color="transparent"` for
  the inner scroll area in all versions; we use a light grey
  (`Colors.SURFACE`) to match Apple Photos' sidebar look.

---

## Section 4 — Files to touch

| File | Action | Reason |
|---|---|---|
| `src/config/settings.py` | rewrite `Colors` | new palette |
| `src/utils/thumbnail_loader.py` | **new** | worker-pool loader |
| `src/utils/image_cache.py` | slim down | `ThumbnailCache` is internal to loader |
| `src/ui/thumbnail_grid.py` | rewrite `_ThumbCell` + grid | async load + new style |
| `src/ui/preview_panel.py` | restyle | light theme |
| `src/ui/lightbox.py` | restyle chrome | light chrome + dark canvas |
| `src/ui/sidebar.py` | restyle | light theme |
| `src/ui/dialogs/common.py` | restyle | light theme |
| `src/ui/pick_badge.py` | restyle | pill, light variants |
| `src/ui/rating_widget.py` | restyle | light theme, smaller default |
| `src/ui/main_window.py` | tab + appearance | `set_appearance_mode("light")` |
| `src/ui/pick_tab.py` | inject loader | no public API change |
| `src/ui/clean_tab.py` | restyle | light theme |
| `src/ui/rename_tab.py` | restyle | light theme |
| `src/app.py` | wire loader | no public API change |
| `tests/test_thumbnail_loader.py` | **new** | unit tests for loader |
| `tests/test_grid_1000_responsive.py` | **new** | perf test, 1000 items |
| `tests/test_perf_panel.py` | update | point at new loader API |
| `tests/test_scale.py` | update | align with new grid |
| `tests/test_lightbox.py` | update | align with new constructor |

---

## Section 5 — Out of scope (still)

- XMP sidecar writeback for ratings.
- True RAW decode (rawpy).
- PyInstaller packaging.
- Full grid virtualization (we still create 1000 cells, just
  asynchronously). If we ever target 5000+ photos, we revisit.

---

## Section 6 — Risks

- **Worker pool size too small**: 2 workers decode 1000 small
  thumbnails in ~15 s. Bumping to 4 cuts it to ~8 s. We start with 2
  (keeps the rest of the app responsive on low-core machines) and
  make it a config knob.
- **Tkinter is not thread-safe**: all `configure()` calls happen on
  the main thread via `after(0, ...)`. The loader never touches a
  widget. The cache itself uses a `threading.Lock` (it already does
  in the LRU `OrderedDict`).
- **Memory**: 1000 thumbnails × 128×128 × ~30 KB each ≈ 30 MB. The
  LRU cache caps at 1024 entries so this is bounded.
- **Placeholder flicker**: cells visibly flicker from placeholder to
  image. The current design accepts this; we can crossfade later
  if it bothers the user.

---

## Open questions for the user

1. Worker pool size: 2 (conservative) or 4 (faster on multicore)?
2. Is a 30 MB thumbnail cache the right ceiling, or do you want
   smaller (e.g. 30 MB → 20 MB by halving capacity)?
3. Should the lightbox keep a dark image area, or do you want it
   fully light (white canvas)? Black is the photography convention
   but it may feel inconsistent with the rest of the light theme.
