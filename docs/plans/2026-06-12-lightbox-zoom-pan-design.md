# Lightbox Zoom + Pan Design

## Motivation

Lightbox 目前只支持 fit/1:1 两种模式的切换，缺少连续的缩放和查看细节时的拖拽平移能力（这是同类软件的核心交互）。

## Goals

- 滚轮平滑缩放（阶梯式：25% / 50% / 100% / 200% / 400%）
- 放大后可拖拽平移查看图片细节
- Z 键切换 fit 和 1:1
- 性能开销尽可能低，不阻塞主线程

## Architecture

### 变更概要

| 文件 | 变更 |
|------|------|
| `src/ui/lightbox.py` | CTkLabel → tk.Canvas，新增缩放/平移逻辑 |

### 图片容器

```
body (CTkFrame)
  └── _image_canvas (tk.Canvas)  ← 替换 CTkLabel
        └── canvas image item
```

- `tk.Canvas` 配置 `highlightthickness=0`，`bg=Colors.LIGHTBOX_BG`
- Canvas 在 body 中 `sticky="nsew"`，跟随窗口 resize

### 缩放模型

```
_ZOOM_LEVELS = [0.25, 0.50, 1.0, 2.0, 4.0]
_zoom_idx = 2  (default = fit)
_factor = _ZOOM_LEVELS[_zoom_idx]
```

缩放比例始终相对于 **fit 尺寸**（即图片在当前窗口下完整可见的大小）：

```
fit_w = viewport_w × (img_w / viewport_w, img_h / viewport_h 的较小值)
fit_h = viewport_h × 同上
display_w = fit_w × _factor
display_h = fit_h × _factor
```

| idx | factor | 相对 fit 尺寸 |
|-----|--------|--------------|
| 0   | 0.25x  | 25%          |
| 1   | 0.50x  | 50%          |
| 2   | 1.0x   | 100% (fit)   |
| 3   | 2.0x   | 200%         |
| 4   | 4.0x   | 400%         |

### 拖拽平移

利用 `tk.Canvas` 内置的 `scan_mark` / `scan_dragto`：

- `<ButtonPress-1>`: `canvas.scan_mark(x, y)`
- `<B1-Motion>`: `canvas.scan_dragto(x, y, gain=1)`
- 仅在 `display_w > viewport_w` 或 `display_h > viewport_h` 时才允许平移
- 切换图片或缩放时，调用 `canvas.xview_moveto(0); canvas.yview_moveto(0)` 复位

### 解码流程

```
ShowCurrent
  → reset _zoom_idx = 2
  → _pool.submit(_decode_worker)  // 仅解码 full-res PIL，不做 resize
  → preload adjacent

DecodeWorker
  → open file → transpose → load → cache → push to queue

PollDecode
  → pop from queue → store _pil_image → _refresh_image()

RefreshImage
  → compute fit_w/fit_h from viewport + image size
  → compute display_w/display_h = fit_size × _ZOOM_LEVELS[_zoom_idx]
  → PIL.resize((display_w, display_h), BILINEAR)   // main thread, <5ms
  → CTkImage(size=(display_w, display_h))
  → canvas.create_image(viewport_center, image=ctk_img)
  → set canvas scrollregion = (display_w, display_h)
  → if display fits viewport: center; else: allow pan
```

### 事件处理

| 事件 | 行为 |
|------|------|
| 滚轮上滚 | `_zoom_idx = min(4, _zoom_idx + 1)` → `_refresh_image()` |
| 滚轮下滚 | `_zoom_idx = max(0, _zoom_idx - 1)` → `_refresh_image()` |
| Z 键 | toggle `_zoom_1_1` flag。On: 原始像素尺寸; Off: 回到 fit |
| 鼠标按下 | `canvas.scan_mark(x, y)` |
| 鼠标拖动 | `canvas.scan_dragto(x, y, gain=1)` |
| 窗口 resize | 如果 `_zoom_idx == 2` 重新计算 fit_size → refresh；否则只 refresh（不计算新 fit） |
| 切换图片 | `_show_current` 重置 idx=2，复位 view |

### 1:1 模式

Z 键切换 `_zoom_1_1` 布尔值：

- 进入 1:1：`display_w = img_w`, `display_h = img_h`
- 退出 1:1：回到 fit（`_zoom_idx = 2`）
- 在 1:1 下滚轮缩放依然有效（内部仍维护 `_zoom_idx`，但显示使用原始像素尺寸）
- 再次 Z → 回到之前保存的 `_zoom_idx`

### UI 变更

- 底部按钮 `Z  1:1` → `Z  缩放`，点击触发 `_toggle_zoom()`
- 按钮文字右侧显示当前缩放比例，例如 `Z  200%` / `Z  50%` / `Z  1:1`

### 边界情况

| 场景 | 处理 |
|------|------|
| 图片比视口小（不放大） | 居中对齐，不允许平移 |
| 4x 下图片超大 | 正常平移，canvas scrollregion 自动适应 |
| 窗口 resize 期间 | 100ms debounce，仅在稳定后触发 refresh |
| 快速连续滚轮 | 每次 `_refresh_image()` 都很便宜（BILINEAR + CTkImage），不会卡顿 |
| 无图片 | Canvas 显示 "(无照片)" 文本 |

## 验证

1. 打开 lightbox → 默认 fit
2. 滚轮上滚 2 次 → 200% → 400%
3. 在 400% 下拖拽 → 图片平滑跟随鼠标
4. 滚轮下滚 4 次 → 回到 fit
5. Z 键 → 1:1 显示原始像素
6. 再 Z 键 → 回到 fit
7. resize 窗口 → fit 模式自适应
8. 切换图片 → 复位到 fit
