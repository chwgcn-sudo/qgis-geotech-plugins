# CLAUDE.md

本文件为 Claude Code 在本仓库中工作时提供指引。

## 项目概述

**Aufschluss Suite**（v0.4.0，作者 Chao Wang）是一个 QGIS Python 插件，面向岩土勘察（Geotechnik）项目，把三个原本独立的插件合并到一个窗口中：

| 按钮 | 包 | 原插件 | 作用 |
|---|---|---|---|
| Aufschluss | `modules/aufschluss` | Vorgabe der Aufschlüsse（v0.23.1） | 在多边形内生成勘察点网格（DP/RKS），从客户文件导入边界，导出 KML/KMZ/CSV/GPKG |
| Mappe | `modules/blaue_mappe` | Blaue Mappe Deckblatt（v1.7.2） | 填写 A4 横版“蓝色文件夹”封面，输出带可编辑表单域的 PDF（含概览图页） |
| Lageplan | `modules/lageplan` | Lageplan Export（v0.7.2） | 生成 A3 平面图 / A4 区位图：CorelDRAW 用 SVG + 底图 PNG + PDF（可带地理参考） |

- 兼容 QGIS 3.28 – 4.99（Qt5 和 Qt6，`supportsQt6=True`）。
- UI 文字、注释、用户提示均为**德语**；`aufschluss` 模块中部分新代码的注释/docstring 用英语。新增内容沿用所在文件的语言。
- 项目类型：`PVA`（光伏）、`BESS`（储能）、`WWM`。点类型：`RKS`、`DP`、`DPM`、`DPH`、`CBR`、`EW`（Erdwiderstand）、`TRT`（导热）。
- AZ（档案号）格式：`AZ` + 年(2) + 月(2) + 流水号(3)，如 `AZ 26 01 001` / `AZ2601001`。

## 运行与测试

没有构建系统、依赖清单、测试套件或 lint 配置。

- **安装/运行**：把 `aufschluss_suite/` 目录放进 QGIS 插件目录（Windows：`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`），在 QGIS 中启用；改代码后用 Plugin Reloader 或重启 QGIS。
- **入口**：`__init__.py:classFactory` → `plugin.py:SuitePlugin` → `main_window.py:SuiteWindow`。
- **可在 QGIS 外单独测试的纯 Python 模块**（不 import qgis）：
  `core/naming.py`、`modules/aufschluss/cvt.py`、`rks.py`、`import_core.py`（只需 numpy）、
  `modules/blaue_mappe/logic.py`（依赖 `core.naming`）、`pdfform.py`、`kml_reader.py`、
  `modules/lageplan/scene.py`、`svgwriter.py`、`svgio.py`、`placement.py`、`textmetrics.py`、`georef.py`、`presets.py`。
  `lageplan/pdfout.py` 在 QGIS 外会回退到 `PyQt5`。保持这些模块不依赖 QGIS。
- 版本号要同步改两处：`__init__.py` 的 `VERSION` 和 `metadata.txt` 的 `version`。

## 架构

```
plugin.py          QGIS 插件外壳：工具栏/菜单动作，懒加载主窗口
main_window.py     主窗口：左侧图层树 | 中间三个模块按钮 | 右侧模块栏（QSplitter）
core/              三个模块共用的内核
modules/<name>/    各模块（dialog.py 为主 UI，其余为逻辑），每个仍带自己的 metadata.txt
```

### 主窗口与模块嵌入（main_window.py）
- 模块在**首次点击时才 import**（`_create`），某个模块加载失败不影响其它模块（异常 → `QMessageBox`）。
- 同一时间只开一个模块；切换时 `_dispose` 关闭前一个（已生成的图层/文件保留）。
- 每个模块的主类是 `QDialog`（`MainDialog` / `DeckblattDialog` / `LageplanDialog`），经 `ui.embed()` 变成普通 widget、`ui.tune()` 压缩到窄栏（~440 px）、`ui.wrap_scroll()` 包进滚动区。
- 宿主设置 `dlg.suite = self`。模块必须容忍 `self.suite is None`（单独运行时），通过它调用 `suite.panel.select_nodes(...)`、`suite.hide_for_map()` / `show_after_map()`（在地图上拾取/绘制时隐藏窗口）。
- 可选钩子：`dlg.on_expand()`（模块栏展开时调用）。窗口固定尺寸 1200×794（`screens.fit_to_screen`），有第二屏时放到第二屏。

### 模块之间不直接通信
三个模块**只通过 QGIS 项目本身**（面图层、点图层）交换数据，不互相 import。共享逻辑全部放在 `core/`：

- `core/selection.py`：**唯一**的图层选择来源。左侧树通过 `set_provider()` 注册；选中组会展开为其图层；什么都没选时取所有可见图层。按几何类型分为 `areas()` / `points()` / `lines()` / `rasters()`。带 `FRAME_KEY` 自定义属性的图层（Lageplan 的图框）永不作为面。模块用 `selection.on_change(cb)` 订阅（关闭时记得 `off_change`）。
- `core/project_data.py`：从项目读取 AZ、项目名/类型、面积（自动选 UTM 带计算，先 unaryUnion 合并重叠）、各类点数。Aufschluss 生成的面图层命名为 `A1_boundary`、`A2_boundary`…（`_BOUNDARY_RE`）。
- `core/naming.py`：AZ 解析、图层名拆分、点类型识别与计数、DP→DPM/DPH 重命名规则（纯 Python）。
- `core/rename.py`：在原点图层内就地重命名，原始值保存在 `Orig_ID` / `Orig_Type` 字段，新名称总是从原始值重建。
- `core/output.py`：统一输出目录 `Desktop/PV-Geopackage/<AZ>_<项目名>/`，文件名 `file_stem()` = `AZ2611001_项目名`（无空格）；生成的组命名 `generated_name(原名, 1|2)` → `原名_N1`（Aufschluss）/ `原名_N2`（Lageplan）。`tree_name()` 仅为兼容旧项目保留。
- `core/basemaps.py`：直接加载 XYZ 底图（OSM Standard、OpenTopoMap、Google Hybrid、Bing Satellite），替代 QuickMapServices；项目没有栅格图层时默认加载 OpenTopoMap + Google Hybrid。
- `core/pageview.py`：Lageplan 和 Mappe 共用的多页预览（页面纵向排列，默认整页适配窗口；滚轮 = 缩放页面视图，Ctrl+滚轮 → `wheel` 信号（地图缩放），左键拖动 → `dragged`，Shift+拖动 → `shift_dragged`（移动剖面），中键拖动 = 滚动，双击 = 最大化）。
- **选择规则**：三个模块使用的图层 = 图层树中**勾选（打钩）**的图层（`ProjectPanel.selected_layers`）；勾选时 QGIS 地图跳到该图层，单击不跳。
- 点名称字段：Aufschluss 生成的点图层用 `ID` 字段，读取点名时用 `project_data.name_field()`（ID → name → …），不要只找 `name`。
- `core/styles.py`：点样式（DP 红圆、RKS 蓝方块，按 `Type` 字段分类，`ID` 标注）；`mark_generated()` 打上 `aufschluss_suite/generated` 属性，图层树里以深绿色显示。
- `core/geocode.py`：OSM Nominatim 反向地理编码（≤1 次/秒，带 User-Agent）。
- `core/ui.py`：配色（Logo 绿 `#439f35`）、全局 QSS、`step_box()` / `section_box()` 浅绿框、`tune`/`embed`/`wrap_scroll`。
- `core/layertree.py`：左侧 `QgsLayerTreeView` 面板 + “Datei hinzufügen…”。
- `core/screens.py`：屏幕放置、尺寸适配、`HideWhileMapping`。

### 模块要点
- **aufschluss**：`dialog.py` 布点（三角/方格网格，CVT/Lloyd 均匀化 `cvt.py`，RKS 子集选取与分配 `rks.py`；PVA 按网格或总点数按面积分配，BESS 每面 3 RKS + 3 DP 置于外接矩形 1/4 处）；`import_dialog.py` + `import_core.py` 从 PDF/图片按图例颜色抠出边界并用控制点配准（可选 PyMuPDF `fitz`、GDAL PDF 驱动、外部 `tesseract` OCR）；`import_vector.py` 读 KML/KMZ/DXF；`export.py` 直接从图层读数据导出（包含用户在 QGIS 中的手工修改）。
- **blaue_mappe**：`logic.py` 档位/取整/字段值；`pdfform.py` 纯 Python 手写 AcroForm PDF（`_widths.py` 为 Helvetica 字宽）；`overview.py` 渲染第 2 页起的地图页（树中选中的 OSM 底图 + QPainter 叠加，JPEG；页面列表 `(k, View)` 来自预览，可用“+ Seite”追加）；`pdfmerge.py` 用 pypdf 追加外部 PDF——优先用 QGIS 自带 pypdf，否则用 `_vendor/pypdf`（第三方代码，不要修改）；驾车距离走 OSRM 公共服务（`router.project-osrm.org`）；设置存于 `QgsSettings` 前缀 `blaue_mappe_deckblatt/`。
- **lageplan**：`scene.py` 构建与 QGIS 无关的场景（单位 mm、按层排列的 dict 元素），同一场景同时输出 SVG（`svgwriter.py`，CorelDRAW 风格分组/ID）和 PDF（`pdfout.py`），保证两者一致；`builder.py` 是 QGIS 部分（范围、底图 PNG、几何→场景、导出、`georef.py` 写入 PDF 地理参考）；`presets.py` 为各项目类型默认值和图签尺寸；`placement.py` 确定性标注避让；`i18n.py` + `translations.json` 提供德/英图面文字（json 覆盖默认值，用户可编辑）；`resources/` 为符号、Logo、指北针 SVG。

## 编码约定

- **Qt5/Qt6 双兼容**是硬性要求：用完全限定的枚举（`Qt.AlignmentFlag.AlignCenter`、`QPainter.RenderHint...`），`QAction` 先从 `QtGui` 再回退 `QtWidgets`，字段类型用 `QMetaType.Type.QString` 回退 `QVariant.String`，几何类型用 `Qgis.GeometryType` 回退 `QgsWkbTypes`（参见 `aufschluss/dialog.py` 的 `_enum` / `_polygon_filter` 等辅助函数）。只从 `qgis.PyQt` 导入。
- 模块内用相对导入共享内核：`from ...core import naming, output, selection, styles, ui`。
- UI 健壮性优先：非关键操作包 `try/except Exception:  # noqa: BLE001` 并静默处理；面向用户的错误用德语 `RuntimeError` 文本或 `QMessageBox`。
- 不要“编造”数据：例如 AZ 没匹配到就返回空串（`naming.az_parts` 的注释“Nichts erfinden”）。
- 文件头 `# -*- coding: utf-8 -*-`，多数文件以模块 docstring 说明用途。
- 生成的图层/组要调用 `styles.mark_generated(obj, level)`（1 = Aufschluss 黄色，2 = Lageplan 浅黄色），组名用 `output.generated_name()`。
- 字号四级（`core/ui.py`）：模块标题 16 px 粗体、步骤标题 14 px 粗体、正文 12 px、提示 11 px 斜体。信息文字用 `ui.info()`（12 px 半粗 #2e7d32，行距 130 %），提示/说明用 `ui.hint()`。
- 所有输入框、下拉框、按钮等高（= Aufschluss“Projektart”下拉框高度），由 `ui.HeightFilter` 在 Polish 时统一设置；模块自己的窗口（预览）通过 `own_windows()` 交给主窗口注册。
- 是/否询问用 `ui.ask()`（德语按钮 Ja/Nein），不要用 `QMessageBox.question`。`ui.embed()` 的透明背景只作用于模块对话框本身（按 objectName），否则子 QMessageBox 会变黑。
- 预览窗口 1200×794，用 `screens.place_preview()` 放在不遮挡 Suite 窗口的位置。
- Lageplan 地图缩放只用 ISO 5455 档位（`presets.ISO_SCALES`，总览图用 `OV_SCALES`）；图签里的 Maßstab 目前统一填 “-”。
- 表单标签（标签在字段上方）不换行，所以标签要短：用复合词（Zeichnungssprache、Projektpunktlage …）。
- 绿色动作按钮（样式里含 #439f35 / #589632 或 objectName `greenBtn`）高度是统一高度的 1.5 倍。
- 主窗口和预览窗口双击背景 = 最大化/还原（`ui.MaximizeOnDoubleClick`）。
