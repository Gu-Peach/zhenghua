# 大车卷盘图纸：Stage 2 内部双图补全（0.1.0）

只处理 task_context 中冻结的连接。通常第一张图是来源页、第二张是唯一目标页；旧任务缺少来源图时只使用已提供证据。不得改起点、原理号、来源页或方向，不扫描其他连接，不调用外部图册。

1. 先读原始 SH.NO.。引用 1G45H 表示 1G 页、45 列、H 行，不是端子 45H。接口规范索引 GCR.1/7 只是兼容字段，目标原页仍为 1G。
2. 用来源地址、目标回指、信号/原理号、设备接口和实际连续路径共同确认。正常回指来源页是匹配证据；没有实际端点而继续绕回同位置才是无法补全。
3. DRIVE-CLiQ 的 X201/X500 是明确接口，可据两页匹配确认。+24VDC/-0VDC 等电位名只是接线功能，若没有针脚编号，terminal 必须 null，不能照 XLSX 猜为 +、-、1、2。
4. 已确认的目标位置/name 保留，device、terminal 或板号看不到则相应字段 null。缺失/模糊/图册外的目标填空、needs_review=true、status=needs_review、warnings/source_note 写原因；不阻塞后续连接。
5. 同时保留原始页标和来源/目标两页证据。端子报告可用于人工核对，但不是此任务的替代业务终点，不把报告中的供方别名自动覆盖原理图。
6. 不把 MVCR-*、+01F11.* 外部柜端子、XLSX 线号/颜色/备用芯当图中直接证据。电流按初扫原规则，已有值不改，没有依据不补。

只输出 CrossPageCompletionData JSON：task_id、end、intermediate_points、current/current_basis/current_source_text、status、needs_review、confidence、source_note、warnings。不能输出 start 或新增连接。
