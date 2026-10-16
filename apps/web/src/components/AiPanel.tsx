import { Activity, Brain, Check, Circle, Loader2, Send, Sparkles, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type { AgentStageProgress } from "@/apis/agent";
import type { AgentEvent } from "@/apis/types";

export interface AiPanelProps {
  events: AgentEvent[];
  stageProgress: AgentStageProgress[];
  isRunning: boolean;
  hasPendingUpload: boolean;
  simulationEnabled: boolean;
  onSimulationToggle: (enabled: boolean) => void;
  onRunRepair: (message: string) => void;
  onReconnect?: () => void;
  onClose?: () => void;
  isVisible?: boolean;
  unavailableReason?: string;
}

export function AiPanel({ events, isRunning, hasPendingUpload, simulationEnabled, onSimulationToggle, onRunRepair, onReconnect, onClose, isVisible = true, unavailableReason }: AiPanelProps) {
  const [request, setRequest] = useState("");
  const feed = useRef<HTMLDivElement>(null);
  const followTail = useRef(true);
  const [shownPlans, setShownPlans] = useState<Set<string>>(() => new Set());
  const finishPlan = useCallback((id: string) => setShownPlans(previous => new Set(previous).add(id)), []);
  const waitingPlan = events.findIndex(event => event.kind === "thought" && !shownPlans.has(event.id));
  const visibleEvents = waitingPlan < 0 ? events : events.slice(0, waitingPlan + 1);
  const latestEvent = events[events.length - 1];
  useEffect(() => { if (isVisible && feed.current && followTail.current) feed.current.scrollTop = feed.current.scrollHeight; }, [events.length, latestEvent?.detail, shownPlans, isRunning, isVisible]);

  function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = request.trim();
    if (!simulationEnabled || !message || isRunning) return;
    onRunRepair(message);
    setRequest("");
  }

  return (
    <aside className="ai-panel">
      <div className="ai-heading">
        <div><span className="ai-mark"><Sparkles size={17} /></span><span><strong>电气图纸与线表智能助手</strong><small>图纸解读、连接提取与线表核对</small></span></div>
        <div className="ai-heading-actions"><span className={`agent-run-status ${isRunning ? "running" : hasPendingUpload ? "queued" : ""}`}><i />{unavailableReason ? "未接入" : isRunning ? "执行中" : hasPendingUpload ? "待启动" : "已就绪"}</span>{onClose ? <button type="button" onClick={onClose} aria-label="收起聊天窗口" title="收起聊天窗口"><X size={18} /></button> : null}</div>
      </div>
      <div ref={feed} className="agent-feed" role="log" aria-live="polite" aria-label="智能助手对话和任务进度" onScroll={e => { const node = e.currentTarget; followTail.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80; }}>
        <div className="agent-feed-label"><span><Activity size={13} />对话与任务进度</span><small>{isRunning ? "实时更新" : ""}</small></div>
        {visibleEvents.map((event) => <AgentFeedItem key={event.id} event={event} onPlanComplete={finishPlan} />)}
        {!events.length ? <div className="agent-feed-empty"><Activity size={22} /><strong>{unavailableReason ? "提取功能待接入" : hasPendingUpload ? "PDF 已上传，等待确认" : "你好，我是电气图纸与线表智能助手"}</strong><span>{unavailableReason ?? "可以直接聊天、询问图纸知识，或上传 PDF 提取连接信息。"}</span></div> : null}
        {isRunning ? <div className="agent-streaming"><Loader2 size={14} className="spin" />助手正在回复或处理任务</div> : null}
      </div>
      <form className="agent-composer" onSubmit={submitRequest}>
        <div className="agent-composer-heading"><span>向主 Agent 提出需求</span>{onReconnect ? <button type="button" disabled={isRunning} onClick={onReconnect}>重新连接进度</button> : null}<button type="button" disabled={isRunning || !!unavailableReason} onClick={() => onSimulationToggle(true)}>新任务</button></div>
        <textarea disabled={!!unavailableReason} value={request} onChange={(event) => setRequest(event.target.value)} rows={3} placeholder={unavailableReason ? "提取与AI对话尚未接入" : "例如：线号 021M0115 的终点可能识别错了，请帮我修复"} aria-label="向主 Agent 提出自然语言需求" />
        <div className="agent-composer-footer"><small>{unavailableReason ? "当前可管理项目、文件和线表" : "Agent :8100 · 数据与规则修改需人工确认"}</small><button type="submit" disabled={!!unavailableReason || !simulationEnabled || !request.trim() || isRunning} aria-label="发送给主 Agent" title="发送给主 Agent"><Send size={16} /></button></div>
      </form>
    </aside>
  );
}

function AgentFeedItem({ event, onPlanComplete }: { event: AgentEvent; onPlanComplete: (id: string) => void }) {
  if (event.kind === "message" || event.title === "用户") {
    return <div className={`agent-message ${event.title === "用户" ? "agent-message-user" : "agent-message-assistant"}`}><strong>{event.title}</strong><p>{event.detail}{event.status === "running" ? <span className="thought-cursor" aria-hidden="true">▌</span> : null}</p></div>;
  }
  if (event.kind === "thought") {
    return <div className="agent-thought"><Brain size={13} /><div><strong>处理说明</strong><ThoughtStream text={event.detail} id={event.id} onComplete={onPlanComplete} /></div></div>;
  }

  const status = event.status === "running" ? "processing" : event.status === "failed" ? "failed" : event.status === "pending" ? "pending" : "done";
  const icon = status === "failed" ? <XCircle size={15} /> : status === "done" ? <Check size={15} /> : <Circle size={13} className="agent-wait-circle" />;
  const agentTitle = event.title;
  const stateLabel = status === "processing" ? "处理中" : status === "done" ? "已完成" : status === "failed" ? "失败" : "等待处理";
  return <article className={`agent-step agent-step-${status} agent-event-${event.kind}`}><span className="agent-step-status">{icon}</span><div><header><strong>{agentTitle}</strong><span>{stateLabel}</span></header><p>{event.detail}</p><footer><span>{event.stage}</span><time>{event.timestamp}</time></footer></div></article>;
}

function ThoughtStream({ text, id, onComplete }: { text: string; id: string; onComplete: (id: string) => void }) {
  const [visibleText, setVisibleText] = useState("");

  useEffect(() => {
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setVisibleText(text.slice(0, index));
      if (index >= text.length) { window.clearInterval(timer); onComplete(id); }
    }, 24);
    return () => window.clearInterval(timer);
  }, [text, id, onComplete]);

  return <p>{visibleText}{visibleText.length < text.length ? <span className="thought-cursor" aria-hidden="true">▌</span> : null}</p>;
}
