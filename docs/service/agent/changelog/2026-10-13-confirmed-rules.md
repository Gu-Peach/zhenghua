# 规则归因确认后直接发布

用户明确取消评测阶段，当前归因建议→一次确认→Profile Patch→启用 Bucket 新版本，无需再次审核/发布。取消模型评测不取消三阶段提取与线表确定性校验。

## 实现

- `ImprovementRunExecutor` 发布后 SUCCEEDED；未确认/拒绝不构建生效包。确定性 candidate ID、持久 pending 包、发布产物及同候选重试，避免重新调用 Patch 模型。
- `ImprovementWorkflow.publish_confirmed` 校验包、manifest、路径、routing schema 后直接启用。Supabase 新 migration `20261013000000` 的 service-role-only RPC 原子更新候选/包/审核审计；核验来源用户及项目权限、全部反馈和冻结 Profile、包 checksum、最新 active 基线。不伪造 gate_passed。
- Supervisor 上下文包含 pending/已启用包；旧 NEEDS_REVIEW 候选直接确认，不误走 WAITING_INPUT 恢复；重复确认幂等。旧改进 run 的终态/事件补齐。
- 新内部 API `/v1/profile-candidates/{id}/confirm` 请求 `reviewer_id, confirmed`，返回 ProfileCandidate。鉴权及权限失败不发布；请求无明确确认被拒绝。`/evaluations` 返回 410；旧评测 Worker/模型/历史审核接口仅兼容已入队任务，不主动取消。
- Web 显示确认将直接修改规则、成功后“规则修改已生效”；终端 `run_rule_release.py` 只展示候选和确认，不再要求评测/模型开关；HTTP 错误正文保存，便于诊断。

## 验证与部署

- Agent 默认套件 182 passed / 12 skipped（显式真实 Supabase 场景默认跳过），相关 Fake Supervisor/Worker/HTTP/终端及授权回归通过；164 源文件 strict mypy、修改文件 Ruff 通过。旧评测缓存单测补固定时钟，避免微秒级 Mock 耗时触发随机延迟比门禁。
- Web typecheck/lint/build，18 项 Playwright HTTP fixture 测试通过，含一次确认发布文案、桌面/窄屏截图，以及既有登录/空/加载/失败/权限/长文本回归。
- 28 份 migration 空库及合成旧数据重放通过；合成规则测试核验拒绝未确认/非来源用户/非服务调用/基线变动，审计失败回滚、原子启用、重复确认唯一审计与旧包保留。
- 新 RPC 已在本地 Supabase 应用并登记；实际 test0 包/结果未修改，当前任务与服务未停止，未调用真实模型。真实 HTTP 发布仍待用户重载后确认，不宣称准确率已验收。

## 风险

确认不等于准确率无回归。旧项目仍绑定旧 checksum；新任务读取最新 active。Bucket 对象保持不可变，不覆盖本地生产 Prompt 文件。非提取 protocol-1 任务跨进程自动接管仍是既有缺口；不要在运行中重启，失败后显式恢复，同一轮复用已存包。
