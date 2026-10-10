import { ArrowUpRight, BookOpenCheck, Clock3, FileText, FolderClosed, FolderOpen, Search, ShieldCheck, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { DrawingLibraryItem, RuleLibraryItem } from "@/apis/types";

export function DrawingLibraryPanel({ items, activeProjectId }: { items: DrawingLibraryItem[]; activeProjectId: string }) {
  const [query, setQuery] = useState("");
  const visibleItems = useMemo(() => items.filter((item) => `${item.name} ${item.folder}`.toLowerCase().includes(query.toLowerCase())), [items, query]);

  return (
    <section className="library-panel">
      <header className="library-heading"><div><span className="section-kicker">DRAWING LIBRARY</span><h2>图纸库</h2><p>按项目归档的原始图纸文件夹</p></div><label className="library-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目图纸" aria-label="搜索项目图纸" /></label></header>
      <div className="library-list" role="list" aria-label="项目图纸文件夹">
        {visibleItems.map((item) => (
          <article className={`library-row ${item.projectId === activeProjectId ? "selected" : ""}`} key={item.id} role="listitem">
            <span className="library-row-icon"><FolderOpen size={19} /></span>
            <div className="library-row-copy"><strong>{item.name}</strong><span><FolderClosed size={13} />{item.folder}</span></div>
            <span className="library-count"><FileText size={14} />{item.drawingCount} 张图纸</span>
            <span className={`library-status status-${item.status}`}>{item.status === "completed" ? "已处理" : item.status === "review" ? "待复核" : item.status === "processing" ? "处理中" : "待处理"}</span>
            <time><Clock3 size={13} />{item.updatedAt}</time>
            <Link to={`/projects/${item.projectId}`} className="library-open" aria-label={`打开${item.name}`} title="打开项目"><ArrowUpRight size={17} /></Link>
          </article>
        ))}
        {!visibleItems.length ? <div className="library-empty"><FolderClosed size={24} /><strong>没有匹配的图纸文件夹</strong></div> : null}
      </div>
    </section>
  );
}

export function RuleLibraryPanel({ items }: { items: RuleLibraryItem[] }) {
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const visibleItems = useMemo(() => items.filter((item) => `${item.name} ${item.summary} ${item.key}`.toLowerCase().includes(query.toLowerCase())), [items, query]);

  return (
    <section className="library-panel">
      <header className="library-heading"><div><span className="section-kicker">EXTRACTION RULES</span><h2>规则库</h2><p>按图纸标准隔离维护提取规则与候选版本</p></div><label className="library-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索规则或标准" aria-label="搜索提取规则" /></label></header>
      <div className="rule-list" role="list" aria-label="提取规则列表">
        {visibleItems.map((rule) => (
          <article className={`rule-row ${rule.status === "candidate" ? "rule-candidate" : ""}`} key={rule.id} role="listitem">
            <span className={`rule-icon rule-icon-${rule.key}`}><BookOpenCheck size={18} /></span>
            <div className="rule-row-copy"><div><strong>{rule.name}</strong><span className={`rule-status rule-status-${rule.status}`}>{rule.status === "published" ? "已发布" : "待审核候选"}</span></div><p>{rule.summary}</p><small>版本 {rule.version} · 更新于 {rule.updatedAt}</small></div>
            <button type="button" className="rule-details-button" onClick={() => setExpandedId((current) => current === rule.id ? null : rule.id)} aria-expanded={expandedId === rule.id}>{expandedId === rule.id ? "收起" : "查看规则"}</button>
            {expandedId === rule.id ? <div className="rule-detail"><ShieldCheck size={15} /><span>{rule.status === "candidate" ? "候选规则仅供评估；完成固定案例回归和人工审核后，才能发布到对应 Profile。" : `规则集 ${rule.key.toUpperCase()} 已与其他图纸标准隔离，供对应项目的三阶段提取使用。`}</span></div> : null}
          </article>
        ))}
        {!visibleItems.length ? <div className="library-empty"><Sparkles size={24} /><strong>没有匹配的规则</strong></div> : null}
      </div>
    </section>
  );
}
