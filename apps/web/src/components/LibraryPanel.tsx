import { BookOpenCheck, Search, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { RuleLibraryItem } from "@/apis/types";
import { RuleResources } from "./RuleResources";
import { projectApi } from "@/apis/projects";
import { skillName } from "@/apis/agents";

export function RuleLibraryPanel({ items, onChanged, asSkills = false }: { items: RuleLibraryItem[]; onChanged: () => Promise<void>; asSkills?: boolean }) {
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const visibleItems = useMemo(() => items.filter((item) => `${item.name} ${item.summary} ${item.key} ${asSkills ? skillName(item.key) : ""}`.toLowerCase().includes(query.toLowerCase())), [items, query, asSkills]);

  async function remove(rule: RuleLibraryItem) {
    if (!window.confirm(`删除规则引用“${rule.name}”？规则文件会保留；已被项目引用时不能删除。`)) return;
    setDeleting(rule.id); setError("");
    try { await projectApi.deleteRule(rule.id); setExpandedId(null); await onChanged(); }
    catch (reason) { setError(String(reason)); }
    finally { setDeleting(null); }
  }

  return (
    <section className="library-panel">
      <header className="library-heading"><div><span className="section-kicker">EXTRACTION SKILLS</span><h2>{asSkills ? "提取 Skills" : "规则库"}</h2><p>读取数据库中已上传的规则包，查看真实版本、Prompt 与样例</p></div><div className="rule-library-actions"><label className="library-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索规则或标准" aria-label="搜索提取规则" /></label></div></header>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      {notice && <p role="status">{notice}</p>}
      <button type="button" className="rule-details-button" disabled={deleting !== null || expandedId !== null} onClick={() => { void onChanged().catch(reason => setError(String(reason))); }}>{asSkills ? "刷新 Skills" : "刷新规则"}</button>
      <div className="rule-list" role="list" aria-label="提取规则列表">
        {visibleItems.map((rule) => (
          <article className="rule-row" key={rule.id} role="listitem">
            <span className={`rule-icon rule-icon-${rule.key}`}><BookOpenCheck size={18} /></span>
            <div className="rule-row-copy"><div><strong>{asSkills ? skillName(rule.key) : rule.name}</strong><span className="rule-status rule-status-published">已上传</span></div><p>{asSkills ? `${rule.name} · ${rule.summary}` : rule.summary}</p><small>版本 {rule.version} · 更新于 {rule.updatedAt}</small></div>
            <button type="button" className="rule-details-button" onClick={() => setExpandedId((current) => current === rule.id ? null : rule.id)} aria-expanded={expandedId === rule.id}>{expandedId === rule.id ? "收起" : "查看规则"}</button>
            {rule.canDelete ? <button type="button" className="rule-details-button" disabled={deleting !== null} onClick={() => void remove(rule)} aria-label={`删除规则包 ${rule.key}`} title="删除规则包"><Trash2 size={15} />{deleting === rule.id ? "删除中…" : "删除"}</button> : null}
            {expandedId === rule.id ? <RuleResources key={rule.id} asSkill={asSkills} rule={asSkills ? { ...rule, name: skillName(rule.key) } : rule} onClose={() => setExpandedId(null)} onChanged={async message => { setNotice(message ?? "规则已更新"); setExpandedId(null); await onChanged(); }} /> : null}
          </article>
        ))}
        {!visibleItems.length ? <div className="library-empty"><Sparkles size={24} /><strong>没有匹配的规则</strong></div> : null}
      </div>
    </section>
  );
}
