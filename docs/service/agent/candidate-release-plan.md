# 候选评测、审核与发布实施计划

日期：2026-10-12。复用既有候选/评测/运行/产物/资源包表，不新增 migration。

1. 已完成：新增 PROFILE_EVALUATION Worker。冻结基线资源包 checksum 与固定案例人工 expected，加入候选 source_feedback_ids 对应目标案例。基线/候选都以同一输入执行，不读候选修改后的 expected，不在模型输入中提供答案；评测时关闭图片 Few-shot，避免把测试样例答案直接喂回模型。
2. 已完成：逐案例/variant 存产物，汇总字段级比较与耗时。失败/缺项不能作为通过；报告与候选包 checksum 绑定，防止混版本。服务端校验 TARGET/PROTECTED/NEGATIVE、阶段覆盖与实际结果，拒绝空报告/客户端伪造统计。
3. 已完成：明确人工审核和发布两次确认。通过服务端评测门禁方可进入 CANARY；独立发布确认方可将对应不可变 Bucket 包变为 active，更新内存 registry。保留旧回滚入口与旧项目 Profile 绑定，不覆盖生产 ZH、不改已完成 test0 的 Profile。
4. 已完成：纯 HTTP 终端脚本从现有 candidate_id 接续；只输入/展示/调用 API，不在脚本运行数据库、文件编辑或 Agent 工具。默认 Fake 回归；真实评测需环境变量和 HTTP 明确授权，不在本次开发中自动运行/审批/发布。

现有外部报告/客户端 canary 计数入口不能作为新发布凭据。正式链路必须引用服务端持久评测产物。同一轮的逐项恢复不代表已实现 protocol 1 Worker 的自动跨进程租约接管，失败任务仍显式 resume。

实现及验证记录见 [2026-10-12 交付记录](./changelog/2026-10-12-candidate-release.md)，启动入口见 [纠错验收说明](../../../services/agent/agent_test/2.纠错agent/README.md)。真实评测及人工发布验收待用户执行。

## 数据和接口契约

- `agent_runs`：PROFILE_EVALUATION，options 保存 `profile_candidate_id` 和 `real_evaluation_authorized`。不重新提交原纠错结果。
- `agent_artifacts.payload`：`evaluation-dataset` 冻结案例和图片位置；`evaluation:{variant}:{case_id}` 保存逐案例结果；`evaluation-report` 保存报告、EvaluationJudge 建议和确定性 gate。产物写完才发布 completed 事件。
- `evaluation_reports.payload`：原有 EvalReport 增加候选 checksum、基线 Profile、dataset checksum、阶段覆盖和 `cost_reported`。供应商费用未上报时保持 false，0 不是“免费”的结论。
- `profile_candidates` / `profile_candidate_audit`：DRAFT→EVALUATING→APPROVED→CANARY→ACTIVE；未通过 gate→REJECTED。这里 CANARY 是审核后待发布状态，不代表已观测生产流量。
- `profile_resource_packages` / 私有 `agent-profile-assets`：只发布原先已上传且 checksum 校验通过的不可变包，通过既有 RPC 切换 active；旧包 retired 后仍可按冻结 checksum 读取。

| 接口 | 输入和行为 |
| --- | --- |
| `POST /v1/profile-candidates/{id}/evaluations` | `reviewer_id, allow_real_model=true`；还要求服务 `AGENT_ALLOW_REAL_EVALUATION=true`，按候选 checksum 幂等创建队列任务 |
| `POST /v1/profile-candidates/{id}/approve` | `reviewer_id, evaluation_run_id, confirmed=true`；核验来源用户、冻结案例、真实 Worker 产物与 gate，记录人工审核 |
| `POST /v1/profile-candidates/{id}/publish` | 同上，独立发布确认；再次核验 receipt 和审核人，拒绝基线已变化，发布并刷新当前进程 registry |
| 旧 `/evaluate`、`/canary-assessment` | 返回 409；客户端报告或计数不作为发布凭据 |

Domain 契约版本升至 4，并更新 schema checksum；HTTP OpenAPI 测试验证审核必填 `evaluation_run_id`。当前 Web/Server 尚无这些发布端点的专用 Client，入口是纯 HTTP 终端脚本。

## 故障和范围

暂时性模型/网络失败保留已提交案例，显式 `/resume` 后只补未完成项；无法校验的输出保存失败结果，不能过门禁。发布不是跨表单事务：candidate 可能已 ACTIVE 但包 RPC 失败，此时同一 receipt 重试 `/publish` 补齐；判断实际发布以资源包 active 和发布响应为准。基线版本检查在应用层，当前串行使用场景适用，多发布者并发的数据库 CAS 不在本轮实现范围。

评测复用现有三阶段 adapter；目标案例同页跑 Stage 2、跨页跑 Stage 2→3，不写线表。固定案例必须三阶段/正例/负例齐全，后续新增 Profile 缺少固定集时阻断发布。默认测试使用 Fake Model；开发中未调用真实模型，也未批准或发布候选。
