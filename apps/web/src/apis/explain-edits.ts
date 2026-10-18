import { request } from "./client";
import type { components } from "./generated";

export type EditProposal = components["schemas"]["ConnectionEditProposal"];
export type EditReceipt = components["schemas"]["ConnectionEditReceipt"];
export function changesRecordOrigin(proposal: EditProposal): boolean {
  return proposal.changes.some(change => ["source_drawing_page", "source_pdf_page_number", "workspace_code", "target_drawing_page", "target_pdf_page_number", "page_item_id", "row_order"].some(field => field in change.after));
}
const path = (project: string) => `/api/v1/projects/${project}/connection-edits`;
export const explainEdits = {
  list: (project: string) => request<EditProposal[]>(path(project)),
  get: (project: string, id: string) => request<EditProposal>(`${path(project)}/${id}`),
  decide: (project: string, proposal: EditProposal, accepted: boolean) => request<EditReceipt>(`${path(project)}/${proposal.proposal_id}/decision`, { method: "POST", body: JSON.stringify({ checksum: proposal.checksum, accepted }) }),
};

export const editFieldNames: Record<string, string> = {
  start_code: "起点元件", start_description: "起点描述", start_terminal: "起点端子",
  end_code: "终点元件", end_description: "终点描述", end_terminal: "终点端子",
  start_terminal_coordinates: "起点坐标", end_terminal_coordinates: "终点坐标",
  source_pdf_page_number: "来源PDF页", source_drawing_page: "来源业务页", workspace_code: "来源工作区",
  target_pdf_page_number: "目标PDF页", target_drawing_page: "目标业务页", needs_review: "需要复核",
  principle_number: "原理号", terminal_strip: "端子排", current_value: "电流", color_mark: "色标", remark: "备注",
};
export function editOperationLabel(proposal: EditProposal): string {
  const op = proposal.request.operation;
  if (op.kind === "remove_terminal_prefix") return `${op.endpoint === "start" ? "起点" : "终点"}端子删除开头的 ${op.prefix}`;
  if (op.kind === "swap_endpoints") return "整组交换起终点（元件、描述、端子及坐标，所属页不变）";
  if (op.kind === "swap_terminals") return "只交换起终点端子，清理旧坐标";
  return "修改指定线表字段";
}
