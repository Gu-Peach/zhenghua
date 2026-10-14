import { FileSpreadsheet, FileText, Loader2, Plus, RefreshCw, Search, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { runArtifacts, streamSupervisorRun, watchRun, type AgentStageProgress, type AgentStreamUpdate } from "@/apis/agent";
import { projectApi, type ResultPage } from "@/apis/projects";
import { request } from "@/apis/client";
import type { AgentEvent, Drawing, ProjectDetail, ProjectSummary, RuleLibraryItem, WiringRow } from "@/apis/types";
import { FloatingAgentPanel } from "@/components/FloatingAgentPanel";
import { AppHeader } from "@/components/AppHeader";
import { ConnectionCreator } from "@/components/ConnectionCreator";
import { DrawingPreview } from "@/components/DrawingPreview";
import { DrawingDirectory } from "@/components/DrawingDirectory";
import { RuleLibraryPanel } from "@/components/LibraryPanel";
import { ProjectTree } from "@/components/ProjectTree";
import { ResultTable } from "@/components/ResultTable";

type Imported = { project_id: string; attachment_id: string; conversationId: string };
const emptyPage: ResultPage = { items: [], offset: 0, limit: 100, has_more: false };

export function ProjectView() {
  const { projectId } = useParams(); const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]); const [error, setError] = useState("");
  const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0);
  useEffect(() => { let active = true; projectApi.list().then(list => { if (active) { setProjects(list); setLoading(false); } }).catch(e => { if (active) { setError(String(e)); setLoading(false); } }); return () => { active = false; }; }, [retry]);
  const projectLoaded = useCallback((loaded: ProjectDetail) => {
    setProjects(previous => previous.some(item => item.id === loaded.id) ? previous.map(item => item.id === loaded.id ? loaded : item) : [...previous, loaded]);
  }, []);
  async function upload(file: File) {
    setLoading(true); setError("");
    try { const conversationId = crypto.randomUUID(); const imported = await projectApi.upload(file, conversationId); setRetry(n => n + 1); navigate(`/projects/${imported.project_id}`, { state: { imported: { ...imported, conversationId } } }); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }
  async function rename(p: ProjectSummary) {
    const name = window.prompt("项目名称", p.name);
    if (!name?.trim()) return;
    try { await projectApi.rename(p.id, name.trim()); setRetry(n => n + 1); } catch (e) { setError(String(e)); }
  }
  async function remove(p: ProjectSummary) {
    if (!window.confirm(`删除项目“${p.name}”？原始 PDF、页面图片、线表和任务记录都会删除，无法撤销。`)) return;
    try { await projectApi.remove(p); setRetry(n => n + 1); } catch (e) { setError(String(e)); }
  }
  if (loading) return <main className="state-page"><Loader2 className="spin" /><p>正在加载真实项目…</p></main>;
  if (error) return <main className="state-page"><p role="alert">{error}</p><button type="button" onClick={() => { setError(""); setRetry(x => x + 1); }}>重试</button></main>;
  if (!projectId) return <main className="project-list-page"><h1>项目目录</h1><p>选择已有项目，或上传一份 PDF 开始新的 Agent 任务。</p><label className="primary-button"><Upload size={16} />上传 PDF<input type="file" accept="application/pdf" className="visually-hidden" onChange={e => { if (e.target.files?.[0]) void upload(e.target.files[0]); }} /></label>{projects.map(p => <div key={p.id} className="project-list-item"><Link to={`/projects/${p.id}`}>{p.name}</Link><span>{p.updatedAt}</span><div><button type="button" onClick={() => void rename(p)}>重命名</button><button type="button" onClick={() => void remove(p)}>删除</button></div></div>)}{!projects.length ? <p>暂无项目，上传后自动创建项目。</p> : null}</main>;
  return <ProjectWorkspace key={projectId} id={projectId} projects={projects} onUpload={upload} onProjectLoaded={projectLoaded} />;
}

function ProjectWorkspace({ id, projects, onUpload, onProjectLoaded }: { id: string; projects: ProjectSummary[]; onUpload: (file: File) => Promise<void>; onProjectLoaded: (project: ProjectDetail) => void }) {
  const location = useLocation();
  const imported = (location.state as { imported?: Imported } | null)?.imported;
  const [project, setProject] = useState<ProjectDetail | null>(() => {
    const summary = projects.find(item => item.id === id);
    return summary ? { ...summary, sourceFilename: "", projectNo: id, resultVersion: "", workspaces: [] } : null;
  });
  const [projectPending, setProjectPending] = useState(true);
  const [rules, setRules] = useState<RuleLibraryItem[]>([]);
  const [rulePending, setRulePending] = useState(true); const [ruleError, setRuleError] = useState("");
  const [page, setPage] = useState<ResultPage>(emptyPage); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [workspaceId, setWorkspace] = useState<string | null>(null); const [drawingId, setDrawing] = useState<string | null>(null);
  const [offset, setOffset] = useState(0); const [query, setQuery] = useState(""); const [revision, setRevision] = useState(0); const [tableLoading, setTableLoading] = useState(true);
  const [section, setSection] = useState<"results" | "drawings" | "rules">("results");
  const [source, setSource] = useState<Drawing | null>(null); const [target, setTarget] = useState<Drawing | null>(null); const [targetTerminal, setTargetTerminal] = useState("");
  const [highlight, setHighlight] = useState<string | null>(null);
  const [creating, setCreating] = useState(false); const [deleting, setDeleting] = useState(false);
  const deletionKeys = useRef(new Map<string, string>());
  const [events, setEvents] = useState<AgentEvent[]>([]); const [stages, setStages] = useState<AgentStageProgress[]>([]); const [running, setRunning] = useState(false);
  const [hint, setHint] = useState<Record<string, string>>({});
  const [left, setLeft] = useState(260);
  const conversation = useRef(imported?.conversationId ?? sessionStorage.getItem(`conversation:${id}`) ?? crypto.randomUUID());
  const currentRun = useRef<string | null>(null); const abort = useRef<AbortController | null>(null); const started = useRef(false);
  const pdfInput = useRef<HTMLInputElement>(null);
  const previewRequest = useRef(0);

  useEffect(() => { let active = true; projectApi.get(id).then(p => { if (active) { setProject(p); onProjectLoaded(p); setError(""); } }).catch(e => { if (active) setError(String(e)); }).finally(() => { if (active) setProjectPending(false); }); return () => { active = false; }; }, [id, revision, onProjectLoaded]);
  useEffect(() => { let active = true; projectApi.listRuleLibrary().then(r => { if (active) { setRules(r); setRuleError(""); } }).catch(e => { if (active) setRuleError(String(e)); }).finally(() => { if (active) setRulePending(false); }); return () => { active = false; }; }, [id, revision]);
  useEffect(() => { let active = true; const timer = window.setTimeout(() => { setTableLoading(true); projectApi.connections(id, { workspaceId, drawingId, offset, search: query }).then(result => { if (active) { setPage(result); setError(""); } }).catch(e => { if (active) setError(String(e)); }).finally(() => { if (active) setTableLoading(false); }); }, 250); return () => { active = false; clearTimeout(timer); }; }, [id, workspaceId, drawingId, offset, query, revision]);
  const defaultDrawing = drawingId ?? page.items[0]?.drawingId;
  useEffect(() => { let active = true; const token = ++previewRequest.current; if (defaultDrawing) projectApi.drawing(defaultDrawing).then(d => { if (active && token === previewRequest.current) { setSource(d); setTarget(null); } }).catch(e => { if (active && token === previewRequest.current) setNotice(String(e)); }); return () => { active = false; }; }, [defaultDrawing]);

  async function consume(stream: AsyncGenerator<AgentStreamUpdate>) {
    setRunning(true); sessionStorage.setItem(`conversation:${id}`, conversation.current);
    try {
      for await (const update of stream) {
        if (update.event) setEvents(e => e.some(x => x.id === update.event!.id) ? e.map(x => x.id === update.event!.id ? update.event! : x) : [...e, update.event!]);
        if (update.event?.kind === "error") { setStages(s => s.map(stage => stage.status === "processing" ? { ...stage, status: "failed" } : stage)); setEvents(e => e.map(item => item.kind === "stage" && item.status === "running" ? { ...item, status: "failed" } : item)); }
        if (update.stageUpdate) setStages(s => [...s.filter(x => x.stage !== update.stageUpdate!.stage), update.stageUpdate!]);
        if (update.refresh) setRevision(n => n + 1);
        if (update.runId) { currentRun.current = update.runId; sessionStorage.setItem(`run:${id}`, update.runId); }
      }
      if (currentRun.current) {
        const artifacts = await runArtifacts(currentRun.current);
        const proposal = artifacts.items.find(a => a.kind === "result_proposal");
        const diagnosis = artifacts.items.find(a => a.kind === "improvement_diagnosis");
        const candidate = artifacts.items.find(a => a.kind === "profile_candidate");
        const ruleUpdate = artifacts.items.find(a => a.kind === "profile_rule_update");
        if (proposal?.proposal_id) {
          const detail = await request<{ operations: unknown[]; feedback_id?: string; committed_result_version_id?: string | null }>(`/api/v1/proposals/${encodeURIComponent(proposal.proposal_id)}`);
          const needsConfirmation = !!detail.feedback_id && !detail.committed_result_version_id;
          setHint(needsConfirmation ? { proposal_id: proposal.proposal_id } : { agent_run_id: currentRun.current });
          setEvents(e => [...e, { id: crypto.randomUUID(), kind: "result", title: needsConfirmation ? "待确认修订" : detail.feedback_id ? "修订已提交" : "提取结果", detail: JSON.stringify(detail.operations, null, 2), status: needsConfirmation ? "pending" : "done", timestamp: new Date().toISOString() }]);
        } else if (ruleUpdate) {
          setHint({ agent_run_id: currentRun.current });
          setEvents(e => [...e.map(item => item.kind === "result" && item.status === "pending" ? { ...item, status: "done" as const } : item), { id: crypto.randomUUID(), kind: "result", title: "规则修改已生效", detail: `已按你的确认修改并启用新规则版本，无需评测或再次审核。已有项目未自动切换版本。\n${JSON.stringify(ruleUpdate.candidate, null, 2)}`, status: "done", timestamp: new Date().toISOString() }]);
        } else if (candidate) {
          setHint({ agent_run_id: currentRun.current });
          setEvents(e => [...e, { id: crypto.randomUUID(), kind: "result", title: "已有规则修改待确认", detail: `确认后直接启用该规则包，无需评测或再次审核。\n${JSON.stringify(candidate.candidate, null, 2)}`, status: "pending", timestamp: new Date().toISOString() }]);
        } else if (diagnosis) {
          setHint({ agent_run_id: currentRun.current });
          setEvents(e => [...e, { id: crypto.randomUUID(), kind: "result", title: diagnosis.candidate_recommended ? "待确认规则建议" : "纠错归因结果", detail: `${diagnosis.candidate_recommended ? "确认规则修改后将直接修改并启用新规则版本。\n" : ""}${JSON.stringify(diagnosis.diagnoses, null, 2)}`, status: diagnosis.candidate_recommended ? "pending" : "done", timestamp: new Date().toISOString() }]);
        } else setHint({ agent_run_id: currentRun.current });
      }
    } catch (e) { if (!abort.current?.signal.aborted) setEvents(events => [...events.map(item => item.status === "running" ? { ...item, status: "failed" as const } : item), { id: crypto.randomUUID(), kind: "error", title: "连接/任务失败", detail: String(e), status: "failed", timestamp: new Date().toISOString() }]); }
    finally { setRunning(false); if (currentRun.current) setRevision(n => n + 1); }
  }
  async function send(message: string, attachmentIds: string[] = []) {
    if (running) return;
    abort.current = new AbortController();
    setEvents(e => [...e, { id: crypto.randomUUID(), kind: "tool", title: "用户", detail: message, status: "done", timestamp: new Date().toISOString() }]);
    currentRun.current = null;
    sessionStorage.removeItem(`run:${id}`);
    await consume(streamSupervisorRun({ projectId: id, conversationId: conversation.current, message, attachmentIds, targetHint: hint }, abort.current.signal));
  }
  useEffect(() => {
    const timer = window.setTimeout(() => {
    if (started.current) return;
    started.current = true;
    if (imported && !sessionStorage.getItem(`import-started:${id}`)) {
      sessionStorage.setItem(`import-started:${id}`, "true");
      void send("请识别这份已上传 PDF 的图纸类型，确认后执行 Stage 1 分类和 Stage 2 逐页提取。", [imported.attachment_id]);
    } else {
      const run = sessionStorage.getItem(`run:${id}`);
      if (run) { abort.current = new AbortController(); void consume(watchRun(run, abort.current.signal)); }
      else if (sessionStorage.getItem(`conversation:${id}`)) {
        void request<{ history?: Array<{ role: string; content: string }> }>(`/api/v1/supervisor/conversations/${conversation.current}`).then(memory => setEvents((memory.history ?? []).map(h => ({ id: crypto.randomUUID(), kind: "message", title: h.role === "user" ? "用户" : "电气图纸助手", detail: h.content, status: "done", timestamp: "" })))).catch(() => setNotice("Agent 短期会话不可恢复；结果仍保存在数据库，可开启新任务。"));
      }
    }
    }, 0);
    return () => { window.clearTimeout(timer); abort.current?.abort(); };
    // One run subscription per mounted project; mutations never run on refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openSource(drawing: string) { const token = ++previewRequest.current; try { const image = await projectApi.drawing(drawing); if (token === previewRequest.current) { setSource(image); setTarget(null); } } catch (e) { if (token === previewRequest.current) setNotice(String(e)); } }
  async function openTarget(row: WiringRow) { const token = ++previewRequest.current; setHighlight(row.id); try { const [s, t] = await Promise.all([projectApi.drawing(row.drawingId), projectApi.target(row)]); if (token === previewRequest.current) { setSource(s); setTarget(t); setTargetTerminal(row.endTerminal); setNotice(""); } } catch (e) { if (token === previewRequest.current) setNotice(String(e)); } }
  function resize(e: PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId); const start = e.clientX; const width = left;
    const node = e.currentTarget;
    function move(event: globalThis.PointerEvent) { setLeft(Math.max(200, Math.min(600, width + event.clientX - start))); }
    function stop() { node.removeEventListener("pointermove", move); node.removeEventListener("pointerup", stop); node.removeEventListener("pointercancel", stop); }
    node.addEventListener("pointermove", move); node.addEventListener("pointerup", stop); node.addEventListener("pointercancel", stop);
  }
  function selectWorkspace(ws: string) { setWorkspace(ws); setDrawing(null); setOffset(0); setSection("results"); }
  async function deleteTerminal(row: WiringRow) {
    if (deleting || !window.confirm(`删除线号 ${row.wireNumber} 下的端子 ${row.startTerminal}？仅删除该连接，保留修改前数据和证据审计。`)) return;
    const fingerprint = `${row.id}:${page.result_revision}:${row.recordVersion}`;
    if (!deletionKeys.current.has(fingerprint)) deletionKeys.current.set(fingerprint, crypto.randomUUID());
    setDeleting(true);
    try { await projectApi.deleteConnection(id, row, page, deletionKeys.current.get(fingerprint)!); setRevision(n => n + 1); setNotice(""); }
    catch (reason) { setNotice(String(reason)); }
    finally { setDeleting(false); }
  }
  function selectDrawing(ws: string, drawing: string) { setWorkspace(ws); setDrawing(drawing); setOffset(0); setSection("results"); }
  if (!project) return <main className="state-page">{error ? <><p role="alert">{error}</p><button onClick={() => setRevision(n => n + 1)}>重试</button></> : "正在读取项目索引…"}</main>;
  return <div className="workbench-app"><AppHeader project={project} /><main className="workbench-grid real-workbench" style={{ "--left-width": `${left}px` } as CSSProperties}>
    <ProjectTree project={project} projects={projects} loading={projectPending} selectedWorkspaceId={workspaceId} selectedDrawingId={drawingId} stageProgress={stages} uploadedFilename={project.sourceFilename || null} simulationEnabled onSelectWorkspace={selectWorkspace} onSelectDrawing={selectDrawing} />
    <div className="panel-resizer" role="separator" aria-label="调整项目树宽度" aria-orientation="vertical" tabIndex={0} onPointerDown={resize} onKeyDown={e => { if (e.key === "ArrowRight") setLeft(w => Math.min(600, w + 20)); if (e.key === "ArrowLeft") setLeft(w => Math.max(200, w - 20)); }} />
    <section className="project-main"><div className="project-context-bar"><h1 className="context-project-name" title={project.name}>{project.name}</h1><nav className="project-resource-nav"><button type="button" className={section === "results" ? "active" : ""} onClick={() => setSection("results")}><FileSpreadsheet size={15} />线表工作区</button><button type="button" className={section === "drawings" ? "active" : ""} onClick={() => setSection("drawings")}><FileText size={15} />图纸库</button><button type="button" className={section === "rules" ? "active" : ""} onClick={() => setSection("rules")}><RefreshCw size={15} />规则库</button></nav><input ref={pdfInput} className="visually-hidden" type="file" accept="application/pdf" onChange={e => { if (e.target.files?.[0]) void onUpload(e.target.files[0]); }} /><button type="button" className="secondary-button" disabled={running} onClick={() => pdfInput.current?.click()}><Upload size={15} />上传 PDF</button></div>
    {error || notice ? <div className="inline-error" role="alert">{error || notice}<button type="button" onClick={() => { setRevision(n => n + 1); setNotice(""); }}>刷新</button></div> : null}
    {projectPending ? <div className="project-data-loading" role="status"><Loader2 size={20} className="spin" />正在读取项目数据…</div> : section === "rules" ? rulePending ? <div className="project-data-loading" role="status">正在读取规则库…</div> : ruleError ? <div className="inline-error" role="alert">{ruleError}<button type="button" onClick={() => setRevision(n => n + 1)}>重试读取规则库</button></div> : <RuleLibraryPanel items={rules} onChanged={async () => { setRules(await projectApi.listRuleLibrary()); }} /> : section === "drawings" ? <DrawingDirectory project={project} /> : <>
    <section className="results-section"><div className="table-toolbar"><h2>线表结果</h2><label className="library-search"><Search size={16} /><input aria-label="搜索线表" value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} placeholder="搜索端子、原理号或描述" /></label><button type="button" className="add-terminal-button" aria-label="新增端子" title="新增端子" disabled={!page.result_version_id || tableLoading || deleting} onClick={() => setCreating(true)}><Plus size={19} /></button></div>{tableLoading ? <p role="status">正在读取线表…</p> : null}<div hidden={tableLoading && !page.items.length}><ResultTable key={`${workspaceId ?? "all"}:${drawingId ?? "all"}:${offset}:${query}`} rows={page.items} onOpenDrawing={d => void openSource(d)} onOpenTarget={row => void openTarget(row)} onHoverTarget={setHighlight} highlightedRowId={highlight} onSave={!tableLoading && page.result_version_id && page.result_revision ? async (row, changes, key) => { await projectApi.edit(row, page, changes, key); setRevision(n => n + 1); } : undefined} onRefresh={() => setRevision(n => n + 1)} onDelete={deleting || tableLoading ? undefined : row => void deleteTerminal(row)} /></div><footer className="table-footer"><span>第 {offset / 100 + 1} 页 · r{page.result_revision ?? "-"}</span><div><button type="button" disabled={offset === 0 || tableLoading} onClick={() => setOffset(o => o - 100)}>上一页</button><button type="button" disabled={!page.has_more || tableLoading} onClick={() => setOffset(o => o + 100)}>下一页</button></div></footer></section>
    <section className={`below-previews ${target ? "with-target" : ""}`}><DrawingPreview key={source?.id ?? "source"} project={project} drawing={source} />{target ? <DrawingPreview key={target.id} project={project} drawing={target} targetTerminal={targetTerminal} /> : null}</section></>}
    </section></main>
    <FloatingAgentPanel initiallyOpen={!!imported} events={events} stageProgress={stages} isRunning={running} hasPendingUpload={false} simulationEnabled onReconnect={currentRun.current ? () => { abort.current = new AbortController(); void consume(watchRun(currentRun.current!, abort.current.signal)); } : undefined} onSimulationToggle={() => { conversation.current = crypto.randomUUID(); currentRun.current = null; sessionStorage.removeItem(`run:${id}`); sessionStorage.setItem(`conversation:${id}`, conversation.current); setEvents([]); setStages([]); setHint({}); }} onRunRepair={m => void send(m)} />
    {creating ? <ConnectionCreator project={project} page={page} onClose={() => setCreating(false)} onSaved={() => setRevision(n => n + 1)} /> : null}</div>;
}
