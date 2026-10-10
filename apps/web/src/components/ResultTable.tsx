import { ExternalLink, MoreHorizontal } from "lucide-react";
import type { WiringRow } from "@/apis/types";

const columns: Array<{ key: keyof WiringRow; label: string; width: number }> = [
  { key: "page", label: "页码", width: 92 }, { key: "lineNumber", label: "原理号", width: 112 }, { key: "voltageLevel", label: "电压等级", width: 92 },
  { key: "startCode", label: "起点代号", width: 116 }, { key: "startDescription", label: "起点描述", width: 180 }, { key: "startTerminal", label: "起点端子", width: 112 },
  { key: "endCode", label: "终点代号", width: 116 }, { key: "endDescription", label: "终点描述", width: 180 }, { key: "endTerminal", label: "终点端子", width: 112 },
  { key: "current", label: "电流", width: 76 }, { key: "remark", label: "备注", width: 180 },
];

export function ResultTable({ rows, onOpenDrawing, onOpenTarget, onHoverTarget, highlightedRowId }: { rows: WiringRow[]; onOpenDrawing: (drawingId: string) => void; onOpenTarget: (row: WiringRow) => void; onHoverTarget: (rowId: string | null) => void; highlightedRowId: string | null }) {
  if (!rows.length) return <div className="table-empty"><span>0</span><strong>当前范围没有线表记录</strong><p>请选择包含已提取结果的图纸或工作区。</p></div>;
  return (
    <div className="result-table-shell">
      <table className="result-table">
        <colgroup>{columns.map((column) => <col key={column.key} style={{ width: column.width }} />)}<col style={{ width: 58 }} /></colgroup>
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}<th aria-label="操作" /></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={row.id} className={`${row.status === "review" ? "review-row" : ""} ${highlightedRowId === row.id ? "target-row" : ""}`}>
            {columns.map((column) => {
              const value = row[column.key];
              if (column.key === "page") return <td key={column.key}><button className="source-link" type="button" onClick={() => onOpenDrawing(row.drawingId)} title="打开来源图纸">{String(value)}<ExternalLink size={13} /></button></td>;
              if (column.key === "endTerminal") return <td key={column.key}>{row.endReference?.kind === "cross-page" ? <button type="button" className="terminal-link" onMouseEnter={() => onHoverTarget(row.id)} onMouseLeave={() => onHoverTarget(null)} onFocus={() => onHoverTarget(row.id)} onBlur={() => onHoverTarget(null)} onClick={() => onOpenTarget(row)} title={`跳转到目标页 ${row.endReference.targetPage}`}>{String(value || "-")}<ExternalLink size={12} /></button> : <span className="terminal-static">{String(value || "-")}</span>}</td>;
              if (column.key === "current") return <td key={column.key}><span className={value ? "current-value" : "empty-value"}>{String(value || "-")}</span></td>;
              return <td key={column.key} title={String(value || "")}>{String(value || "-")}</td>;
            })}
            <td><button type="button" className="row-menu" aria-label="打开记录菜单" title="记录菜单"><MoreHorizontal size={17} /></button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
