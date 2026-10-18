import type { Drawing, WiringRow } from "./types";

export interface DrawingMarker { kind: "start" | "end"; x: number; y: number; label: string }
export function previewConnectionKey(row: WiringRow | null): string {
  return JSON.stringify(row ? [row.id, row.recordVersion, row.drawingId, row.startTerminal, row.endTerminal,
    row.startTerminalCoordinates, row.endTerminalCoordinates, row.raw?.target_pdf_page_number, row.raw?.target_drawing_page] : null);
}
export function drawingEvidence(row: WiringRow | null, drawing: Drawing | null, role: "source" | "target") {
  const markers: DrawingMarker[] = []; const notes: string[] = [];
  if (!row || !drawing) return { markers, notes };
  const endpoints = [
    { kind: "start" as const, point: row.startTerminalCoordinates, label: `起点 ${row.startTerminal || "未确认"}`, required: role === "source" },
    { kind: "end" as const, point: row.endTerminalCoordinates, label: `终点 ${row.endTerminal || "未确认"}`, required: role === "target" || !row.isCrossPage },
  ];
  for (const endpoint of endpoints) {
    const point = endpoint.point;
    if (!point) { if (endpoint.required) notes.push(`${endpoint.label}未保存坐标`); continue; }
    const valid = Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1;
    if (!valid) { if (endpoint.required) notes.push(`${endpoint.label}坐标无效，未标注`); continue; }
    if (point.pdf_page_number !== drawing.pdfPage) {
      const knownPages = [row.raw?.pdf_page_number, row.raw?.target_pdf_page_number];
      if (endpoint.required && !knownPages.includes(point.pdf_page_number)) notes.push(`${endpoint.label}坐标所属PDF页不匹配，未标注`);
      continue;
    }
    markers.push({ kind: endpoint.kind, label: endpoint.label, x: point.x, y: point.y });
  }
  return { markers, notes };
}
