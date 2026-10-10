# ADR-0005：迁移 ZH 工作流实现到模块所有者

日期：2026-10-10。状态：accepted。

## 决策

将 `agent_service.zh_workflow` 内仍被正式提取调用的实现按职责迁移，不重写已验证的页扫描和跨页算法。正式入口调用公共文档提取 Graph，模型调用继续经三个专业 Agent 子图和 Profile adapter。

- `graphs/document_extraction/`：文档 Graph、运行状态及阶段编排。
- `application/document_extraction/`：阶段客户端协议、运行配置及运行上下文。
- `domain/models/wiring.py`：可追溯的扁平结果模型；结构化阶段响应复用现有 `extraction_stages` 模型。
- `infrastructure/document/`：PDF/图片输入、原子 checkpoint、JSON 解析、表格导出。
- `profiles/zh/`：端子规则、字段归一化、方向/电流校验、图纸引用解析及跨页合并策略。
- `profiles/extraction_policy.py`：公共 Graph 所需的确定性策略协议与 adapter 注册解析。

公共 Graph 通过注入的策略调用模板算法，不直接导入 ZH 规则，也不通过品牌条件分支选择规则。当前只注册具备实现和验收资产的 `zh_native`；未注册 adapter 显式失败，ABB 不继承 ZH 策略。

迁移保持现有阶段 JSON、checkpoint 文件名及版本、11 列诊断 XLSX、ResultProposal 和数据库提交契约。结构化阶段模型使用已有领域模型，并显式转换分类页号。迁移期间曾暂留薄 `zh_workflow` import 兼容模块；正式代码与测试切换后，该目录已删除。

2026-10-10 后续决定：用户要求删除 `zh_workflow` 兼容目录。仓库生产代码及脚本已无旧 import，仅兼容验收测试使用旧路径；本轮删除整个兼容目录，并改为检验新模块及旧包不可导入。删除后旧 `agent_service.zh_workflow.*` 路径不再受支持，当前 Agent/CLI 用法与新 API 保持不变。

## 执行顺序

1. 核对依赖、记录设计和默认测试基线（完成：86 项）。
2. 迁移 domain/infrastructure/Profile 实现及确定性策略（完成）。
3. 拆分文档 Graph，切换生产入口和测试；兼容路径只转发（完成）。
4. 验证 Fake PDF 全流程、阶段恢复、跨页冲突、导出、Profile 资产及数据库契约，更新文档（完成）。

导出格式化通过 `ExportFields` 注入，公共 XLS/XLSX writer 消费预处理值，不导入 ZH 端子规则。ZH 字段映射由调用方显式注入 `ZhExportFields`。已有 checkpoint 的 `_identity_project/_identity_prefix` 和引用索引辅助字段由领域转换函数分离，不能当作模型响应字段放宽严格 Schema。

2026-10-10 用户明确要求删除相邻页分段与批量提取。执行顺序：依赖核对（完成）→删除实现、兼容入口及独占辅助代码（完成）→正式三阶段回归与文档收口（完成）。随后整个旧 import 兼容目录已删除，Agent/CLI 直接调用新 Graph。

已删除 segment decider、legacy batch workflow、batch client 协议、batch checkpoint、batch planner、相邻页辅助函数及旧批次合并策略。公共 Runtime/Graph 不接收分段决策器；Prompt 由 Profile stage adapter 读取，不再把无效的旧 Prompt 字符串传给文档 Graph。旧分段配置移除，新运行不再写两个空诊断文件 `merge_decisions.json` / `extraction_batches.json`。当前三个阶段的 checkpoint、单目标跨页处理和标准导出保留；历史运行目录与旧 backend 未改动。

## 验收与限制

默认验证不得调用真实 VLM。真实模型字段级基线仍需显式评测命令。迁移不改变正在执行的进程，不触发数据库迁移，不改生产 Prompt/Few-shot 内容；策略移动后通过固定离线案例验证字段结果和来源页。
