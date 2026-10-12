import { useEffect, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { projectApi, type RulePackage } from "@/apis/projects";
import type { components } from "@/apis/generated";
import type { RuleLibraryItem } from "@/apis/types";

const stages = [
  { key: "classification_prompt", label: "Stage 1 页面分类 Prompt" },
  { key: "page_scan_prompt", label: "Stage 2 当前页扫描 Prompt" },
  { key: "cross_page_prompt", label: "Stage 3 跨页补全 Prompt" },
] as const;

export function RulePackageCreator({ items, onClose, onCreated }: { items: RuleLibraryItem[]; onClose: () => void; onCreated: () => Promise<void> }) {
  const templates = items.filter(item => item.isActive);
  const [baseId, setBaseId] = useState(templates[0]?.id ?? "");
  const [resource, setResource] = useState<RulePackage | null>(null);
  const [error, setError] = useState(""); const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    if (baseId) projectApi.package(baseId).then(value => { if (active) setResource(value); }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [baseId, retry]);
  return <div className="modal-backdrop"><section className="resource-modal rule-create-modal" role="dialog" aria-modal="true" aria-labelledby="rule-create-heading">
    <header><h2 id="rule-create-heading">新建规则包</h2><button type="button" disabled={saving} onClick={onClose} aria-label="关闭新建规则包"><X size={18} /></button></header>
    <div className="rule-create-body">
      <p>基于已发布模板建立独立规则包，继承图片样例、预期答案和提取算法。创建后立即注册给 Agent，用于新任务。</p>
      {!templates.length ? <p>没有可用的规则模板，请先发布一个完整的规则包。</p> : <>
        <label>规则模板<select aria-label="规则模板" value={baseId} disabled={saving} onChange={event => { setBaseId(event.target.value); setResource(null); setError(""); }}>{templates.map(item => <option key={item.id} value={item.id}>{item.name} · {item.version}</option>)}</select></label>
        {error ? <p role="alert">{error}<button type="button" onClick={() => { setError(""); setRetry(n => n + 1); }}>重新读取模板</button></p> : resource === null ? <p role="status">正在读取模板资源…</p> : <RuleForm key={baseId} baseId={baseId} resource={resource} onCreated={onCreated} onClose={onClose} saving={saving} setSaving={setSaving} />}
      </>}
    </div>
  </section></div>;
}

function RuleForm({ baseId, resource, onCreated, onClose, saving, setSaving }: { baseId: string; resource: RulePackage; onCreated: () => Promise<void>; onClose: () => void; saving: boolean; setSaving: (value: boolean) => void }) {
  const [error, setError] = useState("");
  let resources: Record<string, string> = {}; let detection: { summary?: string; strong_signals?: string[] } = {};
  try {
    resources = JSON.parse(resource.files.find(file => file.path === "profile.json")?.content ?? "{}").resources ?? {};
    detection = JSON.parse(resource.files.find(file => file.path === resources.routing_rules)?.content ?? "{}").detection ?? {};
  } catch { /* Incomplete templates cannot submit; Agent validates the complete package. */ }
  const prompts = stages.map(stage => ({ ...stage, content: resource.files.find(file => file.path === resources[stage.key])?.content }));
  const complete = prompts.every(prompt => prompt.content !== undefined);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSaving(true);
    const form = new FormData(event.currentTarget);
    const body: components["schemas"]["RuleCreate"] = {
      base_package_id: baseId, profile_key: String(form.get("profile_key")).trim(), display_name: String(form.get("display_name")).trim(), description: String(form.get("description") ?? ""),
      detection_summary: String(form.get("detection_summary")).trim(), strong_signals: String(form.get("strong_signals")).split(/\r?\n/).map(signal => signal.trim()).filter(Boolean),
      prompts: Object.fromEntries(stages.map(stage => [stage.key, String(form.get(stage.key))])), confirmed: true,
    };
    try { await projectApi.createRule(body); await onCreated(); onClose(); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <form className="rule-create-form" onSubmit={submit}>
    <label>规则标识<input name="profile_key" required maxLength={64} pattern="[a-z][a-z0-9_-]*" placeholder="例如 custom-zh" disabled={saving} /></label>
    <label>规则名称<input name="display_name" required maxLength={200} disabled={saving} /></label>
    <label>说明<textarea name="description" maxLength={4000} rows={2} disabled={saving} /></label>
    <label>识别说明<textarea name="detection_summary" defaultValue={detection.summary} required maxLength={4000} rows={3} disabled={saving} /></label>
    <label>识别特征（每行一条）<textarea name="strong_signals" defaultValue={detection.strong_signals?.join("\n")} required rows={3} disabled={saving} /></label>
    {prompts.map(stage => <details key={stage.key}><summary>{stage.label}</summary><textarea aria-label={stage.label} name={stage.key} defaultValue={stage.content} maxLength={100000} rows={10} required disabled={saving} /></details>)}
    {!complete ? <p role="alert">模板缺少三阶段 Prompt，无法创建。</p> : null}
    <label className="rule-confirm"><input type="checkbox" required disabled={saving} />确认创建并注册为可用规则包</label>
    {error ? <p role="alert" className="form-error">{error}</p> : null}
    <footer><button type="button" disabled={saving} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={saving || !complete}>{saving ? "正在保存并注册…" : "创建并注册"}</button></footer>
  </form>;
}
