# 真实工作台接入：实施进度

后续更新：真实资源包/图纸索引浏览器已通过，用户授权后的真实模型提取已成功落库；剩余浏览器纠错因自动审批服务配置故障尚未续跑。以下为分阶段历史记录，当前状态见 [真实模型联调](./2026-10-12-live-agent-acceptance.md)。

## 最新进度：用户授权后的端子增删与真实 CRUD 验收

单条端子新增/删除已实现，见 ADR-0011 与 connection-crud-plan.md。Server 既有表 PostgreSQL 原子事务保留其他 ID/线号/代次；删除前存完整记录与证据，新增指定既有单元/来源/明确跨页目标；权限、revision/record_version、幂等 receipt 与 before/after 审计齐全。Web 新增按钮、选择表单、行删除确认及 OpenAPI 类型同步。无 DSN 返回 503，不新增 migration，不改 Agent 主功能。

24 项默认 API、5 项 HTTP 浏览器夹具、Ruff/strict mypy（8 个 Server 源文件）与 Web lint/typecheck/build 通过。显式一次性真实 Auth/DB/Storage/API/浏览器登录/续期、增改删、签名双图预览通过；真实事务验证越权/过期/幂等冲突与重放、注入审计失败后记录/revision/审计全部回滚。临时项目、账号、对象及自建进程清理，test0 未改。

完整 Supabase/Fake 模型提取联调未通过：两个场景在自身 Worker claim 返回 false 失败，共享队列存在活跃用户 Agent/审校消费者；没有声明三阶段成功，不继续向共享队列追加 Fake 任务，也未停用户服务。需队列空闲且无其他消费者时继续完整 Web 上传/纠错验收。本次 CRUD 验收不调用模型或向 Agent 入队；不保证此前共享队列测试没有被其他 Worker 抢占。下文是本次授权前的历史进度，未完成描述以本段和完成性核对为准。

启动：生产配置 SERVER_DATABASE_URL；本地 `services/server/scripts/run_local_api.py --supabase-container supabase_db_zhenghua_test --port 8000`。显式验收脚本 `verify_connection_crud.py --allow-temporary-data --local-container supabase_db_zhenghua_test --browser`，说明见 services/server/README.md。

本轮不修改数据库 Schema、数据库业务数据或 Agent 核心。

已实现：Server Supabase Auth/JWT/权限、项目 CRUD 与两系统删除策略、项目树/真实结果过滤分页、带审计/版本的手动修改、签名图纸/跨页定位、真实包规则资源、8100 SSE 代理。Web 默认真实数据；页码/线号组首、表格编辑、下方原页/目标页、图纸索引、三阶段规则面板/样例、真实用户菜单、拖拽/键盘调整面板、上传/确认与 run 事件卡片、浏览器刷新订阅。

已验证：21 项 Fake API 测试（包括项目创建/修改权限、历史跨页精确匹配/歧义拒绝、删除权限/活跃任务拒绝/Storage 故障恢复、登录/续期/过期退出、共享单元编辑 before/after、非法目标拒绝、内部 Agent 鉴权/上传幂等请求头及完整上传响应）；5 项 Playwright HTTP 夹具场景（分组、预览、编辑请求、阶段样例说明/图片/expected、登录/空态、上传/类型确认/阶段单卡片、断线序号续传、纠错 proposal 人工确认/结果刷新/归因解释、键盘缩放和桌面/窄屏截图）；Web lint/build 与 Server Ruff/mypy。只读 Supabase 冒烟读取 test0 的 4 工作区/12 连接/2 已发布包，两个包各 22 文本/7 签名图片校验；历史 target evidence 唯一定位到 PDF 第4页；既有原位修订 SQL 冒烟在事务中通过并回滚（稳定 ID/revision/幂等/权限/过期拒绝/批次原子性）。没有修改 test0 或保存真实写入。

后续收尾修复：StrictMode 重放取消首个自动检测请求、最终 Supervisor 类型确认消息丢失、阶段开始/完成重复卡片、已提交 proposal/提取结果错误显示为待确认、并发 refresh、过期 JWT 无法退出。手工编辑增加电压等级/端子排共享字段，同一提交失败重试复用幂等 key；图纸预览具备签名刷新/失败态和请求顺序保护；新发布树自动展开。

完成性核对又补齐：规则包按实际 manifest 逐阶段展示样例标题/说明/图片角色/expected，归因无规则问题时仍展示原因，已生成候选不再重复请求创建授权；内部 Agent 401 不再导致浏览器误退出，上传必须有幂等请求头。核对记录见 ../workbench-completion-audit.md。

仍需完成：真实登录与写入联调、真实上传/Agent 全链路浏览器验收。单条线表新增/删除尚未提供，已询问用户是否属于本次 CRUD 范围，以及是否允许一次性验收数据；手工编辑已实现。代码接通不等于完整生产验收。未调用真实模型，未启动/停止用户 Agent。
