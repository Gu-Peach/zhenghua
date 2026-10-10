import { CheckCircle2, ChevronRight, Download, FileSpreadsheet, FileText, Loader2, RefreshCw, Search, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { streamSupervisorRun, type AgentStageProgress, type SupervisorCommand, type SupervisorRequest } from "@/apis/agent";
import { projectApi } from "@/apis/projects";
import type { AgentEvent, DrawingLibraryItem, ProjectDetail, ProjectSummary, RuleLibraryItem, StageEvent, WiringRow } from "@/apis/types";
import { AiPanel } from "@/components/AiPanel";
import { AppHeader } from "@/components/AppHeader";
import { DrawingPreview } from "@/components/DrawingPreview";
import { DrawingLibraryPanel, RuleLibraryPanel } from "@/components/LibraryPanel";
import { ProjectTree } from "@/components/ProjectTree";
import { ResultTable } from "@/components/ResultTable";
import { StageTimeline } from "@/components/StageTimeline";
import { useProjectWorkbench } from "@/hooks/use-project-workbench";

interface ViewData {
  project: ProjectDetail;
  projects: ProjectSummary[];
  rows: WiringRow[];
  drawingLibrary: DrawingLibraryItem[];
  ruleLibrary: RuleLibraryItem[];
}

type MainSection = "results" | "drawings" | "rules";

export function ProjectView() {
  const { projectId = "peru-tpp-1-sts" } = useParams();
  const [data, setData] = useState<ViewData | null>(null);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([
      projectApi.get(projectId), projectApi.list(), projectApi.listConnections(projectId),
      projectApi.listDrawingLibrary(), projectApi.listRuleLibrary(),
    ]).then(([project, projects, rows, drawingLibrary, ruleLibrary]) => {
      if (active) setData({ project, projects, rows, drawingLibrary, ruleLibrary });
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "项目加载失败");
    });
    return () => { active = false; };
  }, [projectId, retryKey]);

  function retry() {
    setError("");
    setData(null);
    setRetryKey((value) => value + 1);
  }

  if (error) return <main className="state-page"><strong>项目加载失败</strong><p>{error}</p><button type="button" onClick={retry}>重新加载</button></main>;
  if (!data || data.project.id !== projectId) return <main className="state-page"><Loader2 size={24} className="spin" /><strong>正在加载项目</strong></main>;
  return <ProjectWorkspace key={data.project.id} data={data} />;
}

function ProjectWorkspace({ data }: { data: ViewData }) {
  const { project, projects } = data;
  const [rows, setRows] = useState(data.rows);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [stageProgress, setStageProgress] = useState<AgentStageProgress[]>([]);
  const drawingLibrary = data.drawingLibrary;
  const [ruleLibrary, setRuleLibrary] = useState(data.ruleLibrary);
  const [isRunning, setIsRunning] = useState(false);
  const [simulationEnabled, setSimulationEnabled] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [pendingExtraction, setPendingExtraction] = useState(false);
  const [activeSection, setActiveSection] = useState<MainSection>("results");
  const [notice, setNotice] = useState<string | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const workbench = useProjectWorkbench(project, rows);
  const projectRows = rows.filter((row) => project.workspaces.some((workspace) => workspace.id === row.workspaceId));
  const targetRow = rows.find((row) => row.id === workbench.highlightedRowId && row.endReference?.kind === "cross-page");
  const processEvents: StageEvent[] = stageProgress.map((stage, index) => ({
    id: `process-${stage.stage}`,
    stage: `Agent ${index + 1}`,
    title: stage.agentName ?? stage.stage,
    detail: stage.status === "processing" ? "主 Agent 已调度该 Agent，正在处理。" : stage.status === "done" ? "处理完成，主 Agent 正在决定下一步。" : "处理失败。",
    status: stage.status === "processing" ? "active" : stage.status === "done" ? "done" : stage.status === "failed" ? "failed" : "pending",
    timestamp: "",
  }));

  async function runSupervisor(input: SupervisorCommand) {
    if (isRunning) return;
    const request: SupervisorRequest = { ...input, projectId: project.id };
    const abortController = new AbortController();
    setAgentEvents([]);
    setStageProgress([]);
    setIsRunning(true);
    try {
      for await (const update of streamSupervisorRun(request, abortController.signal, projectRows)) {
        if (update.stageUpdate) {
          setStageProgress((current) => {
            const index = current.findIndex((stage) => stage.stage === update.stageUpdate?.stage);
            if (index < 0) return [...current, update.stageUpdate!];
            const next = [...current];
            next[index] = update.stageUpdate!;
            return next;
          });
        }
        if (update.event) setAgentEvents((current) => [
          ...current.map((event) => event.status === "running" ? { ...event, status: "done" as const } : event),
          update.event!,
        ]);
        if (update.rowPatch) setRows((current) => current.map((row) => row.id === update.rowPatch?.id ? update.rowPatch : row));
        if (update.ruleCandidate) setRuleLibrary((current) => [update.ruleCandidate!, ...current.filter((rule) => rule.id !== update.ruleCandidate?.id)]);
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Agent 运行失败";
      setStageProgress((current) => current.map((stage) => stage.status === "processing" ? { ...stage, status: "failed" } : stage));
      setAgentEvents((current) => [
        ...current.map((event) => event.status === "running" ? { ...event, status: "failed" as const } : event),
        { id: `agent-error-${Date.now()}`, kind: "error", title: "主 Agent", detail: message, stage: "任务执行", status: "failed", timestamp: new Date().toLocaleTimeString("zh-CN", { hour12: false }) },
      ]);
    } finally {
      setIsRunning(false);
    }
  }

  function runRepair(message: string) {
    void runSupervisor({ kind: "repair", message });
  }

  function handleSimulationToggle(enabled: boolean) {
    setSimulationEnabled(enabled);
    if (enabled && pendingExtraction && uploadedFilename && !isRunning) {
      setPendingExtraction(false);
      void runSupervisor({ kind: "extract", filename: uploadedFilename });
    }
  }

  function handlePdfUpload(file?: File) {
    if (!file) return;
    setUploadedFilename(file.name);
    setAgentEvents([]);
    setStageProgress([]);
    setPendingExtraction(!simulationEnabled);
    if (simulationEnabled) {
      setPendingExtraction(false);
      void runSupervisor({ kind: "extract", filename: file.name });
    }
    if (pdfInputRef.current) pdfInputRef.current.value = "";
  }

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2400);
  }

  return (
    <div className="workbench-app">
      <AppHeader project={project} />
      <main className="workbench-grid">
        <ProjectTree project={project} projects={projects} selectedWorkspaceId={workbench.effectiveWorkspaceId} selectedDrawingId={workbench.selectedDrawingId} stageProgress={stageProgress} uploadedFilename={uploadedFilename} simulationEnabled={simulationEnabled} onSelectWorkspace={workbench.selectWorkspace} onSelectDrawing={workbench.selectDrawing} />
        <section className="project-main">
          <div className="project-context-bar">
            <div className="breadcrumbs"><span>项目</span><ChevronRight size={14} /><span>{project.name}</span>{workbench.selectedWorkspace ? <><ChevronRight size={14} /><strong>{workbench.selectedWorkspace.code}</strong></> : null}</div>
            <nav className="project-resource-nav" aria-label="项目资源导航">
              <button type="button" className={activeSection === "results" ? "active" : ""} onClick={() => setActiveSection("results")}><FileSpreadsheet size={15} />线表工作区</button>
              <button type="button" className={activeSection === "drawings" ? "active" : ""} onClick={() => setActiveSection("drawings")}><FileText size={15} />图纸库<span>{drawingLibrary.length}</span></button>
              <button type="button" className={activeSection === "rules" ? "active" : ""} onClick={() => setActiveSection("rules")}><RefreshCw size={14} />规则库<span>{ruleLibrary.length}</span></button>
            </nav>
            <div className="context-actions"><input ref={pdfInputRef} className="visually-hidden" type="file" accept="application/pdf,.pdf" onChange={(event) => handlePdfUpload(event.target.files?.[0])} /><button type="button" className="secondary-button" disabled={isRunning} onClick={() => pdfInputRef.current?.click()}><Upload size={15} />{isRunning ? "Agent 处理中" : "上传 PDF"}</button><button type="button" className="primary-button" onClick={() => showNotice("结果快照 XLSX 将由导出 API 生成")}><Download size={16} />导出 XLSX</button></div>
          </div>
          <header className="project-overview">
            <div className="overview-copy"><div className="overview-title"><h1>{project.name}</h1><span className={`project-status project-status-${project.status}`}><CheckCircle2 size={14} />{project.status === "completed" ? "已完成" : project.status === "review" ? "待复核" : "等待处理"}</span></div><p>{project.sourceFilename}</p><div className="project-meta"><span>项目号 <strong>{project.projectNo}</strong></span><span>图纸标准 <strong>{project.profile}</strong></span><span>当前版本 <strong>{project.resultVersion}</strong></span></div></div>
            <div className="overview-stats"><div><strong>{project.workspaceCount}</strong><span>工作区</span></div><div><strong>{project.drawingCount}</strong><span>图纸</span></div><div><strong>{projectRows.length}</strong><span>示例记录</span></div><div className="progress-stat"><strong>{project.progress}%</strong><span>处理进度</span><i><b style={{ width: `${project.progress}%` }} /></i></div></div>
          </header>
          {activeSection === "drawings" ? <DrawingLibraryPanel items={drawingLibrary} activeProjectId={project.id} /> : null}
          {activeSection === "rules" ? <RuleLibraryPanel items={ruleLibrary} /> : null}
          {activeSection === "results" ? <>
            <div className="content-tabs" role="tablist" aria-label="线表工作区视图"><button type="button" role="tab" aria-selected={workbench.activeTab === "results"} className={workbench.activeTab === "results" ? "active" : ""} onClick={() => workbench.setActiveTab("results")}><FileSpreadsheet size={16} />线表结果<span>{workbench.visibleRows.length}</span></button><button type="button" role="tab" aria-selected={workbench.activeTab === "drawing"} className={workbench.activeTab === "drawing" ? "active" : ""} onClick={() => workbench.setActiveTab("drawing")}><FileText size={16} />图纸与证据</button><button type="button" role="tab" aria-selected={workbench.activeTab === "events"} className={workbench.activeTab === "events" ? "active" : ""} onClick={() => workbench.setActiveTab("events")}><RefreshCw size={15} />处理过程</button></div>
            {workbench.activeTab === "results" ? <section className="results-section"><div className="table-toolbar"><div><h2>{workbench.selectedDrawing ? `图纸 ${workbench.selectedDrawing.drawingPage} · ${workbench.selectedDrawing.name}` : workbench.selectedWorkspace ? `${workbench.selectedWorkspace.code} · ${workbench.selectedWorkspace.name}` : "线表结果"}</h2><span>{workbench.visibleRows.length} 条记录 · 按图纸页序排列</span></div><div className="table-tools"><label><Search size={16} /><input value={workbench.query} onChange={(event) => workbench.setQuery(event.target.value)} placeholder="搜索端子、原理号或描述" /></label></div></div><ResultTable rows={workbench.visibleRows} onOpenDrawing={workbench.openDrawing} onOpenTarget={workbench.openRowTarget} onHoverTarget={workbench.hoverRowTarget} highlightedRowId={workbench.highlightedRowId} /><footer className="table-footer"><span>第 1 页，共 1 页</span><div><button type="button" disabled>上一页</button><button type="button" className="active">1</button><button type="button" disabled>下一页</button></div></footer></section> : null}
            {workbench.activeTab === "drawing" ? <DrawingPreview project={project} drawing={workbench.selectedDrawing} targetTerminal={targetRow?.endReference?.targetTerminal} /> : null}
            {workbench.activeTab === "events" ? <StageTimeline events={processEvents} /> : null}
          </> : null}
        </section>
        <AiPanel events={agentEvents} stageProgress={stageProgress} isRunning={isRunning} hasPendingUpload={pendingExtraction} simulationEnabled={simulationEnabled} onSimulationToggle={handleSimulationToggle} onRunRepair={runRepair} />
      </main>
      {notice ? <div className="prototype-toast" role="status">{notice}</div> : null}
    </div>
  );
}
