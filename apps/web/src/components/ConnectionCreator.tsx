import { Check, Loader2, X } from "lucide-react";
import { useRef, useState, type KeyboardEvent } from "react";
import { projectApi, type ResultPage } from "@/apis/projects";
import { editableConnectionFields, type ConnectionDraft } from "@/apis/connection-fields";
import type { components } from "@/apis/generated";
import type { ProjectDetail } from "@/apis/types";

export function ConnectionCreator({ project, page, defaultDrawingId, workspaceId, disabled, onError: setError, onClose, onSaved }: { project: ProjectDetail; page: ResultPage; defaultDrawingId?: string; workspaceId: string | null; disabled: boolean; onError: (message: string) => void; onClose: () => void; onSaved: () => void }) {
  const drawings = project.workspaces.filter(w => !workspaceId || w.id === workspaceId).flatMap(w => w.drawings);
  const allDrawings = project.workspaces.flatMap(w => w.drawings);
  const [source, setSource] = useState(defaultDrawingId ?? drawings[0]?.id ?? "");
  const [target, setTarget] = useState("");
  const [draft, setDraft] = useState<ConnectionDraft>(() => Object.fromEntries(editableConnectionFields.map(f => [f.key, ""])) as ConnectionDraft);
  const [saving, setSaving] = useState(false);
  const [batch] = useState(page.batch_id ?? "manual");
  const lock = useRef(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  async function save() {
    if (lock.current || disabled) return;
    if (batch !== (page.batch_id ?? "manual")) { setError("结果批次已变化，请取消后重新新增。"); return; }
    if (!source || !draft.start_terminal.trim()) { setError("请选择来源图纸并填写起点端子。"); return; }
    const fields = Object.fromEntries(editableConnectionFields.map(f => [f.key, draft[f.key].trim() || null])) as components["schemas"]["ConnectionFields"];
    const body: components["schemas"]["SimpleConnectionCreate"] = { batch_id: batch, source_drawing_id: source, target_drawing_id: target || null, fields };
    const fingerprint = JSON.stringify(body);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    lock.current = true; setSaving(true); setError("");
    try { await projectApi.addConnection(project.id, body, submission.current.key); onSaved(); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "新增失败，请重试"); }
    finally { lock.current = false; setSaving(false); }
  }
  function keyboard(event: KeyboardEvent) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Enter") { event.preventDefault(); void save(); }
    if (event.key === "Escape" && !lock.current) { event.preventDefault(); onClose(); }
  }
  return <>
    <tr className="editing-row new-connection-row" aria-label="新增端子草稿" onKeyDown={keyboard}>
      <td className="editing-cell"><select aria-label="新增来源图纸" value={source} onChange={event => setSource(event.target.value)} disabled={saving || disabled}>{drawings.map(d => <option key={d.id} value={d.id}>{d.drawingPage} · PDF {d.pdfPage}</option>)}</select><select aria-label="新增跨页目标" value={target} onChange={event => setTarget(event.target.value)} disabled={saving || disabled}><option value="">同页 / 未确认</option>{allDrawings.map(d => <option key={d.id} value={d.id}>{d.drawingPage} · PDF {d.pdfPage}</option>)}</select></td>
      {editableConnectionFields.map(f => <td key={f.key} className="editing-cell"><input aria-label={`新增${f.label}`} placeholder={f.key === "start_terminal" ? "填写端子" : ""} autoFocus={f.key === "start_terminal"} value={draft[f.key]} maxLength={f.maxLength} disabled={saving || disabled} onChange={event => setDraft(current => ({ ...current, [f.key]: event.target.value }))} /></td>)}
      <td className="row-actions"><span className="row-state">新端子</span><button type="button" className="row-menu inline-save" aria-label="保存新增端子" title="保存新增端子（Enter）" disabled={saving || disabled} onClick={() => void save()}>{saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}</button><button type="button" className="row-menu" aria-label="取消新增端子" title="取消新增端子（Esc）" disabled={saving || disabled} onClick={onClose}><X size={16} /></button></td>
    </tr>
  </>;
}
