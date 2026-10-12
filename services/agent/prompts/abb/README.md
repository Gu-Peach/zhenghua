# ABB 三阶段规则资源（1.1.2）

按用户要求精简为每阶段一个案例，使用两张原始整页图：`1.png`（LV11/Sheet 205）和 `2.png`（LV12/Sheet 241）。原始 `1.png`～`4.png` 均保留，原图序号不是 PDF 物理页号。

| 阶段 | 图片 | 示例内容 |
| --- | --- | --- |
| Stage 1 | 原页 205 一张 | 识别 LV11/205、+EH.Q1.1；不把 Cont 206 当当前页 |
| Stage 2 | 原页 205 一张 | 示范 Q4:2/4/6/8 出线到 Sheet 241；未知终点留空 |
| Stage 3 | 原页 205 + 目标页 241 | 一条 Q4 L1 任务，补全 +EH.Q21-Q1:2；起点冻结 |

格式与 ZH 一致：`examples_page_classification/manifest.json` 包含图片和身份 expected；`examples_wiring/annotated/manifest.json` 分 `stage2_cases` 与 `stage3_cases`，包含图片、expected 和 task。Stage 2 图片为完整原页，expected 明确只示范 Q4 出线，不是整页全部连接；真实扫描仍处理所有符合规则的连接。Stage 3 两张图用于解释来源与落点，不允许重写起点或扩展任务范围。

包内只保留所需图片和案例文件，移除旧额外案例及裁剪副本。两阶段复用同一原页对象。三阶段规则独立于 ZH。

红色教学标注不是业务字段；不确定电流/端点留空。任务物理序号 1/2 是合成夹具位置，不代表原 PDF；PageScanData.pdf_page_number 为 null。来源和范围见 `examples_wiring/annotated/provenance.json`。

资源包已接入独立 `abb_native` 三阶段适配器、Sheet 引用解析与确定性策略，可供新任务直接选择。当前未运行 ABB 真实模型字段级验收，因此“可执行”不等于识别准确率已验收；无法确认的字段仍应置空并进入复核。旧版本保留为不可变历史，新任务默认使用最新可用版本。

复现图片：`.\.venv\Scripts\python.exe services/agent/scripts/prepare_abb_example_images.py`。
