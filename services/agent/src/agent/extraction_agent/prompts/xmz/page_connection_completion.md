# XMZ Stage 2内部：定向连接补全（0.2.0）

只接收目标图和初扫保留的task_context，补指定连接的终点。source_page/target_page.drawing_label保存原生SH.NO.（如1B、2A），drawing_function/page是可逆程序索引（GCR.1/2对应1B），不是图上印刷页标；PDF物理页只用于图片绑定。来源端子、坐标和方向已由state保存，不在这里重新识别。

## 读取顺序

1. 在目标图查找来源SH.NO.的回指，再核对signal_name、原理号和references。1G45H表示1G页45列H行，不能将45H当针脚。references是目标地址，目标图回指是来源地址。24VDC/ABS、0VDC/ABS、PN2等信号名帮助区分线路，不能当针脚；同号N/PE或相同原理号须结合来源页和完整信号匹配，不按左右顺序配对。两端原理号缺失或标注不同时，只有来源页、完整信号和实际路径仍能唯一对应才保留匹配，并在uncertainties说明冲突。
2. 从对应回指沿实线找到第一个实际端子或设备接口，遇到即停止，不穿过它追到更远设备。回指可在任意边界、箭头可朝外，按冻结任务确定终点归属，不重新交换起终点；正常回指不触发递归跳页。
3. 分开读取实际元件device、描述name、位置location、接口/排号terminal_board及针脚terminal。明确同排X标识与数字组合，例如X3:19；设备接口X150与P1组合为X150:P1，不能把信号或功能标注当针脚。保留图上实际元件代号，不套用ZH的+01F别名和XA/XD分类。terminal_code仅存独立接口标识，terminal_strip留null，由程序处理。
4. end.terminal_coordinates读取实际端子符号中心，按本次实际输入图宽高归一化x/y（0～1），左上为原点，绑定目标PDF物理页。image_view存在表示按本模板01～48列裁出的全高局部图，返回局部图坐标，由程序还原整页；没有image_view时按整页读取。不标文字、箭头或放线斜杠的位置。

若导线离开局部图边界、回指不唯一或针脚不可辨，保留可读事实，未知字段为null，通过uncertainties记录缺失证据。只有24VDC功能文字而未标针脚时terminal=null，不能套入来源针脚。不从人工表、图外设备常识或相邻线路补值。目标位置可以使用target_page已知元数据；元件名称只读取视图内可见标注。

## 电流与输出

来源已有current时输出current=null表示保留。来源为空且目标明确给出当前三相断路器对应相线电流时，优先Ir，其次单一明确In/Ie，必须带单位及current_basis/current_source_text。N、PE、控制、通信、光纤为空；不计算范围、系数或电压/功率。

只输出CrossPageCompletionData JSON，明确给出end（可为null），并用source_note或uncertainties说明匹配路径或未找到的原因。禁止返回{}或只给task_id；不输出start，不创建其他连接，不改来源原理号和坐标。
