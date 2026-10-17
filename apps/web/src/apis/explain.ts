import { sse } from "./agent";
import type { components } from "./generated";
import type { WiringRow } from "./types";

type Schema = components["schemas"];
export type ExplainEvent = Schema["ExplainEvent"];
export type ExplainResponse = Schema["ExplainResponse"];
export type ToolActivity = Schema["ToolActivity"];
export type ExplainContext = Schema["ExplainContext"] | Schema["SearchResult"];
export interface ExplainSelection {
  title: string;
  scope: "row" | "page";
  connectionId?: string;
  query?: Schema["ConnectionQuery"];
  batchId?: string;
  recordVersion?: number;
}
export interface EvidenceDrawing { key: string; title: string; role: string; url?: string; pdfPage: number }
export interface ToolResultView { summary: string; connections: Array<{ id: string; number: string; start: string; end: string }>; pages: string[]; gaps: string[]; json: string }

export function explainSelection(row: WiringRow, scope: "row" | "page", batchId?: string | null): ExplainSelection {
  const pdfPage = typeof row.raw?.pdf_page_number === "number" ? row.raw.pdf_page_number : undefined;
  return {
    scope, title: scope === "page" ? `${row.page} · 本页端子` : `${row.startTerminal || row.lineNumber || "连接"} → ${row.endTerminal || "待确认"}`,
    connectionId: scope === "row" ? row.id : undefined,
    query: scope === "page" ? { drawing_page: row.page, offset: 0, limit: 50, ...(pdfPage ? { pdf_page_number: pdfPage } : {}) } : undefined,
    batchId: batchId ?? undefined, recordVersion: scope === "row" ? row.recordVersion : undefined,
  };
}

export async function* streamExplanation(selection: ExplainSelection, projectId: string, conversationId: string, turnId: string, message: string, signal: AbortSignal): AsyncGenerator<ExplainEvent> {
  const body: Schema["ExplainTurn"] = {
    project_id: projectId, connection_id: selection.connectionId, query: selection.query,
    batch_id: selection.batchId, record_version: selection.recordVersion,
    conversation_id: conversationId, turn_id: turnId, message,
  };
  let completed = false;
  for await (const frame of sse("/api/v1/explain/turns/stream", { method: "POST", body: JSON.stringify(body), signal })) {
    if (frame.event === "error") {
      const data = frame.data as { message?: string; detail?: { message?: string } };
      throw new Error(data.message ?? data.detail?.message ?? "解释服务暂不可用，请重试。");
    }
    const event = frame.data as ExplainEvent;
    if (!event || typeof event !== "object" || !event.type) continue;
    if (event.conversation_id !== conversationId || event.turn_id !== turnId) throw new Error("解释响应不属于当前会话。");
    completed ||= event.type === "completed";
    yield event;
    if (completed) return;
  }
  if (!signal.aborted && !completed) throw new Error("连接已中断，解释尚未完成。可重试获取资料。");
}

const roleNames = { source: "原页", target: "跨页目标", reference: "引用候选页" };
export function evidenceDrawings(context: ExplainContext | ExplainResponse): EvidenceDrawing[] {
  return (context.drawings ?? []).map(drawing => ({
    key: String(drawing.pdf_page_number), pdfPage: drawing.pdf_page_number,
    title: `${drawing.drawing_page || "未登记业务页"} · PDF ${drawing.pdf_page_number}`,
    role: roleNames[drawing.role],
    url: drawing.image_url && /^(https?:\/\/|\/)/.test(drawing.image_url) ? drawing.image_url : undefined,
  }));
}

export function toolLabel(tool: ToolActivity): string {
  if (tool.name === "load_connection") return "读取端子连接及来源证据";
  if (tool.name === "view_drawings") return `查看图纸 · PDF ${Array.isArray(tool.arguments?.pdf_page_numbers) ? tool.arguments.pdf_page_numbers.join("、") : ""}`;
  if (tool.name === "search_connections") {
    const page = tool.arguments?.drawing_page ?? tool.arguments?.target_drawing_page;
    return page ? `检索 ${String(page)} 的连接与跨页图纸` : "检索连接与关联图纸";
  }
  return "检查工具请求";
}

export function toolResultView(tool: ToolActivity): ToolResultView {
  const data = (tool.result ?? {}) as Record<string, unknown>;
  const rows = (Array.isArray(data.rows) ? data.rows : data.row ? [data] : []) as Schema["ExplainContext"][];
  const drawings = (Array.isArray(data.drawings) ? data.drawings : []) as Schema["DrawingEvidence"][];
  const gaps = (Array.isArray(data.gaps) ? data.gaps : []) as string[];
  return {
    summary: tool.error ?? (tool.result ? tool.name === "view_drawings" ? `已读取 ${Array.isArray(data.visual_pages) ? data.visual_pages.length : 0} 张图纸` : `返回 ${rows.length} 条连接 · ${drawings.length} 张图纸${data.has_more ? " · 还有后续记录" : ""}` : "正在处理…"),
    connections: rows.filter(item => item?.row).map(({ row }) => ({ id: row.id, number: row.principle_number || row.wire_number || "未登记编号", start: row.start_terminal || "未确认", end: row.end_terminal || "未确认" })),
    pages: drawings.map(item => `${roleNames[item.role]} ${item.drawing_page || ""}（PDF ${item.pdf_page_number}）`),
    gaps, json: JSON.stringify(data, null, 2),
  };
}
