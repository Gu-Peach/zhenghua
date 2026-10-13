# 振华大车卷盘 SH.NO. 网格模板

本地实验版本 `zh_gantry_reel@0.1.0`，来源为 1002001693 大车卷盘 PDF 和放线 XLSX。未上传、未发布、未调用真实模型。XLSX 用作对照，不是图中不可见字段的生成依据。

## 资源入口

- `page_classification.md`：Stage 1；读取原始 SH.NO.，区分原理图/封面/TD，规范索引与物理页分开。
- `page_scan_index.md`：Stage 2 初扫；识别实际放线、方向和连接，不使用旧 XA/XD 白名单。
- `page_connection_completion.md`：Stage 2 内部双图补全；冻结来源，不把电位/引用当针脚。
- `examples_page_classification/manifest.json`：两组案例，1A 正例和 TD 3.a 负例。
- `examples_wiring/manifest.json`：初扫两组（1E、TD 3.a），内部补全两组（1E→1G 明确接口、1B→2A 未标针脚）。`stage3_cases` 是当前加载器的历史资源键，不是独立 Stage 3。
- `sheet-index.json`：25 页原标、规范索引、物理页与非接线标志。
- `title-block-evidence.json`：来自 PDF 的精简图框文本，用于离线页标回归，不含作者行。
- `field-rules.json`：字段优先级、禁止推测项、业务映射禁用状态。
- `baseline-review.json`：XLSX 单元格级代表性差异；不是完整准确率审计。
- `schema.json`、`provenance.json`：当前结构化协议、源文件/图片/资源 checksum。

## 页标与连接依据

此图册使用 SH.NO. 如 1E，续接坐标如 1G45H（页1G/列45/行H），而不是原 zh 图册的 Plant Function + Page Number。规范索引将 1E 表示为 GCR.1/page 5，3A 为 GCR.3/page 1；这是可逆接口键，原始页标留在 reason/source_drawing_pages/drawing_page。TD 3.a 使用 GCR.TD/page 301，避免与 TD 3 和原理图3A冲突。

只有绑定在当前线路续接箭头旁的坐标才生成引用。原理号可能具有相同字形，全文匹配会产生假任务。正常目标回指用于匹配；图册外目标、模糊端点留空并复核。

图中 X3 与表中电缆类别 X4 不等同；实际 X0、X21、S11 等不得被标准表别名覆盖。型号/规格/长度/颜色/芯号/备用芯没有明确图中证据时为空。一个可见 PE 段不扩展成多个芯。

## 验证与待确认

运行（Fake Gateway、禁止 HTTP）：

```powershell
python -m pytest services/agent/tests/unit/test_zh_gantry_reel_profile.py -q
```

该命令核对 25 个实际图框、每类两个样例、路径/Schema/hash、引用与原样字段、六案例的 Fake 适配器逐字段结果。它不证明模型能从图像正确识别。

新 expected 已根据图像和明确约定目视核对，状态为 `source_checked_draft_pending_engineer_confirmation`，仍待工程人员确认；真实模型固定回归未运行。Profile 是 experimental，选择时需显式允许；既有 zh/ABB 资源未修改。

当前通用导出/页面展示仍主要消费规范数字索引；原始 SH.NO. 已保留在结果字段，但完整展示/导出原页标需后续输出适配。本轮没有修改业务接口、数据或生成整本提取结果。
