import { useConnectionPreview } from "@/hooks/useConnectionPreview";
import { drawingEvidence } from "@/apis/drawing-evidence";
import { useExtractionUpdates } from "@/hooks/useExtractionUpdates";
import { CheckCheck, Download, FileSpreadsheet, FileText, Loader2, Network, PanelLeftClose, PanelLeftOpen, Plus, Search, Upload, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "@/apis/client";
import { projectApi, type ResultPage } from "@/apis/projects";
import { explainSelection, type ExplainSelection } from "@/apis/explain";
import { type EditProposal } from "@/apis/explain-edits";
import type { ProjectDetail, ProjectSummary, WiringRow } from "@/apis/types";
import { useAnswerStore } from "@/stores/answer-store";
import { useAssistantStore } from "@/stores/assistant-store";
import { AppHeader } from "@/components/AppHeader";
import { EmptyWorkspace } from "@/components/EmptyWorkspace";
import { ConnectionCreator } from "@/components/ConnectionCreator";
import { DrawingPreview } from "@/components/DrawingPreview";
import { ProjectTree } from "@/components/ProjectTree";
import { ResultTable } from "@/components/ResultTable";
import { UploadDialog } from "@/components/UploadDialog";
import { EditableName } from "@/components/EditableName";
import { ResizableResults } from "@/components/ResizableResults";
import { ExtractionFailureNotice } from "@/components/ExtractionFailureNotice";
import { isGcr101, isGcrRelationSource, isRelationMockProject, relationMockProjects } from "@/apis/mock/project-relations";
import { RelatedProjects } from "@/components/RelatedProjects";
import { MockRelatedWorkspace } from "@/components/MockRelatedWorkspace";

const AnswerComparison = lazy(() => import("@/components/AnswerComparison").then(module => ({ default: module.AnswerComparison })));

const emptyPage: ResultPage = { items: [], offset: 0, limit: 100, has_more: false };
const ExplainPanel = lazy(() => import("@/components/ExplainPanel").then(module => ({ default: module.ExplainPanel })));

export function ProjectView() {
  const { projectId } = useParams(); const navigate = useNavigate(); const [urlParams] = useSearchParams();
  const [projects, setProjects] = useState<ProjectSummary[]>([]); const [error, setError] = useState("");
  const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0); const [uploadFile, setUploadFile] = useState<File | null>(null);
  useEffect(() => { let active = true; projectApi.list().then(list => { if (active) { setProjects(list); setLoading(false); } }).catch(reason => { if (active) { setError(String(reason)); setLoading(false); } }); return () => { active = false; }; }, [retry]);
  const projectLoaded = useCallback((loaded: ProjectDetail) => { setProjects(previous => previous.some(item => item.id === loaded.id) ? previous.map(item => item.id === loaded.id ? loaded : item) : [...previous, loaded]); }, []);
  async function rename(project: ProjectSummary, name: string): Promise<void> {
    if (isRelationMockProject(project.id)) return;
    await projectApi.rename(project.id, name);
    setProjects(previous => previous.map(item => item.id === project.id ? { ...item, name } : item));
    setRetry(n => n + 1);
  }
  async function remove(project: ProjectSummary) {
    if (isRelationMockProject(project.id)) return;
    if (!window.confirm(`删除项目“${project.name}”及其 PDF、页面文件和线表？此操作无法撤销。`)) return;
    try { await projectApi.remove(project); useAnswerStore.getState().remove(project.id); useAnswerStore.getState().open(project.id, false); setProjects(previous => previous.filter(item => item.id !== project.id)); setRetry(n => n + 1); if (projectId === project.id) navigate("/projects", { replace: true }); } catch (reason) { setError(String(reason)); }
  }
  if (!loading && !error && !projectId && projects.length) return <Navigate to={`/projects/${projects[0].id}`} replace />;
  const origin = projects.find(item => item.id === urlParams.get("origin") && isGcrRelationSource(item)) ?? projects.find(isGcrRelationSource);
  const directory = origin ? [...projects, ...relationMockProjects] : projects;
  const mockProject = relationMockProjects.find(item => item.id === projectId);
  if (!loading && !error && mockProject && !origin) return <EmptyWorkspace loading={false} error="关联来源项目不可用，请返回有权限的项目。" onRetry={() => setRetry(n => n + 1)} onUpload={setUploadFile} />;
  if (!loading && !error && mockProject && origin) return <MockRelatedWorkspace key={`${projectId}:${urlParams.toString()}`} project={mockProject} projects={directory} origin={origin} />;
  return <>{loading || error || !projectId ? <EmptyWorkspace loading={loading} error={error} onRetry={() => { setError(""); setRetry(n => n + 1); }} onUpload={setUploadFile} /> : <ProjectWorkspace key={`${projectId}:${urlParams.toString()}`} id={projectId} projects={directory} refreshToken={retry} onRename={rename} onDelete={remove} onUpload={setUploadFile} onProjectLoaded={projectLoaded} />}{uploadFile ? <UploadDialog file={uploadFile} onClose={() => setUploadFile(null)} onSaved={id => { setUploadFile(null); setRetry(n => n + 1); navigate(`/projects/${id}`); }} /> : null}</>;
}

function ProjectWorkspace({ id, projects, refreshToken, onRename, onDelete, onUpload, onProjectLoaded }: { id: string; projects: ProjectSummary[]; refreshToken: number; onRename: (project: ProjectSummary, name: string) => Promise<void>; onDelete: (project: ProjectSummary) => void; onUpload: (file: File) => void; onProjectLoaded: (project: ProjectDetail) => void }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const relationsOpen = searchParams.get("view") === "relations";
  function closeRelations(view?: "preview") { if (relationsOpen) { const next = new URLSearchParams(searchParams); if (view) next.set("view", view); else next.delete("view"); setSearchParams(next); } }
  const assistantRefresh = useAssistantStore(state => state.refresh);
  const comparisonOpen = useAnswerStore(state => state.opened[id] ?? false);
  const closeComparison = () => useAnswerStore.getState().open(id, false);
  const [project, setProject] = useState<ProjectDetail | null>(() => { const summary = projects.find(item => item.id === id); return summary ? { ...summary, sourceFilename: "", projectNo: id, resultVersion: "", workspaces: [] } : null; });
  const [projectPending, setProjectPending] = useState(true);
  const [explanation, setExplanation] = useState<{ key: string; selection: ExplainSelection } | null>(null);
  const explainTrigger = useRef<HTMLButtonElement | null>(null);
  function closeExplanation() { setExplanation(null); if (explainTrigger.current?.isConnected) explainTrigger.current.focus({ preventScroll: true }); }
  const [page, setPage] = useState<ResultPage>(emptyPage); const [error, setError] = useState(""); const [tableError, setTableError] = useState(""); const [notice, setNotice] = useState("");
  const [editNotice, setEditNotice] = useState("");
  const [workspaceChoice, setWorkspace] = useState<string | null>(searchParams.get("workspace")); const [drawingId, setDrawing] = useState<string | null>(searchParams.get("drawing"));
  const [offset, setOffset] = useState(0); const [query, setQuery] = useState(""); const [revision, setRevision] = useState(0); const [tableLoading, setTableLoading] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(searchParams.get("view") === "preview"); const [selectedId, setSelectedId] = useState<string | null>(null);
  const [explicitSource, setExplicitSource] = useState<string | null>(null); const [jumpRequested, setJumpRequested] = useState(false); const [previewRetry, setPreviewRetry] = useState(0);
  const [rowBusy, setRowBusy] = useState(false);
  const [bulkReviewing, setBulkReviewing] = useState(false);
  const bulkLock = useRef(false);
  const bulkSubmission = useRef<{ fingerprint: string; key: string } | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null); const [creating, setCreating] = useState(false); const [deleting, setDeleting] = useState(false);
  const deletionKeys = useRef(new Map<string, string>()); const [left, setLeft] = useState(260); const pdfInput = useRef<HTMLInputElement>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [exporting, setExporting] = useState(false);
  async function exportProject() {
    if (exporting || processing) return;
    setExporting(true); setNotice("");
    try { await projectApi.exportXlsx(id); } catch (reason) { setNotice(String(reason)); }
    finally { setExporting(false); }
  }
  const workspaceId = drawingId ? project?.workspaces.find(w => w.drawings.some(d => d.id === drawingId))?.id ?? null : (!project || project.workspaces.some(w => w.id === workspaceChoice)) ? workspaceChoice : null;
  useEffect(() => {
    if (!project || projectPending) { useAssistantStore.getState().setScope({}); return; }
    const workspace = project?.workspaces.find(item => item.id === workspaceId);
    const drawing = workspace?.drawings.find(item => item.id === drawingId);
    useAssistantStore.getState().setScope({ project_id: id, project_name: project?.name,
      workspace_code: workspace?.code, workspace_id: workspaceId, drawing_id: drawingId,
      drawing_page: drawing?.drawingPage, pdf_page_number: drawing?.pdfPage,
      connection_ids: selectedId ? [selectedId] : [], batch_id: page.batch_id }, !!explanation);
  }, [id, project, projectPending, workspaceId, drawingId, selectedId, page.batch_id, explanation]);
  useEffect(() => () => useAssistantStore.getState().setScope({}), []);
  useEffect(() => { let active = true; projectApi.get(id).then(p => { if (active) { setProject(p); onProjectLoaded(p); setError(""); } }).catch(reason => { if (active) { setError(String(reason)); if (reason instanceof ApiError && [403, 404].includes(reason.status)) { setProject(null); setPage(emptyPage); } } }).finally(() => { if (active) setProjectPending(false); }); return () => { active = false; }; }, [id, revision, refreshToken, onProjectLoaded, assistantRefresh]);
  useEffect(() => { let active = true; const timer = window.setTimeout(() => { setTableLoading(true); projectApi.connections(id, { workspaceId, drawingId, offset, search: query }).then(result => { if (active) { setPage(result); setTableError(""); } }).catch(reason => { if (active) setTableError(String(reason)); }).finally(() => { if (active) setTableLoading(false); }); }, 250); return () => { active = false; window.clearTimeout(timer); }; }, [id, workspaceId, drawingId, offset, query, revision, assistantRefresh]);
  const refreshResults = useCallback(() => setRevision(n => n + 1), []);
  async function reviewAll() {
    if (!project || !page.batch_id || bulkLock.current || rowBusy || creating || tableLoading || processing) return;
    const scope = { batchId: page.batch_id, workspaceId, drawingId, search: query };
    const fingerprint = JSON.stringify([project.updatedAt, scope]);
    if (bulkSubmission.current?.fingerprint !== fingerprint) bulkSubmission.current = { fingerprint, key: crypto.randomUUID() };
    bulkLock.current = true; setBulkReviewing(true); setNotice(""); setEditNotice("");
    try {
      const count = await projectApi.reviewScope(project, scope, bulkSubmission.current.key);
      setEditNotice(count ? `已审核 ${count} 条待复核记录。` : "当前范围没有待复核记录。");
      refreshResults();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "批量审核失败，请重试。"); }
    finally { bulkLock.current = false; setBulkReviewing(false); }
  }
  const processing = project?.status === "processing";
  const disconnected = useExtractionUpdates(id, processing, refreshResults);
  const stages: Record<string, string> = { queued: "等待提取 Worker 接收任务", preparing: "正在进行第一阶段处理：准备图纸与规则", render: "正在进行第一阶段处理：拆分 PDF", classification: "正在进行第一阶段处理：识别工作区和页码", scan: "正在进行第二阶段处理：扫描连接", completion: "正在进行第二阶段处理：补全跨页连接", page_completed: "正在进行第二阶段处理：逐页校验并保存", finished: "提取完成", failed: "提取未完成" };
  const progress = project?.processing; const progressText = stages[progress?.stage ?? "queued"] ?? "正在处理图纸";
  const selectedRow = page.items.find(row => row.id === selectedId) ?? null;
  const firstRow = page.items.find(row => (!workspaceId || row.workspaceId === workspaceId) && (!drawingId || row.drawingId === drawingId));
  const defaultDrawing = project?.workspaces.find(workspace => !workspaceId || workspace.id === workspaceId)?.drawings[0]?.id;
  const sourceId = selectedRow?.drawingId ?? explicitSource ?? drawingId ?? firstRow?.drawingId ?? defaultDrawing;
  const preview = useConnectionPreview(previewOpen, sourceId, selectedRow, jumpRequested, previewRetry);
  const sourceEvidence = drawingEvidence(selectedRow, preview.source, "source"); const targetEvidence = drawingEvidence(selectedRow, preview.target, "target");
  const sameTarget = !!preview.target && preview.target.pdfPage === preview.source?.pdfPage;
  function clearSelection() { setSelectedId(null); setExplicitSource(null); setJumpRequested(false); setHighlight(null); }
  function showModified(proposal: EditProposal) {
    setEditNotice(`已保存 ${proposal.changed_count} 行修改，记录所属页、工作区和ID保持不变。`);
    setRevision(n => n + 1);
  }
  function rescanSelected() {
    if (!project || processing) return;
    explainTrigger.current = document.activeElement instanceof HTMLButtonElement ? document.activeElement : null;
    const workspace = project.workspaces.find(item => item.id === workspaceId);
    const chosen = workspace?.drawings.filter(item => !drawingId || item.id === drawingId) ?? [];
    if (!chosen.length) return;
    const scope = drawingId || !workspace?.code ? { pdf_page_numbers: chosen.map(item => item.pdfPage) } : { workspace_code: workspace.code };
    setExplanation({ key: crypto.randomUUID(), selection: { scope: "page", title: drawingId ? `${chosen[0].drawingPage} · 重扫` : `${workspace?.code || "未分类工作区"} · 重扫`,
      query: drawingId || !workspace?.code ? { pdf_page_number: chosen[0].pdfPage, offset: 0, limit: 50 } : { workspace_code: workspace.code, offset: 0, limit: 50 },
      sourcePdf: chosen[0].pdfPage, batchId: page.batch_id ?? undefined,
      initialMessage: `请直接调用重扫工具完整重新扫描${"workspace_code" in scope ? `工作区 ${scope.workspace_code}` : `PDF物理页 ${chosen.map(item => item.pdfPage).join("、")}`}，包含未提取到线表的图纸。用户已点击重扫按钮，请直接发起任务，无需再次询问。沿用原规则，先生成候选，确认前不改正式线表。` } });
  }
  function openSource(drawing: string) { clearSelection(); setExplicitSource(drawing); setPreviewOpen(true); }
  function selectConnection(row: WiringRow, jump = false) { setSelectedId(row.id); setExplicitSource(null); setJumpRequested(jump); setPreviewOpen(true); }
  async function openPdf() { try { window.open(await projectApi.source(id), "_blank", "noopener,noreferrer"); } catch (reason) { setNotice(String(reason)); } }
  function resize(event: PointerEvent<HTMLDivElement>) { event.currentTarget.setPointerCapture(event.pointerId); const start = event.clientX; const width = left; const node = event.currentTarget; function move(next: globalThis.PointerEvent) { setLeft(Math.max(200, Math.min(600, width + next.clientX - start))); } function stop() { node.removeEventListener("pointermove", move); node.removeEventListener("pointerup", stop); node.removeEventListener("pointercancel", stop); } node.addEventListener("pointermove", move); node.addEventListener("pointerup", stop); node.addEventListener("pointercancel", stop); }
  async function deleteTerminal(row: WiringRow) { if (deleting || !window.confirm(`从数据库永久删除连接 ${row.startTerminal}？该行及相关修改方案将移除，无法撤销。`)) return; const fingerprint = `${row.id}:${row.recordVersion}`; if (!deletionKeys.current.has(fingerprint)) deletionKeys.current.set(fingerprint, crypto.randomUUID()); setDeleting(true); try { await projectApi.deleteConnection(id, row, deletionKeys.current.get(fingerprint)!); clearSelection(); closeExplanation(); setOffset(0); setRevision(n => n + 1); setNotice(""); setEditNotice(""); } catch (reason) { setNotice(String(reason)); } finally { setDeleting(false); } }
  function selectWorkspace(workspace: string) { setCreating(false); clearSelection(); setEditNotice(""); setWorkspace(workspace); setDrawing(null); setOffset(0); setSearchParams(relationsOpen ? { workspace, view: "relations" } : { workspace }); }
  function selectDrawing(workspace: string, drawing: string) { setCreating(false); clearSelection(); setEditNotice(""); setWorkspace(workspace); setDrawing(drawing); setOffset(0); setSearchParams(relationsOpen ? { workspace, drawing, view: "relations" } : { workspace, drawing }); }
  const invalidTarget = !projectPending && !!project && (!!workspaceChoice && !project.workspaces.some(w => w.id === workspaceChoice) || !!drawingId && !project.workspaces.some(w => w.drawings.some(d => d.id === drawingId)));
  if (!project) return <main className="state-page">{error ? <><p role="alert">{error}</p><button onClick={() => setRevision(n => n + 1)}>重试</button></> : "正在读取项目索引…"}</main>;
  const bulkButton = <button type="button" className="secondary-button" aria-label="一键审核" title={`${drawingId ? "当前图纸" : workspaceId ? "当前工作区" : "当前项目"}${query.trim() ? "的搜索结果" : ""}：审核全部待复核记录，包含所有分页`} disabled={bulkReviewing || rowBusy || creating || processing || projectPending || tableLoading || deleting || invalidTarget || !page.batch_id} onClick={() => void reviewAll()}>{bulkReviewing ? <Loader2 size={14} className="spin" /> : <CheckCheck size={14} />}{bulkReviewing ? "审核中…" : "一键审核"}</button>;
  return <div className="workbench-app"><AppHeader project={project} /><main className={`workbench-grid real-workbench ${sidebarCollapsed ? "sidebar-collapsed" : ""}`} style={{ "--left-width": `${left}px` } as CSSProperties}>
    <ProjectTree project={project} projects={projects} loading={projectPending} selectedWorkspaceId={workspaceId} selectedDrawingId={drawingId} stageProgress={[]} uploadedFilename={project.sourceFilename || null} simulationEnabled={false} onRename={onRename} onDelete={onDelete} onSelectWorkspace={selectWorkspace} onSelectDrawing={selectDrawing} onSelectProject={() => { clearSelection(); setWorkspace(null); setDrawing(null); setOffset(0); setQuery(""); setSearchParams(relationsOpen ? { view: "relations" } : {}); }} />
    <div className="panel-resizer" role="separator" aria-label="调整项目树宽度" aria-orientation="vertical" tabIndex={0} onPointerDown={resize} onKeyDown={event => { if (event.key === "ArrowRight") setLeft(w => Math.min(600, w + 20)); if (event.key === "ArrowLeft") setLeft(w => Math.max(200, w - 20)); }} />
    <section className="project-main results-workspace"><div className="project-context-bar"><div className="project-context-heading"><button type="button" className="icon-button sidebar-toggle" aria-label={sidebarCollapsed ? "展开项目目录" : "收起项目目录"} title={sidebarCollapsed ? "展开项目目录" : "收起项目目录"} aria-expanded={!sidebarCollapsed} aria-controls="project-directory" onClick={() => setSidebarCollapsed(value => !value)}>{sidebarCollapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}</button><h1 className="context-project-name"><EditableName value={project.name} label="项目名称" onSave={name => onRename(project, name)} /></h1></div><nav className="project-resource-nav"><button type="button" className={!previewOpen && !comparisonOpen && !relationsOpen ? "active" : ""} onClick={() => { closeComparison(); closeRelations(); setPreviewOpen(false); }} aria-pressed={!previewOpen && !comparisonOpen && !relationsOpen}><FileSpreadsheet size={15} />线表工作区</button><button type="button" className={previewOpen && !comparisonOpen && !relationsOpen ? "active" : ""} onClick={() => { closeComparison(); closeRelations("preview"); setPreviewOpen(true); }} aria-pressed={previewOpen && !comparisonOpen && !relationsOpen}><FileText size={15} />图纸预览</button><button type="button" className={comparisonOpen && !relationsOpen ? "active" : ""} aria-pressed={comparisonOpen && !relationsOpen} onClick={() => { closeRelations(); useAnswerStore.getState().open(id, true); }}><FileSpreadsheet size={15} />答案对比</button><button type="button" className={relationsOpen ? "active" : ""} aria-pressed={relationsOpen} onClick={() => { closeComparison(); const next = new URLSearchParams(searchParams); next.set("view", "relations"); setSearchParams(next); }}><Network size={15} />关联项目</button></nav><input ref={pdfInput} className="visually-hidden" type="file" accept="application/pdf" onChange={event => { if (event.target.files?.[0]) onUpload(event.target.files[0]); event.target.value = ""; }} /><div className="project-file-actions">{!workspaceId && !drawingId ? <button type="button" className="secondary-button" aria-label="导出项目XLSX" title="导出该项目当前批次全部正式线表，不受搜索和分页影响" disabled={processing || projectPending || exporting} onClick={() => void exportProject()}>{exporting ? <Loader2 size={15} className="spin" /> : <Download size={15} />}{exporting ? "正在导出…" : "导出 XLSX"}</button> : null}<button type="button" className="secondary-button" onClick={() => pdfInput.current?.click()}><Upload size={15} />上传 PDF</button>{project.sourceAvailable ? <button type="button" className="secondary-button" onClick={() => void openPdf()}>原始 PDF</button> : null}</div></div>
    {invalidTarget || error || tableError || notice ? <div className="inline-error" role="alert">{relationsOpen && error ? error : invalidTarget ? "跳转目标不属于当前项目，请重新检索。" : error || tableError || notice}<button type="button" onClick={() => { setRevision(n => n + 1); setNotice(""); }}>刷新</button></div> : null}
    {editNotice ? <p className="inline-notice" role="status">{editNotice}</p> : null}
    {projectPending ? <div className="project-data-loading" role="status"><Loader2 size={20} className="spin" />正在读取项目数据…</div> : <>
      {!project.workspaces.length && !processing ? <p className="inline-notice" role="status">{project.sourceAvailable ? "PDF 已保存，尚无图纸索引和提取结果。" : "项目尚无图纸索引，文件未保存成功时请重试上传。"}</p> : null}
      {processing ? <div className="extraction-progress" role="status"><Loader2 size={18} className="spin" /><div><strong>{progressText}</strong><p>拆页 {progress?.rendered_pages ?? 0}/{progress?.total_pages ?? 0} · 分类 {progress?.classified_pages ?? 0} · 提取 {progress?.completed_pages ?? 0} · 已保存 {progress?.row_count ?? 0} 条</p><small>{disconnected ? "实时连接中断，正在重连并刷新已保存结果…" : "结果逐步保存并更新，处理期间暂不可编辑。"}</small></div></div> : null}
      {project.status === "failed" && progress ? <ExtractionFailureNotice key={JSON.stringify([progress.run_id, progress.error])} message={progress.error?.message ?? "提取失败，已保存的数据已保留。"} onRetry={() => { void projectApi.retryExtraction(id).then(refreshResults).catch(reason => setNotice(String(reason))); }} /> : null}
      {relationsOpen ? error || invalidTarget ? null : <RelatedProjects origin={project} originWorkspace={workspaceId ?? ""} originDrawing={drawingId ?? ""} available={isGcr101(project, drawingId)} /> : comparisonOpen ? <Suspense fallback={<p role="status">正在加载答案对比…</p>}><AnswerComparison project={project} drawingId={drawingId} workspaceId={workspaceId} revision={revision + assistantRefresh} /></Suspense> : <ResizableResults primary={
        <section className="results-section"><div className="table-toolbar"><div className="table-title-actions"><h2>线表结果</h2><button type="button" className="secondary-button" aria-label="重新扫描所选范围" title="按左侧所选工作区或图纸生成重扫候选" disabled={bulkReviewing || processing || !workspaceId || tableLoading || deleting} onClick={rescanSelected}>重新扫描</button></div><label className="library-search"><Search size={16} /><input aria-label="搜索线表" disabled={bulkReviewing} value={query} onChange={event => { setCreating(false); clearSelection(); setQuery(event.target.value); setOffset(0); }} placeholder="搜索端子、原理号或描述" /></label><button type="button" className="add-terminal-button" aria-label="新增端子" title="新增端子" disabled={bulkReviewing || rowBusy || creating || processing || !project.workspaces.some(workspace => workspace.drawings.length) || tableLoading || deleting} onClick={() => { setNotice(""); setPreviewOpen(false); setCreating(true); }}><Plus size={19} /></button></div>
          {tableLoading ? <p role="status">正在读取线表…</p> : null}
          <div className="table-data" hidden={tableLoading && !page.items.length}>{processing && !page.items.length ? <div className="table-empty" role="status"><Loader2 size={24} className="spin" /><strong>{progressText}</strong><p>扫描完成后会在这里显示初步线表，跨页补全后更新同一行。</p></div> : <ResultTable actionHeader={bulkButton} onBusy={setRowBusy} draftRow={creating ? <ConnectionCreator project={project} page={page} defaultDrawingId={drawingId ?? firstRow?.drawingId ?? defaultDrawing} workspaceId={workspaceId} disabled={processing || tableLoading} onError={setNotice} onClose={() => { setCreating(false); setNotice(""); }} onSaved={refreshResults} /> : null} onReview={bulkReviewing || processing || tableLoading || creating ? undefined : async (row, key) => { await projectApi.review(row, key); refreshResults(); }} compact={previewOpen && !creating} onSelectConnection={row => selectConnection(row)} onExplain={tableLoading ? undefined : (row, scope) => { explainTrigger.current = document.activeElement instanceof HTMLButtonElement ? document.activeElement : null; setExplanation({ key: crypto.randomUUID(), selection: explainSelection(row, scope, page.batch_id) }); }} key={`${workspaceId ?? "all"}:${drawingId ?? "all"}:${offset}:${query}`} rows={page.items} onOpenDrawing={openSource} onOpenTarget={row => selectConnection(row, true)} onHoverTarget={setHighlight} highlightedRowId={highlight ?? selectedRow?.id ?? null} onSave={bulkReviewing || creating || processing || tableLoading ? undefined : async (row, changes, key) => { await projectApi.edit(row, page, changes, key); setRevision(n => n + 1); }} onRefresh={() => setRevision(n => n + 1)} onDelete={bulkReviewing || creating || processing || deleting || tableLoading ? undefined : row => void deleteTerminal(row)} />}</div>
          <footer className="table-footer"><span>第 {offset / 100 + 1} 页 · {page.batch_id ? `批次 ${page.batch_id}` : "暂无结果"}</span><div><button type="button" disabled={bulkReviewing || offset === 0 || tableLoading} onClick={() => { setCreating(false); clearSelection(); setOffset(n => n - 100); }}>上一页</button><button type="button" disabled={bulkReviewing || !page.has_more || tableLoading} onClick={() => { setCreating(false); clearSelection(); setOffset(n => n + 100); }}>下一页</button></div></footer>
        </section>
        } secondary={previewOpen ? <aside className={`connection-preview ${jumpRequested && !sameTarget ? "has-target" : ""}`} aria-label="图纸校验面板">
          <header className="connection-preview-heading"><strong>图纸预览</strong><button type="button" onClick={() => setPreviewRetry(n => n + 1)}>刷新图纸</button></header>
          {preview.loading ? <p className="preview-loading" role="status">正在读取图纸…</p> : null}
          <div className="source-preview-slot">{preview.error ? <p className="inline-error" role="alert">{preview.error}</p> : <DrawingPreview key={`source:${preview.source?.id}:${preview.source?.imageUrl}`} project={project} drawing={preview.source} role="source" markers={sourceEvidence.markers} notes={sourceEvidence.notes} />}</div>
          <div className="target-preview-slot">{preview.targetError ? <p className="inline-error" role="alert">目标页读取失败：{preview.targetError}</p> : jumpRequested && preview.target && !sameTarget ? <DrawingPreview key={`target:${preview.target.id}:${preview.target.imageUrl}`} project={project} drawing={preview.target} role="target" targetTerminal={selectedRow?.endTerminalCoordinates?.pdf_page_number === preview.target?.pdfPage ? selectedRow?.endTerminal : undefined} markers={targetEvidence.markers} notes={targetEvidence.notes} /> : <p className="target-placeholder">{sameTarget || selectedRow && !selectedRow.isCrossPage ? "同页连接：两端在上方原页标注" : "点击跨页终点，在这里预览目标页"}</p>}</div>
        </aside> : null} />}
    </>}
    </section></main>
    {explanation ? <Suspense fallback={<section className="explain-panel" role="dialog" aria-modal="false" aria-label="来源解释"><header className="explain-header"><div><strong>来源解释</strong></div><button type="button" className="icon-button" aria-label="关闭来源解释" onClick={closeExplanation}><X size={19} /></button></header><p className="explain-working" role="status">正在加载解释界面…</p></section>}><ExplainPanel key={explanation.key} projectId={id} selection={explanation.selection} onClose={closeExplanation} onModified={showModified} onRescanned={run => { if (run.candidate?.replacement) { clearSelection(); setQuery(""); setOffset(0); } refreshResults(); }} availablePages={project.workspaces.flatMap(workspace => workspace.drawings.map(drawing => ({ pdf: drawing.pdfPage, title: `${workspace.code} / ${drawing.drawingPage}` })))} readOnly={processing} /></Suspense> : null}

  </div>;
}
