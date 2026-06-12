# RawPicker Pro 产品需求文档 (PRD)

**版本**: v2.0  
**日期**: 2026-06-07  
**状态**: 开发基线  

---

## 1. 文档目的

本文档定义 RawPicker Pro 桌面应用程序的产品需求、工作流、功能规格及验收标准，作为开发、测试及验收的唯一依据。

---

## 2. 术语表

| 术语 | 定义 |
|------|------|
| **Folder A** | 素材库（源文件夹），包含用户拍摄的 JPG 预览图及同名 RAW 文件 |
| **Folder B** | 挑选结果（目标文件夹），存放用户选中的 JPG 及其伴随 RAW |
| **伴随 RAW** | 与 JPG 同名（不含扩展名）、位于同一文件夹的 RAW 格式文件 |
| **孤件 RAW** | 某文件夹中存在 RAW 文件，但不存在同名 JPG 的文件 |
| **孤件 JPG** | 某文件夹中存在 JPG 文件，但不存在同名 RAW 的文件 |
| **完整对** | 同一 basename 下同时存在 RAW 和 JPG |
| **Pick 状态** | 用户对照片的主观标记：Accepted（选中）、Rejected（淘汰）、Pending（未决） |
| **basename** | 不含扩展名的文件名，如 `DSC_0001` |

---

## 3. 产品概述

RawPicker Pro 是一款面向摄影师的轻量级 RAW + JPG 挑选与清理工具。它解决的核心痛点是：在素材库（Folder A）中，用户通过预览 JPG 快速决定保留哪些照片，并一键将"JPG + 伴随 RAW"移动到目标文件夹（Folder B），同时提供独立的清理工具处理孤件文件。

### 3.1 目标用户
- 使用相机拍摄 RAW + JPG 双格式的摄影师
- 需要在海量素材中快速筛选保留照片的用户
- 需要定期清理无对应文件的孤件 RAW/JPG 的用户

### 3.2 设计哲学
- **极简**：只解决"挑选"和"清理"两个核心问题，不做后期编辑
- **键盘优先**：所有高频操作均支持快捷键，实现盲操
- **安全**：任何文件删除均有确认，默认使用回收文件夹而非直接删除

---

## 4. 工作流定义

### 4.1 工作流一：挑选（Picking Workflow）

```text
[开始]
  |
  ▼
[用户设置 Folder A 和 Folder B]
  |
  ▼
[系统扫描 Folder A]
  ├── 识别所有 JPG/JPEG 文件
  └── 对每个 JPG，查找是否存在同名伴随 RAW（遍历 RawFormats）
  |
  ▼
[展示 JPG 缩略图列表]
  ├── 标记：是否有伴随 RAW（图标提示）
  └── 支持大图预览、EXIF 读取、地图定位
  |
  ▼
[用户交互：浏览与标记]
  ├── 方向键 / 鼠标：浏览
  ├── 空格键：勾选/取消勾选（仅影响 JPG）
  ├── 1-5：星级评分
  ├── P：标记为 Accepted（绿色）
  ├── X：标记为 Rejected（红色）
  └── U：标记为 Pending（默认）
  |
  ▼
[用户点击"选片到 B"]
  ├── 遍历所有被勾选的 JPG
  │   ├── 移动 JPG 到 Folder B
  │   └── 如果存在伴随 RAW，一并移动到 Folder B
  │   └── 如果无伴随 RAW，仅移动 JPG，并记录警告
  |
  ▼
[生成操作报告]
  ├── 成功移动 JPG：N 个
  ├── 成功移动 RAW：M 个
  ├── 无伴随 RAW：K 个
  └── 失败：Z 个
  |
  ▼
[刷新 Folder A 视图，已移动项消失]
  |
  ▼
[结束]
```

**关键规则**：
- 系统**只展示 JPG**，RAW 不可见但跟随移动
- 只有被**勾选**的 JPG 才会被处理，未勾选的不动
- 移动后，Folder A 中不再保留已选文件的任何副本（JPG 和 RAW 都移走）

### 4.2 工作流二：清理（Cleaning Workflow）

```text
[开始]
  |
  ▼
[用户选择目标文件夹（任意路径）]
  |
  ▼
[系统扫描目标文件夹]
  ├── 按 basename 分组
  ├── 识别完整对（RAW + JPG）
  ├── 识别孤件 RAW（仅有 RAW）
  └── 识别孤件 JPG（仅有 JPG）
  |
  ▼
[进入清理视图]
  ├── 默认展示：孤件 RAW + 孤件 JPG
  └── 可选：展示完整对（用于用户二次确认）
  |
  ▼
[用户预览与勾选]
  ├── 空格键：勾选/取消
  └── 支持大图预览
  |
  ▼
[用户选择清理方式]
  ├── 模式 A：移到回收文件夹（_Orphaned/RAW 或 _Orphaned/JPG）
  └── 模式 B：永久删除（需二次确认）
  |
  ▼
[执行清理]
  |
  ▼
[生成报告]
  |
  ▼
[结束]
```

**关键规则**：
- 清理是**独立功能**，不依赖挑选工作流
- 清理目标可以是 Folder A、Folder B 或任何其他文件夹
- 回收文件夹命名规则：`_Orphaned_YYYYMMDD_HHMMSS`，位于目标文件夹同级目录或内部（默认内部）

### 4.3 工作流三：重命名（Renaming Workflow）

```text
[开始]
  |
  ▼
[用户选择文件夹]
  |
  ▼
[选择文件范围]
  ├── 全部文件
  └── 仅已勾选文件
  |
  ▼
[设置命名模板]
  ├── 变量：{basename}, {seq}, {seq:03d}, {rating}, {date}, {camera}
  └── 实时预览新文件名
  |
  ▼
[执行重命名]
  └── RAW 和 JPG 同步重命名（保持 basename 一致）
  |
  ▼
[结束]
```

---

## 5. 功能需求（Functional Requirements）

### 5.1 模块：文件夹设置（FR-01）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-01-01 | 支持浏览选择 Folder A 和 Folder B | P0 |
| FR-01-02 | 自动记忆最近使用的 5 组 A/B 路径 | P1 |
| FR-01-03 | 支持路径拖拽到输入框 | P2 |
| FR-01-04 | 路径有效性实时校验（文件夹不存在时红字提示） | P0 |

### 5.2 模块：扫描与索引（FR-02）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-02-01 | 扫描 Folder A 时，仅识别 JPG/JPEG 作为主文件 | P0 |
| FR-02-02 | 对每个 JPG，自动查找同名伴随 RAW（遍历 RawFormats 列表，大小写不敏感） | P0 |
| FR-02-03 | 扫描结果缓存，避免重复生成缩略图 | P1 |
| FR-02-04 | 支持进度条显示（当 A 中文件 >500 时） | P1 |

### 5.3 模块：JPG 浏览与预览（FR-03）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-03-01 | 缩略图网格展示，支持自适应列数 | P0 |
| FR-03-02 | 缩略图下方显示：basename、是否有 RAW 图标、评分、Pick 状态 | P0 |
| FR-03-03 | 右侧大图预览面板，等比缩放，最大 400px 高 | P0 |
| FR-03-04 | 右侧展示 EXIF：ISO、光圈、快门、焦距、相机、镜头、拍摄日期 | P0 |
| FR-03-05 | 右侧展示 GPS 坐标（如有） | P1 |
| FR-03-06 | 缩略图支持懒加载，仅视口内渲染 | P1 |

### 5.4 模块：选择与标记（FR-04）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-04-01 | 鼠标点击缩略图：选中并高亮 | P0 |
| FR-04-02 | 空格键：切换当前选中项的勾选状态 | P0 |
| FR-04-03 | Ctrl+A：全选当前筛选结果 | P1 |
| FR-04-04 | 1-5 数字键：设置 1-5 星评分 | P1 |
| FR-04-05 | P 键：设置 Pick 状态为 Accepted | P0 |
| FR-04-06 | X 键：设置 Pick 状态为 Rejected | P0 |
| FR-04-07 | U 键：设置 Pick 状态为 Pending | P0 |
| FR-04-08 | 勾选状态、评分、Pick 状态在内存中维护，不写入文件（除非用户开启 XMP 回写） | P0 |

### 5.5 模块：批量移动（FR-05）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-05-01 | 仅处理被勾选的 JPG | P0 |
| FR-05-02 | 对每个勾选的 JPG，移动其同名伴随 RAW（如存在）到同一目标 | P0 |
| FR-05-03 | 如果 JPG 无伴随 RAW，仅移动 JPG，并在报告中标记警告 | P0 |
| FR-05-04 | 移动前检查 Folder B 是否已存在同名文件，存在则弹窗提示（覆盖/跳过/重命名） | P0 |
| FR-05-05 | 移动后刷新 Folder A 视图，已移动项从列表移除 | P0 |
| FR-05-06 | 生成操作报告弹窗 | P0 |

### 5.6 模块：清理工具（FR-06）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-06-01 | 支持选择任意文件夹进行扫描 | P0 |
| FR-06-02 | 识别孤件 RAW（有 RAW 无 JPG） | P0 |
| FR-06-03 | 识别孤件 JPG（有 JPG 无 RAW） | P0 |
| FR-06-04 | 支持筛选展示：仅孤件 RAW / 仅孤件 JPG / 全部孤件 | P0 |
| FR-06-05 | 孤件列表支持勾选、全选、预览 | P0 |
| FR-06-06 | 清理模式：移到回收文件夹（默认）/ 永久删除 | P0 |
| FR-06-07 | 回收文件夹路径：`<目标文件夹>/_Orphaned_YYYYMMDD_HHMMSS/` | P0 |
| FR-06-08 | 清理前二次确认弹窗，显示待清理文件数量及总大小 | P0 |

### 5.7 模块：地图视图（FR-07）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-07-01 | 基于 OpenStreetMap 展示照片 GPS 位置 | P1 |
| FR-07-02 | 不同颜色标记：Accepted(绿)、Rejected(红)、Pending(灰)、高评分(橙) | P1 |
| FR-07-03 | 点击地图标记，自动跳转到对应缩略图并选中 | P1 |
| FR-07-04 | 支持"适配边界"按钮，自动缩放显示所有标记 | P1 |
| FR-07-05 | 支持 GPS 筛选：有 GPS / 无 GPS | P2 |

### 5.8 模块：重命名工具（FR-08）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-08-01 | 支持模板变量：{basename}, {seq}, {seq:03d}, {rating}, {date}, {camera} | P2 |
| FR-08-02 | 实时预览前 5 个新文件名 | P2 |
| FR-08-03 | 重命名时 RAW 和 JPG 同步改名，保持 basename 一致 | P2 |
| FR-08-04 | 冲突检测（目标名已存在时提示） | P2 |

### 5.9 模块：键盘快捷键（FR-09）

| 快捷键 | 功能 | 场景 |
|--------|------|------|
| ← → ↑ ↓ | 缩略图导航 | 挑选模式 |
| Space | 勾选/取消勾选 | 挑选模式 |
| 1-5 | 设置评分 | 挑选模式 |
| P | Accepted | 挑选模式 |
| X | Rejected | 挑选模式 |
| U | Pending | 挑选模式 |
| Ctrl+M | 执行"选片到 B" | 挑选模式 |
| Delete | 打开清理工具（或删除当前选中） | 全局 |
| Ctrl+R | 打开重命名工具 | 全局 |
| Ctrl+1/2/3 | Tab 切换：挑选 / 清理 / 重命名 | 全局 |

---

## 6. 数据模型

### 6.1 PhotoItem（挑选模式）

```python
@dataclass
class PhotoItem:
    basename: str              # 不含扩展名，如 "DSC_0001"
    folder: str                # 所在文件夹绝对路径
    jpg_path: Optional[str]    # JPG 文件绝对路径（主文件）
    jpg_ext: str               # "jpg" 或 "jpeg"
    raw_path: Optional[str]    # 伴随 RAW 绝对路径（可能为 None）
    raw_ext: Optional[str]     # RAW 扩展名，如 "nef"（可能为 None）

    # 交互状态
    selected: bool = False     # 是否被勾选
    rating: int = 0            # 1-5 星，0=未评分
    pick_status: str = "pending"  # "accepted" | "rejected" | "pending"

    # 元数据
    exif: Dict[str, Any] = field(default_factory=dict)
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None

    @property
    def has_raw(self) -> bool:
        return self.raw_path is not None

    @property
    def file_size_mb(self) -> float:
        # 计算 JPG + RAW 总大小
        pass
```

### 6.2 OrphanItem（清理模式）

```python
@dataclass
class OrphanItem:
    basename: str
    folder: str
    file_path: str           # 孤件文件的绝对路径
    file_type: str           # "raw" | "jpg"
    ext: str                 # 实际扩展名
    size_mb: float
    selected: bool = False
```

### 6.3 配置模型

```python
@dataclass
class AppConfig:
    folder_a: str = ""
    folder_b: str = ""
    raw_formats: List[str] = field(default_factory=lambda: [
        "nef", "cr2", "cr3", "arw", "raf", "orf", "dng", ...
    ])
    thumbnail_size: int = 160
    theme: str = "dark"
    delete_mode: str = "trash"   # "trash" | "permanent"
    recent_paths: List[Tuple[str, str]] = field(default_factory=list)
```

---

## 7. UI/UX 设计

### 7.1 布局架构

采用 **三栏式布局**，顶部 Tab 切换工作模式：

```
┌─────────────────────────────────────────────────────────────┐
│  [Tab: 挑选] [Tab: 清理] [Tab: 重命名]          [设置按钮]  │
├──────────┬──────────────────────────────┬─────────────────────┤
│          │                              │                     │
│  左侧边栏 │      中间主内容区              │    右侧详情面板      │
│          │                              │                     │
│  ┌─────┐ │  ┌────┐ ┌────┐ ┌────┐       │  ┌─────────────┐   │
│  │A路径│ │  │ ⭐⭐│ │ ⭐  │ │ ✅ │       │  │             │   │
│  │B路径│ │  │ JPG│ │ JPG│ │ JPG│       │  │   大图预览   │   │
│  │扫描 │ │  │RAW✓│ │RAW✗│ │RAW✓│       │  │             │   │
│  └─────┘ │  └────┘ └────┘ └────┘       │  └─────────────┘   │
│          │                              │  ┌─────────────┐   │
│  ┌─────┐ │  [缩略图网格 / 地图 / 清理列表] │  │  EXIF 表格   │   │
│  │筛选 │ │                              │  │  GPS 信息    │   │
│  │统计 │ │                              │  │  操作按钮    │   │
│  └─────┘ │                              │  └─────────────┘   │
│          │                              │                     │
└──────────┴──────────────────────────────┴─────────────────────┘
```

### 7.2 视觉规范（CustomTkinter）

- **主题**：Dark Mode 为主，支持 Light Mode 切换
- **主色调**：`#3B8ED0`（CTk 默认蓝）
- **Accepted**：`#4CAF50`（绿边框 + 绿角标）
- **Rejected**：`#f44336`（红边框 + 红角标）
- **Pending**：无边框，默认背景
- **高评分**：缩略图底部显示金色星星 `★★★★★`
- **无伴随 RAW**：缩略图右上角显示灰色警告图标 `⚠`

### 7.3 状态流转

```
JPG 项状态：
  Pending（默认） → P键 → Accepted（绿）
                  → X键 → Rejected（红）
                  → U键 → Pending（恢复）

  勾选状态：
    空格键切换：☐ → ☑ → ☐
```

---

## 8. 技术架构

### 8.1 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| GUI 框架 | `customtkinter` | 现代化暗色主题，支持高 DPI |
| 图像处理 | `Pillow` | 缩略图生成、大图预览、EXIF 读取 |
| 地图组件 | `tkintermapview` | OpenStreetMap 嵌入，离线瓦片缓存 |
| GPS 解析 | `Pillow.ExifTags` | 内建 GPSInfo 提取，无需额外依赖 |
| 文件操作 | `shutil` + `os` | 移动、删除、重命名 |
| 安全删除 | `send2trash`（可选） | 跨平台移到系统回收站 |
| 配置存储 | `json` | 用户偏好持久化 |
| 打包工具 | `PyInstaller` | 输出独立 .exe |

### 8.2 项目结构（src 布局）

```
raw-picker-pro/
├── requirements.txt
├── pyproject.toml
└── src/
    ├── __init__.py
    ├── main.py
    ├── app.py                    # 主应用控制器，管理 Tab 切换
    ├── config/
    │   ├── __init__.py
    │   └── settings.py           # 配置常量、RawFormats、主题色
    ├── core/
    │   ├── __init__.py
    │   ├── scanner.py            # 扫描器：JPG 锚点扫描 + 清理扫描
    │   ├── picker_engine.py      # 挑选引擎：移动 JPG + 伴随 RAW
    │   ├── cleaner_engine.py     # 清理引擎：孤件识别 + 安全删除
    │   ├── renamer_engine.py     # 重命名引擎：模板解析 + 批量改名
    │   ├── metadata_reader.py    # EXIF/GPS 读取
    │   └── file_ops.py           # 文件操作封装（冲突检测、重试）
    ├── models/
    │   ├── __init__.py
    │   ├── photo_item.py         # 挑选模式数据模型
    │   └── orphan_item.py        # 清理模式数据模型
    ├── ui/
    │   ├── __init__.py
    │   ├── main_window.py        # 主窗口布局（三栏 + Tab）
    │   ├── pick_tab.py           # 挑选模式界面（缩略图 + 预览）
    │   ├── clean_tab.py          # 清理模式界面（孤件列表）
    │   ├── rename_tab.py         # 重命名界面
    │   ├── thumbnail_grid.py     # 缩略图网格组件
    │   ├── preview_panel.py      # 右侧预览 + EXIF 面板
    │   ├── sidebar.py            # 左侧边栏（路径 + 筛选）
    │   ├── map_panel.py          # 地图视图组件
    │   ├── rating_widget.py      # 星级评分组件
    │   ├── pick_badge.py         # Accepted/Rejected 角标
    │   └── dialogs/
    │       ├── confirm_dialog.py
    │       ├── conflict_dialog.py
    │       └── report_dialog.py
    └── utils/
        ├── __init__.py
        ├── image_cache.py        # 缩略图 LRU 缓存
        ├── keyboard_handler.py   # 全局快捷键路由
        └── validators.py         # 路径校验、模板校验
```

---

## 9. 接口定义（模块间）

### 9.1 Scanner -> UI

```python
def scan_for_picking(folder_a: str) -> List[PhotoItem]:
    """
    扫描文件夹，以 JPG 为锚点，返回 PhotoItem 列表。
    每个 PhotoItem 包含 jpg_path 和可选的 raw_path。
    """

def scan_for_cleaning(target_folder: str) -> Tuple[List[OrphanItem], List[PhotoItem]]:
    """
    扫描文件夹，返回：
    - orphans: 孤件 RAW + 孤件 JPG 列表
    - complete: 完整对列表（可选展示）
    """
```

### 9.2 PickerEngine

```python
def pick_to_b(items: List[PhotoItem], folder_b: str) -> PickReport:
    """
    输入：被勾选的 PhotoItem 列表
    输出：操作报告（成功/失败/警告明细）
    行为：移动 JPG 和伴随 RAW 到 folder_b
    """

@dataclass
class PickReport:
    moved_jpg: int
    moved_raw: int
    missing_raw: int      # 有 JPG 但无 RAW 的警告计数
    failed: List[str]     # 失败文件名列表
```

### 9.3 CleanerEngine

```python
def clean_orphans(orphans: List[OrphanItem], mode: str) -> CleanReport:
    """
    mode: "trash" | "permanent"
    返回操作报告
    """
```

---

## 10. 错误处理与边界情况

| 场景 | 处理策略 |
|------|----------|
| A 文件夹中某 JPG 有多个同名 RAW（如 `DSC.nef` + `DSC.dng`） | 移动第一个找到的 RAW，其余在报告中提示"多个伴随 RAW" |
| B 文件夹已存在同名文件 | 弹窗冲突处理：覆盖 / 跳过 / 自动重命名（加 `_1`） |
| 移动过程中文件被占用 | 重试 3 次，失败后计入失败列表 |
| 用户勾选后、执行前删除了源文件 | 执行时校验存在性，不存在则跳过并报告 |
| 清理时回收文件夹创建失败 | 降级为弹窗提示用户手动处理 |
| 图片 EXIF 损坏 | 静默忽略，EXIF 面板显示"无法读取" |

---

## 11. 验收标准（Acceptance Criteria）

### 11.1 挑选功能验收

- [ ] 扫描 1000 张 JPG 的文件夹，缩略图加载时间 < 3 秒（含伴随 RAW 检测）
- [ ] 用户勾选 50 张 JPG，点击"选片到 B"，50 张 JPG 及对应 RAW 正确移动到 B
- [ ] 某 JPG 无伴随 RAW，移动时仅移动 JPG，报告弹窗提示"1 个文件无伴随 RAW"
- [ ] 移动后 Folder A 中不再存在已移动的 JPG 和 RAW
- [ ] 键盘快捷键：方向键、空格、P/X/U、1-5 全部可用

### 11.2 清理功能验收

- [ ] 扫描包含 100 个孤件 RAW 和 50 个孤件 JPG 的文件夹，正确识别全部 150 个孤件
- [ ] 用户全选孤件，选择"移到回收文件夹"，文件被移动到 `_Orphaned_xxx` 子文件夹
- [ ] 选择"永久删除"时，弹出二次确认窗口，确认后文件被删除
- [ ] 清理后刷新视图，已清理项消失

### 11.3 地图功能验收

- [ ] 有 GPS 的照片在地图上显示标记，颜色与 Pick 状态一致
- [ ] 点击地图标记，界面自动切换到"缩略图"Tab 并选中对应照片
- [ ] 无 GPS 的照片不显示标记，但可通过"无 GPS"筛选器查看

---

## 12. 附录

### 12.1 RawFormats 完整列表

```
nef, cr2, cr3, arw, raf, orf, dng, rw2, pef, x3f, srw, nrw, erf,
kdc, k25, mef, dcr, mos, iiq, rwl, gpr, 3fr, crw, sr2, srf, bay,
cs1, fff, mdc, mrw, qtk, raw, rwz, sti, tif, tiff
```

### 12.2 版本规划

| 版本 | 功能 | 时间 |
|------|------|------|
| v1.0 | 挑选 + 清理 + 基础预览 | 2 周 |
| v1.1 | 地图 + GPS + 筛选 | 1 周 |
| v1.2 | 重命名 + 评分持久化 | 1 周 |
| v1.3 | 打包 + 安装程序 + 高 DPI 适配 | 1 周 |

---

**文档结束**
