# 结果端子坐标契约

2026-10-16用户要求结果表保留起点端子坐标和终点端子坐标，供后续前端在图片定位。复用现有Agent字段名start_terminal_coordinates和end_terminal_coordinates，不修改Agent识别规则或接通正式提取。

两个独立可空JSONB列位于extraction_connection_rows。非空结构为{"x":0.17773,"y":0.53735,"pdf_page_number":60}：x/y为完整页面图像上的归一化端子中心，左上(0,0)、右下(1,1)，有限数且范围0～1；pdf_page_number为该坐标所属图片的PDF物理页，从1开始。两端可以属于不同页，不用业务页号代替，也不强制等于记录的来源页。

API返回同名结构化字段；Server独立Pydantic边界与Agent契约对齐，前端生成类型并映射至WiringRow的startTerminalCoordinates/endTerminalCoordinates。未知保持null，不填(0,0)，不在普通线表编辑框中允许手填坐标，本轮不实现图片叠加高亮。

新增migration，不修改已应用的建表迁移：增加列、JSON形状/数值校验及端点变更失效触发器。人工修改端子或相应页号而未提供新坐标时清除旧坐标，避免指错；不相关描述/备注编辑保留坐标。既有行CRUD返回值与审计使用实际更新后的记录，兼容性需通过真实本地事务验证。

本轮仅存储与接口元数据接入；未来Agent持久化须直接保存这两个键。没有坐标的历史/人工新增行可继续读取。定位时前端按坐标自身pdf_page_number取图，再用x×图像显示宽、y×图像显示高计算位置（缩放/平移由图片容器处理）。
