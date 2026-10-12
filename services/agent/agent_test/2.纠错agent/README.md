# 混合纠错终端验收：第一个脚本

已有候选无需再注错或重新执行纠错；接续评测/审核/发布使用下方 `run_rule_release.py`。

`run_acceptance.py` 验收直接答案＋同页重识别＋跨页重识别的混合输入；默认预期归因后规则无问题。规则问题可用既有 `--expect-rule-issue`，候选生成后再进入下方发布验收，不重复提交已经修正的数据。

## 从已有规则候选接续评测、审核和发布

服务需加载新代码。在启动服务/Worker 的终端设置（独立 Worker 时两个进程均设置）：

```powershell
$env:AGENT_PERSISTENCE_BACKEND="supabase"
$env:AGENT_PROFILE_PACKAGES_ENABLED="true"
$env:AGENT_ALLOW_REAL_EVALUATION="true"
$env:AGENT_INLINE_WORKER="true"
.\.venv\Scripts\python.exe -m uvicorn agent_service.main:app `
  --app-dir services/agent/src --host 127.0.0.1 --port 8100
```

另开终端，运行纯 HTTP 脚本。候选及用户 UUID 取现有任务值：

```powershell
$env:AGENT_ACCEPTANCE_ALLOW_REAL_MODEL="true"
$env:AGENT_ACCEPTANCE_USER_ID="<候选来源用户 UUID>"
# 如服务配置内部 token，此终端设置相同 AGENT_INTERNAL_TOKEN。
.\.venv\Scripts\python.exe "services/agent/agent_test/2.纠错agent/run_rule_release.py" `
  --candidate-id "<已有 candidate_id>" `
  --base-url "http://127.0.0.1:8100"
```

1. 输入“开始评测”：冻结基线/候选包以及同一套图片、人工 expected，分别实际运行三个阶段。当前 ZH 固定集 7 案例，另加 candidate 的已接受纠错目标；同页目标 Stage 2，跨页目标 Stage 2→3。不修改线表。
2. 终端持续显示模型公开结构化输出、逐案例 expected/actual、耗时和最终 gate/EvaluationJudge 报告，保存到忽略提交的 `runs/`。不展示模型私有推理链；费用未上报明确标记未知。
3. gate 未通过则停止发布。通过后阅读报告和候选 operations，输入“确认审核”进入 CANARY（已审核待发布）。其他输入/退出均不审核。
4. 单独输入“确认发布”：将这份候选不可变包设置 active 并刷新 registry；新任务使用新版本，旧项目继续冻结旧版本。不重绑 test0、不改本地生产 ZH。

中断后用同一命令追加 `--evaluation-run-id "<终端打印的评测 run UUID>"`，监看既有报告后继续人工步骤，不重新纠错。若评测 run FAILED 且错误可重试，先由用户显式恢复，再使用该参数：

```powershell
$headers = @{}
if ($env:AGENT_INTERNAL_TOKEN) { $headers.Authorization = "Bearer $env:AGENT_INTERNAL_TOKEN" }
Invoke-RestMethod -Method Post -Headers $headers `
  -Uri "http://127.0.0.1:8100/v1/runs/<评测 run UUID>/resume"
```

如果 `/publish` 网络失败，先查 candidate audit 和资源包 active；候选可能已 ACTIVE 而包发布尚未成功。可引用同一 evaluation_run_id 再确认发布来补齐，不重新生成候选。旧 `/evaluate` 客户端提交报告及 `/canary-assessment` 计数接口现返回 409。

完整接口/限制见 [候选发布契约](../../../../docs/service/agent/candidate-release-plan.md)。内部 HTTP 使用服务 token；`reviewer_id` 是已认证业务调用者传入的用户标识，不等同用户 JWT。发布前真实评测仍需人工验收。

脚本仅调用 Agent HTTP 接口和读取输入文件，不导入 Agent/Graph/tool，不访问 Supabase、不读取服务端 `.env`、不注入错误、不选择 Stage 执行路径、不伪造记忆或判断结果。目标定位、批次拆分、识别、落库和归因均由服务执行。

## 前置与启动

使用已有 test0 项目，不重传 PDF。先手工在当前结果的目标行注错，保留原值及人工预期；可在 raw_payload 追加 `origin=manual_injected_test_error`。至少选择三类目标：明确答案、`same_page` 重识别、`cross_page` 重识别。跨页目标如果不在上传的 PDF 中，必须报告证据不足，不能当成功。

需要此前迁移已应用，尤其原位更新 `20261011020000`。让服务加载本轮模型输出接口；不要同时运行两个监听 8100 的服务：

```powershell
$env:AGENT_PERSISTENCE_BACKEND="supabase"
$env:AGENT_PROFILE_PACKAGES_ENABLED="true"
$env:AGENT_INLINE_WORKER="true"
.\.venv\Scripts\python.exe -m uvicorn agent_service.main:app `
  --app-dir services/agent/src --host 127.0.0.1 --port 8100
```

另开终端：

```powershell
$env:AGENT_ACCEPTANCE_ALLOW_REAL_MODEL="true"
$env:AGENT_ACCEPTANCE_USER_ID="<已有 Auth 用户 UUID>"
# 若服务配置内部 Token，在此终端也设置相同 AGENT_INTERNAL_TOKEN；不是 service-role key。
.\.venv\Scripts\python.exe "services/agent/agent_test/2.纠错agent/run_acceptance.py" `
  --project-id "<test0 项目 UUID>"
```

输入一条混合消息，例如（替换成真实目标，脚本不自动填答案）：

```text
工作区A第50页，线号1000、起点端子X1:1的终点端子改为2；第51页线号1001、起点端子X1:3请重新识别；第52页跨页连接线号1002、起点端子X2:1请重新识别。只修复这些连接，不重新提取整份PDF。
```

也可用 `--message "..."` 或 `--message-file "输入.txt"`。所有回答在同一 conversation 中发送，API 从自己的会话/任务状态恢复上下文。

## 人工交互和输出

若此前混合任务在 Stage 2 后因起点匹配失败，需先重载 API/Worker 的修复代码，再用新会话重跑。
原注错值未提交时不需再次注错；不要用旧 `--run-id` 重试，它仅监看，不能重算修复前的缓存提案。

1. Supervisor 的公开计划/路由理由通过 SSE 展示，显示原始结构化模型输出（不是内部推理链）。
2. 实时显示批次规划、阶段事件、Stage 2/3 结构化输出与校验；每阶段输出写库后再读取展示。direct patch 没有识别模型调用，不伪造输出。
3. 展示 proposal before/after，等用户输入“确认提交”。输入 `/quit` 不提交，也不自动取消后台任务。
4. 确认后通过业务 HTTP 查询当前结果，核对同 connection/unit ID、线号、代次、revision 和字段值；不使用 SQL 或数据库工具。
5. 自动监看已启动的 Improvement，显示每条反馈的模型输出、诊断类别/依据和修改建议。
6. 若规则无问题、没有候选建议：正常结束，记录 `candidate_rejection=not_needed`，不调用 PatchBuilder/Eval/ReleaseGate。
7. 默认模式若意外建议候选：等待用户明确输入“拒绝规则候选”，通过 Supervisor 提交拒绝并监看结束；记录预期偏差为 FAIL。规则问题案例使用 `--expect-rule-issue`，候选出现后输入“确认规则修改”，继续 Profile Patch、评测和发布门禁流程。

“规则无问题”和“等待拒绝候选”不是必然连续的两个步骤：没有建议候选就不应强行创建等待事项。诊断为 `SOURCE_INSUFFICIENT` 时记 INCOMPLETE，不能证明规则正确。

程序不会输出 provider `reasoning_content`、隐藏 `<think>`、system Prompt、请求头或图片 base64。展示的是模型任务输出、简短理由、证据和诊断解释；非 JSON 响应只标记不可用，后台私有 Trace 保留用于诊断。

## 预期字段、监看和验收结论

可提供 `--expected expected.json`，内容由人工确定，按稳定连接 ID 写期望字段：

```json
{
  "<connection UUID>": {"end_terminal": "2"}
}
```

不提供时只验证实际字段与获准 proposal 一致，不声称视觉准确率通过。默认要求 direct/Stage2/Stage2→Stage3 三类均被实际覆盖、四类模型输出可获取、规则无问题、没有候选创建、生产 Profile 未变，否则 FAIL 或 INCOMPLETE。

已有 run 只监看（不重新提交、不恢复或修改它）：

```powershell
.\.venv\Scripts\python.exe "services/agent/agent_test/2.纠错agent/run_acceptance.py" `
  --project-id "<项目 UUID>" --run-id "<已有 run UUID>"
```

此模式记录 MONITOR_ONLY，不算完整验收。SSE 自动续读已知 event seq；POST 不盲目重试，尤其提交响应丢失时应先核对 receipt/数据，不能自动重新注错。

若 `correction_committed=true`、数据核对通过，只有后续归因 run 失败：先加载相应修复，
再通过现有 `POST /v1/runs/<归因run UUID>/resume` 恢复归因（无请求体，携带配置的内部 Token）。
这会重新调用真实模型，需明确授权后手工执行；不要恢复纠错 run 或重复注错/提交。
随后用本脚本 `--run-id <归因run UUID>` 监看即可，该模式不会改写之前完整验收的 ERROR 结论。

记录按回合/事件逐步写入本目录 `runs/<时间>-<会话>/transcript.jsonl` 和 `summary.json`，即使中断也保留 run/turn/proposal ID。包含本项目数据，默认不提交 Git。模型/耗时/usage 可见；供应商未返回费用时 cost=null，不推算价格。
