# ADR-0015：ZH 大车卷盘网格页标 Profile

状态：Accepted for local experimental resources，2026-10-13。仅本地资源与适配，不发布、不修改既有 ZH/ABB、不写数据库。

## 证据与边界

1002001693 图册有 25 个 PDF 物理页：封面 0A，18 个原理图页（1A～1H、2A、3A～3F、4A～4B、5A），6 个端子报告（TD 1、2、3、4、5、3.a）。原理图采用 SH.NO.、CONT.ON.SH 和数字列/字母行网格，不是原 ZH 的 Plant Function/Page Number。表格中的业务元件、外部柜端子、线号、型号、颜色和备用芯不能作为图中已读出的事实。

## 决策

2026-10-14用户确认本地资源目录采用`prompts/xmz`，Profile key/adapter继续使用`zh_gantry_reel`/`zh_gantry_reel_native`。0.1.1对齐ZH放线标记优先和最近端子边界，保留独立SH.NO.身份/引用规则；模型端子排分类留空，由程序从实际X排号确定，不复用XA/XD业务映射。移除已删诊断资源的运行时引用，样例expected仅以提供图片为依据，未知针脚为空，不从人工XLSX补写。保持本地experimental，不跑测试或模型，不写库或发布。

建立 `zh_gantry_reel@0.1.0` experimental Profile，独立三个 Prompt 及分类/初扫/内部补全各两案例。保留 Stage 1 + Stage 2 页闭环，不恢复独立 Stage 3。单独的 Profile policy/adapter 处理此模板；公共 Graph 不增加厂商条件。

当前协议的页号字段是正整数。使用可逆映射：原始 `1E` → function `GCR.1`、page 5（A=1...Z=26）；`3A` → `GCR.3`/1；封面 `0A` → `GCR.0`/1；TD 的整数页用 `GCR.TD`/整数，TD `3.a` 用 `GCR.TD`/301（整数部分×100+字母序号）。该 function 是适配器命名空间，不能声称图中有 Plant Function。raw SH.NO. 留在 classification.reason、source_drawing_pages、drawing_page 和 sheet-index 资源。

引用 `1B30B` → sheet 1B、column 30、row B；只有明确位于续接箭头旁的坐标才是引用，导线旁相同格式的文字仍可能是原理号。不得把原理号的所有出现全量解析为跨页任务。CONT.ON.SH 是图册接续目录，不是每条连接的引用。目标页必须命中图册实际页标，否则未知。

端子报告保留作为核对证据，non_wiring=true，不重复创建连接。外部供电接口只有本地接收点时，不伪造另一端 XD10:13、XD21:7、N-BAR 等；正常回指是匹配证据，不判循环。图中实际 X0/X1/X21/X22/X3 与 XLSX 电缆类别 X4/X41 等分开，不迁入旧 ZH 的 XA/XD 映射。

新 adapter 只覆盖模板指令，复用稳定的 ZH JSON/图像请求基础设施；policy 只覆盖页标/引用及原样字段保留。实际模型调用和规则上线需另行授权。完整业务导出的原始 SH.NO. 展示不在本轮改造，运行记录保留原标与规范索引，不能把规范页号当原标。
