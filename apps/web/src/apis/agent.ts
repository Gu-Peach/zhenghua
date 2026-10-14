import { authenticatedFetch, request } from "./client";
import type { AgentEvent } from "./types";

export type AgentStageStatus = "pending" | "processing" | "done" | "failed";
export interface AgentStageProgress { stage: string; status: AgentStageStatus; agentName?: string }
export interface SupervisorRequest { projectId: string; conversationId: string; message: string; attachmentIds?: string[]; targetHint?: Record<string, string> }
export interface AgentStreamUpdate { stageUpdate?: AgentStageProgress; event?: AgentEvent; response?: TurnResponse; refresh?: boolean; runId?: string; seq?: number }
export interface TurnResponse { receipt?: { agent_run_id?: string; payload?: Record<string, unknown> }; decision?: { reason?: string; intent?: string }; user_event?: { turn_id?: string; event_type?: string; user_message: string; requires_input?: boolean; occurred_at?: string } }
interface RunEvent { seq: number; agent_run_id: string; event_type: string; stage?: string; message: string; occurred_at: string; metrics?: Record<string, unknown>; error?: { message: string } }
const labels: Record<string, string> = { RENDER: "PDF 渲染", PAGE_CLASSIFICATION: "Stage 1", PAGE_SCAN: "Stage 2", BUILD_CROSS_PAGE_TASKS: "跨页任务索引", CROSS_PAGE_COMPLETION: "Stage 3", VALIDATION: "确定性校验", ISSUE_DIAGNOSIS: "规则归因", PROPOSAL: "结果修订" };

export async function* sse(path: string, options: RequestInit = {}): AsyncGenerator<{ event: string; data: unknown }> {
  const response = await authenticatedFetch(path, { ...options, credentials: "include", headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok || !response.body) {
    const failure = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null;
    const message = typeof failure?.detail === "string" ? failure.detail : failure?.detail?.message;
    throw new Error(message ?? `事件流连接失败 (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder(); let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const lines = frame.split(/\r?\n/);
        const data = lines.filter(l => l.startsWith("data:")).map(l => l.slice(5).trimStart()).join("\n");
        if (data) yield { event: lines.find(l => l.startsWith("event:"))?.slice(6).trim() ?? "message", data: JSON.parse(data) as unknown };
      }
      if (done) break;
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
}

export async function* streamSupervisorRun(input: SupervisorRequest, signal?: AbortSignal): AsyncGenerator<AgentStreamUpdate> {
  let final: TurnResponse | undefined;
  let lastMessage = "";
  let replyText = "";
  let replyId = "";
  for await (const frame of sse("/api/v1/supervisor/turns/stream", { method: "POST", signal, body: JSON.stringify({ conversation_id: input.conversationId, turn_id: crypto.randomUUID(), project_id: input.projectId, message: input.message, attachment_ids: input.attachmentIds ?? [], target_hint: input.targetHint ?? {} }) })) {
    if (frame.event === "error") { const error = frame.data as { detail: unknown }; throw new Error(typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail)); }
    if (frame.event === "message") {
      const message = frame.data as { turn_id?: string; event_type: string; user_message: string; occurred_at: string; payload?: { workflow?: string } };
      if (message.event_type === "ASSISTANT_DELTA") {
        replyText += message.user_message;
        replyId ||= `reply:${message.turn_id ?? input.conversationId}`;
        yield { event: { id: replyId, kind: "message", title: "电气图纸助手", detail: replyText, timestamp: message.occurred_at, status: "running" } };
        continue;
      }
      if (message.event_type === "WORKFLOW_DISPATCHED" && message.payload?.workflow === "READ_ONLY_QUERY") continue;
      lastMessage = message.user_message;
      yield { event: { id: crypto.randomUUID(), kind: message.event_type === "SUPERVISOR_PLAN" ? "thought" : "result", title: "Supervisor", detail: message.user_message, timestamp: message.occurred_at, status: "done" } };
    }
    if (frame.event === "response") {
      final = frame.data as TurnResponse;
      const userEvent = final.user_event;
      const intent = final.decision?.intent;
      const taskCard = !intent || ["PROCESS_DOCUMENT", "DETECT_PROFILE", "CORRECT_RESULT", "CONFIRM_INPUT", "CONFIRM_RESULT_PATCH", "AUTHORIZE_PROFILE_CANDIDATE"].includes(intent);
      const plainReply = userEvent?.event_type === "ASSISTANT_MESSAGE" || !taskCard;
      yield { response: final, refresh: !!final.receipt || !plainReply, event: userEvent && (replyId || userEvent.user_message !== lastMessage) ? { id: replyId || crypto.randomUUID(), kind: plainReply ? "message" : "result", title: plainReply ? "电气图纸助手" : userEvent.requires_input ? "等待用户确认" : "任务处理", detail: userEvent.user_message, timestamp: userEvent.occurred_at ?? new Date().toISOString(), status: !plainReply && userEvent.requires_input ? "pending" : "done" } : undefined };
    }
  }
  if (!final) throw new Error("Supervisor 响应中断，尚无法确认任务是否创建；请查询会话状态，不要盲目重复提交。");
  const runId = final?.receipt?.agent_run_id;
  if (runId) yield* watchRun(runId, signal);
}

export async function* watchRun(runId: string, signal?: AbortSignal, afterSeq = -1): AsyncGenerator<AgentStreamUpdate> {
  let cursor = afterSeq;
  yield { runId };
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      for await (const frame of sse(`/api/v1/runs/${runId}/events/stream?after_seq=${cursor}`, { signal })) {
        const e = frame.data as RunEvent;
        if (e.seq <= cursor) continue;
        cursor = e.seq;
        const stage = labels[e.stage ?? ""] ?? e.stage ?? "任务";
        const completed = e.event_type === "STAGE_COMPLETED" || e.event_type === "RUN_COMPLETED";
        const stageEvent = e.event_type.startsWith("STAGE_");
        const failed = e.event_type === "RUN_FAILED";
        const waiting = e.event_type === "HUMAN_INPUT_REQUIRED";
        yield { runId, seq: cursor, refresh: completed, stageUpdate: stageEvent || failed && !!e.stage ? { stage, status: failed ? "failed" : completed ? "done" : "processing", agentName: stage } : undefined, event: { id: stageEvent ? `${runId}:stage:${e.stage}` : `${runId}:${e.seq}`, kind: failed ? "error" : stageEvent ? "stage" : completed || waiting ? "result" : "tool", stage: stageEvent || failed ? stage : undefined, status: failed ? "failed" : waiting ? "pending" : e.event_type === "STAGE_STARTED" ? "running" : "done", title: waiting ? "等待用户确认" : stage, detail: e.error?.message ?? `${e.message}${e.metrics && Object.keys(e.metrics).length ? ` · ${JSON.stringify(e.metrics)}` : ""}`, timestamp: e.occurred_at } };
      }
      const status = await request<{ run: { status: string } }>(`/api/v1/runs/${runId}`);
      if (!["QUEUED", "RUNNING"].includes(status.run.status)) return;
    } catch (error) { if (signal?.aborted || attempt === 3) throw error; }
    await new Promise(resolve => window.setTimeout(resolve, 1000 * (attempt + 1)));
  }
  throw new Error("事件流连接中断；任务未取消，可重新连接查看进度。");
}

export async function runArtifacts(runId: string): Promise<{ items: Array<{ kind: string; proposal_id?: string; candidate_recommended?: boolean; diagnoses?: unknown; candidate?: unknown }> }> {
  return request(`/api/v1/runs/${runId}/artifacts`);
}
