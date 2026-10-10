import { ChevronDown, ChevronRight, FileImage, FileText, Folder, FolderOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { AgentStageProgress } from "@/apis/agent";
import type { EntityStatus, ProjectDetail, ProjectSummary } from "@/apis/types";

interface ProjectTreeProps {
  project: ProjectDetail;
  projects: ProjectSummary[];
  selectedWorkspaceId: string | null;
  selectedDrawingId: string | null;
  stageProgress: AgentStageProgress[];
  uploadedFilename: string | null;
  simulationEnabled: boolean;
  onSelectWorkspace: (workspaceId: string) => void;
  onSelectDrawing: (workspaceId: string, drawingId: string) => void;
}

export function ProjectTree({ project, projects, selectedWorkspaceId, selectedDrawingId, stageProgress, uploadedFilename, simulationEnabled, onSelectWorkspace, onSelectDrawing }: ProjectTreeProps) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(() => project.workspaces.map((workspace) => workspace.id));
  const visibleProjects = useMemo(() => projects.filter((item) => `${item.name} ${item.company}`.toLowerCase().includes(query.toLowerCase())), [projects, query]);
  const stage1 = stageProgress.find((stage) => stage.stage === "Stage 1");
  const stage1Complete = stage1?.status === "done";
  const uploadedFileStatus: EntityStatus = stage1?.status === "done" ? "completed" : stage1?.status === "failed" ? "failed" : stage1?.status === "processing" ? "processing" : "queued";
  const stage2 = stageProgress.find((stage) => stage.stage === "Stage 2");
  const hasWorkspaceIndex = stage1Complete || stageProgress.some((stage) => stage.stage === "数据库查询");

  function toggleWorkspace(workspaceId: string) {
    setExpanded((current) => current.includes(workspaceId) ? current.filter((id) => id !== workspaceId) : [...current, workspaceId]);
  }

  return (
    <aside className="project-sidebar">
      <div className="sidebar-heading"><div><span className="section-kicker">PROJECT LIBRARY</span><h2>项目目录</h2></div><span className="count-badge">{projects.length}</span></div>
      <label className="tree-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目或公司" aria-label="搜索项目或公司" /></label>
      <nav className="project-tree" aria-label="项目、工作区和图纸">
        {visibleProjects.map((item) => {
          const active = item.id === project.id;
          return (
            <div className="project-node" key={item.id}>
                  <Link to={`/projects/${item.id}`} className={`project-row ${active ? "active" : ""}`}>
                    {active ? <FolderOpen size={18} /> : <Folder size={18} />}
                    <span className="tree-row-copy"><strong>{item.name}</strong><small>{active ? uploadedFilename ? `原始文件 · ${uploadedFilename}` : "项目文件夹" : `${item.company} · ${item.drawingCount} 张图纸`}</small></span>
                    <StatusDot status={item.status} />
                  </Link>
                  {active && (uploadedFilename || hasWorkspaceIndex) ? (
                    <div className="workspace-tree">
                  {uploadedFilename ? <div className="uploaded-file-row"><FileText size={15} /><span>{uploadedFilename}</span><StatusDot status={uploadedFileStatus} /></div> : null}
                  {uploadedFilename && !hasWorkspaceIndex ? <p className="tree-empty">{simulationEnabled ? "Supervisor 正在分析并分类页面" : "等待开启模拟链路"}</p> : null}
                  {hasWorkspaceIndex && project.workspaces.length === 0 ? <p className="tree-empty">Stage 1 正在识别工作区</p> : null}
                  {hasWorkspaceIndex ? project.workspaces.map((workspace) => {
                    const isExpanded = expanded.includes(workspace.id);
                    const isActive = selectedWorkspaceId === workspace.id && !selectedDrawingId;
                    const workspaceStatus: EntityStatus = stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : stage2?.status === "done" ? workspace.status : "queued";
                    return (
                      <div key={workspace.id} className="workspace-node">
                        <div className={`workspace-row ${isActive ? "active" : ""}`}>
                          <button type="button" className="tree-toggle" onClick={() => toggleWorkspace(workspace.id)} aria-label={`${isExpanded ? "收起" : "展开"}${workspace.code}`}>{isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>
                          <button type="button" className="tree-select" onClick={() => onSelectWorkspace(workspace.id)}><span><strong>{workspace.code}</strong><small>{workspace.name}</small></span><StatusDot status={workspaceStatus} /></button>
                        </div>
                        {isExpanded ? (
                          <div className="drawing-tree">
                            {workspace.drawings.map((drawing) => (
                              <button type="button" key={drawing.id} className={`drawing-row ${selectedDrawingId === drawing.id ? "active" : ""}`} onClick={() => onSelectDrawing(workspace.id, drawing.id)}>
                                <FileImage size={15} /><span><strong>图纸 {drawing.drawingPage}.png</strong><small>{drawing.name}</small></span><StatusDot status={stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : stage2?.status === "done" ? drawing.status : "queued"} />
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  }) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>
      <div className="sidebar-footer"><span className="legend-dot completed" />已完成 <span className="legend-dot processing" />处理中 <span className="legend-dot review" />待复核</div>
    </aside>
  );
}

function StatusDot({ status }: { status: EntityStatus }) {
  return <span className={`status-dot status-${status}`} title={status} />;
}
