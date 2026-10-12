# 规则包新建、删除与 Agent 自动注册

规则库新增模板克隆表单和创建者删除入口。新建成功时，完整资源包已经上传、发布并注册到 Agent；删除停用元数据并移出新任务候选，保留历史项目的精确 checksum 资源。本轮不新增表或 migration，不改 test0，不调用真实模型，不停止服务。

## 创建和删除约定

- 业务 `POST /api/v1/rule-library` 接收 `base_package_id`、新的 `profile_key`、`display_name`、`description`、`detection_summary`、`strong_signals`、可选三阶段 `prompts` 和 `confirmed=true`。JWT 提供用户身份，不能传入其他 user_id。
- 模板必须 active，继承经过包校验的真实图片 Few-shot、expected JSON、Schema 和 adapter；当前仅支持 `zh_native`。这是已实现算法的新配置，不能自动适配新的厂商算法。新包版本为 1.0.0。
- 人工创建使用由 key 决定的独立元数据 ID。相同所有者/内容重发复用既有包，不同所有者/内容返回冲突。已有 key 和停用 key 不复用，不通过此入口更新生产版本。
- `DELETE /api/v1/rule-library/{package_id}?confirmed=true` 只允许创建者删除 active/retired 包。候选继续通过候选审核处理。删除后状态 retired，库列表和新任务不再选择，私有 Bucket 对象和元数据保留。
- AI 候选仍走固定案例评测、人工审核、发布门禁；人工新包需在 UI 明确确认。创建成功说明完整包可加载，不保证改写 Prompt 的真实准确率。

## 修改位置

- Agent：`application/profile_package_lifecycle.py` 负责完整包克隆/封存/发布/注册；`api/routes/profiles.py` 提供内部生命周期接口；`main.py` 注入服务。
- Agent：`infrastructure/supabase_profile_packages.py` 负责不可变上传、远端 active 集合指纹与缓存；`profiles/registry.py` 原子替换 active 集合并停用旧快照。缺少可选版本稳定返回 ProfileRegistryError，避免对空集合调用 max。
- Agent：`api/dependencies.py`、imports/runs/supervisor 路由与 `tools/profile_detection.py` 在新命令/检测前同步，API 和独立 Worker 可看见新包；运行中冻结绑定不切换。
- Server：`rule_library.py`、`models.py`、`agent_bridge.py`、`workbench.py` 完成鉴权、模板可见性、创建者权限、稳定错误与列表标志；`apps/api/src/main.py` 提供公开路由。
- Web：`RulePackageCreator.tsx`、`LibraryPanel.tsx`、`ProjectView.tsx`、`apis/projects.ts`、`apis/types.ts` 和 CSS，提供模板加载/重试、长 Prompt、确认、冲突重试、删除确认与列表刷新。
- 契约：`apps/api/openapi.json` 已重新导出；`apps/web/src/apis/generated.ts` 手动同步新增路径、DTO 和标志，原因见下面的验证限制。

## 验证

- 44 项相关 Agent/Server 测试通过（17 项注册/路由/检测/包生命周期，27 项 Server HTTP）。包测试使用实际模板封存/校验和 HTTP Storage/RPC 夹具，覆盖新包进入首页路由候选、幂等、冲突、越权、注册失败重试、其他 Registry 刷新、停用及冷缓存历史读取、损坏刷新原子性；不访问真实 Supabase。
- 修正旧 Registry/Router 测试对本地目录数量、ABB 状态/版本的固定假设。experimental 场景在测试中明确设置状态，不修改用户 Profile 文件。
- 7 项 Playwright HTTP 夹具测试通过，包括模板加载失败/重试、无模板、冲突、Prompt 输入、确认、删除取消/接受和只读包权限。桌面/窄屏截图已检查，存放忽略的 `.runtime/web-tests/`。
- 前端应用 strict 类型检查通过：在 `apps/web` 执行 `node ../../node_modules/.pnpm/typescript@5.9.3/node_modules/typescript/bin/tsc --noEmit -p tsconfig.app.json`。相关 Python Ruff 和 5 个 Agent 核心改动文件 strict mypy 通过。
- Web lint、production build 和 OpenAPI 自动生成未完成：node_modules 的 debug/yargs-parser/tinyglobby/Node 类型等读取被 EPERM 拒绝；离线 install 未修复。本地生成命令的提权请求被自动审批服务拒绝，返回审核服务模型权限 HTTP 403，命令未执行。类型暂按已导出的 OpenAPI 手动同步，权限修复后重新生成和检查。
- 未验证本次功能的真实数据库创建/停用、真实 VLM 路由准确率或三阶段质量；浏览器测试使用夹具，不能称为线上全链路验收。

## 用户验收

用户在空闲时重载 Server 和 Agent 加载本轮代码，保持 `AGENT_PROFILE_PACKAGES_ENABLED=true`；Web 开发模式刷新页面。进入规则库 → 新建规则包 → 选已发布模板 → 填写新的 key/识别信息 → 确认创建。成功后新包出现在库和 Agent 候选中。创建者确认删除后刷新列表消失，原项目仍可以查看历史规则。资源包变动本身不需要服务重启。

无需 migration；使用现有 `profile_resource_packages`、`agent-profile-assets` 和 `publish_profile_package`。本轮没有修改用户运行中的进程或任务。
