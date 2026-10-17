import { authenticatedFetch, request } from "./client";
import type { components } from "./generated";
import type { Drawing, ProjectDetail, ProjectSummary, RuleLibraryItem, WiringRow, Workspace } from "./types";

type Schema = components["schemas"];
const drawingOrder = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });
export type ResultPage = Omit<Schema["SimpleConnectionPage"], "items"> & { items: WiringRow[] };
export type RulePackage = Schema["ResourcePackage"];
export type ProfileOption = Schema["LocalProfileOption"];

function summary(row: Schema["SimpleProjectRead"]): ProjectSummary {
  const status = row.status === "failed" || row.status === "archived" ? "failed" : row.status === "processing" ? "processing" : row.status === "ready" ? "completed" : "queued";
  return { id: row.id, name: row.name, company: "", profile: row.standard_profile ?? "未指定", status, progress: row.status === "ready" ? 100 : 0, workspaceCount: row.workspaces?.length ?? 0, drawingCount: row.workspaces?.reduce((n, w) => n + (w.drawings?.length ?? 0), 0) ?? 0, updatedAt: row.updated_at };
}
export function drawingFromDb(d: Schema["DrawingRead"]): Drawing {
  return { id: d.id, drawingPage: d.workspace_page ?? "未识别", name: `PDF 第 ${d.pdf_page_number} 页`, pdfPage: d.pdf_page_number, status: d.status === "failed" ? "failed" : d.status === "needs_review" ? "review" : ["rendered", "classified", "scan", "completion"].includes(d.status) ? "processing" : "completed", recordCount: 0, imageUrl: d.image_url ?? undefined, referenceNote: d.reference_note ?? undefined };
}
function connection(row: Schema["SimpleConnectionRead"]): WiringRow {
  return { processingStatus: row.processing_status, reviewReasons: row.review_reasons, id: row.connection_id, workspaceId: row.workspace_id, drawingId: row.drawing_id, page: row.workspace_page ?? `${row.workspace_name} / PDF ${row.pdf_page_number}`, wireNumber: row.wire_number ?? "", lineNumber: row.principle_number ?? "", voltageLevel: row.voltage_level ?? "", terminalStrip: row.terminal_strip ?? "", startCode: row.start_code ?? "", startDescription: row.start_description ?? "", startTerminal: row.start_terminal ?? "", endCode: row.end_code ?? "", endDescription: row.end_description ?? "", endTerminal: row.end_terminal ?? "", startTerminalCoordinates: row.start_terminal_coordinates ?? null, endTerminalCoordinates: row.end_terminal_coordinates ?? null, current: row.current_value ?? "", remark: row.remark ?? "", colorMark: row.color_mark ?? "", status: row.needs_review ? "review" : "confirmed", confidence: 0, isCrossPage: row.is_cross_page, recordVersion: row.record_version, raw: row as unknown as Record<string, unknown> };
}

export const projectApi = {
  async retryExtraction(id: string): Promise<void> { await request(`/api/v1/projects/${id}/extraction/retry`, { method: "POST" }); },
  async watchExtraction(id: string, signal: AbortSignal, changed: () => void, connectivity: (disconnected: boolean) => void): Promise<void> {
    let cursor = -1;
    while (!signal.aborted) {
      try {
        const response = await authenticatedFetch(`/api/v1/projects/${id}/extraction/events?cursor=${cursor}`, { signal, headers: { Accept: "text/event-stream" } });
        if (!response.ok || !response.body) {
          if ([401, 403, 404].includes(response.status)) { changed(); connectivity(true); return; }
          throw new Error("事件流暂不可用");
        }
        connectivity(false);
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
        try {
          while (!signal.aborted) {
            const { value, done } = await reader.read(); if (done) break;
            buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
            let boundary: number;
            while ((boundary = buffer.indexOf("\n\n")) >= 0) {
              const packet = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
              const event = packet.match(/^event: (.+)$/m)?.[1]; const seq = packet.match(/^id: (\d+)$/m)?.[1];
              if (seq) cursor = Number(seq);
              if (event === "refresh" || event === "done") changed();
              if (event === "unavailable") throw new Error("事件流暂不可用");
              if (event === "access_revoked") { connectivity(true); changed(); return; }
              if (event === "done") return;
            }
          }
        } finally { await reader.cancel(); reader.releaseLock(); }
      } catch { if (!signal.aborted) { connectivity(true); changed(); } }
      if (!signal.aborted) await new Promise<void>(resolve => {
        const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
        const timer = setTimeout(finish, 3000); signal.addEventListener("abort", finish, { once: true });
      });
    }
  },
  async rename(id: string, name: string): Promise<void> { await request(`/api/v1/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }); },
  async remove(project: ProjectSummary): Promise<void> { await request(`/api/v1/projects/${project.id}?${new URLSearchParams({ confirmed: "true", expected_updated_at: project.updatedAt })}`, { method: "DELETE" }); },
  async list(): Promise<ProjectSummary[]> { return (await request<Schema["SimpleProjectRead"][]>("/api/v1/projects")).map(summary); },
  async get(id: string): Promise<ProjectDetail> {
    const row = await request<Schema["SimpleProjectRead"]>(`/api/v1/projects/${id}`);
    const workspaces: Workspace[] = (row.workspaces ?? []).map(w => ({ id: w.id, code: w.code ?? w.name, name: w.name, status: "completed" as const, drawings: (w.drawings ?? []).map(drawingFromDb).sort((a, b) => drawingOrder.compare(a.drawingPage, b.drawingPage) || a.pdfPage - b.pdfPage || a.id.localeCompare(b.id)) }));
    workspaces.sort((a, b) => drawingOrder.compare(a.code, b.code) || a.id.localeCompare(b.id));
    return { ...summary(row), processing: row.processing, sourceAvailable: row.source_saved, sourceFilename: row.sources?.[0]?.original_filename ?? "", projectNo: row.id, resultVersion: row.batch_id ? `批次 ${row.batch_id}` : "暂无结果", workspaces };
  },
  async connections(id: string, options: { offset?: number; workspaceId?: string | null; drawingId?: string | null; search?: string; batchId?: string | null } = {}): Promise<ResultPage> {
    const params = new URLSearchParams({ offset: String(options.offset ?? 0), limit: "100" });
    if (options.workspaceId) params.set("workspace_id", options.workspaceId);
    if (options.drawingId) params.set("drawing_id", options.drawingId);
    if (options.search) params.set("search", options.search);
    if (options.batchId) params.set("batch_id", options.batchId);
    const page = await request<Schema["SimpleConnectionPage"]>(`/api/v1/projects/${id}/connections?${params}`);
    return { ...page, items: page.items.map(connection) };
  },
  async drawing(id: string): Promise<Drawing> { return drawingFromDb(await request<Schema["DrawingRead"]>(`/api/v1/drawings/${id}`)); },
  async source(id: string): Promise<string> { return (await request<{ url: string }>(`/api/v1/projects/${id}/source`)).url; },
  async addConnection(id: string, body: Schema["SimpleConnectionCreate"], key: string): Promise<void> { await request(`/api/v1/projects/${id}/connections`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) }); },
  async deleteConnection(id: string, row: WiringRow, key: string): Promise<void> {
    const body: Schema["SimpleConnectionDelete"] = { record_version: row.recordVersion!, confirmed: true };
    await request(`/api/v1/projects/${id}/connections/${row.id}`, { method: "DELETE", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) });
  },
  async target(row: WiringRow): Promise<Drawing> { return drawingFromDb(await request<Schema["DrawingRead"]>(`/api/v1/connections/${row.id}/target`)); },
  async edit(row: WiringRow, _page: ResultPage, changes: Schema["ConnectionFields"], key: string = crypto.randomUUID()): Promise<void> {
    const body: Schema["SimpleConnectionEdit"] = { record_version: row.recordVersion!, changes };
    await request(`/api/v1/connections/${row.id}`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify(body) });
  },
  async listRuleLibrary(): Promise<RuleLibraryItem[]> {
    const rows = await request<Schema["ProfileReferenceRead"][]>("/api/v1/rule-library");
    return rows.map(row => ({ id: row.id, key: row.profile_key, name: row.display_name, version: row.profile_version, summary: `规则引用 · ${row.checksum.slice(7, 19)}`, status: "published", updatedAt: row.created_at ?? "", canDelete: row.can_delete ?? false, isActive: true }));
  },
  async localProfiles(): Promise<ProfileOption[]> { return request("/api/v1/rule-library/local"); },
  async createRule(body: Schema["ProfileReferenceCreate"]): Promise<void> { await request("/api/v1/rule-library", { method: "POST", body: JSON.stringify(body) }); },
  async deleteRule(id: string): Promise<void> { await request(`/api/v1/rule-library/${id}?confirmed=true`, { method: "DELETE" }); },
  async package(id: string): Promise<RulePackage> { return request(`/api/v1/rule-library/${id}`); },
  async upload(file: File, profileKey: string, key: string): Promise<Schema["SimpleImportRead"]> {
    const params = new URLSearchParams({ profile_key: profileKey, project_name: file.name.replace(/\.pdf$/i, ""), filename: file.name });
    return request(`/api/v1/imports?${params}`, { method: "POST", headers: { "Content-Type": "application/pdf", "Idempotency-Key": key }, body: file });
  },
};
