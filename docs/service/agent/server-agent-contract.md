# Server-Agent 服务契约

> 状态：Draft  
> Agent API：`http://agent:8100/v1`  
> 调用方向：Web -> Server -> Agent；Web 不直接调用 Agent

## 1. 契约原则

2026-10-11 用户调整局部修订语义，见 [ADR-0010](../../adr/0010-in-place-confirmed-corrections.md)。当前领域契约版本为 3，checksum 为 `sha256:0d8e56f256c6e1d5d8f0ed2c7e8d24a12c7d6986dcb805d1ec8aed1d4512e9be`。局部 correction 确认后原位更新稳定连接 ID；`base_result_version` 为提取代次，新增 `base_result_revision` 校验代次内修订。receipt 新增 `result_revision/update_mode/updated_connection_ids`，结果分页响应新增 `result_revision`。旧 snapshot receipt 保留兼容；未提交且没有 base revision 的旧 proposal 需重新生成。

- Server 是业务身份、权限和生产结果的权威；
- Agent 是执行、诊断和候选结果的权威；
- 请求传 ID 和受控资源引用，不传任意本地路径；
- 所有长任务异步创建 run；
- Agent 返回 proposal，Server 使用乐观锁提交新版本；
- 所有接口使用 Pydantic/OpenAPI 并做契约测试。

阶段 0 对话接口新增 `POST /v1/supervisor/conversations/{id}/attachments`（原始 PDF body、user_id/filename query）、`POST /v1/supervisor/turns/stream`（ConversationTurn，SSE message/response/error）和 `GET /v1/supervisor/conversations/{id}?user_id=...`。接口沿用内部服务鉴权。会话附件只用于类型识别，不接受本地文件路径，不等同业务项目的 source document。短期历史与待确认对象只保存于单个 Agent API 进程，不由 Run checkpoint 自动恢复。

Supervisor 意图增加 `DETECT_PROFILE` 与 `QUERY_CONTEXT`；前者只检测并等待确认，后者查询本会话类型选择。常规 `/turns` 与流式回合均由会话服务加载历史和目标引用。阶段 0 确认成功返回 `ANSWERED`，不创建 FULL_EXTRACTION run。域 Schema checksum 已同步。

Gate A 增加 AgentRun.protocol_version（默认 1，正式 Supabase FULL_EXTRACTION 新 run 为 2）和 RunLease/StageInput/StageItem/StageManifest/StageCommitReceipt/RunFinalizationReceipt 领域契约。阶段 manifest 由数据库计算预期集合/计数，下一阶段须按同 run 上游清单加载；最终 receipt 与 run 收尾区分。Gate B 增加业务 import/read model 与 ProfileConfirmation，当前 Schema checksum：`sha256:1c141c9e0026e89b3141cd19e838aeb6608e2313886d8346f9c11a42b98653ed`。新 RPC 仅 service-role 可执行，不新增 Web 可直调接口；Gate B 内部接口/Fake 验收已实现，真实模型验收未执行。

## 2. Run 类型

```text
PROFILE_DETECTION       识别 ZH / ABB / UNKNOWN
FULL_EXTRACTION         完整三阶段提取
SCOPED_CORRECTION       连接、图纸或工作区局部修订/重提取
IMPROVEMENT_CANDIDATE   生成候选 Profile 补丁
PROFILE_EVALUATION      候选与基线回归评测
PROFILE_CANARY          已批准 Profile 的小流量验证
```

Run 状态：

```text
QUEUED -> RUNNING -> WAITING_INPUT -> SUCCEEDED
                  -> NEEDS_REVIEW  -> SUCCEEDED
                  -> FAILED
                  -> CANCELLED
```

`WAITING_INPUT` 表示缺少 Profile 或必要上下文；`NEEDS_REVIEW` 表示已有 proposal，但必须人工确认。

## 3. 创建 Run

```http
POST /v1/runs
Authorization: Bearer <internal-service-token>
Idempotency-Key: <server-generated-uuid>
Content-Type: application/json
```

```json
{
  "run_type": "FULL_EXTRACTION",
  "project_id": "project-uuid",
  "source_document_id": "document-uuid",
  "feedback_id": null,
  "requested_by": "user-uuid",
  "profile_hint": "zh",
  "expected_result_version": 3,
  "scope": {
    "type": "PROJECT",
    "id": "project-uuid"
  },
  "callback": {
    "url": "http://server:8000/internal/agent/events",
    "audience": "server"
  },
  "options": {
    "dry_run": false,
    "keep_stage_artifacts": true,
    "model_override": null
  }
}
```

响应：

```json
{
  "agent_run_id": "run-uuid",
  "status": "QUEUED",
  "run_type": "FULL_EXTRACTION",
  "profile": {
    "key": "zh",
    "version": "1.0.0"
  },
  "created_at": "2026-10-08T08:00:00Z"
}
```

## 4. Scope

```json
{
  "type": "CONNECTION | DRAWING | WORKSPACE | PROJECT | PROFILE",
  "id": "domain-object-id",
  "field": "start_terminal",
  "source_drawing_ids": ["drawing-a"],
  "target_drawing_ids": ["drawing-b"]
}
```

- `field` 只用于单字段反馈；
- `SCOPED_CORRECTION` 必须提供 `feedback_id`，Agent 通过 Server 工具读取完整反馈，不能信任请求内重复提交的自由文本；
- Agent 不信任调用方给出的页面列表，必须通过工具核对对象关系；
- PROJECT 和 WORKSPACE 重跑需要 Server 返回当前结果版本和受影响记录集合；
- PROFILE scope 仅允许管理员创建离线 improvement/eval run。

局部修复示例：

```json
{
  "run_type": "SCOPED_CORRECTION",
  "project_id": "project-uuid",
  "source_document_id": "document-uuid",
  "feedback_id": "feedback-uuid",
  "expected_result_version": 3,
  "scope": {
    "type": "CONNECTION",
    "id": "connection-uuid",
    "field": "end_terminal"
  }
}
```

## 4.1 Supervisor 对话契约

终端只读观测新增 `GET /v1/runs/{run_id}/model-outputs?user_id=...` 和 `GET /v1/supervisor/conversations/{conversation_id}/turns/{turn_id}/model-output?user_id=...`，沿用内部 Bearer。run 输出校验 requested_by，Supervisor 输出按已记录 user/conversation 过滤。返回结构化 output、agent/model/stage/item/耗时/usage/安全 schema 错误；不返回私有推理、system Prompt、请求头、图片 base64 或未解析自由文本。此观测不推进工作流、不新增数据库结构。

纠错检索 query/target_hint 新增可选 `start_terminal`、`end_terminal` 用于明确方向的精确匹配；原 `terminal` 继续匹配任一端。`workspace_page/wire_number` 的契约仍为字符串（保留前导零），输入边界也接受整数并无损转为字符串。权限和稳定连接 ID 的确认要求不变。当前领域 Schema checksum 为 `sha256:f13be2ce6ef98ac7b45db8de661d1f0e7de646fb3c1fb974dbe767e91b62fb12`。

Web 不直接调用 Agent。业务 Server 保存会话并将结构化回合提交给 Supervisor：

```http
POST /v1/supervisor/turns
```

```json
{
  "conversation_id": "conversation-uuid",
  "user_id": "user-uuid",
  "project_id": "project-uuid",
  "message": "重新检查线号 0272 的终点",
  "target_hint": {
    "result_version_id": "result-version-uuid",
    "connection_id": "connection-uuid",
    "wire_number": "0272"
  }
}
```

同步响应只返回当前回合决策，不等待长任务：

```json
{
  "turn_id": "turn-uuid",
  "intent": "CORRECT_RESULT",
  "status": "DISPATCHED",
  "agent_run_id": "run-uuid",
  "message": "已开始复核该连接，我会持续反馈各阶段结果。",
  "requires_input": false
}
```

若目标或 Profile 不明确，返回 `WAITING_INPUT`、结构化缺失字段和用户问题。Server 通过既有 run event 通道将子工作流事件代理给 Web。

## 5. 查询、事件和控制

```text
GET  /v1/runs/{agent_run_id}
GET  /v1/runs/{agent_run_id}/events?after_seq=120
GET  /v1/runs/{agent_run_id}/artifacts
POST /v1/runs/{agent_run_id}/cancel
POST /v1/runs/{agent_run_id}/resume
POST /v1/runs/{agent_run_id}/input
```

Profile 与评测管理接口：

```text
GET  /v1/profiles
GET  /v1/profiles/{profile_key}/versions
GET  /v1/evals/{eval_run_id}
GET  /v1/evals/{eval_run_id}/report
POST /v1/profile-candidates/{candidate_id}/approve
POST /v1/profile-candidates/{candidate_id}/reject
POST /v1/profile-candidates/{candidate_id}/rollback
```

approve/reject/rollback 仅供内部管理员调用；Agent 自身没有调用这些接口的凭证。

`resume` 复用相同 run 和 checkpoint，不创建新的业务结果版本。需要使用不同 Profile 或输入重新执行时创建新 run，并通过 `parent_run_id` 建立关系。

## 6. 事件信封

```json
{
  "event_id": "event-uuid",
  "agent_run_id": "run-uuid",
  "seq": 121,
  "occurred_at": "2026-10-08T08:01:03Z",
  "event_type": "STAGE_COMPLETED",
  "stage": "PAGE_SCAN",
  "level": "INFO",
  "scope": {
    "type": "DRAWING",
    "id": "drawing-uuid"
  },
  "message": "page scan completed",
  "metrics": {
    "processed": 12,
    "total": 30,
    "records": 18,
    "needs_review": 1
  },
  "artifact_refs": ["artifact-uuid"],
  "error": null
}
```

事件类型最少包括：

```text
RUN_CREATED
RUN_STARTED
PROFILE_DETECTED
PROFILE_REVIEW_REQUIRED
STAGE_STARTED
ITEM_COMPLETED
STAGE_COMPLETED
PROPOSAL_CREATED
HUMAN_INPUT_REQUIRED
RUN_FAILED
RUN_CANCELLED
RUN_COMPLETED
```

回调可能重复、乱序到达。Server 使用 `event_id` 去重，使用 `seq` 排序，不根据 HTTP 到达顺序推断状态。

## 7. ResultProposal

完整提取和局部修复都先形成 proposal。Supabase 生产模式会把完整提取原子持久化为 `draft/needs_review` 结果版本；局部修复在用户确认前仍只保存 proposal：

```json
{
  "proposal_id": "proposal-uuid",
  "agent_run_id": "run-uuid",
  "project_id": "project-uuid",
  "base_result_version": 3,
  "profile": {
    "key": "zh",
    "version": "1.0.0",
    "checksum": "sha256:..."
  },
  "model": {
    "provider": "openai-compatible",
    "name": "configured-vlm",
    "snapshot": "provider-specific-version"
  },
  "operations": [
    {
      "op": "replace",
      "target_type": "CONNECTION",
      "target_id": "connection-uuid",
      "expected_version": 7,
      "before": {
        "end_terminal": "FC103:3"
      },
      "after": {
        "end_terminal": "FC103:2"
      },
      "evidence_ids": ["evidence-uuid"],
      "reason": "目标页 003.C/20 的放线标记连接到 FC103:2",
      "confidence": 0.94
    }
  ],
  "unchanged_assertions": [
    {
      "scope": "workspace-uuid",
      "connection_ids": ["connection-2", "connection-3"],
      "hash": "sha256:..."
    }
  ],
  "validation": {
    "schema_valid": true,
    "business_rules_valid": true,
    "regressions": [],
    "warnings": []
  },
  "status": "READY_FOR_REVIEW"
}
```

Server 提交时校验：

1. 当前业务结果版本等于 `base_result_version`；
2. 每个目标记录版本等于 `expected_version`；
3. 用户对目标项目有权限；
4. 证据属于目标项目；
5. Server 端 Schema 和确定性业务规则通过；
6. `unchanged_assertions` 未被并发修改。

校验通过后创建新的 `result_version`，不得原地覆盖历史版本。

## 8. Profile Detection 返回

```json
{
  "document_id": "document-uuid",
  "selected": {
    "profile_key": "zh",
    "profile_version": "1.0.0",
    "confidence": 0.97
  },
  "candidates": [
    {"profile_key": "zh", "score": 0.97},
    {"profile_key": "abb", "score": 0.08}
  ],
  "evidence": [
    {
      "drawing_id": "drawing-uuid",
      "signals": ["Plant Function", "Page Number", "ZPMC title block"]
    }
  ],
  "needs_review": false,
  "reason": "标题栏和跨页引用格式符合 ZH Profile"
}
```

M4 检测只读取 PDF 物理首页。高置信且状态为 `active` 的 Profile 可直接锁定；无法识别、低置信或 `experimental` Profile 返回 `WAITING_INPUT`，并携带用户选择问题。用户确认后生成不可变 ProfileBinding，后续 Extraction Graph 必须使用其中的版本和 checksum，不能在运行中切换 Profile。

建议阈值：

```text
confidence >= 0.90 且领先第二候选 >= 0.20 -> 自动选择
0.70 <= confidence < 0.90                  -> 人工确认
confidence < 0.70                           -> UNKNOWN
```

阈值最终应由真实分类集校准，而不是写死后长期不变。

## 9. Server 提供给 Agent 的工具 API

Agent 只能通过以下受控接口获取业务上下文：

```text
GET  /internal/agent/projects/{project_id}/context
GET  /internal/agent/workspaces/{workspace_id}/bundle
GET  /internal/agent/drawings/{drawing_id}/access
GET  /internal/agent/connections/{connection_id}/evidence-bundle
GET  /internal/agent/runs/{business_run_id}/stage-artifacts
POST /internal/agent/result-proposals
POST /internal/agent/events
```

### Drawing access

返回短期签名 URL、checksum、PDF 物理页、业务页号和工作区，不返回 Storage service-role key。

### Evidence bundle

返回：

- 当前结构化记录和版本；
- 来源页、目标页和跨页引用；
- Stage 1/2/3 对应输出；
- Prompt/Profile/模型版本；
- 用户历史修订；
- 可选的 bbox/crop；
- 相邻记录的只读摘要。

## 10. 错误模型

```json
{
  "error": {
    "code": "PROFILE_NOT_CONFIRMED",
    "message": "The document profile requires human confirmation.",
    "retryable": false,
    "agent_run_id": "run-uuid",
    "details": {
      "candidates": ["zh", "abb"]
    }
  }
}
```

稳定错误码：

```text
INVALID_REQUEST
UNAUTHORIZED_SERVICE
PROJECT_CONTEXT_NOT_FOUND
PROFILE_NOT_CONFIRMED
PROFILE_VERSION_NOT_FOUND
SOURCE_ARTIFACT_EXPIRED
MODEL_TEMPORARILY_UNAVAILABLE
MODEL_SCHEMA_INVALID
CHECKPOINT_CONFLICT
BASE_VERSION_CONFLICT
RUN_ALREADY_ACTIVE
RUN_CANCELLED
EVALUATION_FAILED
INTERNAL_ERROR
```

只有临时模型错误、签名 URL 过期和暂时网络错误可自动重试。Schema、权限和版本冲突不得盲目重试。

## 11. 幂等、并发和认证

- `POST /v1/runs` 强制 Idempotency-Key；
- 同一个业务 scope 可以并行读，但只能有一个可提交 correction proposal；
- Agent API 使用内部 JWT/mTLS，不接受 Supabase anon key；
- callback 使用独立签名，包含时间戳和 replay window；
- 所有请求携带 `X-Request-ID`，模型请求派生 child request ID；
- 日志不记录签名 URL、JWT、API key 和完整用户反馈原文。

## 12. 契约测试

Server 和 Agent 必须共享 OpenAPI 快照或生成 Client，并至少覆盖：

- 创建 run、重复 Idempotency-Key；
- 事件重复和乱序；
- 签名 URL 过期；
- UNKNOWN Profile；
- base version 冲突；
- 单连接 patch；
- 工作区批量 patch；
- proposal 被拒绝后不修改生产数据；
- cancel/resume；
- Agent 离线时 Server 的降级状态。

## 13. Gate B 内部验收接口（已实现）

这些 `/v1` 路由由内部 Bearer 保护，只供可信 Server/受控终端；`user_id` 是调用者传入的已有 Auth UUID，不是浏览器身份凭证。新读接口仅允许 owner / run.requested_by。Web JWT/成员代理未实现。

| 方法/路径 | 输入与输出 |
| --- | --- |
| `POST /v1/imports` | raw PDF body；Query `user_id,conversation_id,project_name,filename`；Header `Idempotency-Key`。返回 ImportedDocument（project/source/attachment UUID、checksum、size、page_count）。UUID 由 owner+key 固定；不同内容同 key 拒绝，部分上传原 key 重试，不自动创建用户 |
| `POST /v1/supervisor/turns[/stream]` | ConversationTurn。上传后脚本仅发 user/message/conversation/turn ID；服务端补附件/project。PROCESS_DOCUMENT→首页检测/WAITING_INPUT→CONFIRM_INPUT→持久 FULL_EXTRACTION；响应 receipt.agent_run_id 用于后续查询 |
| `GET /v1/projects/{project_id}/tree?user_id=...` | ProjectTreeResponse；只展开 published 分类 snapshot，封存前只有 sources；不返回公开图片 URL |
| `GET /v1/projects/{project_id}/results?user_id=...` | `result_version_id` 可选；`offset>=0,limit=1..500`；返回固定版本、扁平字段、has_more；翻页必须沿用第一次返回的版本 ID |
| `GET /v1/runs/{agent_run_id}/summary?user_id=...` | RunStageSummaryResponse；阶段封存/计数/digest/持久事件跨度/模型/Profile/final receipt；费用 unknown/null |
| `GET /v1/runs/{agent_run_id}/events/stream` | `after_seq` 或 `Last-Event-ID` 续传；关闭前排空终态事件。既有 run/events 路由继续信任内部服务身份，不作为浏览器越权边界 |

CreateRunRequest 新增可选 `profile: ProfileRef`；RunOptions 新增类型化 `profile_confirmation`，保存确认 Profile、操作者、源 checksum、检测 ID/置信度和确认时间。业务入口由服务端填写 `expected_result_version=0`，LLM 不猜版本。protocol 2 新 run、RUN_CREATED、queue 在 `gate_b_create_extraction` 内原子登记；service-role-only、owner/source 关联及指纹冲突校验。Gate B 固定完整提取 key 到 source UUID，重传/重启复用已有任务，不改旧确认审计。

`/v1/imports` 是受限内部验收上传，不替代产品大文件直传。会话在进程重启后消失，但已创建 run/阶段/结果仍可用 ID 查询；未确认会话需重新检测确认。ABB experimental 不可正式提取，阶段 0 仍可只确认类型。OpenAPI 路由/响应模型测试和 domain schema checksum 已同步，Web TS Client 尚未接这些内部接口。
