import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import type { WiringRow } from "@/apis/types";

const columns: Array<{ key: keyof WiringRow; label: string; width: number }> = [
  { key: "page", label: "页码", width: 115 }, { key: "wireNumber", label: "线号", width: 80 }, { key: "lineNumber", label: "原理号", width: 112 }, { key: "voltageLevel", label: "电压等级", width: 92 }, { key: "terminalStrip", label: "端子排", width: 80 },
  { key: "startCode", label: "起点代号", width: 116 }, { key: "startDescription", label: "起点描述", width: 180 }, { key: "startTerminal", label: "起点端子", width: 112 },
  { key: "endCode", label: "终点代号", width: 116 }, { key: "endDescription", label: "终点描述", width: 180 }, { key: "endTerminal", label: "终点端子", width: 112 },
  { key: "current", label: "电流", width: 76 }, { key: "remark", label: "备注", width: 180 }, { key: "colorMark", label: "色标", width: 80 },
];

export function ResultTable({ rows, onOpenDrawing, onOpenTarget, onHoverTarget, highlightedRowId, onEdit, onDelete }: { rows: WiringRow[]; onOpenDrawing: (drawingId: string) => void; onOpenTarget: (row: WiringRow) => void; onHoverTarget: (rowId: string | null) => void; highlightedRowId: string | null; onEdit?: (row: WiringRow) => void; onDelete?: (row: WiringRow) => void }) {
  if (!rows.length) return <div className="table-empty"><span>0</span><strong>当前范围没有线表记录</strong><p>请选择包含已提取结果的图纸或工作区。</p></div>;
  return (
    <div className="result-table-shell">
      <table className="result-table">
        <colgroup>{columns.map((column) => <col key={column.key} style={{ width: column.width }} />)}<col style={{ width: 90 }} /></colgroup>
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}<th aria-label="操作" /></tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={row.id} className={`${row.status === "review" ? "review-row" : ""} ${highlightedRowId === row.id ? "target-row" : ""}`}>
            {columns.map((column) => {
              const value = row[column.key];
              if (column.key === "page") return <td key={column.key}>{index === 0 || rows[index - 1].drawingId !== row.drawingId ? <button className="source-link" type="button" onClick={() => onOpenDrawing(row.drawingId)} title="在下方显示来源图纸">{String(value)}<ExternalLink size={13} /></button> : <span className="visually-hidden">{String(value)}</span>}</td>;
              if (column.key === "wireNumber") return <td key={column.key}>{rows.findIndex(item => item.wireNumber === row.wireNumber) === index ? String(value ?? "-") : <span className="visually-hidden">{String(value)}</span>}</td>;
              if (column.key === "endTerminal") return <td key={column.key}>{row.isCrossPage || row.endReference?.kind === "cross-page" ? <button type="button" className="terminal-link" onMouseEnter={() => onHoverTarget(row.id)} onMouseLeave={() => onHoverTarget(null)} onFocus={() => onHoverTarget(row.id)} onBlur={() => onHoverTarget(null)} onClick={() => onOpenTarget(row)} title="在表格下方显示跨页目标">{String(value || "-")}<ExternalLink size={12} /></button> : <span className="terminal-static">{String(value || "-")}</span>}</td>;
              if (column.key === "current") return <td key={column.key}><span className={value ? "current-value" : "empty-value"}>{String(value || "-")}</span></td>;
              return <td key={column.key} title={String(value || "")}>{String(value || "-")}</td>;
            })}
            <td><button type="button" className="row-menu" disabled={!onEdit} aria-label={`编辑 ${row.startTerminal}`} title="编辑记录" onClick={() => onEdit?.(row)}><Pencil size={16} /></button><button type="button" className="row-menu" disabled={!onDelete} aria-label={`删除 ${row.startTerminal}`} title="删除端子（保留审计）" onClick={() => onDelete?.(row)}><Trash2 size={16} /></button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
