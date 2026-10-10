# ADR-0002：规范化线表记录与端子排线号

状态：Accepted  
日期：2026-10-09

## 背景

旧表 `public.wiring_tables` 将整组线表明细保存在 `records jsonb` 中。项目、工作区、业务页码、线号和端子字段无法稳定分页、检索、建立外键或执行字段级修订。图中一个绿色分组行代表一个线号/端子排逻辑单元，其下可以有多条芯线、色标、原理号和起终点端子明细。

## 决策

1. 保留旧 `wiring_tables` 作为迁移期只读表，不修改或删除它。
2. 新建 `projects`、`project_members`、`workspaces`、`drawings` 和 `result_versions`，为线表提供所有权、来源位置和不可变结果版本。
3. `wiring_units` 表示一个结果版本中的端子排逻辑单元；一个单元对应一个数据库分配的线号和零到多条 `wiring_connections`。
4. 线号不是 VLM 推断字段。每个结果版本第一次分配为 `1000`，之后在事务内递增；同一单元下的多条端子明细共享该线号。
5. `wiring_connections` 将以下 Agent 结果保存为可查询列：
   - `principle_number`：原理号；
   - `voltage_level`：电压等级，保存在所属 `wiring_units`；
   - `terminal_strip`：端子排，保存在所属 `wiring_units`；
   - `start_code`、`start_description`、`start_terminal`；
   - `end_code`、`end_description`、`end_terminal`；
   - `current_value`、`remark`、`color_mark`。
6. `project_name`、`workspace_name` 和 `workspace_page` 不重复写入每条连接；它们通过外键保持单一事实来源，并由 `wiring_connection_rows` 扁平视图作为同名查询列暴露给 Agent/API。
7. `workspace_page` 使用文本，允许 `006C01` 等非纯数字业务页号；`pdf_page_number` 独立保存物理页号。
8. 原始模型输出只作为 `raw_payload jsonb` 辅助审计，核心字段不得仅存在于 JSONB。
9. 每条连接可关联多条 `connection_evidence`，保存来源图纸、证据类型、框选位置和原始文字。
10. 新表启用 RLS。浏览器只允许读取当前用户拥有或参与的项目；生产写入由业务 API 使用受控服务身份执行。
11. `wiring_connections.is_cross_page` 只使用 `same_page`、`cross_page`、`unknown` 三个文本状态，由 Stage 2 产生并用于纠错路由；不新增跨页专用表，详细引用继续保存在 evidence 和阶段产物中。

## 结果

- Agent 可以通过项目、工作区、页码、线号、原理号或端子字段定位问题连接。
- 多端子不会再被压缩为一个 JSON 对象，也不会因为重复项目名称产生孤立记录。
- 结果版本、字段级修订、证据追踪和服务端分页有稳定主键与索引。
- Agent 和前端需要在后续迭代中改用新表/API；本 ADR 不授权直接修改生产结果。

## 未选择的方案

- 在旧 `wiring_tables` 上增加大量列：一行仍包含多条连接，无法表达端子排的一对多关系。
- 在每条连接重复保存项目名称和工作区名称：更新名称时会产生不一致；扁平视图可以提供相同查询体验。
- 让 Agent 生成线号：无法保证并发唯一性和版本内顺序，改由数据库确定性分配。
