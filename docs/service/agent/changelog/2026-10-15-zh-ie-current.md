# ZH2.0.5：端点冻结后读取对应相线的Ie电流

用户明确Ie也作为电流读取。初扫与内部补全改为先固定放线段起终点和坐标，再独立沿同一相线寻找对应断路器的电流标注；允许为读取电流经过端子，不改变实际端点或坐标。不同回路分别关联，不使用相邻断路器或整unit的电流。

Ir仍优先；没有Ir时读取明确In/Ie。Ie:(0.7-1)*160A直接取原文160A，current_basis=Ie并保存完整current_source_text，不计算系数、不改取Set。原有单位、原文依据和N/PE/控制/通信/光纤为空的约束保留。既有validated_current已支持Ie依据和带单位的明确数值，无需修改公共Graph或校验器。

003C01按原图修正：FC11、FC12的Ie均为160A，关联XA:8～13六条相线；FC13的Ie为80A，关联XD10:13～15三条相线，并非全部160A。N、PE及两条同页控制段仍为空。XA:8跨页任务保留来源160A及Ie原文，补全expected的current=null表示保留已有值，N-BAR任务仍为空。

ZH Profile升2.0.5、manifest v9；Prompt/调用文字、rules、expected/任务和资源摘要同步。既有端点、元件标识和坐标字段保持，新增字段级回归预期但未执行测试。

仅静态核对资源路径、Pydantic Schema、Python语法、checksum及只读Profile绑定；遵照用户此前自行测试要求，未运行pytest/冒烟、真实模型或提取脚本，未生成新XLSX。不写数据库/Storage、不发布/重绑规则、不重启服务或覆盖旧结果。实际VLM关联电流效果待用户复测。
