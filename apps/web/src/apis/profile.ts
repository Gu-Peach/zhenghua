import { request } from "./client";
import type { components } from "./generated";
import { sse } from "./agent";

export type ProfileDraft = components["schemas"]["DraftView"];
export type ProfileState = components["schemas"]["WizardState"];
export type ProfileCandidate = components["schemas"]["StageCandidate"];
export type ProfileStage = "classification" | "scan" | "completion";
export type Expected = Record<string, unknown>;
export type TargetImage = components["schemas"]["TargetImage"];
export type ProfileConversationState = components["schemas"]["ConversationState"];
export type ProfileConversationTurn = components["schemas"]["ConversationTurn"];
export type ProfileConversationEvent = components["schemas"]["ConversationEvent"];
export type ProfilePdfSample = components["schemas"]["PdfSampleResult"];
const base = "/api/v1/profile/drafts";

export const profileApi = {
  list: async () => (await request<ProfileDraft[]>(base)).filter(draft => !draft.source?.profile_id),
  create: (key: string, displayName: string, draftId: string = crypto.randomUUID()) => request<ProfileDraft>(base, { method: "POST", body: JSON.stringify({ draft_id: draftId, key, display_name: displayName }) }),
  conversation: (id: string) => request<ProfileConversationState>(`${base}/${id}/conversation`),
  async samplePdf(draft: ProfileDraft, file: File, requestId: string, signal?: AbortSignal): Promise<ProfilePdfSample> {
    if (!file.size || file.size > 50 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf")) throw new Error("请上传不超过50MiB的有效PDF文件。");
    const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("PDF读取失败")); reader.readAsDataURL(file); });
    return request<ProfilePdfSample>(`${base}/${draft.draft_id}/pdf-samples`, { method: "POST", signal, body: JSON.stringify({ revision: draft.revision, request_id: requestId, filename: file.name, content_base64: content, stage: "classification" }) });
  },
  state: (id: string) => request<ProfileState>(`${base}/${id}/wizard`),
  pixels: (id: string, image: string) => request<{ data_url: string }>(`${base}/${id}/images/${image}`),
  async upload(draft: ProfileDraft, file: File, imageId: string = crypto.randomUUID()): Promise<ProfileDraft> {
    if (file.size > 10 * 1024 * 1024) throw new Error("每张图片不能超过10MiB");
    const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("图片读取失败")); reader.readAsDataURL(file); });
    return request<ProfileDraft>(`${base}/${draft.draft_id}/images`, { method: "POST", body: JSON.stringify({ revision: draft.revision, image_id: imageId, filename: file.name, content_base64: content }) });
  },
  generate: (draft: ProfileDraft, stage: ProfileStage, description: string, source: string, targets: TargetImage[], requestId: string, negativeImages: string[] = []) => request<ProfileState>(`${base}/${draft.draft_id}/stages/${stage}/generate`, { method: "POST", body: JSON.stringify({ revision: draft.revision, request_id: requestId, description, source_image: source, targets, negative_images: negativeImages }) }),
  confirm: (draft: ProfileDraft, stage: ProfileStage, candidate: ProfileCandidate, ruleText: string, expected: Expected[]) => request<ProfileState>(`${base}/${draft.draft_id}/stages/${stage}/confirm`, { method: "POST", body: JSON.stringify({ revision: draft.revision, candidate_id: candidate.id, rule_text: ruleText, expected }) }),
  publish: (draft: ProfileDraft) => request<components["schemas"]["ProfileReferenceRead"]>(`${base}/${draft.draft_id}/publish`, { method: "POST", body: JSON.stringify({ revision: draft.revision }) }),
};

export async function* streamProfileConversation(draft: string, body: ProfileConversationTurn, signal: AbortSignal): AsyncGenerator<ProfileConversationEvent> {
  let completed = false;
  for await (const frame of sse(`${base}/${draft}/conversation/turns/stream`, { method: "POST", body: JSON.stringify(body), signal })) {
    if (frame.event === "error") {
      const error = frame.data as { code?: string; diagnostic_id?: string; message?: string; detail?: { message?: string } };
      const category = error.code ? ` [${error.code}]` : "";
      const reference = error.diagnostic_id ? ` · 诊断编号 ${error.diagnostic_id}` : "";
      throw new Error((error.message ?? error.detail?.message ?? "规则对话失败，请恢复草稿或重试本轮。") + category + reference);
    }
    const event = frame.data as ProfileConversationEvent;
    if (!event?.type) continue;
    if (event.turn_id !== body.turn_id) throw new Error("回复不属于当前规则对话。");
    yield event;
    if (event.type === "completed") { completed = true; break; }
  }
  if (!signal.aborted && !completed) throw new Error("对话连接已中断，可重试本轮或恢复已保存内容。");
}

/** Completion Expected stores only the target; the accepted source remains in case.input. */
export function completionOverview(input: Expected | null | undefined, expected: Expected): string {
  const record = (value: unknown): Expected => value && typeof value === "object" && !Array.isArray(value) ? value as Expected : {};
  const source = record(input?.source_connection);
  const start = record(source.start).terminal;
  const end = record(expected.end).terminal;
  const reference = record(input?.reference).raw;
  return `已确认起点 ${String(start ?? "待确认")} → 终点 ${String(end ?? "待确认")} · 来源引用 ${String(reference ?? "未标注")}`;
}

export function expectedOverview(stage: ProfileStage, expected: Expected, input?: Expected | null): string[] {
  if (stage === "classification") return [`工作区 ${String(expected.plant_function ?? "待确认")} · 业务页 ${String(expected.drawing_page_number ?? "待确认")}`];
  if (stage === "completion") return [completionOverview(input, expected)];
  const record = (value: unknown): Expected => value && typeof value === "object" && !Array.isArray(value) ? value as Expected : {};
  return (Array.isArray(expected.units) ? expected.units : []).flatMap(unit => {
    const connections = record(unit).connections;
    return (Array.isArray(connections) ? connections : []).map(connection => {
      const row = record(connection); const references = Array.isArray(row.references) ? row.references.map(ref => String(record(ref).raw ?? "未确认引用")).join("、") : "";
      return `${String(row.line_number ?? "未标注原理号")}：${String(record(row.start).terminal ?? "待确认")} → ${String(record(row.end).terminal ?? (references ? "跨页待补全" : "待确认"))}${references ? ` · 引用 ${references}` : ""}`;
    });
  });
}
