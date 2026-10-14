# 大车卷盘图纸：Stage 1 页面分类（0.1.0）

输入是一张实际 PDF 页面。只识别页面身份，不提取连接。此模板的页标是右下角 SH.NO.，不是 Plant Function/Page Number，也不是 CONT.ON.SH。

1. 原理图原始页标如 0A、1A、1B、1H、2A、3F、4B、5A。字母属于完整页标，不能丢掉。CONT.ON.SH 是图册接续页，不能代替当前页，也不能作为所有线路的引用。
2. 为兼容当前正整数协议，原理图 `nL` 映射为 plant_function=`GCR.n`，drawing_page_number=字母序号（A=1...Z=26）。这是可逆的接口索引，不是图中印刷字段。例：1E→GCR.1/5，3A→GCR.3/1。reason 必须写原始 SH.NO.。
3. 端子图表使用另一个空间 GCR.TD：整数 SH.NO. 直接取整数，3.a→301（整数部分×100+字母序号）。reason 保存 TD:3.a。不能与原理图 3A 合并。
4. 封面 0A、端子图表（F13_001、标题端子图表/端子排报告）为 non_wiring=true；它们不是空白页，blank=false。保留身份供核对，不重复提取线表。
5. ZPMC、1002001693、GANTRY/SPREADER CABLE REEL 和 +GCR 是本样本可见证据。封面与部分端子报告混用 GANTRY/SPREADER 文案，不据此猜另一个项目或工作区。
6. PDF 物理页码只来自调用上下文，不用其推断 SH.NO.。身份看不清时对应字段 null、needs_review=true，不拿全册物理序号补造。

只输出 PageClassificationData JSON：plant_function、drawing_page_number、blank、non_wiring、confidence、needs_review、reason。不输出连接和未知额外字段。
