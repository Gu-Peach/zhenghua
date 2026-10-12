import { BookOpenCheck, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { RuleLibraryItem } from "@/apis/types";
import { RuleResources } from "./RuleResources";
import { RulePackageCreator } from "./RulePackageCreator";
import { projectApi } from "@/apis/projects";

export function RuleLibraryPanel({ items, onChanged }: { items: RuleLibraryItem[]; onChanged: () => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState("");
  const visibleItems = useMemo(() => items.filter((item) => `${item.name} ${item.summary} ${item.key}`.toLowerCase().includes(query.toLowerCase())), [items, query]);

  async function remove(rule: RuleLibraryItem) {
    if (!window.confirm(`删除规则包“${rule.name}”？Agent 将不再为新任务选择它，已处理项目使用的历史资源会保留。`)) return;
    setDeleting(rule.id); setError("");
    try { await projectApi.deleteRule(rule.id); setExpandedId(null); await onChanged(); }
    catch (reason) { setError(String(reason)); }
    finally { setDeleting(null); }
  }

  return (
    <section className="library-panel">
      <header className="library-heading"><div><span className="section-kicker">EXTRACTION RULES</span><h2>规则库</h2><p>所有登录用户共享规则包，存储后可直接查看与提取</p></div><div className="rule-library-actions"><button type="button" className="primary-button" onClick={() => setCreating(true)} disabled={deleting !== null}><Plus size={15} />新建规则包</button><label className="library-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索规则或标准" aria-label="搜索提取规则" /></label></div></header>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <div className="rule-list" role="list" aria-label="提取规则列表">
        {visibleItems.map((rule) => (
          <article className="rule-row" key={rule.id} role="listitem">
            <span className={`rule-icon rule-icon-${rule.key}`}><BookOpenCheck size={18} /></span>
            <div className="rule-row-copy"><div><strong>{rule.name}</strong><span className="rule-status rule-status-published">可用</span></div><p>{rule.summary}</p><small>版本 {rule.version} · 更新于 {rule.updatedAt}</small></div>
            <button type="button" className="rule-details-button" onClick={() => setExpandedId((current) => current === rule.id ? null : rule.id)} aria-expanded={expandedId === rule.id}>{expandedId === rule.id ? "收起" : "查看规则"}</button>
            {rule.canDelete ? <button type="button" className="rule-details-button" disabled={deleting !== null} onClick={() => void remove(rule)} aria-label={`删除规则包 ${rule.key}`} title="删除规则包"><Trash2 size={15} />{deleting === rule.id ? "删除中…" : "删除"}</button> : null}
            {expandedId === rule.id ? <RuleResources key={rule.id} rule={rule} onClose={() => setExpandedId(null)} /> : null}
          </article>
        ))}
        {!visibleItems.length ? <div className="library-empty"><Sparkles size={24} /><strong>没有匹配的规则</strong></div> : null}
      </div>
      {creating ? <RulePackageCreator items={items} onClose={() => setCreating(false)} onCreated={onChanged} /> : null}
    </section>
  );
}
