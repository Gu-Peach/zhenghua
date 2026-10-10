# Server-Agent 服务契约

> 状态：Draft  
> Agent API：`http://agent:8100/v1`  
> 调用方向：Web -> Server -> Agent；Web 不直接调用 Agent

## 1. 契约原则

- Server 是业务身份、权限和生产结果的权威；
- Agent 是执行、诊断和候选结果的权威；
- 请求传 ID 和受控资源引用，不传任意本地路径；
- 所有长任务异步创建 run；
- Agent 返回 proposal，Server 使用乐观锁提交新版本；
- 所有接口使用 Pydantic/OpenAPI 并做契约测试。

阶段 0 对话接口新增 `POST /v1/supervisor/conversations/{id}/attachments`（原始 PDF body、user_id/filename query）、`POST /v1/supervisor/turns/stream`（ConversationTurn，SSE message/response/error）和 `GET /v1/supervisor/conversations/{id}?user_id=...`。接口沿用内部服务鉴权。会话附件只用于类型识别，不接受本地文件路径，不等同业务项目的 source document。短期历史与待确认对象只保存于单个 Agent API 进程，不由 Run checkpoint 自动恢复。

Supervisor 意图增加 `DETECT_PROFILE` 与 `QUERY_CONTEXT`；前者只检测并等待确认，后者查询本会话类型选择。常规 `/turns` 与流式回合均由会话服务加载历史和目标引用。阶段 0 确认成功返回 `ANSWERED`，不创建 FULL_EXTRACTION run。域 Schema checksum 已同步。

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
