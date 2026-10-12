import { request } from "./client";
import type { components } from "./generated";
import type { Drawing, ProjectDetail, ProjectSummary, RuleLibraryItem, WiringRow } from "./types";

type Schema = components["schemas"];
export type ResultPage = Omit<Schema["ConnectionPage"], "items"> & { items: WiringRow[] };
export type RulePackage = Schema["ResourcePackage"];
export type WiringUnit = Schema["WiringUnitRead"];

function summary(row: Schema["ProjectRead"]): ProjectSummary {
  const runStatus = row.latest_run?.status;
  const status = runStatus === "WAITING_INPUT" || runStatus === "NEEDS_REVIEW" ? "review" : runStatus === "FAILED" || row.status === "failed" ? "failed" : runStatus === "RUNNING" || runStatus === "QUEUED" ? "processing" : row.result?.status === "needs_review" ? "review" : row.result ? "completed" : "queued";
  return { id: row.id, name: row.name, company: "", profile: String(row.result?.profile?.key ?? row.standard_profile ?? "待识别"), status, progress: row.result ? 100 : 0, workspaceCount: row.workspaces?.length ?? 0, drawingCount: row.workspaces?.reduce((n, w) => n + (w.drawings?.length ?? 0), 0) ?? 0, updatedAt: row.updated_at };
}
export function drawingFromDb(d: Schema["DrawingRead"]): Drawing {
  return { id: d.id, drawingPage: d.workspace_page ?? "未识别", name: `PDF 第 ${d.pdf_page_number} 页`, pdfPage: d.pdf_page_number, status: d.status === "failed" ? "failed" : d.status === "needs_review" ? "review" : "completed", recordCount: 0, imageUrl: d.image_url ?? undefined, referenceNote: d.reference_note ?? undefined };
}
function connection(row: Schema["ConnectionRow"]): WiringRow {
  return { id: row.connection_id, workspaceId: row.workspace_id, drawingId: row.drawing_id ?? "", page: `${row.workspace_name} / ${row.workspace_page ?? "?"}`, wireNumber: String(row.wire_number), lineNumber: row.principle_number ?? "", voltageLevel: row.voltage_level ?? "", terminalStrip: row.terminal_strip ?? "", startCode: row.start_code ?? "", startDescription: row.start_description ?? "", startTerminal: row.start_terminal ?? "", endCode: row.end_code ?? "", endDescription: row.end_description ?? "", endTerminal: row.end_terminal ?? "", current: row.current_value ?? "", remark: row.remark ?? "", colorMark: row.color_mark ?? "", status: row.needs_review ? "review" : "confirmed", confidence: row.confidence ?? 0, isCrossPage: row.is_cross_page === "cross_page", recordVersion: row.record_version, raw: row as unknown as Record<string, unknown> };
}

export const projectApi = {
  async rename(id: string, name: string): Promise<void> { await request(`/api/v1/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }); },
  async remove(project: ProjectSummary): Promise<void> { const params = new URLSearchParams({ confirmed: "true", expected_updated_at: project.updatedAt }); await request(`/api/v1/projects/${project.id}?${params}`, { method: "DELETE" }); },
  async list(): Promise<ProjectSummary[]> {
    return (await request<Schema["ProjectRead"][]>("/api/v1/projects")).map(summary);
  },
  async get(id: string): Promise<ProjectDetail> {
    const row = await request<Schema["ProjectRead"]>(`/api/v1/projects/${id}`);
    return { ...summary(row), sourceFilename: row.sources?.[0]?.original_filename ?? "", projectNo: row.id, resultVersion: row.result ? `V${row.result.version} · r${row.result.revision}` : "暂无结果", workspaces: (row.workspaces ?? []).map(w => ({ id: w.id, code: w.code ?? w.name, name: w.name, status: "completed", drawings: (w.drawings ?? []).map(drawingFromDb) })) };
  },
  async connections(id: string, options: { offset?: number; workspaceId?: string | null; drawingId?: string | null; search?: string; versionId?: string | null } = {}): Promise<ResultPage> {
    const params = new URLSearchParams({ offset: String(options.offset ?? 0), limit: "100" });
    if (options.workspaceId) params.set("workspace_id", options.workspaceId);
    if (options.drawingId) params.set("drawing_id", options.drawingId);
    if (options.search) params.set("search", options.search);
    if (options.versionId) params.set("result_version_id", options.versionId);
    const result = await request<Schema["ConnectionPage"]>(`/api/v1/projects/${id}/connections?${params}`);
    return { ...result, items: result.items.map(connection) };
  },
  async drawing(id: string): Promise<Drawing> { return drawingFromDb(await request<Schema["DrawingRead"]>(`/api/v1/drawings/${id}`)); },
  async units(id: string): Promise<WiringUnit[]> { return request(`/api/v1/projects/${id}/wiring-units`); },
  async addConnection(id: string, body: Schema["ConnectionCreate"], key: string): Promise<Schema["ConnectionMutationReceipt"]> { return request(`/api/v1/projects/${id}/connections`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) }); },
  async deleteConnection(id: string, row: WiringRow, page: ResultPage, key: string): Promise<void> {
    const body: Schema["ConnectionDelete"] = { result_version_id: page.result_version_id!, result_revision: page.result_revision!, record_version: row.recordVersion!, confirmed: true };
    await request(`/api/v1/projects/${id}/connections/${row.id}`, { method: "DELETE", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) });
  },
  async target(row: WiringRow): Promise<Drawing> { return drawingFromDb(await request<Schema["DrawingRead"]>(`/api/v1/connections/${row.id}/target`)); },
  async edit(row: WiringRow, page: ResultPage, changes: Schema["ConnectionFields"], idempotencyKey: string = crypto.randomUUID()): Promise<void> {
    const input: Schema["ConnectionEdit"] = { result_version_id: page.result_version_id!, result_revision: page.result_revision!, record_version: row.recordVersion!, changes };
    await request(`/api/v1/connections/${row.id}`, { method: "PATCH", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(input) });
  },
  async listRuleLibrary(): Promise<RuleLibraryItem[]> {
    const rows = await request<Schema["RuleRead"][]>("/api/v1/rule-library");
    return rows.filter(row => row.status !== "retired").map(row => ({ id: row.id, key: row.profile_key, name: row.profile_key, version: row.profile_version, summary: `真实资源包 · ${row.package_checksum.slice(7, 19)}`, status: "published", updatedAt: row.created_at, canDelete: row.can_delete ?? false, isActive: true }));
  },
  async createRule(body: Schema["RuleCreate"]): Promise<Schema["RuleCreateReceipt"]> { return request("/api/v1/rule-library", { method: "POST", body: JSON.stringify(body) }); },
  async deleteRule(id: string): Promise<void> { await request(`/api/v1/rule-library/${id}?confirmed=true`, { method: "DELETE" }); },
  async package(id: string): Promise<RulePackage> { return request(`/api/v1/rule-library/${id}`); },
  async upload(file: File, conversationId: string): Promise<Schema["ImportResponse"]> {
    const params = new URLSearchParams({ conversation_id: conversationId, project_name: file.name.replace(/\.pdf$/i, ""), filename: file.name });
    return request(`/api/v1/imports?${params}`, { method: "POST", headers: { "Content-Type": "application/pdf", "Idempotency-Key": crypto.randomUUID() }, body: file });
  },
};
