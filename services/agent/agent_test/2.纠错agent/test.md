# 纠错 Agent 人工验收

> 按用户最新要求，本目录已新增第一个纯 HTTP 终端脚本 `run_acceptance.py`，复用已上传的 test0，以混合输入验收到“规则无问题／必要时拒绝候选”。详见 [README](./README.md)。第二个规则问题脚本待用户构造问题后再写，本轮未创建。Swagger 手工验收仍可使用。

> 当前代码基础已实现；真实包模式须先应用 `20261011010000`、发布 bootstrap 包并启用 `AGENT_PROFILE_PACKAGES_ENABLED=true`。部署命令和未实现的故障恢复边界见[实施记录](../../../../docs/service/agent/changelog/2026-10-11-correction-packages-implementation.md)。

## 验收目标

验证主 Agent 是否能够：

1. 接收用户的纠错信息并给出清晰计划；
2. 将一条消息拆成直接修订、同页重识别、跨页重识别批次；
3. 统一按 **Stage 2 → Stage 3** 处理跨页重识别；
4. 在每个阶段执行时发送事件反馈，结果先持久化再报告完成；
5. 生成字段级 proposal，等待用户确认后原位更新当前连接，ID/线号不变，revision 递增；
6. 读取图纸、阶段产物、模型 Trace 和 Profile 资源包，判断问题属于模型感知/幻觉还是规则问题；
7. 规则问题先向用户展示修改建议，只有确认后才创建 Profile 候选，不能直接修改生产规则。

## 前置数据与隔离要求

使用阶段 1 已完成的 test0 项目和结果版本作为 baseline（当前验收记录中的项目为 `3d66b325-bfe1-5227-9d95-0f22260fd0b0`）。

1. 备份目标行的原值，使用专门的 test0 测试项目；不改 `wiring_connection_rows` 视图。
2. 人工注错只修改当前最新代次中的连接，不修改历史旧行；纠错确认后应覆盖这同一条连接。
3. 每条注错记录写入 `origin=manual_injected_test_error`，保留 before/after、操作者和时间。
4. 记录 `agent_run_id`、`result_version_id`、Profile key/version/checksum，确保后续 Improvement 能复现同一资源包。
5. 人工注错只验证纠错链路，不能据此断言原始模型产生了幻觉；归因结果必须显示该限制。

## 对话方式

使用已有接口：

- `POST /v1/supervisor/turns`，或
- `POST /v1/supervisor/turns/stream`。

沿用阶段 0/1 的会话和用户鉴权环境变量，不创建新的 `run_acceptance.py`。每轮保存请求、事件、proposal ID 和响应；用户确认使用下一轮 Supervisor 输入完成。

## 手工案例

### A：直接给出正确答案

示例意图：指出项目/工作区/线号或端子，明确给出某字段的正确值。

期望：Supervisor 检索唯一 connection，生成最小字段 patch；不调用 Stage 2/3；返回 before/after 并等待用户确认。

### B：同页重新识别

示例意图：指出某连接字段错误，但不提供答案，要求重新识别；该记录 `is_cross_page=same_page`。

期望：发送“Stage 2 正在执行”事件，读取目标页和 frozen Profile，生成 Stage 2 artifact 与 proposal；不调用 Stage 3。

### C：跨页重新识别

示例意图：指出跨页连接错误，要求重新识别；该记录 `is_cross_page=cross_page`。

期望：先发送 Stage 2 事件并确认起点/跨页任务，再执行 Build Tasks 和 Stage 3；Stage 3 只处理指定任务，结果写入 artifact 后生成 proposal。

### D：混合输入

一条消息同时包含：一条直接答案、一条同页重识别、一条跨页重识别。

期望：得到三个结构化 item，确定性拆为 direct patch、Stage 2、Stage 2→Stage 3 三个批次；按固定顺序串行执行，事件和 proposal 不互相覆盖。

### E：多个同类目标

一条消息包含多个线号/端子，且都要求同页或跨页重识别。

期望：同类 item 可在一个 batch 中执行，但每项有稳定 connection ID、独立 artifact 和字段级 diff；检索歧义时暂停并追问。

### F：拒绝规则候选

Improvement 返回规则问题和 Profile 修改建议后，用户拒绝创建候选。

期望：保留诊断和审计，不上传 candidate 包、不改变 active Profile。

### G：确认规则候选

用户确认创建规则候选。

期望：ProfilePatchBuilder 在沙箱生成完整资源包候选，执行 manifest/checksum/schema 和固定回归，记录 candidate/review/audit；即使通过，也等待人工发布门禁，不自动 active。

## 检查清单

- [ ] Supervisor 能解析并展示纠错计划，目标不明确时会追问。
- [ ] `direct_patch` 不调用 VLM；`same_page` 只走 Stage 2；`cross_page` 统一走 Stage 2→Stage 3。
- [ ] 每个阶段先写 `agent_artifacts`/`agent_traces`，再发 completed 事件。
- [ ] proposal 含 before/after、证据、阶段 artifact IDs、Profile checksum 和 base version。
- [ ] 未确认前当前值不变；确认后同一 connection ID 值更新，result_version_id/线号不变，revision/record_version 增加。
- [ ] 连接、端子排、证据和结果版本行数不因局部修订增加；feedback 保存 before/after，重复确认不重复写入。
- [ ] Improvement 能读取目标图片、阶段产物、Trace、Prompt、Few-shot、expected JSON 和规则包。
- [ ] 诊断分类、证据、受影响文件和修改建议结构化返回，并保留 `feedback_origin`。
- [ ] 规则建议被拒绝时无候选；确认时只创建候选，不直接修改生产包。
- [ ] 重复请求返回原 proposal/receipt；服务恢复后能继续未完成 batch。
- [ ] 过期 base version、权限错误、目标歧义、资源包 checksum 错误和阶段失败均阻断写入并返回稳定错误。

## 结果记录格式

每个案例在本文件下方或对应运行目录记录：

```text
case: A/B/C/D/E/F/G
session_id:
agent_run_id:
base_result_version_id:
new_result_version_id:
profile_package: zh@<version> sha256:<checksum>
expected_batches: direct_patch / stage2 / stage2_stage3
observed_events:
proposal_ids:
diagnosis_category:
candidate_package_id:
status: PASS | FAIL | BLOCKED
notes:
```
