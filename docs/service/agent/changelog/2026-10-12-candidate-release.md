# 规则候选评测、人工审核与资源包发布

日期：2026-10-12。代码实现完成，真实模型评测和真实审核/发布验收尚未执行。

新增 `application/candidate_evaluation.py` 和 `candidate_release.py`，在 main 注册 PROFILE_EVALUATION Worker 与服务端发布服务。复用既有候选、评测、artifact、审计和私有资源包表；没有新增 migration，没有修改 test0 线表、Profile 指针或资源包状态，没有停止服务。

基线不可变包提供固定集；当前 ZH 有 2 个分类、4 个 Stage 2（含空结果负例）和 1 个跨页案例。accepted feedback 补目标集，当前候选共 9 案例。基线/候选同图、同 expected；关闭 few-shot 防止答案泄漏，目标输入仅保留起点身份、清理 raw_payload/正确终点/诊断文字，跨页目标仍实际运行 Stage 2→3。

评测逐案例存 `agent_artifacts.payload`，汇总存 `evaluation_reports.payload`。恢复跳过完成案例，逐项 schema 错误阻断 gate，临时模型失败交给 Worker/resume。报告绑定候选包、基线和案例摘要。ReleaseGate 复算字段指标，要求目标全过、保护集不退化、负例不幻觉、schema 全过和耗时门限；费用未知明确标记。EvaluationJudge 提供建议、风险和回归摘要，不能越过确定性门禁或替代人工审核。

HTTP 新增 `/evaluations`、`/publish`；`/approve` 增加 evaluation_run_id 和显式确认。旧外部报告/客户端 canary 计数不再充当发布证据。审核和发布都检查 Worker receipt、用户来源、候选 checksum、实际案例与 audit。审核仅到 CANARY；单独确认发布才激活 Bucket 包并刷新 registry。旧项目冻结绑定保留。部分发布失败可重复同一 `/publish` 补齐，不用重新生成候选或纠错。

`run_rule_release.py` 是纯 HTTP 终端入口，支持已有 eval run 接续、模型公开结构化输出、逐案例和最终报告展示、审核/发布两次输入确认及拒绝退出；不导入 Agent 工具，也不直接操作数据库。`verify_candidate_inputs.py` 提供只读资源和案例预检。

验证：49 项相关离线测试通过，覆盖原生三阶段 Fake Gateway、目标 Stage 2→3、答案隔离、恢复去重、receipt、审核/发布拒绝、发布失败补齐、基线变化、内部 token 和 OpenAPI 必填字段。160 源文件 strict mypy、Ruff 检查通过。实际候选只读预检成功：9 个案例，模型调用 0，数据库写入 0。

此前全量测试有六项遗留 fixture 假设与用户现有 Profile 配置不符（ABB 已使用 zh_native，新增 zh-wrong）；本轮没有回退用户 Profile 或改写这些无关测试。真实固定集通过率、成本和发布/回滚效果仍需人工运行验收。protocol 1 自动 RUNNING 接管、多发布者数据库 CAS 和真实流量 canary 未在本轮实现；详见 [实施计划/契约](../candidate-release-plan.md)。
