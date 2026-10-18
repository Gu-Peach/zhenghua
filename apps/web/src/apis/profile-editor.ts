import { ApiError, request } from "./client";
import { sse } from "./agent";
import type { components } from "./generated";

export type ProfileEditState = components["schemas"]["ProfileEditState"];
export type EditProposal = components["schemas"]["Proposal"];
export type EditTurn = components["schemas"]["ProfileTurn"];
export type EditEvent = components["schemas"]["ProfileEvent"];
export type PublishedProfile = components["schemas"]["ProfileReferenceRead"];
const base = "/api/v1/profile";

export const profileEditorApi = {
  async open(profile: string, checksum: string, draft: string): Promise<ProfileEditState> {
    try { return await request<ProfileEditState>(`${base}/references/${profile}/draft`, { method: "POST", body: JSON.stringify({ draft_id: draft, base_checksum: checksum }) }); }
    catch (error) { if (error instanceof ApiError && error.status === 404 && error.message === "Not Found") throw new Error("规则编辑接口尚未加载，请重新启动8000后端和8100 Agent。", { cause: error }); throw error; }
  },
  state: (draft: string) => request<ProfileEditState>(`${base}/drafts/${draft}/editor`),
  save: (state: ProfileEditState, edits: components["schemas"]["FileEdit"][], operationId: string) => request<ProfileEditState>(`${base}/drafts/${state.draft.draft_id}/editor/files`, { method: "POST", body: JSON.stringify({ revision: state.draft.revision, operation_id: operationId, edits }) }),
  accept: (state: ProfileEditState) => request<ProfileEditState>(`${base}/drafts/${state.draft.draft_id}/editor/accept`, { method: "POST", body: JSON.stringify({ revision: state.draft.revision }) }),
  confirm: (state: ProfileEditState, proposal: string, accepted: boolean) => request<ProfileEditState>(`${base}/drafts/${state.draft.draft_id}/editor/proposals/${proposal}/confirm`, { method: "POST", body: JSON.stringify({ revision: state.draft.revision, accepted }) }),
  publish: (state: ProfileEditState) => request<PublishedProfile>(`${base}/drafts/${state.draft.draft_id}/publish`, { method: "POST", body: JSON.stringify({ revision: state.draft.revision }) }),
  cleanup: () => request<{ cleanup_pending: boolean }>(`${base}/cleanup`, { method: "POST" }),
};

export async function* streamProfileEditor(draft: string, body: EditTurn, signal: AbortSignal): AsyncGenerator<EditEvent> {
  let done = false;
  for await (const frame of sse(`${base}/drafts/${draft}/editor/turns/stream`, { method: "POST", signal, body: JSON.stringify(body) })) {
    if (frame.event === "error") {
      const error = frame.data as { message?: string; code?: string };
      throw new Error(`${error.message ?? "规则分析失败"}${error.code ? ` [${error.code}]` : ""}`);
    }
    const value = frame.data as EditEvent;
    if (!value?.type) continue;
    yield value;
    if (value.type === "completed") { done = true; break; }
  }
  if (!signal.aborted && !done) throw new Error("分析连接已中断，请重试本轮或恢复编辑草稿。");
}
