import { FileSpreadsheet, FileText, Loader2, PanelLeftClose, PanelLeftOpen, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { AppHeader } from "./AppHeader";
import { FloatingAgentPanel } from "./FloatingAgentPanel";
import { ProjectTree } from "./ProjectTree";

export function EmptyWorkspace({ loading, error, onRetry, onUpload }: { loading: boolean; error: string; onRetry: () => void; onUpload: (file: File) => void }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false); const input = useRef<HTMLInputElement>(null);
  return <div className="workbench-app"><AppHeader /><main className={`workbench-grid real-workbench ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
    <ProjectTree project={null} projects={[]} loading={loading} selectedWorkspaceId={null} selectedDrawingId={null} stageProgress={[]} uploadedFilename={null} simulationEnabled={false} onSelectWorkspace={() => {}} onSelectDrawing={() => {}} />
    <div className="panel-resizer" aria-hidden="true" />
    <section className="project-main results-workspace"><div className="project-context-bar"><div className="project-context-heading"><button type="button" className="icon-button sidebar-toggle" aria-label={sidebarCollapsed ? "展开项目目录" : "收起项目目录"} title={sidebarCollapsed ? "展开项目目录" : "收起项目目录"} aria-expanded={!sidebarCollapsed} aria-controls="project-directory" onClick={() => setSidebarCollapsed(value => !value)}>{sidebarCollapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}</button><h1 className="context-project-name">工作区</h1></div><nav className="project-resource-nav"><button type="button" className={!previewOpen ? "active" : ""} onClick={() => setPreviewOpen(false)}><FileSpreadsheet size={15} />线表工作区</button><button type="button" className={previewOpen ? "active" : ""} onClick={() => setPreviewOpen(true)}><FileText size={15} />图纸预览</button></nav><div className="project-file-actions"><button type="button" className="secondary-button" disabled={loading} onClick={() => input.current?.click()}><Upload size={15} />上传 PDF</button></div></div>
    <input ref={input} type="file" className="visually-hidden" accept="application/pdf" onChange={event => { if (event.target.files?.[0]) onUpload(event.target.files[0]); event.target.value = ""; }} />
    {loading ? <div className="project-data-loading" role="status"><Loader2 className="spin" size={20} />正在加载项目…</div> : error ? <div className="workspace-empty-state"><p role="alert">{error}</p><button type="button" className="secondary-button" onClick={onRetry}>重试</button></div> : <div className="workspace-empty-state"><FileSpreadsheet size={28} /><h2>{previewOpen ? "暂无图纸" : "暂无项目"}</h2><p>上传 PDF 创建项目，在此管理图纸和线表。</p><button type="button" className="primary-button" onClick={() => input.current?.click()}><Upload size={16} />上传 PDF</button></div>}
    </section></main><FloatingAgentPanel events={[]} stageProgress={[]} isRunning={false} hasPendingUpload={false} simulationEnabled={false} unavailableReason="先上传PDF创建项目；提取 Skills 可在用户菜单的智能体中心管理。" onSimulationToggle={() => {}} onRunRepair={() => {}} /></div>;
}
