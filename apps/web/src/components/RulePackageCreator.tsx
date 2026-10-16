import { useEffect, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type ProfileOption } from "@/apis/projects";

export function RulePackageCreator({ onClose, onCreated }: { onClose: () => void; onCreated: () => Promise<void> }) {
  const [options, setOptions] = useState<ProfileOption[] | null>(null);
  const [selected, setSelected] = useState(""); const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  useEffect(() => { let active = true; projectApi.localProfiles().then(rows => { if (active) { setOptions(rows); setSelected(rows[0]?.profile_key ?? ""); } }).catch(reason => { if (active) setError(String(reason)); }); return () => { active = false; }; }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try { await projectApi.createRule({ profile_key: selected }); await onCreated(); onClose(); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="register-rule-title"><header><h2 id="register-rule-title">登记规则引用</h2><button type="button" disabled={saving} onClick={onClose} aria-label="关闭规则登记"><X size={18} /></button></header><form className="edit-grid" onSubmit={submit}><p>选择已配置的本地规则，保存其版本和资源引用。</p><label>本地规则<select aria-label="本地规则" value={selected} onChange={event => setSelected(event.target.value)} disabled={saving || options === null} required>{options?.map(option => <option key={option.profile_key} value={option.profile_key}>{option.display_name} · {option.profile_version}</option>)}</select></label>{options === null && !error ? <p role="status">正在读取本地规则…</p> : options?.length === 0 ? <p>暂无资源完整的本地规则。</p> : null}{error ? <p role="alert">{error}</p> : null}<footer><button type="button" disabled={saving} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={!selected || saving}>{saving ? "正在登记…" : "登记"}</button></footer></form></section></div>;
}
