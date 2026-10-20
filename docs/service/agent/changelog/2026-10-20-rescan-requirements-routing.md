# Explain 重扫规划与执行路由修复

实现[ADR-0042](../../../adr/0042-rescan-requirements-and-routing.md)。本轮修改Explain任务规划/工具、重扫Worker与适配层，复用既有页提取Graph；没有重写Extraction算法或改动生产Profile包。

## 行为

新模型任务必须显式填写requirements的所需字段、预期起点集合、保留/重建集合及同页约束。要求原理号却选择end/start权限、要求重建却只传旧行ID、预期起点和局部选择不完整对应时拒绝入队，返回稳定错误供模型重新规划。字段完整性不再只写在instructions里。公共DTO仍允许历史requirements缺省；新工具Schema及执行门禁要求完整需求。

“纠正整页起点集合/补漏/多提/补提原理号”规划为页scope、fields=all、connection_set=rebuild，不带旧行ID。沿用完整页Graph生成replace_scope候选，可含新增起点及原理号；旧数据仅在用户核对完整删除/写入对照并确认后替换。

fields仅控制写入权限。Worker按实际端点页与显式目标绑定分流：跨页终点继续冻结起点补全；同页终点使用本页扫描/归一化/校验，按唯一的起点身份对应旧行，冻结ID、起点、原理号及归属，仅生成终点patch。重复旧起点竞争同一扫描连接时不挑一条猜测。实际端点所在页与记录提取归属分开处理；模型调用metadata.rescan_operation与metric.operation记录page_extraction/same_page_endpoint_scan/cross_page_completion，供核对实际路径。

同页扫描不再混入旧目标页完整图；模型推测的跨页引用受本页约束，不触发额外补全。图片与需求作为模型真实输入，原理号需求映射到视觉Schema的line_number。预期起点不能生成模型未识别的新行，预期终点不能直接写成答案。

候选按需求检查缺失/多提/重复起点及原理号、端子缺项；缺口进入warnings，变更行标记needs_review。任务卡展示本轮要求和预期起点，提示变更数不代表全部识别成功；“未唯一匹配”改为“未完成或无法唯一匹配”。ready仅表示候选已生成。失败尝试仍保留原错误，同轮存在真实成功工具回执时标为“尝试失败·本轮已有任务”；历史任务不为本轮失败背书，不把任务存在说成识别成功。

## 契约和缓存

API2.14.0：Agent/Server DTO、OpenAPI、Web生成类型同步，Agent与Server JSON Schema一致。request仍保存在原JSONB，无新增表/列或migration；权限、私有附件、确认事务沿用原机制。

新输入契约rescan-v7、模型输入标识4，不复用旧路径的model/page缓存。旧输入checkpoint要求新建任务，已完成历史任务与正式结果不改写。

## 验证

- 先补8项旧版失败复现，再实现修复。新增Agent15项覆盖需求/范围门禁、纠错后重新规划、整页四旧五新及原理号、同页冻结/跨页拦截、缺口、重复锚点与旧缓存隔离；既有ZH/ABB及跨页固定Fake场景保留。
- 213项Agent相关离线回归通过，最后23项需求/页流程/绑定复验通过；46项Server测试通过，16项显式数据库集成默认跳过。
- 21项浏览器场景分批通过（含8项状态相关复验），覆盖要求/缺项/确认保护、失败尝试/历史隔离、范围替换/空结果、附件、冲突及登录/工作台空/加载/失败/无权限/长文本。失败尝试提示先补失败复现再实现。一次旧附件测试误点前轮“立即显示”导致失败，改为定位本轮消息后连续3次通过；未改产品逐字显示逻辑。
- Agent与生成Server Schema相同；Ruff、8个Agent源码及生成Server DTO的strict mypy（follow-imports=silent）、Web类型检查/lint/production build通过。构建保留既有大chunk提示，桌面/窄屏截图已核对，位于忽略目录`.runtime/rescan-requirements-browser`与`.runtime/rescan-requirements-retry`。

默认只用Fake模型/HTTP；未调用真实VLM、重跑实际任务、修改正式线表/生产Profile、应用迁移或启停用户服务。真实模型的需求理解和图纸识别质量尚未验收；真实数据库写入集成未运行。

## 使用

先重载8000以加载API2.14.0契约，再重载8100和实际执行Worker（内置Worker随8100重载），刷新Web重开Explain并新建重扫。无需新增环境变量或启动服务种类。原已确认保存的结果不会自动恢复或修正，新候选仍需确认。
