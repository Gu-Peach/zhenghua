import { useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type ResultPage } from "@/apis/projects";
import type { components } from "@/apis/generated";
import type { WiringRow } from "@/apis/types";

const fields = [{ key: "principle_number", label: "原理号", view: "lineNumber" }, { key: "voltage_level", label: "电压等级（同线号共享）", view: "voltageLevel" }, { key: "terminal_strip", label: "端子排（同线号共享）", view: "terminalStrip" }, { key: "start_code", label: "起点代号", view: "startCode" }, { key: "start_description", label: "起点描述", view: "startDescription" }, { key: "start_terminal", label: "起点端子", view: "startTerminal" }, { key: "end_code", label: "终点代号", view: "endCode" }, { key: "end_description", label: "终点描述", view: "endDescription" }, { key: "end_terminal", label: "终点端子", view: "endTerminal" }, { key: "current_value", label: "电流", view: "current" }, { key: "remark", label: "备注", view: "remark" }, { key: "color_mark", label: "色标", view: "colorMark" }] as const;

export function ConnectionEditor({ row, page, onClose, onSaved }: { row: WiringRow; page: ResultPage; onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setSaving(true); setError("");
    const data = new FormData(e.currentTarget);
    const changes: components["schemas"]["ConnectionFields"] = {};
    for (const f of fields) { const value = String(data.get(f.key) ?? "").trim(); if (value !== (row[f.view] ?? "")) changes[f.key] = value || null; }
    const fingerprint = JSON.stringify(changes);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    try { await projectApi.edit(row, page, changes, submission.current.key); onSaved(); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); }
    finally { setSaving(false); }
  }
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="edit-heading"><header><h2 id="edit-heading">编辑连接 · 线号 {row.wireNumber} · {row.startTerminal}</h2><button disabled={saving} type="button" onClick={onClose} aria-label="关闭编辑"><X size={18} /></button></header><form className="edit-grid" onSubmit={submit}>{fields.map(f => <label key={f.key}>{f.label}<input name={f.key} defaultValue={row[f.view] ?? ""} maxLength={f.key.includes("description") || f.key === "remark" ? 4000 : f.key === "voltage_level" || f.key === "terminal_strip" || f.key === "color_mark" || f.key === "current_value" ? 100 : 500} /></label>)}<p>保存将原位更新并保留审计。电压等级与端子排属于线号单元，修改会作用于同线号的所有记录；页码和线号作为来源索引不可在此改写。如果其他任务已修改结果，需刷新后重新编辑。</p>{error ? <p role="alert" className="form-error">{error}</p> : null}<footer><button type="button" onClick={onClose} disabled={saving}>取消</button><button type="submit" className="primary-button" disabled={saving}>{saving ? "保存中…" : "确认保存"}</button></footer></form></section></div>;
}
