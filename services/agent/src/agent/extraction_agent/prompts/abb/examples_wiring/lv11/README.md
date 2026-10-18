# ABB LV11/205整页适用连接样例

本地1.3.0。沿用ZH目录结构，初扫仍一张205图、补全仍一张241目标图。

- stage2/lv11_205.expected.json：公共PageScanData最终结果，57条适用连接，覆盖完整图面；具体纳入/排除范围见coverage.json，不将无独立标记的内部符号或未定位箭头补造为外接线。
- stage2/lv11_205.markers.json：与每条local_connection_id对应的两侧原始标记数字。数字从图读出，不从最终原理号反推。适配器把该证据与Expected转成AbbScanResponse示例，line_number留null，程序统一拼接。
- completion/205_q4_l1_to_241_q1.task.json与expected：冻结来源205的Q4 L1，核对目标241回指并读取Q1:2。来源端子/坐标不送给补全模型，也不改写。

当前原图、跨页case、十四列及坐标机制保留。新增电流例子同时示范直接单值与范围置空；当前281/432/241聚焦案例只作为tests/fixtures/abb_reference中的离线字段参考，运行时图片数不增加。

修改初扫Expected时须同步markers旁文件和manifest摘要。quality-provenance记录转录来源、待确认范围与内容摘要。原图坐标为人工目视近似，真实准确率和全页召回仍待用户模型测试，不宣称通过真实回归。
