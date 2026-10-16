import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { projectApi, type RulePackage } from "@/apis/projects";
import { ruleStages } from "@/apis/rule-resources";
import type { RuleLibraryItem } from "@/apis/types";

const roles: Record<string, string> = { source_page: "来源页", target_page: "目标页", drawing_page: "图纸页" };

export function RuleResources({ rule, onClose }: { rule: RuleLibraryItem; onClose: () => void }) {
  const [data, setData] = useState<RulePackage | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(0);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    projectApi.package(rule.id).then(d => { if (active) { setData(d); setError(""); } }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [rule.id, refresh]);
  const stages = data ? ruleStages(data) : [];
  const stage = stages[tab];
  return <div className="modal-backdrop"><section className="resource-modal" role="dialog" aria-modal="true" aria-labelledby="rule-heading">
    <header><h2 id="rule-heading">{rule.name} · {rule.version} · 规则引用</h2><div><button type="button" onClick={() => setRefresh(n => n + 1)}>刷新资源</button><button type="button" onClick={onClose} aria-label="关闭规则面板"><X size={18} /></button></div></header>
    <nav className="content-tabs" aria-label="提取规则">{["Stage 1 页面分类", "Stage 2 当前页扫描", "Stage 2 内部连接补全"].map((title, i) => <button key={title} type="button" className={tab === i ? "active" : ""} onClick={() => setTab(i)}>{title}</button>)}</nav>
    <div className="resource-body">{error ? <p role="alert">{error}</p> : !stage ? <p>正在校验并加载规则资源…</p> : <>
      <h3>规则 Prompt</h3><pre>{stage.prompt}</pre>
      <h3>本阶段实际样例 · {stage.examples.length}</h3>
      {stage.description ? <p>{stage.description}</p> : null}
      {stage.examples.map(example => <article className="rule-example" key={example.id}>
        <h4>{example.title}</h4><small>样例 ID：{example.id}</small>{example.description ? <p>{example.description}</p> : null}
        <div className="sample-grid">{example.images.map(img => <figure key={img.path}>
          {img.url ? <img src={img.url} alt={`${example.title} · ${roles[img.role] ?? img.role}`} /> : <p role="alert">资源包缺少图片：{img.path}</p>}
          <figcaption><strong>{roles[img.role] ?? img.role}</strong> · {img.path}{img.note ? <p>{img.note}</p> : null}</figcaption>
        </figure>)}</div>
        {example.input ? <details><summary>任务上下文</summary><pre>{example.input}</pre></details> : null}
        {example.expected ? <details><summary>人工确认的预期结果</summary><pre>{example.expected}</pre></details> : <p>本资源包未提供该样例的 expected JSON。</p>}
      </article>)}
      {!stage.examples.length ? <p>此阶段尚无 manifest 登记的样例，不将其他阶段图片当作该阶段样例。</p> : null}
      {stage.readme ? <details><summary>样例包说明</summary><pre>{stage.readme}</pre></details> : null}
    </>}</div>
  </section></div>;
}
