# RawPicker Pro

专为摄影师打造的轻量级 RAW + JPG 选片与清理桌面工具 — 键盘优先、深色专业主题、性能优先。

## 功能特性

- **选片工作流** — 扫描文件夹内 JPG，预览全分辨率照片，标记状态（`P` 保留/`O` 删除/`[` 待定），一键批量移动保留的 JPG（连带 RAW 文件）到目标文件夹，同时删除标记为删除的文件。
- **灯箱预览** — 全屏查看器，5 级阶梯式缩放（`Z` 切换适应屏幕/100%，缩放倍率 `[0.25×, 0.5×, 1×, 2×, 4×]`），鼠标拖拽平移，键盘翻页（`←`/`→`），侧邻图片预解码实现即切换。
- **清理工作流** — 扫描成对文件夹中孤立的 RAW/JPG 文件，预览后删除或移至回收文件夹。
- **重命名工作流** — 使用模板批量重命名（`{basename}`, `{seq}`, `{rating}`, `{date}`, `{camera}`）。
- **地图视图** — 在 OpenStreetMap 上查看带有 GPS 坐标的照片，按选择状态颜色编码。
- **筛选** — 按选择状态（全部/保留/删除/有 GPS）筛选。
- **键盘优先** — 高频操作均有快捷键，减少对鼠标的依赖。
- **深色专业主题** — 借鉴 Lightroom / Capture One / Darktable 设计原则的中性灰色调色板，确保长时间编辑不疲劳。

## 性能优化

- 后台线程池解码缩略图，统一 LRU 缓存（1024 条目，6 个并行工作线程）
- BILINEAR 重采样生成缩略图（比 LANCZOS 快 3–5 倍，缩略图尺寸下无感知差异）
- PIL 图像缓存在网格视图与灯箱间共享 — 缩放或放大切换时无需重复解码
- 灯箱侧邻图片预解码，实现即时翻页
- 缩略图网格滚动方向预测；延迟重排（150 ms）
- `PreviewCache`（容量 4）用于灯箱全分辨率视图

## 技术栈

- GUI: `customtkinter`
- 图像处理: `Pillow`
- 地图: `tkintermapview`（OpenStreetMap）
- 回收站: `send2trash`
- Windows 标题栏: `pywinstyles`

## 快速开始

需要 Python 3.11+ 和 [uv](https://github.com/astral-sh/uv)。

```powershell
# 安装依赖（uv 会自动管理 Python 版本）
uv sync

# 启动应用
uv run raw-picker-pro
```

## 打包

使用 PyInstaller 构建独立的 Windows 可执行文件：

```powershell
uv run pyinstaller --onefile --windowed --strip --icon icon.ico src/main.py
```

输出位于 `dist/RawPickerPro.exe`。

## 项目结构

```
src/
  config/         常量、RAW 格式列表、深色/浅色调色板
  core/           扫描器、选片/清理/重命名引擎、EXIF 读取、文件操作
  models/         PhotoItem、OrphanItem、AppConfig
  ui/             主窗口 + 标签页（选片/清理/重命名/地图）+ 灯箱 + 组件
  utils/          图像缓存、缩略图加载器、配置存储、校验器
  app.py          应用控制器 — 连接 UI 与引擎
  main.py         入口点
tests/            pytest 测试套件 + 无头冒烟测试
icon.ico          应用程序图标（CustomTkinter 风格）
```
