# ABB Stage 2内部：定向连接补全（1.2.1）

本次只提供一张目标图和task_context。source_page为冻结来源的功能代码、Sheet、位置及PDF物理页，target_page为当前目标页；Sheet与PDF物理页不能互换。line_number是初扫保存的原理号，signal_name是导线旁可见电位名称，references是目标地址。来源端子、坐标和方向已保存在工作流state，不在本节点重读。

## 读取顺序

1. 先匹配线路。在目标图查找指向来源Sheet的回指，再结合signal_name、电位身份、原理号及references核对。例如目标LV12/241上的=LV11-Q4 L1和/205.3D对应来源205的Q4 L1。/241.1A表示目标Sheet241列1行A，/205.3D表示来源Sheet205列3行D，都不是端子。目标图框功能可以与源电位不同；不按PDF页、Cont或相邻位置匹配。N/PE或同号线路必须结合来源Sheet与完整信号区分，不能仅凭同号确定。来源line_number包含拼接的Sheet，目标图不一定印有同一原理号，不要求照抄该编号；用实际电位、回指和路径核对。
2. 从对应回指沿实际导线找最近实际端点，遇到即停止。大空心圆/设备针脚是端子，标有L1/L2/L3/N的母线接点也可作为端点；小圆点是放线标记，旁边数字是标记编号而非端子号。不能穿过实际端子追到下游设备。同段两处同号小圆点属于一条连接，不重复输出。回指可在任意边界、箭头可朝外，按冻结任务归属补终点，不重新交换起终点。
3. 分开读取位置location、元件device、描述name、排号/接口terminal_board。terminal保留完整端子身份，例如-Q1的2端填device=-Q1、terminal_board=Q1、terminal=Q1:2；-X1旁11/12/13分别填X1:11、X1:12、X1:13，不能把11当成X11排号。母线端只有L1/N等标注时保留原文。实际X排按图读取，不套用ZH的XA/XD分类或+01F业务别名。红框/中文教学批注不是业务值，未标出的字段为null。
4. 读取实际端子符号中心的terminal_coordinates={x,y,pdf_page_number}。x/y按本次实际输入图片归一化到0～1，左上为原点，使用目标PDF物理页。image_view存在表示程序按目标列裁出的全高局部图，只返回该局部图坐标，程序还原整页；没有image_view时按整页读取。

裁剪区域只是候选范围。若线路离开左右边界、回指或针脚不清晰，保留可确认字段，未知字段为null，并用uncertainties记录原因。无法唯一匹配时end=null，不能选相邻同号线。正常来源回指是匹配证据，不递归跳页；不扫描目标图其他连接。

## 电流与输出

已有current由工作流保留，输出current=null表示不改。来源为空时，只在目标图对当前连接有直接、单一明确电流时补充，并填写current_basis/current_source_text；不取范围上下限、不用SET系数、电压或功率推算，N/PE/控制/通信无依据为空。

只输出CrossPageCompletionData JSON，每次明确返回end（可为null）及source_note或uncertainties中的匹配依据/未确认原因。禁止返回{}或只给task_id。来源起点、原理号、Sheet和坐标不改写；只补指定的一条连接。
