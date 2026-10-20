import { ArrowLeft, Network, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isGcr101, originProjectHref, terminalRelations } from "@/apis/mock/project-relations";
import { projectApi } from "@/apis/projects";
import type { ProjectDetail, ProjectSummary } from "@/apis/types";
import { AppHeader } from "./AppHeader";
import { ProjectTree } from "./ProjectTree";
import { RelatedProjects } from "./RelatedProjects";

export function MockRelatedWorkspace({ project, projects, origin }: { project: ProjectDetail; projects: ProjectSummary[]; origin: ProjectSummary }) {
  const [params, setParams] = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);
  const [source, setSource] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    projectApi.get(origin.id).then(detail => { if (active) setSource(detail); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "关联来源项目读取失败"); });
    return () => { active = false; };
  }, [origin.id]);
  const selectedDrawing = params.get("drawing");
  const selectedWorkspace = project.workspaces.find(workspace => workspace.drawings.some(drawing => drawing.id === selectedDrawing))?.id ?? params.get("workspace");
  const sourceWorkspace = source?.workspaces.find(workspace => workspace.drawings.some(drawing => isGcr101(source, drawing.id)));
  const originWorkspace = sourceWorkspace?.id ?? "";
  const originDrawing = sourceWorkspace?.drawings.find(drawing => source && isGcr101(source, drawing.id))?.id ?? "";
  const invalid = !!selectedDrawing && !project.workspaces.some(workspace => workspace.drawings.some(drawing => drawing.id === selectedDrawing)) || !!selectedWorkspace && !project.workspaces.some(workspace => workspace.id === selectedWorkspace);
  const connections = terminalRelations.filter(row => row.projectId === project.id && (!selectedDrawing || row.drawingId === selectedDrawing));
  function select(workspace?: string, drawing?: string) {
    const next = new URLSearchParams(params); next.set("view", "relations");
    if (workspace) next.set("workspace", workspace); else next.delete("workspace");
    if (drawing) next.set("drawing", drawing); else next.delete("drawing");
    setParams(next);
  }
  return <div className="workbench-app"><AppHeader project={project} /><main className={`workbench-grid real-workbench ${collapsed ? "sidebar-collapsed" : ""}`}>
    <ProjectTree project={project} projects={projects} selectedWorkspaceId={selectedWorkspace} selectedDrawingId={selectedDrawing} stageProgress={[]} uploadedFilename={null} simulationEnabled={false} onSelectProject={() => select()} onSelectWorkspace={workspace => select(workspace)} onSelectDrawing={select} />
    <div className="panel-resizer" aria-hidden="true" />
    <section className="project-main results-workspace"><div className="project-context-bar"><div className="project-context-heading"><button type="button" className="icon-button sidebar-toggle" aria-label={collapsed ? "展开项目目录" : "收起项目目录"} onClick={() => setCollapsed(value => !value)}><span>{collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}</span></button><h1 className="context-project-name">{project.name}</h1></div><nav className="project-resource-nav"><button type="button" className="active" aria-pressed="true"><Network size={15} />关联项目</button></nav><Link className="secondary-button" to={originProjectHref(origin.id, originWorkspace, originDrawing)}><ArrowLeft size={15} />返回 GCR101</Link></div>
      {error ? <p className="inline-error" role="alert">{error}</p> : !source ? <p className="inline-notice" role="status">正在读取关联来源项目…</p> : invalid ? <p className="inline-error" role="alert">模拟项目中没有这张图纸，请从目录重新选择。</p> : <RelatedProjects key={selectedDrawing ?? "all"} origin={source} originWorkspace={originWorkspace} originDrawing={originDrawing} available={!!originDrawing && connections.length > 0} mockProjectId={project.id} mockDrawingId={selectedDrawing} />}
    </section>
  </main></div>;
}
