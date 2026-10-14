# ZH2.0.2：直接端子与程序分类

用户明确修订：去掉Prompt中的图像反例自查和过多硬限制，按每个放线标记找两侧直接端子。002.M/23应包含XD3:17→XD3:1及XD3:2～8→XD3:109～115，不把下游PLC作为这些放线段的终点。设计见[ADR-0016](../../../adr/0016-zh-direct-terminal-segments.md)。

修改位置：

- `prompts/zh/page_scan_index.md`：精简为提取方法、电流约束、输出结构；删除特定页反例自查、按特定功能号排除引用及重复限制，保留用户已精简的意图。电流段原文保留。
- `prompts/zh/page_connection_completion.md`：按对应放线段在目标图读到直接端子即停止；精简硬例与逐字段检查，保留未知值、任务范围和电流要求。
- `infrastructure/zh_vlm_stages.py`：同步随调用附加的文字，避免仍指导模型猜业务端子排。ZH运行时Schema说明actual board/interface/pin；terminal_strip为null，公共Schema未改变。
- `profiles/zh/normalization.py`、`policy.py`：根据明确实际board补齐数字端子，对起终点对称处理，完整端子优先。分类忽略模型返回的terminal_strip；起点已知映射优先，无映射再查终点，两端未知则空。
- `profiles/zh/terminal_strips.py`：native ZH使用用户图片给出的业务映射；普通X3/X5/X9不是业务分类依据，XD1/XD0未列入映射则空。旧通用配置映射保留用于兼容接口，不用它让模型自行分类。
- ZH版本2.0.2，Few-shot manifest v4，新增M23原图和用户确认八条expected；既有expected中的terminal_strip置空，资源/后处理checksum同步。既有测试版本和分类预期更新，但没有运行。

分类表：XA/XD10～12→X1；XD21→X21，XD23→X23；XD22→X22，XD24→X24；XD3/XD5→X3；XD4→X4；XH→X5。

根据用户“不用跑测试，规则改完我自己测试”，本轮未运行任何测试、类型检查、提取脚本或真实模型，没有新的效果/准确率结论。只改本地当前分支，不写数据库/Storage、执行migration、发布远端包、重启服务、改.env或覆盖旧运行产物。ABB/大车卷盘规则不改。
