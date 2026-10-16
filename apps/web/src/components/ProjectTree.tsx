import { ChevronDown, ChevronRight, FileImage, Folder, FolderOpen, Pencil, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { AgentStageProgress } from "@/apis/agent";
import type { EntityStatus, ProjectDetail, ProjectSummary } from "@/apis/types";

interface ProjectTreeProps {
  project: ProjectDetail | null;
  loading?: boolean;
  projects: ProjectSummary[];
  selectedWorkspaceId: string | null;
  selectedDrawingId: string | null;
  stageProgress: AgentStageProgress[];
  uploadedFilename: string | null;
  simulationEnabled: boolean;
  onSelectWorkspace: (workspaceId: string) => void;
  onSelectDrawing: (workspaceId: string, drawingId: string) => void;
  onRename?: (project: ProjectSummary) => void;
  onDelete?: (project: ProjectSummary) => void;
}

export function ProjectTree({ project, projects, loading = false, selectedWorkspaceId, selectedDrawingId, stageProgress, uploadedFilename, simulationEnabled, onSelectWorkspace, onSelectDrawing, onRename, onDelete }: ProjectTreeProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [expandedProjects, setExpandedProjects] = useState<string[]>(project ? [project.id] : []);
  const visibleProjects = useMemo(() => projects.filter((item) => `${item.name} ${item.company}`.toLowerCase().includes(query.toLowerCase())), [projects, query]);
  const stage1 = stageProgress.find((stage) => stage.stage === "Stage 1");
  const stage1Complete = stage1?.status === "done";
  const stage2 = stageProgress.find((stage) => stage.stage === "Stage 2");
  const hasWorkspaceIndex = (project?.workspaces.length ?? 0) > 0 || stage1Complete || stageProgress.some((stage) => stage.stage === "数据库查询");

  function toggleWorkspace(workspaceId: string) {
    setCollapsed((current) => current.includes(workspaceId) ? current.filter((id) => id !== workspaceId) : [...current, workspaceId]);
  }

  function toggleProject(projectId: string) {
    if (projectId !== project?.id) { navigate(`/projects/${projectId}`); return; }
    setExpandedProjects(ids => ids.includes(projectId) ? ids.filter(id => id !== projectId) : [...ids, projectId]);
  }

  return (
    <aside className="project-sidebar">
      <div className="sidebar-heading"><div><span className="section-kicker">PROJECT LIBRARY</span><h2>项目目录</h2></div><span className="count-badge">{projects.length}</span></div>
      <label className="tree-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目或公司" aria-label="搜索项目或公司" /></label>
      <nav className="project-tree" aria-label="项目、工作区和图纸">
        {visibleProjects.map((item) => {
          const active = item.id === project?.id;
          const expanded = expandedProjects.includes(item.id);
          const childrenId = `project-children-${item.id}`;
          return (
            <div className="project-node" key={item.id}>
                  <div className={`project-row ${active ? "active" : ""}`}>
                    <button type="button" className="project-folder-toggle" aria-expanded={expanded} aria-controls={childrenId} aria-label={`${expanded ? "收起" : "展开"}项目 ${item.name}`} onClick={() => toggleProject(item.id)}>{expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>
                    <Link to={`/projects/${item.id}`} className="project-folder-link" aria-label={item.name} aria-current={active ? "page" : undefined} onClick={() => { if (active && !expanded) setExpandedProjects(ids => [...ids, item.id]); }}>
                    {expanded ? <FolderOpen size={18} /> : <Folder size={18} />}
                    <span className="tree-row-copy"><strong title={item.name}>{item.name}</strong></span>
                    <StatusDot status={item.status} />
                    </Link>
                    {onRename ? <button type="button" className="project-action" aria-label={`重命名项目 ${item.name}`} title="重命名项目" onClick={() => onRename(item)}><Pencil size={13} /></button> : null}
                    {onDelete ? <button type="button" className="project-action" aria-label={`删除项目 ${item.name}`} title="删除项目" onClick={() => onDelete(item)}><Trash2 size={13} /></button> : null}
                  </div>
                  {project && active && expanded ? <div id={childrenId} className="workspace-tree">
                  {loading ? <p className="tree-empty">正在读取工作区…</p> : null}
                  {uploadedFilename && !hasWorkspaceIndex ? <p className="tree-empty">{simulationEnabled ? "等待 Agent 分类并发布图纸索引" : "尚无图纸索引"}</p> : null}
                  {hasWorkspaceIndex && project.workspaces.length === 0 ? <p className="tree-empty">Stage 1 正在识别工作区</p> : null}
                  {hasWorkspaceIndex ? project.workspaces.map((workspace) => {
                    const isExpanded = !collapsed.includes(workspace.id);
                    const isActive = selectedWorkspaceId === workspace.id && !selectedDrawingId;
                    const workspaceStatus: EntityStatus = stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : workspace.status;
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
                                <FileImage size={15} /><span><strong>图纸 {drawing.drawingPage}.png</strong><small>{drawing.name}</small></span><StatusDot status={stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : drawing.status} />
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  }) : null}
                </div> : null}
            </div>
          );
        })}
        {!projects.length ? <p className="tree-empty">{loading ? "正在读取项目…" : "暂无项目"}</p> : null}
      </nav>
      <div className="sidebar-footer"><span className="legend-dot completed" />已完成 <span className="legend-dot processing" />处理中 <span className="legend-dot review" />待复核</div>
    </aside>
  );
}

function StatusDot({ status }: { status: EntityStatus }) {
  return <span className={`status-dot status-${status}`} title={status} />;
}
