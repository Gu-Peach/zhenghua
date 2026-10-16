import { Check, ExternalLink, Loader2, Pencil, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { changedConnectionFields, connectionDraft, editableConnectionFields, type ConnectionChanges, type ConnectionDraft, type EditableConnectionKey } from "@/apis/connection-fields";
import type { WiringRow } from "@/apis/types";

const columns: Array<{ key: keyof WiringRow; label: string; width: number }> = [
  { key: "page", label: "页码", width: 115 }, { key: "wireNumber", label: "线号", width: 80 }, { key: "lineNumber", label: "原理号", width: 112 }, { key: "voltageLevel", label: "电压等级", width: 92 }, { key: "terminalStrip", label: "端子排", width: 80 },
  { key: "startCode", label: "起点代号", width: 116 }, { key: "startDescription", label: "起点描述", width: 180 }, { key: "startTerminal", label: "起点端子", width: 112 },
  { key: "endCode", label: "终点代号", width: 116 }, { key: "endDescription", label: "终点描述", width: 180 }, { key: "endTerminal", label: "终点端子", width: 112 },
  { key: "current", label: "电流", width: 76 }, { key: "remark", label: "备注", width: 180 }, { key: "colorMark", label: "色标", width: 80 },
];

type SaveRow = (row: WiringRow, changes: ConnectionChanges, idempotencyKey: string) => Promise<void>;
type RowEditor = { row: WiringRow; draft: ConnectionDraft; focus: EditableConnectionKey; save: SaveRow };

export function ResultTable({ rows, onOpenDrawing, onOpenTarget, onHoverTarget, highlightedRowId, onSave, onRefresh, onDelete }: { rows: WiringRow[]; onOpenDrawing: (drawingId: string) => void; onOpenTarget: (row: WiringRow) => void; onHoverTarget: (rowId: string | null) => void; highlightedRowId: string | null; onSave?: SaveRow; onRefresh?: () => void; onDelete?: (row: WiringRow) => void }) {
  const [editor, setEditor] = useState<RowEditor | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const savingLock = useRef(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);

  function beginEdit(row: WiringRow, focus: EditableConnectionKey = "start_terminal") {
    if (!onSave || editor || savingLock.current || !row.recordVersion) return;
    submission.current = null;
    setError("");
    // Freeze the baseline and callback, including the parent's revision at edit start.
    setEditor({ row, draft: connectionDraft(row), focus, save: onSave });
  }
  function cancel() {
    if (savingLock.current) return;
    setEditor(null); setError(""); submission.current = null;
  }
  async function save() {
    if (!editor || savingLock.current) return;
    const changes = changedConnectionFields(editor.row, editor.draft);
    if (!Object.keys(changes).length) { cancel(); return; }
    const fingerprint = JSON.stringify(changes);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    savingLock.current = true; setSaving(true); setError("");
    try { await editor.save(editor.row, changes, submission.current.key); setEditor(null); submission.current = null; }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败，请重试"); }
    finally { savingLock.current = false; setSaving(false); }
  }
  const editorVisible = editor && rows.some(row => row.id === editor.row.id);
  if (!rows.length && !editor) return <div className="table-empty"><span>0</span><strong>当前范围没有线表记录</strong><p>请选择包含已提取结果的图纸或工作区。</p></div>;
  return (
    <div className="inline-table">
      {editor ? <div className="table-edit-notice" role="status">{saving ? "正在保存…" : "表格编辑中 · Enter 保存 · Esc 取消"}<span>修改仅应用于本行，并保留修改前后记录</span></div> : null}
      {editor && !editorVisible ? <div className="table-edit-error" role="alert"><span>正在编辑的记录已不在当前结果中。</span><button type="button" disabled={saving} onClick={() => { cancel(); onRefresh?.(); }}>取消本次编辑</button></div> : null}
      {error ? <div className="table-edit-error" role="alert"><span>{error}</span>{onRefresh ? <button type="button" disabled={saving} onClick={() => { cancel(); onRefresh(); }}>取消编辑并刷新</button> : null}</div> : null}
    <div className="result-table-shell">
      <table className="result-table">
        <colgroup>{columns.map((column) => <col key={column.key} style={{ width: column.width }} />)}<col style={{ width: 90 }} /></colgroup>
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}<th aria-label="操作" /></tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={row.id} className={`${row.status === "review" ? "review-row" : ""} ${highlightedRowId === row.id ? "target-row" : ""} ${editor?.row.id === row.id ? "editing-row" : ""}`}>
            {columns.map((column) => {
              const value = row[column.key];
              const field = editableConnectionFields.find(item => item.view === column.key);
              if (editor?.row.id === row.id && field) return <td key={column.key} className="editing-cell"><input aria-label={field.label} title={field.shared ? `${field.label}（同线号共享）` : field.label} value={editor.draft[field.key]} maxLength={field.maxLength} disabled={saving} autoFocus={editor.focus === field.key} onFocus={event => event.currentTarget.select()} onChange={event => { const value = event.target.value; setEditor(current => current ? { ...current, draft: { ...current.draft, [field.key]: value } } : null); }} onKeyDown={event => { if (event.nativeEvent.isComposing) return; if (event.key === "Enter") { event.preventDefault(); void save(); } if (event.key === "Escape") { event.preventDefault(); cancel(); } }} /></td>;
              const cellProps = { className: field && onSave ? "editable-cell" : undefined, onDoubleClick: () => { if (field) beginEdit(row, field.key); } };
              if (column.key === "page") return <td key={column.key}>{index === 0 || rows[index - 1].drawingId !== row.drawingId ? <button className="source-link" type="button" onClick={() => onOpenDrawing(row.drawingId)} title="在下方显示来源图纸">{String(value)}<ExternalLink size={13} /></button> : <span className="visually-hidden">{String(value)}</span>}</td>;
              if (column.key === "wireNumber") return <td key={column.key}>{rows.findIndex(item => item.wireNumber === row.wireNumber) === index ? String(value ?? "-") : <span className="visually-hidden">{String(value)}</span>}</td>;
              if (column.key === "endTerminal") return <td key={column.key} {...cellProps}>{row.isCrossPage || row.endReference?.kind === "cross-page" ? <button type="button" className="terminal-link" onMouseEnter={() => onHoverTarget(row.id)} onMouseLeave={() => onHoverTarget(null)} onFocus={() => onHoverTarget(row.id)} onBlur={() => onHoverTarget(null)} onClick={() => onOpenTarget(row)} title="在表格下方显示跨页目标">{String(value || "-")}<ExternalLink size={12} /></button> : <span className="terminal-static">{String(value || "-")}</span>}</td>;
              if (column.key === "current") return <td key={column.key} {...cellProps}><span className={value ? "current-value" : "empty-value"}>{String(value || "-")}</span></td>;
              return <td key={column.key} {...cellProps} title={String(value || "")}>{String(value || "-")}</td>;
            })}
            <td className="row-actions">{editor?.row.id === row.id ? <><button type="button" className="row-menu inline-save" disabled={saving} aria-label="保存本行修改" title="保存本行修改（Enter）" onClick={() => void save()}>{saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}</button><button type="button" className="row-menu" disabled={saving} aria-label="取消本行修改" title="取消本行修改（Esc）" onClick={cancel}><X size={16} /></button></> : <><button type="button" className="row-menu" disabled={!onSave || !!editor || !row.recordVersion} aria-label={`编辑 ${row.startTerminal}`} title="在表格内编辑" onClick={() => beginEdit(row)}><Pencil size={16} /></button><button type="button" className="row-menu" disabled={!onDelete || !!editor} aria-label={`删除 ${row.startTerminal}`} title="删除端子（保留审计）" onClick={() => onDelete?.(row)}><Trash2 size={16} /></button></>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
    </div>
  );
}
