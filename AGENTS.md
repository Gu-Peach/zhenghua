# AGENTS.md

本文件约束本仓库中的人工开发者与编码 Agent。除非用户明确要求偏离，否则所有改动都应遵守本文。

## 1. 开工前

按顺序阅读：

1. `docs/README.md`
2. `docs/frontend.md`
3. `docs/refactor-plan.md`
4. `docs/roadmap.md`
5. `docs/TODO.md`

然后阅读与任务直接相关的代码、测试、数据库迁移和 Prompt。不要仅根据旧 README 或聊天记录推断当前实现。

开始实现前：

- 检查工作区已有改动，不覆盖用户未提交内容；
- 把本次明确可交付事项加入 `docs/TODO.md` 的“进行中”；
- 大范围任务先写执行计划，并保证同一时间只有一个步骤处于进行中；
- 需要改变架构、数据含义或公共契约时，先更新设计文档或新增 ADR。

## 2. 总体原则

- 使用渐进迁移，不在新链路通过验收前删除旧 Vite、旧 API 或旧表。
- 数据库是业务事实来源；JSON、XLSX 和本地任务文件是产物或诊断信息。
- 前端、API、Agent Worker、图纸 Profile 和基础设施保持清晰边界。
- 复用现有稳定代码，通过适配器迁移；不要为了目录整齐重写已验证算法。
- 结构化数据使用 Pydantic、SQL 和 JSON Schema 等结构化工具，不使用脆弱的字符串拼接。
- 只改任务需要的文件，不顺手做无关重构。

## 3. 目标目录边界

重构目标以 `docs/refactor-plan.md` 为准：

- `apps/web`：React + Vite + TypeScript，负责页面、路由、交互和前端数据适配。
- `apps/api`：FastAPI，负责鉴权、领域 API、事务和任务编排。
- `services/agent`：独立 Agent API/Worker、LangGraph、Harness、checkpoint、Profile 和阶段事件，默认端口 `8100`。
- `services/server`：可复用的 Python 领域服务、repository 和基础设施适配器。
- `packages/ui`：无业务依赖的共享 UI。
- `packages/api-client`：由 OpenAPI 生成的 TypeScript Client。
- `services/agent/profiles/<profile>`：模板专属 Prompt、Few-shot、规则和回归案例。
- `infra/supabase`：数据库迁移、RLS 和种子数据。

迁移期间允许旧 `frontend/`、`backend/` 和 `supabase/` 共存。新模块不得反向依赖旧前端。

## 4. 前端规范

- 使用 React + Vite + TypeScript strict mode。
- `src` 按 `apis/assets/components/directives/hooks/layout/router/stores/views` 分层；路由页面归 `views`，可复用业务界面归 `components`。
- `apis` 统一维护接口函数、请求 Client 和 DTO；`views/components` 不得散落请求 URL 或后端字段转换。
- `router` 只定义路由和守卫，`stores` 只保存跨页面状态，局部状态优先留在组件或 hook。
- 服务端数据使用统一 API Client；禁止在组件内散落 `fetch` URL 和数据转换逻辑。
- 不在浏览器中使用 Supabase service-role key。
- 登录状态由 Supabase Auth 管理；页面路由保护和 FastAPI JWT 校验必须同时存在。
- 项目工作台遵循 Header + 左侧项目树 + 中间结果区 + 右侧 AI 栏布局。
- 右侧 AI 在未接入真实能力前保持静态，不伪造可用回复。
- 大表格采用服务端分页或虚拟化，固定表头，状态和来源可访问。
- 使用 Lucide 图标；图标按钮必须有可访问名称或 tooltip。
- 页面文案使用中文，代码标识符使用英文。
- 不创建营销式首页、装饰性大卡片、渐变背景或无业务价值动画。

前端改动至少验证：

- TypeScript 类型检查；
- lint；
- production build；
- 登录页和项目工作台的桌面/窄屏截图；
- 空、加载、失败、无权限和长文本状态。

## 5. API 与 Python 规范

- 路由层只处理 HTTP、鉴权和 DTO 转换，业务逻辑放 application service。
- Pydantic 模型用于所有外部输入、输出和 VLM 结构化响应。
- 数据访问通过 repository/adapter，不在路由或 Graph 节点中直接拼 SQL。
- I/O 路径使用 async；CPU 密集和长任务进入 Worker。
- 不使用 FastAPI `BackgroundTasks` 承担生产级小时任务。
- 错误响应使用稳定错误码和安全消息，详细异常进入结构化日志。
- API 变更后重新生成或校验 OpenAPI Client，禁止仅修改一侧类型。
- 新增公共函数必须有类型注解；复杂边界需有简短 docstring。

## 6. 数据库与 Storage

- Schema 变更只能通过新 migration，禁止修改已应用迁移来伪造历史。
- Migration 应可重复审阅，尽可能提供回滚或明确不可逆原因。
- 新表必须评估主键、外键、唯一约束、查询索引、RLS 和 `updated_at`。
- 所有项目数据必须带所有者或成员权限路径，并有越权测试。
- 核心线表字段使用可查询列；原始模型响应可额外保存在 JSONB。
- 同时保留 PDF 物理页号和图纸业务页号，命名必须明确。
- Storage 默认私有；浏览器使用签名 URL。
- 原始 PDF、页面图片、阶段产物和导出文件使用稳定、不可冲突的对象路径。
- 删除项目时先定义数据库和 Storage 的一致性策略，禁止只删一侧。

## 7. Agent 与 Profile

公共 Graph 负责稳定阶段：

```text
render -> detect profile -> classify -> page scan
       -> build cross-page tasks -> cross-page completion
       -> deterministic validation -> persist
```

模板差异必须进入 `DrawingProfile`：

- 禁止在公共节点中不断添加 `if vendor == "zh"` 或 `if vendor == "abb"`；
- ZH、ABB 的 Prompt、Few-shot、端子规则和引用解析互不复用，除非明确提取为公共规则；
- 三阶段 Few-shot 必须包含真实图片输入和经过人工确认的 expected JSON；
- Prompt、Few-shot manifest、Schema 和校验器需要版本号或 checksum；
- 无法确认的字段置空并标记 `needs_review`，禁止根据常识补造终点；
- Stage 3 只能处理任务指定连接，不能偷偷改写已确认的起点；
- 确定性规则负责白名单、方向、单位、去重和排序，不能把这些全部交给模型。
- 用户反馈后的在线局部重提取只能生成 ResultPatch proposal；业务 Server 执行版本校验并提交新结果。
- 自完善只能修改 Profile 沙箱；评测、人工审批和发布门禁通过前不得影响生产 Profile。

新增或修改 Profile 时必须：

1. 增加正例、负例和跨页案例；
2. 校验 manifest 中所有文件路径；
3. 运行该 Profile 固定回归集；
4. 对比字段级差异，不只比较记录条数；
5. 在 CHANGELOG 记录 Profile 版本变化。

## 8. 任务可靠性

- 任务节点以 `run_id + stage + item_id` 幂等。
- checkpoint 不得写入 `frontend/public` 或 Web 构建目录。
- 原子写入使用唯一临时文件；Windows 下替换需重试和锁，不能因保存诊断文件让整个 Agent 失败。
- 每阶段先持久化产物，再发出 completed 事件。
- 重试只覆盖暂时性错误；Schema 错误、权限错误和配置错误需分类处理。
- 断点恢复必须跳过已确认完成项，并保留失败项的历史错误。
- 任务取消在页循环和 VLM 调用批次边界检查。
- 所有阶段都记录耗时、重试、模型、Profile 版本、输入页和结果数。

## 9. 测试门槛

测试范围与风险匹配：

- 纯函数、归一化、引用解析：单元测试；
- API、repository、RLS：集成测试；
- Graph：使用 Fake VLM 的节点和断点测试；
- Profile：真实图片离线回归测试；
- 登录、项目树、进度、表格、导出：端到端测试；
- 数据迁移：在空库和带旧数据快照的数据库各执行一次。

默认测试不能调用付费 VLM。真实模型评测必须通过显式命令和环境开关执行，并输出模型、成本、耗时和案例摘要。

修复缺陷时先补能复现问题的测试。没有运行某类测试时，在交付说明中明确指出。

## 10. 用户反馈与规则发布

- 数据修订与规则建议是不同对象，不能混在一条自由文本中处理。
- 用户修订保存 before/after、操作者、时间和来源范围。
- 单次用户建议不能自动修改生产 Prompt 或校验器。
- 规则候选必须经过固定案例回归、人工审核和版本发布。
- 已完成项目保留其原 Profile 版本，除非用户明确发起重新处理。

## 11. 文档工作流

每次完成开发后：

1. 更新 `docs/TODO.md`，移除或勾选已完成项；
2. 更新 `docs/roadmap.md` 的阶段状态；
3. 行为、架构、Schema、API 或 Profile 变化写入 `docs/changelog/README.md`；
4. 新增环境变量、命令或部署步骤时更新对应 README；
5. 重大决策新增 ADR，并链接到重构方案。

模块实现记录按所有权归档：

- `apps/web` -> `docs/apps/web/`
- `apps/api` -> `docs/apps/api/`
- `services/agent` -> `docs/service/agent/`
- `services/server` -> `docs/service/server/`

模块目录至少保留一个 `README.md` 作为当前入口；阶段性交付记录放在其 `changelog/` 下。`docs/changelog/README.md` 只记录跨模块、架构或产品行为变化，模块内部细节写入对应归档。

不要把尚未实现的内容写成已完成。文档、代码、迁移和测试必须保持一致。

## 12. 安全与仓库卫生

- `.env`、密钥、JWT、service-role key 和真实用户数据不得提交。
- 测试 PDF/XLSX、运行结果、模型日志和本地 Storage 默认不提交。
- Prompt Few-shot 图片只有作为版本化测试资产时才允许提交。
- 不提交 `node_modules`、构建目录、缓存、checkpoint 或临时文件。
- 日志和异常中对 API key、Authorization header 和签名 URL 脱敏。
- 不执行破坏性 Git 或数据库命令，除非用户明确授权并已确认目标。

## 13. 完成定义

任务只有在以下条件满足时才算完成：

- 行为符合产品需求和模块边界；
- Schema/API/类型契约同步；
- 关键测试通过，或未运行项已说明；
- 空态、失败态、权限和重试路径已考虑；
- 文档、TODO 和 CHANGELOG 已更新；
- 没有泄漏密钥、提交生成物或破坏旧链路；
- 用户可以从交付说明中找到修改位置、验证方式和剩余风险。
