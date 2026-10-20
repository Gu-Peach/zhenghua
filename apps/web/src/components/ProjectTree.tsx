import { ChevronDown, ChevronRight, FileImage, Folder, FolderOpen, Search, Trash2 } from "lucide-react";
import { Fragment, useLayoutEffect, useMemo, useRef, useState } from "react";
import { isRelationMockProject } from "@/apis/mock/project-relations";
import { useProjectTreeStore } from "@/stores/project-tree-store";
import { useNavigate } from "react-router-dom";
import { EditableName } from "./EditableName";
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
  onSelectProject?: () => void;
  onRename?: (project: ProjectSummary, name: string) => Promise<void>;
  onDelete?: (project: ProjectSummary) => void;
}

export function ProjectTree({ project, projects, loading = false, selectedWorkspaceId, selectedDrawingId, stageProgress, uploadedFilename, simulationEnabled, onSelectWorkspace, onSelectDrawing, onSelectProject, onRename, onDelete }: ProjectTreeProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const branches = useProjectTreeStore(state => state.branches);
  const navigation = useRef<HTMLElement>(null);
  const restored = useRef(false);
  const projectId = project?.id ?? "project-list";
  const selection = `${projectId}:${selectedWorkspaceId ?? ""}:${selectedDrawingId ?? ""}`;
  const projectBranch = (id: string) => `project:${id}`;
  const workspaceBranch = (id: string) => `workspace:${projectId}:${id}`;
  function opened(branch: string, ancestor = false) {
    const saved = branches[branch];
    return saved?.selection === selection ? saved.opened : ancestor || saved?.opened || false;
  }
  function disclose(branch: string, value: boolean) { useProjectTreeStore.getState().disclose(branch, value, selection); }
  useLayoutEffect(() => {
    if (loading || !navigation.current) return;
    const nav = navigation.current;
    nav.scrollTop = useProjectTreeStore.getState().positions[projectId] ?? 0;
    const target = nav.querySelector<HTMLElement>('[data-tree-selected="true"]');
    if (target) {
      const viewport = nav.getBoundingClientRect(); const row = target.getBoundingClientRect();
      if (row.top < viewport.top) nav.scrollTop -= viewport.top - row.top;
      else if (row.bottom > viewport.bottom) nav.scrollTop += row.bottom - viewport.bottom;
    }
    restored.current = true;
  }, [loading, projectId, selectedWorkspaceId, selectedDrawingId]);
  const visibleProjects = useMemo(() => projects.filter((item) => `${item.name} ${item.company} ${isRelationMockProject(item.id) ? "mock" : ""}`.toLowerCase().includes(query.toLowerCase())), [projects, query]);
  const stage1 = stageProgress.find((stage) => stage.stage === "Stage 1");
  const stage1Complete = stage1?.status === "done";
  const stage2 = stageProgress.find((stage) => stage.stage === "Stage 2");
  const hasWorkspaceIndex = (project?.workspaces.length ?? 0) > 0 || stage1Complete || stageProgress.some((stage) => stage.stage === "数据库查询");

  function toggleProject(id: string) {
    const ancestor = id === project?.id && !!(selectedWorkspaceId || selectedDrawingId);
    disclose(projectBranch(id), !opened(projectBranch(id), ancestor));
    if (id !== project?.id) navigate(`/projects/${id}`);
  }

  return (
    <aside id="project-directory" className="project-sidebar" aria-label="项目目录">
      <div className="sidebar-heading"><div><span className="section-kicker">PROJECT LIBRARY</span><h2>项目目录</h2></div><span className="count-badge">{projects.length}</span></div>
      <label className="tree-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目或公司" aria-label="搜索项目或公司" /></label>
      <nav ref={navigation} className="project-tree" aria-label="项目、工作区和图纸" onScroll={event => { if (!loading && restored.current) useProjectTreeStore.getState().savePosition(projectId, event.currentTarget.scrollTop); }}>
        {[false, true].map(mock => {
          const items = visibleProjects.filter(item => isRelationMockProject(item.id) === mock);
          if (!items.length) return null;
          const content = items.map((item) => {
          const active = item.id === project?.id;
          const expanded = opened(projectBranch(item.id), active && !!(selectedWorkspaceId || selectedDrawingId));
          const childrenId = `project-children-${item.id}`;
          return (
            <div className="project-node" key={item.id}>
                  <div className={`project-row ${active ? "active" : ""}`} data-tree-selected={active && !selectedWorkspaceId && !selectedDrawingId}>
                    <button type="button" className="project-folder-toggle" aria-expanded={expanded} aria-controls={childrenId} aria-label={`${expanded ? "收起" : "展开"}项目 ${item.name}`} onClick={() => toggleProject(item.id)}>{expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>
                    <EditableName value={item.name} label="项目名称" current={active} to={`/projects/${item.id}`} className="project-folder-link" leading={expanded ? <FolderOpen size={18} /> : <Folder size={18} />} trailing={<StatusDot status={item.status} />} onActivate={() => { if (active) { onSelectProject?.(); if (!expanded) disclose(projectBranch(item.id), true); } }} onSave={!mock && onRename ? name => onRename(item, name) : undefined} />
                    {!mock && onDelete ? <button type="button" className="project-action" aria-label={`删除项目 ${item.name}`} title="删除项目" onClick={() => onDelete(item)}><Trash2 size={13} /></button> : null}
                  </div>
                  {project && active && expanded ? <div id={childrenId} className="workspace-tree">
                  {loading ? <p className="tree-empty">正在读取工作区…</p> : null}
                  {uploadedFilename && !hasWorkspaceIndex ? <p className="tree-empty">{project.status === "processing" || simulationEnabled ? "正在拆分并识别图纸…" : "尚无图纸索引"}</p> : null}
                  {hasWorkspaceIndex && project.workspaces.length === 0 ? <p className="tree-empty">Stage 1 正在识别工作区</p> : null}
                  {hasWorkspaceIndex ? project.workspaces.map((workspace) => {
                    const isExpanded = opened(workspaceBranch(workspace.id), selectedWorkspaceId === workspace.id);
                    const isActive = selectedWorkspaceId === workspace.id && !selectedDrawingId;
                    const workspaceStatus: EntityStatus = stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : workspace.status;
                    return (
                      <div key={workspace.id} className="workspace-node">
                        <div className={`workspace-row ${isActive ? "active" : ""}`}>
                          <button type="button" className="tree-toggle" aria-expanded={isExpanded} onClick={() => disclose(workspaceBranch(workspace.id), !isExpanded)} aria-label={`${isExpanded ? "收起" : "展开"}${workspace.code}`}>{isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</button>
                          <button type="button" className="tree-select" data-tree-selected={isActive} aria-current={isActive ? "page" : undefined} onClick={() => { disclose(workspaceBranch(workspace.id), true); onSelectWorkspace(workspace.id); }}><span><strong>{workspace.code}</strong><small>{workspace.name}</small></span><StatusDot status={workspaceStatus} /></button>
                        </div>
                        {isExpanded ? (
                          <div className="drawing-tree">
                            {workspace.drawings.map((drawing) => (
                              <button type="button" key={drawing.id} className={`drawing-row ${selectedDrawingId === drawing.id ? "active" : ""}`} data-tree-selected={selectedDrawingId === drawing.id} aria-current={selectedDrawingId === drawing.id ? "page" : undefined} onClick={() => onSelectDrawing(workspace.id, drawing.id)}>
                                <FileImage size={15} /><span><strong>{drawing.drawingPage}</strong><small>{drawing.name}</small></span><StatusDot status={stage2?.status === "processing" ? "processing" : stage2?.status === "failed" ? "failed" : drawing.status} />
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
          });
          if (!mock) return <Fragment key="server-projects">{content}</Fragment>;
          const mockOpen = !!query || opened("mock-folder", isRelationMockProject(projectId));
          return <div className="mock-project-folder" key="mock-projects"><button type="button" className="mock-folder-toggle" aria-expanded={mockOpen} aria-controls="mock-project-children" onClick={() => disclose("mock-folder", !mockOpen)}>{mockOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}{mockOpen ? <FolderOpen size={18} /> : <Folder size={18} />}<strong>Mock</strong><span>{items.length}</span></button>{mockOpen ? <div id="mock-project-children">{content}</div> : null}</div>;
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
