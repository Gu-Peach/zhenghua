import { FileSpreadsheet, FileText, Loader2, RefreshCw, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { projectApi } from "@/apis/projects";
import type { RuleLibraryItem } from "@/apis/types";
import { AppHeader } from "./AppHeader";
import { FloatingAgentPanel } from "./FloatingAgentPanel";
import { RuleLibraryPanel } from "./LibraryPanel";
import { ProjectTree } from "./ProjectTree";

export function EmptyWorkspace({ loading, error, onRetry, onUpload }: { loading: boolean; error: string; onRetry: () => void; onUpload: (file: File) => void }) {
  const [section, setSection] = useState<"results" | "drawings" | "rules">("results");
  const [rules, setRules] = useState<RuleLibraryItem[] | null>(null); const [ruleError, setRuleError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  async function loadRules() { try { setRules(await projectApi.listRuleLibrary()); setRuleError(""); } catch (reason) { setRuleError(String(reason)); } }
  return <div className="workbench-app"><AppHeader /><main className="workbench-grid real-workbench">
    <ProjectTree project={null} projects={[]} loading={loading} selectedWorkspaceId={null} selectedDrawingId={null} stageProgress={[]} uploadedFilename={null} simulationEnabled={false} onSelectWorkspace={() => {}} onSelectDrawing={() => {}} />
    <div className="panel-resizer" aria-hidden="true" />
    <section className="project-main"><div className="project-context-bar"><h1 className="context-project-name">工作区</h1><nav className="project-resource-nav"><button type="button" className={section === "results" ? "active" : ""} onClick={() => setSection("results")}><FileSpreadsheet size={15} />线表工作区</button><button type="button" className={section === "drawings" ? "active" : ""} onClick={() => setSection("drawings")}><FileText size={15} />图纸库</button><button type="button" className={section === "rules" ? "active" : ""} onClick={() => { setSection("rules"); if (rules === null) void loadRules(); }}><RefreshCw size={15} />规则库</button></nav><div className="project-file-actions"><button type="button" className="secondary-button" disabled={loading} onClick={() => input.current?.click()}><Upload size={15} />上传 PDF</button></div></div>
    <input ref={input} type="file" className="visually-hidden" accept="application/pdf" onChange={event => { if (event.target.files?.[0]) onUpload(event.target.files[0]); event.target.value = ""; }} />
    {loading ? <div className="project-data-loading" role="status"><Loader2 className="spin" size={20} />正在加载项目…</div> : error ? <div className="workspace-empty-state"><p role="alert">{error}</p><button type="button" className="secondary-button" onClick={onRetry}>重试</button></div> : section === "rules" ? ruleError ? <div className="inline-error" role="alert">{ruleError}<button type="button" onClick={() => void loadRules()}>重试读取规则库</button></div> : rules === null ? <p role="status">正在读取规则引用…</p> : <RuleLibraryPanel items={rules} onChanged={loadRules} /> : <div className="workspace-empty-state"><FileSpreadsheet size={28} /><h2>{section === "results" ? "暂无项目" : "暂无图纸"}</h2><p>上传 PDF 创建项目，在此管理图纸和线表。</p><button type="button" className="primary-button" onClick={() => input.current?.click()}><Upload size={16} />上传 PDF</button></div>}
    </section></main><FloatingAgentPanel events={[]} stageProgress={[]} isRunning={false} hasPendingUpload={false} simulationEnabled={false} unavailableReason="当前支持项目、文件和线表数据管理。自动提取与AI对话将在后续接入。" onSimulationToggle={() => {}} onRunRepair={() => {}} /></div>;
}
