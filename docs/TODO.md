# TODO

> 这是当前执行清单，不替代 [开发路线](./roadmap.md)。每次开发只把本次可交付内容放入“进行中”。

## 进行中

- [x] 修复 Stage 2 页码类型兼容：统一将模型返回的 unit/connection `source_drawing_pages` 数字转换为字符串，保留非法结构校验；新增回归测试，4 项跨页状态测试与 Ruff 通过。旧失败 run 不重试，用户重载 Agent 后重新提交新图纸。

- [ ] 兼容规则候选确认的重复 `/resume`：当旧客户端或 Supervisor 将“确认规则修改”误判为通用人工输入时，依据已有候选 artifact 强制走幂等直接发布分支，避免已确认 run 被错误标记失败；补回归测试并由用户重载 Agent 验收。

- [x] 2026-10-13 移除规则修改链路的模型评测/二次审核：归因建议一次确认后直接构建并发布包；旧候选接续、重复确认、原子审计/版本保护及前端/终端文案同步。Agent 默认测试、strict mypy/Ruff、18 项浏览器回归及 Web 检查通过；28 迁移空库/旧数据与合成发布事务通过，新增 RPC 已在本地部署。未发布 test0 候选、未调用真实模型/停止任务；用户重载后验收。见 ADR-0013。

- [x] 项目切换使用已知摘要保留 Header/目录/导航，仅中间加载数据；目录不随点击重拉，Server 按 created_at/id 固定顺序，详情更新只原位合并状态。17 项浏览器夹具、29 项 Server 默认测试、Web typecheck/lint/build 与加载中桌面/窄屏截图检查通过。Server 排序需用户重载服务，未停止现有服务。

- [x] 左侧项目目录单击文件夹/名称直接切换项目数据，当前项目箭头独立折叠，非当前项目箭头直接进入该项目；移除二次“打开项目”入口。17 项浏览器夹具及 typecheck/lint/build 通过，桌面/窄屏截图检查完成。

- [x] 2026-10-13 导航/搜索按容器水平居中；线表双击或行按钮原位编辑，Enter/行保存、Esc/行取消，冻结版本基线，失败保留草稿/幂等标识；原 PATCH/审计语义不变。16 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过。见 docs/apps/web/changelog/2026-10-13-centered-inline-edit.md。

- [x] 2026-10-13 工作台精简：新增端子换为最右加号；移除全部工作区按钮、项目概览及结果统计副标题；导航显示当前项目名；左侧项目可折叠且移除 PDF 中间行/文件名副标题；聊天移除当前阶段卡片。13 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过。见 docs/apps/web/changelog/2026-10-13-workbench-cleanup.md。

- [x] 2026-10-13 前端目录/悬浮聊天：图纸库项目→工作区→图片原地展开及懒加载预览；右下角按钮切换非模态悬浮聊天，隐藏后保留草稿/订阅、重新打开不重复任务。13 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过；未调用真实模型或修改数据库。见 docs/apps/web/changelog/2026-10-13-directory-floating-chat.md。

- [x] 规则库取消草稿使用门槛：三个增量 migration 已应用；所有登录用户可读非候选手工规则包，旧 draft 升 active，同 key 默认最新版本，候选隔离/回滚不误伤其他版本。ABB 1.1.2 已上传读回并以 `abb_native` 注册，Stage 1/2/3 Fake 链路、RLS 非创建者读取、27 个 migration 空库/旧数据重放通过。未调用真实模型或修改项目数据。

- [x] 完成图纸目录最终检查：空目录提示、跨工作区平铺/点击定位、桌面/窄屏截图；11 项 Playwright、Web typecheck/lint/build 通过。初次只读核对发现 ABB 旧包为 draft；后续按用户新决策迁移为共享 active 并新增 1.1.2。
- [x] 用户确认规则库与账号无关后改为共享读取；数据库用非创建者 authenticated 身份验证可见 ABB，浏览器不再依赖包创建者 UUID。

- [x] 修复候选评测 Stage 2 定位上下文：明确传递冻结目标的起点身份，不传正确终点/原记录答案；4 种同页/跨页、扁平/嵌套起点用例核验最终模型消息，32 项相关离线回归通过、1 项既有 ABB adapter 名称断言失败未改，Ruff/161 源文件 mypy 通过。不改数据库/规则包/运行服务，不调用真实模型；旧评测缓存与失败后新评测入口仍另行处理。见 Agent 目标定位修复记录。

- [x] 图纸库只展示当前项目图纸、不展示项目或工作区文件夹；规则库显示共享可用包，不再显示草稿/候选/已发布三态。AI Improvement 候选不属于规则库列表。

- [x] 精简 ABB 样本：Stage 1 一页、Stage 2 一张含 Q4 跨页连接的原页（示例答案范围明确）、Stage 3 一例原页+目标页；三个阶段各一案例。abb@1.1.1 草稿已上传私有 Bucket，18 文件读回核验通过；11 项相关离线回归/Ruff 通过。原图、旧远端包与生产绑定保留，见 docs/service/agent/changelog/2026-10-12-abb-resource-compact.md。

- [x] ABB 样本资源包：4 张标注图整理为 4 个 Stage 1、4 个局部 Stage 2、7 个 Stage 3 样例，独立 Prompt/manifest/expected/task 与来源说明完成；21 项离线回归通过，abb@1.1.0 草稿上传私有 agent-profile-assets，45 文件读回校验通过。不改 test0、active 包或运行服务，见 docs/service/agent/changelog/2026-10-12-abb-resource-draft.md。
- [ ] ABB 质量验收：`abb_native` 执行支持及 1.1.2 可用包已完成；仍需工程确认 expected 与原理号优先级，并运行真实图片字段级回归。无需再做草稿发布操作。

- [x] 规则库包管理实现：基于共享可用模板新建、人工确认后 Bucket 直接注册、创建者删除/停用并保留历史引用；后续已由 ADR-0012 取消手工包草稿/发布步骤。API/Web/动态注册同步，未调用模型、不改 test0、不停止服务。
- [ ] 规则包交付验收：用户重载 Agent/Server 后验收真实 Bucket 创建/停用；修复本机 node_modules 读取权限后运行自动 OpenAPI 类型生成、Web lint/production build。本轮这些检查受 EPERM 限制，生成类型暂按已导出的 OpenAPI 手动同步。

- [ ] 工作台剩余验收：真实 Bucket 三阶段资源与图纸索引已通过；用户已授权使用现有 8100 和一次性项目调用真实模型。上传/检测/人工确认后的三阶段已成功，继续在同一临时项目验证纠错/人工确认/归因并清理；不停止用户任务，不改 Schema/test0。

- [x] 规则候选评测/审核/发布代码：冻结固定正例/负例与 accepted-feedback 目标，三阶段实际调用、持久案例/报告与断点复用，服务端 receipt/gate、两次人工确认和不可变 Bucket 发布；纯 HTTP 终端入口。49 项离线测试、160 源文件 mypy/Ruff 通过，真实候选只读预检 9 案例通过。无 migration/模型调用/线上发布，真实评测和审核/发布验收待用户执行，见 docs/service/agent/candidate-release-plan.md。

- [x] 修复规则补丁 JSON 解析：完整 JSON 优先、仅识别真正外层 fence，保留文件字符串内嵌代码块；新增纯 JSON/外层包装/前言三类回归，31 项相关测试与 158 源码类型检查通过，实际失败 Trace 只读重放通过。未调用模型/恢复任务/改库/发布规则，真实恢复待服务重载。

- [x] 修复 ProfilePatchBuilder 输出契约：只读 Trace 确认失败为 ProfilePatchModelOutput invalid_json；动态注入 Schema，明确纯 JSON、转义、完整文件替换与包相对路径；11 项相关离线回归通过。未重提取/提交已完成修订、未调用真实模型或发布规则；真实恢复待重载服务。

- [x] 修复独立提取审校脚本：缺失跨页页码保留待复核、循环引用检测；11 项离线回归通过，说明快照变化，未调用真实模型。
- [x] 修复独立审校对账：模型返回 matched 但缺少 connection_id 时降级为 needs_review，避免中断整批；离线回归覆盖。

- [x] 按用户确认完成单条端子新增/删除：既有表 Server 原子事务、权限/revision/幂等/before-after、稳定其他 ID/线号/代次与 Web 入口；24 项默认 API、5 项 HTTP 浏览器夹具通过，真实 Auth/DB/Storage/API/浏览器增改删/双图/越权/过期/冲突/重放/审计失败回滚通过。一次性项目/对象/账号及自建进程清理，不改 test0/Schema/Agent 核心。

- [ ] 真实工作台接入（不改数据库/Agent 核心）：Server JWT/项目权限、项目树/线表 CRUD/图纸索引/私有资源包接口；Web 页码与线号分组、原页/跨页下方预览、编辑、规则资源面板、Agent 流式上传/纠错、可缩放布局。执行计划见 docs/service/server/workbench-integration-plan.md。
  - [x] Server/Web 基础接入与 OpenAPI 类型；21 项 Fake API、5 项 Playwright 夹具、Ruff/mypy/lint/build、真实库只读与既有修订 RPC 回滚验证。
  - [x] 真实 Auth 登录/续期、表格增改删与双图验收；事务失败回滚、权限/过期/幂等检查，临时数据清理。
  - [x] 真实账号浏览器验证 Bucket 三阶段 Prompt/样例图片/描述/expected、资源链接刷新和图纸索引。
  - [ ] PDF/纠错真实浏览器全链路验收：用户授权后上传/检测/确认与三阶段落库成功（5 页/13 连接，约 226 秒）；浏览器进程退出，纠错/确认/归因尚未验证。已有一次性项目可续跑，不重提取；自动审批服务模型权限 403 导致续跑命令未执行，详见 Server 联调记录。不停止用户服务。
  - [x] 流式交互收尾：最终确认提示可见、阶段单卡片更新、等待/失败展示、断线重连、StrictMode 首次检测取消和登录重复续期修复；补齐共享字段编辑、图片链接刷新、上传完整响应契约。写入真实联调已完成，会话全链路另验，不改 Agent 核心或 Schema。
  - [x] 完整性核对：规则 manifest 样例、纠错确认/归因、候选授权与 Agent 401 边界；端子增删和临时数据授权已落实。证据见 docs/service/server/workbench-completion-audit.md，完整 Agent 验收仍未完成。

- [x] 准备 test0 三条混合纠错注错样例：PDF 核对 XD3:251→2、XD3:260→1、006.M/1 XD3:113→006.C/1 X3:1，仅将最新代次三条 end_terminal 改为999；标记人工注错并备份原值/预期/消息到忽略的 runs/test0-mixed-prepared-001，revision 1→2。未修改规则、起点、跨页状态/引用，未调用模型或重启服务。

- [ ] 用户混合纠错及规则发布人工验收：`2.纠错agent/run_acceptance.py` 检查混合修订/归因，规则问题使用 `--expect-rule-issue`；一次确认直接启用。既有候选使用 `run_rule_release.py` 确认发布，不再评测，不重复注错或纠错。

- [ ] 用户重载 Agent 后验收原位纠错：本地 `20261011020000` 和契约 V3 已部署，直接答案/Stage 2/3 共用稳定 ID 提交；先只对当前最新行注错，确认后检查同 ID 更新和 revision，历史不清理、现有服务未重启。

- [x] 修复案例 A 确认后的 409：只读确认版本 2 已 accepted，错误来自归因 run 把 feedback ID 当成 PDF ID；改用原纠错 run 的 source document，冻结 Profile，归因启动失败明确返回已提交结果；5 项相关回归/strict mypy 通过，未重复提交修订或重启服务，待用户同 proposal 幂等补启动。

- [x] 修复案例 A 的 Supervisor MODEL_SCHEMA_INVALID：实际模型输出数字页码及 start_terminal 导致校验失败；增加方向查询、编号整数归一化和动态输出 Schema，23 项相关离线测试/strict mypy 通过；修复后只读模型路由和唯一匹配验证通过，未分派工作流或修改线表，服务待用户重载。

- [x] 编写纠错批次与 Bucket Profile 资源包修改方案：保留跨页 Stage 2→Stage 3，复用 test0 手工注错/自然语言输入验收，不新增终端验收脚本；本轮仅文档、不修改代码/数据库/规则包。详见 `docs/service/agent/correction-agent-refactor-plan.md` 与 ADR-0009。
- [ ] API/Worker 启用 `AGENT_PROFILE_PACKAGES_ENABLED=true` 并由用户加载新代码，然后进行 test0 手工纠错验收；数据库迁移和 ZH bootstrap 包发布已完成，现有服务未重启。

- [ ] Gate B 真实模型人工验收：使用已有 Auth 用户 UUID、真实 PDF 和人工 baseline，通过显式开关/终端确认运行 `1.3stage/run_acceptance.py`；接口与 Fake 验收已完成，准确率尚未验收。

- [x] 从保留的 `.git-new` 恢复本地 Git 历史和 origin，整理当前源码、文档及版本化 Few-shot 资产，排除密钥、缓存和提取运行产物。

- [x] 排查 Codex 新模型不可见问题：核对官方发布、客户端版本、配置优先级、模型目录来源与账号返回，并在需要时备份和刷新自定义目录。
- [ ] 将规范化线表 migration 应用到远端 Supabase，并执行空库、权限、线号并发和旧数据快照验证。
- [ ] 完成 Agent M8 剩余生产化：完整中断续跑测试和 ZH 真实字段级基线；Supabase 持久 repository 与跨进程租约队列已完成。
- [ ] 解除 Agent M15-M16 阻塞：补齐 ABB 独立真实资产，并先建设 `apps/api`、业务持久化与 Server 事件代理。
- [ ] 使用真实 VLM 完成 Agent M4 首页路由准确率、耗时和费用验收。
- [ ] 审核并确认 `docs/refactor-plan.md` 的领域模型与迁移顺序。
- [ ] 为 ZH、ABB 各建立一份不可变的验收案例清单。
- [ ] 接入 Supabase Auth，并实现真实路由守卫和会话恢复。
- [ ] 用新 `apps/api` 替换 `src/apis` 的 Mock 适配器。
- [ ] 评审独立 Agent 服务的端口、Server 契约和数据所有权。
- [x] 评审多 Agent 提取、反馈重提取和离线自完善方案。
- [ ] 确认 Agent Harness 的 V1 边界与 Profile 发布门禁。

## 下一步

- [ ] 补齐纠错/改进（protocol 1）run 的过期 RUNNING 接管和 fenced 写入；当前仅已持久 item 能在重新执行时复用，不声称自动故障恢复。

- [ ] 初始化 monorepo 根配置。
- [ ] 创建 FastAPI 新模块目录和兼容适配层。
- [x] 设计并评审 Supabase 新迁移和 RLS。
- [ ] 用真实 API 替换 mock 数据。
- [x] 将 Agent runtime/checkpoint 迁出 `frontend/public`。

## Agent

- [x] 实施阶段持久化 Gate A：真实数据库/Fake VLM 验证阶段屏障、RUNNING 接管/fencing、权威集合、最终收尾、树发布、退避/取消及独立 Worker 进程空缓存续跑；不包含 Gate B。
- [x] Gate B 接口与 Fake 验收：业务上传/Profile 确认/原子入队、持久 Worker、HTTP 查询/SSE、`1.3stage` 纯 HTTP 终端脚本；真实模型人工验收另列。
- [ ] 严格按 M0-M16 顺序实现并逐阶段验收 Agent，不并行跳过依赖门槛。
- [x] 预先建立 Supervisor/Correction 架构决策、领域契约、意图决策骨架和确定性纠错路由；Supervisor Graph 后续开发。
- [x] 建立 Stage 1 页面分类、Stage 2 当前页扫描、Stage 3 跨页补全独立 Agent 子图，并通过 ZH adapter 复用原流程。
- [x] 完成 Agent M0-M3：服务骨架、公共契约、Harness、Profile Registry 与 ZH 兼容适配器。
- [x] 定义 `DrawingProfile` Protocol 和 Profile Registry。
- [x] 将 ZH Prompt、图片 Few-shot、PDF/索引/跨页/校验/XLSX 工作流迁入 `services/agent`，并提供无 backend 导入的三阶段测试 runner。
- [x] 为 VLM HTTP 错误增加脱敏 provider 详情；不可重试的请求错误立即终止工作流，避免整本 PDF 重复发送无效请求。
- [x] 将 ZH Stage 1/2/3 当前页和 Few-shot 图片的 OpenAI `image_url.detail` 设为 NInfer 兼容的 `auto`。
- [x] Agent dotenv 配置仅加载 `services/agent/.env`；根目录和 `backend/.env` 不再参与配置合并。
- [x] 修复 Stage 2/3 图片 Few-shot 超出 VLM 视觉 patch 预算的问题；请求内按配置缩小样例图，保留所有图像样例及原始图纸分辨率。
- [ ] 使用真实 VLM 对 ZH 固定案例做字段级结果、耗时和费用对照。
- [x] 完成 ABB 三阶段独立 Prompt、图片 Few-shot 和 Expected JSON 草稿；工程确认与真实模型验收另列。
- [ ] 增加 Profile 识别结果和人工覆盖字段。
- [x] 通过 repository 接口保存阶段事件并提供可续传 SSE；Supabase 模式已接入持久 Run/Event/Artifact/Proposal/Checkpoint repository 和租约队列。
- [x] 增加节点级幂等键、Run 创建幂等和任务取消检查。

## 数据与结果

- [x] 新建规范化领域表，不修改旧 `wiring_tables` 数据。
- [x] 定义 Connection 与 Evidence 的字段映射。
- [ ] 实现服务端分页、筛选和排序。
- [ ] 实现结果版本和 XLSX 快照导出。
- [ ] 编写旧数据回填与核对报告。

## 待决策

- [ ] 项目是否支持多人协作，还是 V1 仅 owner 可见。
- [ ] 工作区名称是否允许用户覆盖 Agent 识别值。
- [ ] ABB 图纸页号和跨页坐标的统一业务键。
- [ ] Profile 自动识别低于多少置信度时要求人工选择。
- [ ] 生产部署采用自管 Redis/Celery，还是托管队列。

## 已完成

- [x] 修复 ImprovementDiagnoser 输出契约：system 动态注入完整 Diagnosis JSON Schema，明确字段/枚举且保留严格校验与端点兼容；24 项相关离线测试、全包 strict mypy 和修改文件 Ruff 通过。原三条修订已提交，未重提取/重新提交/注错，也未写数据库、调用真实模型或重启服务；用户重载后仅恢复失败的归因 run。

- [x] 修复混合纠错起点身份匹配：区分位置/设备/端子、保留稳定 ID 和起点，缺失/歧义/重复明确报错；Worker 记录安全异常类型和调用帧。33 项相关离线回归、全包 strict mypy 和修改文件 Ruff 通过，失败任务 Stage 2 产物只读重放通过；未改数据库或规则、未调用真实模型、未重启服务。用户重载后用新会话重跑混合验收。

- [x] 第一个混合纠错终端脚本：纯 HTTP 输入/SSE/阶段与模型输出、人工确认、原位数据核对、规则无问题/证据不足/拒绝意外候选分支、逐步落盘和只监看模式；只读观测接口过滤私有推理并限制用户范围。离线 Mock 流程/相关回归、strict mypy/Ruff 通过；后续已补充 `run_rule_release.py` 接续候选发布链路。

- [x] 原位纠错（ADR-0010）：当前集合内连接/单元/证据 ID 和线号保持稳定，revision/record_version+1，before/after 留在 feedback，proposal receipt 幂等；内存/Supabase、确认消息、分页契约已同步。17 项相关离线测试/strict mypy/Ruff 通过，真实数据库合成回滚验证权限/幂等/过期拒绝/批次原子性，本地 migration 已部署，不修改 test0 的现有值、不重启服务。

- [x] 部署纠错资源包：本地 `zhenghua_test` 事务应用并登记 `20261011010000`，发布与 test0 checksum 一致的 ZH bootstrap；29 个包文件下载校验通过，7 张图片签名 URL 可生成，匿名元数据读取为 0 行，原线表摘要不变；修复 void RPC 空成功响应解析。未运行真实模型、未更改服务开关或重启服务。

- [x] 纠错方案代码基础：混合 CorrectionBatch、统一 proposal 提交、Stage 2→Stage 3 持久阶段调用、归因证据上下文、自包含 Profile 资源包及候选发布/回滚适配器；26 项离线测试、全包 strict mypy/Ruff 通过。数据库部署、真实包上传、人工验收和非提取 run 接管/fencing 未完成，详见 Agent 实施记录。

- [x] Gate B 实现：阶段 0 临时附件与业务源 PDF 隔离、冻结 Profile/确认审计、原子 run/event/queue、published 树与版本化分页结果、阶段摘要/SSE 续传和纯 HTTP 脚本；113 默认测试、2 个真实本地 Supabase/Fake HTTP 场景通过，22 migration 空库/旧数据及原子失败回滚通过；真实 VLM 未运行、Web/JWT 代理未接。

- [x] Gate A：逐阶段提交/读库屏障、不可变模型项/清单、输入/结果/记录摘要、Worker fencing 与幂等 finalize；105 项默认测试通过、10 个真实 Supabase/Fake VLM 场景分批通过，21 份 migration 空库/合成旧数据验证通过；未调用真实 VLM、未重启既有服务。
- [x] 按六项评审意见修订持久化方案/ADR 至 V1.1：补齐 Worker 状态接管、上游权威集合、最终 receipt/finalize、未发布树/epoch、精确摘要/冲突语义和 Gate A/B；仅文档，运行链路未改。
- [x] 编写三阶段持久化改造方案及 proposed ADR-0007：逐轮数据结构、数据库/Storage 位置、事务/恢复边界、最终字段映射、改动文件与验收顺序；本轮仅交付文档。
- [x] 建立阶段 0 纯 HTTP 终端验收脚本、会话附件接口、Supervisor 短期记忆与检测后确认闭环；103 项 Agent 测试、strict mypy、Ruff 与 compileall 通过，默认测试不调用真实 VLM。短期记忆限定为单进程最近 12 回合，长期记忆仍未实现。
- [x] 修复真实 OpenAI-compatible 模型请求中结构化 Supervisor 消息的 `content` 类型，并以请求体回归覆盖 mapping 序列化；重新执行阶段 0 前需让 Agent 服务加载修复后的代码。
- [x] 兼容不支持 provider structured-output 的 OpenAI-compatible 模型端点：默认不发送 `response_format`，保留本地 JSON/Pydantic 校验；完成离线回归，阶段 0 真实重试需重载 Agent 服务。

- [x] 删除 `agent_service/zh_workflow` 全部兼容文件与缓存目录，旧路径测试切换到新模块；93 项默认测试及全包 strict mypy/Ruff/编译检查通过。
- [x] 删除 Agent 旧相邻页分段、批量提取及独占辅助代码、配置、checkpoint 和兼容入口；正式链路只使用新三阶段 Graph。93 项默认测试及全包 strict mypy/Ruff/编译检查通过。
- [x] 完成 `zh_workflow` 实现迁移：公共文档 Graph、共享 domain 结果、PDF/checkpoint/导出基础设施与 ZH 确定性策略分离；正式提取使用新模块，兼容目录已在后续清理中删除。新增非空 PDF 字段/跨页/恢复与导出回归，全包 strict mypy/Ruff 通过。
- [x] 完成 Agent 结构化结果落库：完整提取 Proposal 原子提交为 `result_versions/wiring_units/wiring_connections/connection_evidence`；数据库从 1000 分配线号，提交具备幂等、base version 校验和事务回滚。
- [x] 将 Supabase 模式下的 Correction bundle、accepted feedback、Model Trace、Profile candidate、release gate、eval 与发布审计迁移为持久适配器；跨进程 Correction 图片从私有 Storage 重新物化。
- [x] 建立受控结果读写 RPC：Supervisor 只通过强类型参数检索和确认 Proposal，禁止任意 SQL/字段写入；局部修订仅在用户确认后创建新的 accepted 结果版本。
- [x] 打通 Agent 本地真实 Supabase 生产基础：应用规范化与 Agent runtime migration，建立私有 `project-assets` Bucket，按项目/工作区/图纸保存原始 PDF 与页面图片，接入持久 Run/Event/Artifact/Proposal/Checkpoint/SourceDocument repository 和跨进程租约队列；真实冒烟覆盖 checksum、RLS、签名 URL、并发事件序号、乐观锁与 1000 起线号分配。
- [x] 按 Supervisor Agent 串联方案 V2 完成离线实现：Profile Detection 内部工具、`is_cross_page` 三态纠错、受控结果查询/版本提交、accepted-feedback Improvement、用户授权后 Profile 候选构建，以及全链路 Fake 测试；Supabase adapter 已在后续任务完成，Web/Server 集成仍待建设。
- [x] 定义并新增规范化线表 migration：项目/工作区/图纸/结果版本、端子排线号单元、端子连接明细、证据、RLS、索引与扁平检索视图；旧 `wiring_tables` 保持不变。
- [x] 完成 Agent M8 离线控制面基础：Run/Worker、阶段 Artifact/Event、ResultProposal、取消/恢复和 SSE。
- [x] 完成 Agent M9-M10 离线基础：Supervisor Graph、事件消息映射、受控工具与局部 Correction Workflow。
- [x] 完成 Agent M11-M14 离线基础：反馈归因、Profile 沙箱候选、离线评测、人工发布门禁、canary 和回滚状态机。
- [x] 盘点 M15/M16 前置条件并记录阻塞：ABB 资产仍混有 ZH 规则；Agent 生产持久化已完成，但 `apps/api` 与 Web 事件代理尚未形成可用链路。
- [x] 记录原始产品需求。
- [x] 给出目标 monorepo、数据库、前端和 Agent 架构。
- [x] 建立开发规范和文档维护机制。
- [x] 在 `apps/web` 初始化 React + Vite + TypeScript 静态前端。
- [x] 实现登录页、项目工作台三栏布局和初始静态 AI 会话原型。
- [x] 实现 `apis/assets/components/directives/hooks/layout/router/stores/views` 分层。
- [x] 实现项目、工作区、图纸树及线表 Mock 数据契约。
- [x] 通过类型检查、ESLint、生产构建与桌面浏览器交互验收。
- [x] 在 `docs/apps/web` 归档前端架构和阶段记录。
- [x] 实现图纸库/规则库、跨页终点定位、Supervisor Mock 事件流与自然语言修复入口。
- [x] 使用 Playwright 验证 PDF 三阶段、带答案直接修订、Stage 2/Stage 3 路由、规则候选和桌面/窄屏布局。
- [x] 收紧 Mock Supervisor 触发和拆分页时序：初始无 Agent 过程，模拟关闭时仅登记 PDF，Stage 1 完成后才出现工作区/图纸，Agent 依序显示运行等待和完成勾选。
- [x] 将图纸库/规则库移动到项目顶部导航，将重新处理改为 PDF 上传，并将修复入口改为自然语言与显式模拟开关。
- [x] 规划 Agent 与业务 Server 独立部署及 `8100` 内部端口。
- [x] 设计 Supervisor、Profile Detection、Extraction、Correction、Improvement 协作架构。
- [x] 设计 Server-Agent run/event/proposal 契约和数据所有权。
- [x] 设计连接、图纸、工作区级局部重提取与字段级 diff。
- [x] 设计 Agent Harness、问题归因、离线评测和 Profile 发布门禁。
- [x] Agent 服务可在 `8100` 独立启动，并提供 live/ready/Profile 查询接口。
- [x] Agent M0-M3 的 20 个默认测试、严格类型检查和 Ruff 验收通过。
- [x] 实现 M4 首页 Profile Router、人工确认、动态 ProfileBinding 和公开规则接口。
- [x] M4 的 27 个默认测试、真实 PDF 首页渲染、严格类型检查和 Ruff 验收通过。
