# 候选评测 Stage 2 起点定位修复

日期：2026-10-12。范围：候选目标评测的输入组装；不改数据库、Profile 包、Supervisor、Stage 2/3 通用实现或发布门禁。

## 原因与修改

`CandidateEvaluationExecutor._dataset()` 原先用泛化文本替换目标请求的 `page_context`，删除原记录答案时也丢掉了给模型的起点定位信息。起点虽保留在内部 `current_records`，只用于输出后的严格匹配，没有传给 Stage 2。

现在评测应用层组装 JSON：任务说明和 `target_connection`，仅包含连接 ID、`start` / `start_*` 起点身份。提示仅按指定起点读取实际线路，同页终点或跨页引用须从图中读取，不得以其他端子代替目标。原上下文、正确终点、原记录终点、raw payload 和备注不复制到该定位对象；expected 仍只在评测器中比较。

该上下文沿原链路经 `ScopedExtractionRunner` 包装，由 Stage 2 模型 adapter 拼入最后一条多模态 user 消息。起点匹配、Stage 3 起点保护、固定案例、关闭评测 Few-shot 与结果/规则写入边界不变。

改动文件：

- `services/agent/src/agent_service/application/candidate_evaluation.py`
- `services/agent/tests/unit/test_candidate_evaluation_release.py`

## 验证

先加回归，4 种组合均复现旧输入缺少起点的问题；修复后通过。覆盖同页/跨页、扁平 `XD3:113` / 嵌套 `XD3` + `114` 身份，核对阶段请求和 Fake Gateway 收到的最终消息：有定位与图像，无正确/错误终点答案，跨页继续 Stage 2→Stage 3。

相关四个测试文件运行结果：32 通过、1 失败。失败是既有 `test_experimental_abb_cannot_fall_through_to_zh_adapter` 期待 `native_pending`，当前 Profile 已使用 `abb_native`；本次未改 ABB 或该测试。排除该项后 32 通过。修改文件 Ruff 通过，161 源文件 strict mypy 通过。

未调用真实模型、未查询/写入数据库、未启动/停止运行服务，也未审批或发布规则。离线通过不证明真实图纸识别准确率。

## 生效与剩余边界

服务需用户重载代码；仅新构建评测数据集携带定位上下文。旧 run 的冻结数据集、失败逐项缓存和完成报告不改，`/resume` 不会使已缓存的失败项重新识别。`CandidateReleaseService.start()` 仍限制 draft/evaluating，且按候选 checksum 幂等创建 run；因此既有 rejected 候选的新一轮评测入口仍需另行实现，不能直接重复旧请求来验证本次修复。
