import { request } from "./client";
import { sse } from "./agent";
import type { components } from "./generated";

export type AssistantScope = components["schemas"]["AssistantScope"];
export type AssistantConversation = components["schemas"]["AssistantConversationRead"];
export type AssistantEvent = components["schemas"]["AssistantEvent"];
export type AssistantTurn = components["schemas"]["AssistantTurnInput"];
export type AssistantAction = components["schemas"]["AssistantActionRead"];
const base = "/api/v1/assistant";
export const assistantApi = {
  capabilities: () => request<{ available: boolean; message?: string }>(`${base}/capabilities`),
  list: () => request<AssistantConversation[]>(`${base}/conversations`),
  create: (id: string, title: string) => request<AssistantConversation>(`${base}/conversations`, { method: "POST", body: JSON.stringify({ id, title }) }),
  get: (id: string, offset = 0) => request<AssistantConversation>(`${base}/conversations/${id}?offset=${offset}`),
  remove: (id: string) => request<void>(`${base}/conversations/${id}`, { method: "DELETE" }),
  upload: (id: string, body: components["schemas"]["AssistantAttachmentInput"]) => request<components["schemas"]["AssistantAttachmentRead"]>(`${base}/conversations/${id}/attachments`, { method: "POST", body: JSON.stringify(body) }),
  action: (id: string) => request<AssistantAction>(`${base}/actions/${id}`),
  decide: (action: AssistantAction, accepted: boolean) => request<AssistantAction>(`${base}/actions/${action.id}/decision`, { method: "POST", body: JSON.stringify({ checksum: action.checksum, accepted }) }),
};
export async function* streamAssistant(id: string, body: AssistantTurn, signal: AbortSignal): AsyncGenerator<AssistantEvent> {
  let completed = false; let failure: string | undefined;
  for await (const frame of sse(`${base}/conversations/${id}/turns/stream`, { method: "POST", body: JSON.stringify(body), signal })) {
    const event = frame.data as AssistantEvent;
    yield event;
    if (event.type === "error") failure = event.message ?? "主助手处理未完成";
    if (event.type === "completed") { completed = true; if (failure || event.data?.status === "failed") throw new Error(failure ?? "主助手处理未完成"); break; }
  }
  if (!completed && !signal.aborted) throw new Error("会话连接已中断，请恢复会话或重试本轮以查询已创建任务。");
}

export function assistantDestination(value: Record<string, unknown>): string | null {
  if (value.destination === "agent" && ["extraction", "profile"].includes(String(value.page))) {
    const params = new URLSearchParams();
    if (typeof value.profile_id === "string") params.set("profile", value.profile_id);
    return `/agents/${String(value.page)}${params.size ? `?${params}` : ""}`;
  }
  const scope = value.scope as AssistantScope | undefined;
  if (value.destination !== "project" || !scope?.project_id || !/^[a-f0-9-]{36}$/i.test(scope.project_id)) return null;
  const params = new URLSearchParams();
  if (scope.workspace_id) params.set("workspace", scope.workspace_id);
  if (scope.drawing_id) params.set("drawing", scope.drawing_id);
  if (value.view === "preview") params.set("view", "preview");
  return `/projects/${scope.project_id}${params.size ? `?${params}` : ""}`;
}
