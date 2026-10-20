import { ArrowLeft, ExternalLink, FolderOpen, Network, Unplug } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { originProjectHref, relationMockProjects, relationProjectHref, terminalRelations } from "@/apis/mock/project-relations";
import type { ProjectSummary } from "@/apis/types";

interface Props {
  origin: ProjectSummary;
  originWorkspace: string;
  originDrawing: string;
  available: boolean;
  mockProjectId?: string;
  mockDrawingId?: string | null;
}

export function RelatedProjects({ origin, originWorkspace, originDrawing, available, mockProjectId, mockDrawingId }: Props) {
  const [filter, setFilter] = useState("all");
  const scoped = terminalRelations.filter(row => !mockProjectId || row.projectId === mockProjectId && (!mockDrawingId || row.drawingId === mockDrawingId));
  const rows = scoped.filter(row => filter === "all" || row.wire === filter);
  const projects = relationMockProjects.filter(project => scoped.some(row => row.projectId === project.id));
  const originHref = originProjectHref(origin.id, originWorkspace, originDrawing);
  return <section className="project-relations" aria-label="关联项目">
    <header className="relations-heading"><div><h2><Network size={18} />关联项目</h2><p>{mockProjectId ? "对端图纸关联" : "GCR101 · 1A · PDF 第2页"}</p></div><span className="relations-mock-label">Mock · 前端模拟</span></header>
    {!available ? <div className="relations-empty"><Unplug size={28} /><strong>当前图纸暂无关联项目</strong><p>{isSource(origin.name) ? "请从项目目录选择 GCR101 查看关联示例。" : "本轮仅提供大车卷盘 GCR101 的关联示例。"}</p></div> : <>
      <p className="relations-note">模拟跨项目连接，未写入正式线表。点击项目节点打开对应项目，选择线号查看端子对应关系。</p>
      <div className={`relations-graph ${projects.length === 1 ? "single-relation" : ""}`} aria-label="GCR101 跨项目端子关联图谱">
        <svg className="relations-edges" viewBox="0 0 1000 300" preserveAspectRatio="none" aria-hidden="true"><path d="M250 150 C350 150 350 150 500 150" /><path d="M500 150 C650 150 650 150 750 150" /></svg>
        {projects.map((project, index) => {
          const pairs = scoped.filter(row => row.projectId === project.id);
          const first = pairs[0];
          const wires = [...new Set(pairs.map(row => row.wire))];
          return <div key={project.id} className={`relation-project-node relation-node-${index} ${mockProjectId === project.id ? "selected" : ""}`}>
            <span className="relation-node-kind">{mockProjectId === project.id ? "当前模拟项目" : "关联项目"}</span>
            <Link className="relation-project-link" to={relationProjectHref(first, origin.id, originWorkspace, originDrawing)} title={`打开${project.name}`}><FolderOpen size={18} /><strong>{project.name}</strong><ExternalLink size={14} /></Link>
            <p>{[...new Set(pairs.map(row => row.drawingPage))].join(" / ")}</p>
            <div className="relation-wire-list">{wires.map(wire => <button type="button" key={wire} aria-pressed={filter === wire} onClick={() => setFilter(filter === wire ? "all" : wire)}>{wire} · {pairs.find(row => row.wire === wire)?.purpose}<span>{pairs.filter(row => row.wire === wire).length} 芯</span></button>)}</div>
            <small>{[...new Set(pairs.map(row => row.remoteTerminal))].join(" · ")}</small>
          </div>;
        })}
        <div className="relation-source-node"><span className="relation-node-kind">{mockProjectId ? "关联来源页" : "当前图纸"}</span><Link to={originHref} title="返回 GCR101 关联项目"><Network size={20} /><strong>GCR101</strong></Link><p title={origin.name}>{origin.name}</p><div className="relation-terminal-list">{[...new Set(scoped.map(row => row.terminal))].map(terminal => <span key={terminal}>{terminal}</span>)}</div><small>1A · PDF 第2页</small></div>
      </div>
      <div className="relations-detail-heading"><h3>端子对应关系 <span>{rows.length}</span></h3><div className="relation-filters" aria-label="按线号查看关联"><button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>全部</button>{[...new Set(scoped.map(row => row.wire))].map(wire => <button type="button" key={wire} aria-pressed={filter === wire} onClick={() => setFilter(wire)}>{wire}</button>)}</div></div>
      <div className="relations-table-scroll"><table className="relations-table" aria-label="跨项目端子对应关系"><thead><tr><th>线号</th><th>GCR101 端子</th><th aria-label="连接方向" /><th>关联项目</th><th>关联图纸</th><th>对端元件</th><th>对端端子</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.wire}<small>{row.purpose}</small></td><td><code>{row.terminal}</code></td><td><ArrowLeft size={14} aria-label="关联项目供电至 GCR101" /></td><td><Link to={relationProjectHref(row, origin.id, originWorkspace, originDrawing)}>{relationMockProjects.find(project => project.id === row.projectId)?.name}</Link></td><td><Link to={relationProjectHref(row, origin.id, originWorkspace, originDrawing)}>{row.drawingPage}<ExternalLink size={12} /></Link></td><td>{row.remoteDevice}</td><td><code>{row.remoteTerminal}</code></td></tr>)}</tbody></table></div>
      <footer className="relations-footer">{projects.length} 个关联项目 · {scoped.length} 条端子对应关系（含 PE）<span>外部项目及图纸页码均为演示数据</span></footer>
    </>}
  </section>;
}

function isSource(name: string): boolean { return name.includes("1002001693") || /大车.*卷盘/.test(name); }
