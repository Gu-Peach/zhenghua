# 规则包新建、删除和自动注册

用户在规则库选择一个已发布包作为模板，填写新 key、名称、识别说明与特征，可修改三个阶段 Prompt。图片 Few-shot、expected JSON、Schema 和确定性 adapter 继承模板；这是已有图纸算法的独立配置，不代表自动支持新的图纸算法。必须使用尚未占用的新 key；不能借此替换现有生产规则或绕过 AI 候选回归/审核门禁。

## 公共契约与存储

- `POST /api/v1/rule-library`：base_package_id、profile_key、display_name、description、detection_summary、strong_signals、可选 prompts、confirmed=true。Server 从 JWT 获取创建者，不接受客户端 user_id。
- `DELETE /api/v1/rule-library/{id}?confirmed=true`：仅创建者可执行。停用并隐藏该版本，保留私有 Bucket 与元数据供冻结 Profile 的历史项目/纠错使用。删除不是清空历史资源，key 不复用。
- 复用 `profile_resource_packages` 和 `agent-profile-assets`，无 Schema 变更。新包 1.0.0、自包含、checksum 封存；克隆入口采用由 key 决定的独立元数据 ID，避免并发创建不同包时覆盖。相同所有者/内容重发复用既有包；不同内容返回冲突。
- Agent 内部 `/v1/profiles/packages` 完成模板读取、校验、上传、显式人工创建发布与注册；Server 只桥接已鉴权身份。创建成功前必须完成注册；若发布后注册失败，同请求可幂等补齐。
- 删除对应 `status=retired`，原 `resolve(ProfileRef)` 继续允许精确 checksum 历史读取；新任务 Registry 仅使用数据库 active 集合。注册更新一次性替换，不能逐项暴露半成品。
- API Profile 查询、新任务入口和检测调用前刷新 active 元数据，其他进程无需重启即可获取新包/停用状态；文件下载仅在集合发生变化时执行。运行中的冻结绑定不切换版本。

## 执行步骤

1. **完成**：Agent 包生命周期和 Registry 同步，Server DTO/权限/桥接。
2. **完成**：Web 新建表单、删除确认、错误/加载状态与列表更新；OpenAPI 快照已导出，受依赖读取权限限制，客户端类型手动同步并通过应用 strict 类型检查。
3. **完成离线验证**：44 项 Agent/Server 回归、7 项 HTTP 夹具浏览器测试通过，桌面/窄屏截图已检查。lint、production build 和自动类型生成受本机 node_modules 读取权限限制未完成；真实数据库写入和模型准确率由用户后续验收。详见[实施记录](./changelog/2026-10-12-rule-package-lifecycle.md)。

新包继承模板的正例/负例/跨页样例并校验路径与预期 JSON；用户改写 Prompt 的实际提取准确率不由创建成功保证。Storage 不主动删除，以避免历史项目断链；未完成上传的孤立对象仍遵循已有包的保留策略。
