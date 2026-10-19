import { request } from "./client";
import type { components } from "./generated";

export type RescanRun = components["schemas"]["RescanRun"];
export type RescanAsset = components["schemas"]["RescanAsset"];
export type RescanEvidenceImage = components["schemas"]["RescanEvidenceImage"];
export type RescanRemovedRow = components["schemas"]["RescanRemovedRow"];

export function legacyFullRescan(run: RescanRun): boolean {
  return run.request.fields === "all" && !run.request.scope.connection_ids?.length && !run.request.scope.principle_numbers?.length && run.request.result_mode !== "replace_scope";
}
export interface RescanPageChoice { pdf: number; title: string }
const path = (project: string) => `/api/v1/projects/${project}/rescans`;
export const rescans = {
  list: (project: string) => request<RescanRun[]>(path(project)),
  get: (project: string, id: string, signal?: AbortSignal) => request<RescanRun>(`${path(project)}/${id}`, { signal }),
  evidence: (run: RescanRun, signal?: AbortSignal) => request<RescanEvidenceImage[]>(`${path(run.project_id)}/${run.id}/evidence`, { signal }),
  decide: (run: RescanRun, accepted: boolean) => request<RescanRun>(`${path(run.project_id)}/${run.id}/decision`, { method: "POST", body: JSON.stringify({ checksum: run.checksum, accepted }) }),
  cancel: (run: RescanRun) => request<RescanRun>(`${path(run.project_id)}/${run.id}/cancel`, { method: "POST" }),
  upload: async (project: string, conversation: string, file: File, page: number, role: "source" | "target") => {
    if (file.size > 8_000_000) throw new Error("图片不能超过8MB");
    const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error("图片读取失败")); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.readAsDataURL(file); });
    return request<RescanAsset>(`/api/v1/projects/${project}/rescan-assets`, { method: "POST", body: JSON.stringify({ conversation_id: conversation, pdf_page_number: page, role, content_base64: content }) });
  },
};
