import { ArrowLeft, Bot, FileScan, MessagesSquare, RefreshCw, Settings2 } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { agentCatalog, type AgentInfo } from "@/apis/agents";
import { projectApi } from "@/apis/projects";
import type { RuleLibraryItem } from "@/apis/types";
import { AppHeader } from "@/components/AppHeader";
import { RuleLibraryPanel } from "@/components/LibraryPanel";
const ProfileConversation = lazy(() => import("@/components/ProfileConversation").then(module => ({ default: module.ProfileConversation })));
const ProfileWizard = lazy(() => import("@/components/ProfileWizard").then(module => ({ default: module.ProfileWizard })));

export function AgentsView() {
  const { agentId } = useParams();
  const [searchParams] = useSearchParams();
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [error, setError] = useState(""); const [retry, setRetry] = useState(0);
  useEffect(() => { let active = true; agentCatalog().then(value => { if (active) { setAgents(value); setError(""); } }).catch(reason => { if (active) setError(String(reason)); }); return () => { active = false; }; }, [retry]);
  const selected = agents?.find(agent => agent.id === agentId);
  const icons = { extraction: FileScan, explain: MessagesSquare, profile: Settings2 };
  return <div className="workbench-app"><AppHeader /><main className="agents-page">
    <nav className="agents-breadcrumb"><Link to={agentId ? "/agents" : "/projects"}><ArrowLeft size={15} />{agentId ? "返回智能体中心" : "返回工作台"}</Link></nav>
    <header className="agents-heading"><Bot size={24} /><div><h1>{selected?.name ?? "智能体中心"}</h1><p>{selected?.description ?? "查看智能体能力、接入状态及提取 Skills"}</p></div><button type="button" className="secondary-button" onClick={() => setRetry(n => n + 1)}><RefreshCw size={14} />刷新状态</button></header>
    {error ? <p className="inline-error" role="alert">状态读取失败：{error}</p> : !agents ? <p role="status">正在读取智能体信息…</p> : !agentId ? <>
      <div className="agent-cards">{agents.map(agent => { const Icon = icons[agent.id as keyof typeof icons]; return <Link className="agent-card" key={agent.id} to={`/agents/${agent.id}`}><div className="agent-card-top"><span className="agent-card-icon"><Icon size={22} /></span><span className={`agent-status-badge${agent.available ? " is-available" : ""}`}>{agent.status}</span></div><h2>{agent.name}</h2><small>{agent.code}</small><p>{agent.description}</p><footer><small>版本 {agent.version}</small><span>{agent.id === "extraction" ? "管理提取 Skills →" : "查看能力说明 →"}</span></footer></Link>; })}</div>
      <p className="agents-note">“已接入”表示业务接口已开放，未检测运行时连通性。Agent 展示版本统一为 1.0.0；Skill 使用各规则包的实际版本。</p>
    </> : !selected ? <p role="alert">没有此智能体。<Link to="/agents">返回智能体中心</Link></p> : agentId === "extraction" || agentId === "profile" && searchParams.has("profile") ? <ExtractionSkills key={searchParams.get("profile")} initialRuleId={searchParams.get("profile") ?? undefined} /> : agentId === "profile" ? <Suspense fallback={<p role="status">正在加载规则对话…</p>}>{searchParams.get("editor") === "form" ? <ProfileWizard /> : <ProfileConversation />}</Suspense> : <section className="agent-capability"><h2>{selected.code}</h2><p>能力状态：{selected.status} · Agent 版本：{selected.version}</p><p>在工作台悬停端子或页码，点击来源解释图标即可检索资料并交流。</p><Link to="/projects">返回工作台</Link></section>}
  </main></div>;
}

function ExtractionSkills({ initialRuleId }: { initialRuleId?: string }) {
  const [rules, setRules] = useState<RuleLibraryItem[] | null>(null); const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => { let active = true; projectApi.listRuleLibrary().then(items => { if (active) { setRules(items); setError(""); } }).catch(reason => { if (active) setError(String(reason)); }); return () => { active = false; }; }, [retry]);
  return error ? <p className="inline-error" role="alert">{error}<button type="button" onClick={() => setRetry(n => n + 1)}>重试读取 Skills</button></p> : !rules ? <p role="status">正在读取提取 Skills…</p> : initialRuleId && !rules.some(rule => rule.id === initialRuleId) ? <p role="alert">指定规则不存在或已被更新，请返回提取 Skills 选择当前版本。</p> : <RuleLibraryPanel items={rules} asSkills initialRuleId={initialRuleId} onChanged={async () => { setRules(await projectApi.listRuleLibrary()); }} />;
}
