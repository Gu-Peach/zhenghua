# ADR-0042：重扫需求、写入权限与识别路径分离

状态：已实施并通过代码/离线验收，真实模型质量待新任务验证。2026-10-20。关联ADR-0034、0036、0041。

## 问题

fields=end同时充当字段写入掩码与跨页补全选择器，用户纠正连接集合/要求原理号时被缩成已有行终点补全，同页线路被要求寻找跨页回指，缺失起点被遗漏。说明文字不能突破Schema或写入权限。

## 决策

1. RescanRequest新增可选requirements以兼容历史任务：required_fields（start_terminal/end_terminal/principle_number）、expected_start_terminals、connection_set（preserve/rebuild）、endpoint_location（unspecified/same_page）。新模型工具Schema要求显式提供，新工具执行拒绝缺少需求；公共历史DTO仍可不带。同步API2.14.0、Server DTO、OpenAPI与Web类型。
2. 入队前及Worker前校验：原理号不能走start/end掩码；rebuild必须fields=all且页/工作区范围，不得带旧行ID/原理号列表；局部模式的预期起点必须完整覆盖选择的真实行。缺失起点不得编造ID或静默省略，应重新规划整页候选。删除模式继续由程序决定。
3. fields只控制写入权限。Worker根据显式绑定和实际端点页分流：跨页终点保留冻结起点补全；同页终点使用既有页扫描/归一化/校验链路，按唯一的起点身份匹配旧行并冻结起点与归属，只生成end字段patch；整页all复用既有完整页Graph生成replace_scope候选。
4. 同页约束在重扫适配层执行：本页扫描不混入旧目标图，模型推测跨页引用不触发额外补全，未知终点待复核；不改厂商Profile包，不在公共节点增加厂商特判。
5. required_fields/expected_start_terminals用于检查候选缺项、多提、重复和字段完整性，写入warnings与needs_review，不作为模型答案。ready仅表示候选生成，确认仍经Server原子版本/权限校验。
6. 输入契约升级rescan-v7，避免混用旧模型/页面checkpoint；不改写已完成任务，不兼容checkpoint明确要求新任务。

## 边界与验收

沿用request JSONB，无新增数据库表/列或migration。RLS、Storage与确认事务保持；不自动重跑或恢复已保存结果。先补混合字段、遗漏起点、同页错路由失败回归，再验完整页新增/删除/原理号、端点掩码、跨页、缺项/失败/恢复与契约一致性。默认Fake模型/HTTP，不调用真实VLM或修改用户业务数据；真实质量需另行显式评测。
