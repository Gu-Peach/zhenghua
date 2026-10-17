import { request } from "./client";
import type { components } from "./generated";

export type ProfileDraft = components["schemas"]["DraftView"];
export type ProfileState = components["schemas"]["WizardState"];
export type ProfileCandidate = components["schemas"]["StageCandidate"];
export type ProfileStage = "classification" | "scan" | "completion";
export type Expected = Record<string, unknown>;
export type TargetImage = components["schemas"]["TargetImage"];
const base = "/api/v1/profile/drafts";

export const profileApi = {
  list: () => request<ProfileDraft[]>(base),
  create: (key: string, displayName: string) => request<ProfileDraft>(base, { method: "POST", body: JSON.stringify({ draft_id: crypto.randomUUID(), key, display_name: displayName }) }),
  state: (id: string) => request<ProfileState>(`${base}/${id}/wizard`),
  pixels: (id: string, image: string) => request<{ data_url: string }>(`${base}/${id}/images/${image}`),
  async upload(draft: ProfileDraft, file: File): Promise<ProfileDraft> {
    if (file.size > 10 * 1024 * 1024) throw new Error("每张图片不能超过10MiB");
    const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("图片读取失败")); reader.readAsDataURL(file); });
    return request<ProfileDraft>(`${base}/${draft.draft_id}/images`, { method: "POST", body: JSON.stringify({ revision: draft.revision, image_id: crypto.randomUUID(), filename: file.name, content_base64: content }) });
  },
  generate: (draft: ProfileDraft, stage: ProfileStage, description: string, source: string, targets: TargetImage[], requestId: string, negativeImages: string[] = []) => request<ProfileState>(`${base}/${draft.draft_id}/stages/${stage}/generate`, { method: "POST", body: JSON.stringify({ revision: draft.revision, request_id: requestId, description, source_image: source, targets, negative_images: negativeImages }) }),
  confirm: (draft: ProfileDraft, stage: ProfileStage, candidate: ProfileCandidate, ruleText: string, expected: Expected[]) => request<ProfileState>(`${base}/${draft.draft_id}/stages/${stage}/confirm`, { method: "POST", body: JSON.stringify({ revision: draft.revision, candidate_id: candidate.id, rule_text: ruleText, expected }) }),
  publish: (draft: ProfileDraft) => request<components["schemas"]["ProfileReferenceRead"]>(`${base}/${draft.draft_id}/publish`, { method: "POST", body: JSON.stringify({ revision: draft.revision }) }),
};
