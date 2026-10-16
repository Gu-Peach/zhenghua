import { useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type ResultPage } from "@/apis/projects";
import { editableConnectionFields } from "@/apis/connection-fields";
import type { components } from "@/apis/generated";
import type { ProjectDetail } from "@/apis/types";

export function ConnectionCreator({ project, page, onClose, onSaved }: { project: ProjectDetail; page: ResultPage; onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  const drawings = project.workspaces.flatMap(workspace => workspace.drawings.map(d => ({ ...d, workspace: workspace.name })));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    const form = new FormData(event.currentTarget);
    const fields: components["schemas"]["ConnectionFields"] = {};
    for (const field of editableConnectionFields) fields[field.key] = String(form.get(field.key) ?? "").trim() || null;
    const body: components["schemas"]["SimpleConnectionCreate"] = { batch_id: String(form.get("batch_id")), source_drawing_id: String(form.get("source_drawing_id")), target_drawing_id: String(form.get("target_drawing_id") ?? "") || null, wire_number: String(form.get("wire_number") ?? "").trim() || null, fields };
    const fingerprint = JSON.stringify(body);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    try { await projectApi.addConnection(project.id, body, submission.current.key); onSaved(); onClose(); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="create-heading"><header><h2 id="create-heading">新增连接</h2><button type="button" disabled={saving} onClick={onClose} aria-label="关闭新增连接"><X size={18} /></button></header>{!drawings.length ? <p>项目尚无图纸索引，暂不能新增连接。上传原始 PDF 不会自动生成提取结果。</p> : <form className="edit-grid" onSubmit={submit}><label>结果批次<input name="batch_id" defaultValue={page.batch_id ?? "manual"} maxLength={200} required disabled={saving} /></label><label>线号（可留空）<input name="wire_number" maxLength={200} disabled={saving} /></label><label>来源图纸<select name="source_drawing_id" aria-label="来源图纸" required disabled={saving}>{drawings.map(d => <option value={d.id} key={d.id}>{d.workspace} / {d.drawingPage} · PDF {d.pdfPage}</option>)}</select></label><label>跨页目标（可选）<select name="target_drawing_id" aria-label="跨页目标（可选）" disabled={saving}><option value="">同页 / 未确认</option>{drawings.map(d => <option value={d.id} key={d.id}>{d.workspace} / {d.drawingPage} · PDF {d.pdfPage}</option>)}</select></label>{editableConnectionFields.map(field => <label key={field.key}>{field.label}<input name={field.key} required={field.key === "start_terminal"} maxLength={field.maxLength} disabled={saving} /></label>)}{error ? <p role="alert">{error}</p> : null}<footer><button type="button" disabled={saving} onClick={onClose}>取消</button><button type="submit" disabled={saving} className="primary-button">{saving ? "正在保存…" : "保存连接"}</button></footer></form>}</section></div>;
}
