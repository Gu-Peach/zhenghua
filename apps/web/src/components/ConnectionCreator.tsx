import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type ResultPage, type WiringUnit } from "@/apis/projects";
import type { components } from "@/apis/generated";
import type { ProjectDetail } from "@/apis/types";

const fields = [{ key: "start_terminal", label: "起点端子" }, { key: "end_terminal", label: "终点端子" }, { key: "principle_number", label: "原理号" }, { key: "start_code", label: "起点代号" }, { key: "start_description", label: "起点描述" }, { key: "end_code", label: "终点代号" }, { key: "end_description", label: "终点描述" }, { key: "current_value", label: "电流" }, { key: "remark", label: "备注" }, { key: "color_mark", label: "色标" }] as const;

export function ConnectionCreator({ project, page, onClose, onSaved }: { project: ProjectDetail; page: ResultPage; onClose: () => void; onSaved: () => void }) {
  const [units, setUnits] = useState<WiringUnit[] | null>(null); const [error, setError] = useState("");
  useEffect(() => { let active = true; projectApi.units(project.id).then(list => { if (active) setUnits(list); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [project.id]);
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="create-heading"><header><h2 id="create-heading">新增端子</h2><button type="button" onClick={onClose} aria-label="关闭新增端子"><X size={18} /></button></header>{error ? <p role="alert">{error}</p> : units === null ? <p>正在读取当前线号…</p> : !units.length ? <p>当前结果没有线号单元。请先完成提取，不能猜测或重新编号线号。</p> : <CreateForm project={project} page={page} units={units} onClose={onClose} onSaved={onSaved} />}</section></div>;
}

function CreateForm({ project, page, units, onClose, onSaved }: { project: ProjectDetail; page: ResultPage; units: WiringUnit[]; onClose: () => void; onSaved: () => void }) {
  const [unitId, setUnitId] = useState(units[0].id);
  const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  const unit = units.find(u => u.id === unitId)!;
  const sources = project.workspaces.find(w => w.id === unit.workspace_id)?.drawings ?? [];
  const targets = project.workspaces.flatMap(w => w.drawings.map(d => ({ ...d, workspaceCode: w.code })));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    const form = new FormData(event.currentTarget);
    const values: components["schemas"]["ConnectionFields"] = {};
    for (const field of fields) values[field.key] = String(form.get(field.key) ?? "").trim() || null;
    const body: components["schemas"]["ConnectionCreate"] = { result_version_id: page.result_version_id!, result_revision: page.result_revision!, wiring_unit_id: unitId, source_drawing_id: String(form.get("source_drawing_id")), target_drawing_id: String(form.get("target_drawing_id") ?? "") || null, fields: values };
    const fingerprint = JSON.stringify(body);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    try { await projectApi.addConnection(project.id, body, submission.current.key); onSaved(); onClose(); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <form className="edit-grid" onSubmit={submit}>
    <label>所属线号<select aria-label="所属线号" value={unitId} onChange={e => setUnitId(e.target.value)} disabled={saving}>{units.map(u => <option key={u.id} value={u.id}>{u.wire_number} · {u.terminal_strip ?? "未填写端子排"}</option>)}</select></label>
    <label>来源图纸<select aria-label="来源图纸" key={unitId} name="source_drawing_id" required disabled={saving} defaultValue={unit.drawing_id ?? sources[0]?.id}>{sources.map(d => <option key={d.id} value={d.id}>{d.drawingPage} · PDF {d.pdfPage}</option>)}</select></label>
    <label>跨页目标（可选）<select aria-label="跨页目标（可选）" name="target_drawing_id" disabled={saving} defaultValue=""><option value="">同页 / 未指定</option>{targets.map(d => <option key={d.id} value={d.id}>{d.workspaceCode}/{d.drawingPage} · PDF {d.pdfPage}</option>)}</select></label>
    <p>挂入既有线号，不改变其他端子。电压等级：{unit.voltage_level ?? "空"}；端子排：{unit.terminal_strip ?? "空"}。跨页必须明确选择目标页，终点留空会标为待复核。</p>
    {fields.map(field => <label key={field.key}>{field.label}<input name={field.key} required={field.key === "start_terminal"} disabled={saving} maxLength={field.key.includes("description") || field.key === "remark" ? 4000 : 100} /></label>)}
    {error ? <p role="alert" className="form-error">{error}</p> : null}<footer><button type="button" onClick={onClose} disabled={saving}>取消</button><button type="submit" className="primary-button" disabled={saving || !sources.length}>{saving ? "保存中…" : "确认新增"}</button></footer>
  </form>;
}
