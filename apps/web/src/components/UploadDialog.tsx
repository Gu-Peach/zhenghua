import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type ProfileOption } from "@/apis/projects";

export function UploadDialog({ file, onClose, onSaved }: { file: File; onClose: () => void; onSaved: (id: string) => void }) {
  const [options, setOptions] = useState<ProfileOption[] | null>(null);
  const [selected, setSelected] = useState(""); const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  const submission = useRef<{ key: string; profile: string } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { let active = true; projectApi.publishedProfiles().then(rows => { if (active) { setOptions(rows); setError(""); } }).catch(reason => { if (active) setError(String(reason)); }); return () => { active = false; }; }, [retry]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    if (submission.current?.profile !== selected) submission.current = { key: crypto.randomUUID(), profile: selected };
    try { const response = await projectApi.upload(file, selected, submission.current.key); onSaved(response.project_id); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="upload-heading"><header><h2 id="upload-heading">保存 PDF</h2><button type="button" disabled={saving} onClick={onClose} aria-label="关闭上传"><X size={18} /></button></header><form className="edit-grid" onSubmit={submit}><p title={file.name} style={{ overflowWrap: "anywhere" }}>{file.name}</p><p>文件保存成功后将自动拆页并提取线表，处理结果逐步显示。</p><label>图纸规则<select aria-label="图纸规则" value={selected} onChange={event => setSelected(event.target.value)} disabled={saving || options === null} required><option value="" disabled>请选择图纸规则</option>{options?.map(option => <option key={option.profile_key} value={option.profile_key}>{option.display_name} · {option.profile_version}</option>)}</select></label>{options === null && !error ? <p role="status">正在读取规则…</p> : options?.length === 0 ? <p>没有已上传的规则包，请先在规则配置智能体中发布规则。</p> : null}{error ? <p role="alert">{error}{options === null ? <button type="button" onClick={() => setRetry(n => n + 1)}>重试读取规则</button> : null}</p> : null}<footer><button type="button" disabled={saving} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={saving || !selected || file.size > 200 * 1024 * 1024}>{saving ? "正在保存 PDF…" : "保存到项目"}</button></footer>{file.size > 200 * 1024 * 1024 ? <p role="alert">文件超过200MB限制。</p> : null}</form></section></div>;
}
