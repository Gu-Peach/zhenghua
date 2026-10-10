import { Activity, Brain, Bot, Check, Circle, Loader2, Send, Sparkles, XCircle } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { AgentStageProgress } from "@/apis/agent";
import type { AgentEvent } from "@/apis/types";

interface AiPanelProps {
  events: AgentEvent[];
  stageProgress: AgentStageProgress[];
  isRunning: boolean;
  hasPendingUpload: boolean;
  simulationEnabled: boolean;
  onSimulationToggle: (enabled: boolean) => void;
  onRunRepair: (message: string) => void;
}

export function AiPanel({ events, stageProgress, isRunning, hasPendingUpload, simulationEnabled, onSimulationToggle, onRunRepair }: AiPanelProps) {
  const [request, setRequest] = useState("");
  const currentStage = useMemo(() => [...stageProgress].reverse().find((stage) => stage.status === "processing"), [stageProgress]);
  const latestEvent = events[events.length - 1];
  const stageLabel = currentStage?.agentName ?? latestEvent?.stage ?? (isRunning ? "Supervisor 正在分析需求" : hasPendingUpload ? "等待模拟链路启动" : "等待上传 PDF 或用户需求");
  const stageStatus = currentStage ? "正在处理" : isRunning ? "思考中" : latestEvent?.status === "failed" ? "执行失败" : latestEvent?.kind === "result" ? "已完成" : "等待触发";

  function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = request.trim();
    if (!simulationEnabled || !message || isRunning) return;
    onRunRepair(message);
  }

  return (
    <aside className="ai-panel">
      <div className="ai-heading">
        <div><span className="ai-mark"><Sparkles size={17} /></span><span><strong>Supervisor 主 Agent</strong><small>思考与子 Agent 调度</small></span></div>
        <span className={`agent-run-status ${isRunning ? "running" : hasPendingUpload ? "queued" : ""}`}><i />{isRunning ? "执行中" : hasPendingUpload ? "待启动" : "已就绪"}</span>
      </div>
      <div className="agent-current-stage"><span className={isRunning ? "agent-pulse" : ""}><Bot size={16} /></span><div><small>当前阶段</small><strong>{stageLabel}</strong></div><span className="agent-stage-state">{stageStatus}</span></div>
      <div className="agent-feed" role="log" aria-live="polite" aria-label="主 Agent 流式思考和子 Agent 事件">
        <div className="agent-feed-label"><span><Activity size={13} />思考与处理过程</span><small>{isRunning ? "实时更新" : ""}</small></div>
        {events.map((event) => <AgentFeedItem key={event.id} event={event} progress={stageProgress.find((stage) => stage.stage === event.stage)} />)}
        {!events.length ? <div className="agent-feed-empty"><Activity size={22} /><strong>{hasPendingUpload ? "PDF 已上传，等待模拟链路" : "等待上传 PDF 或用户提出需求"}</strong><span>{hasPendingUpload ? "开启模拟后，主 Agent 将从 Stage 1 页面分类开始处理。" : "主 Agent 处理过程会在触发后从意图分析开始逐步显示。"}</span></div> : null}
        {isRunning ? <div className="agent-streaming"><Loader2 size={14} className="spin" />主 Agent 正在思考</div> : null}
      </div>
      <form className="agent-composer" onSubmit={submitRequest}>
        <div className="agent-composer-heading"><span>向主 Agent 提出需求</span><label className="simulation-toggle"><input type="checkbox" checked={simulationEnabled} disabled={isRunning} onChange={(event) => onSimulationToggle(event.target.checked)} /><span aria-hidden="true" /><strong>模拟链路</strong></label></div>
        <textarea value={request} onChange={(event) => setRequest(event.target.value)} rows={3} placeholder="例如：线号 021M0115 的终点可能识别错了，请帮我修复" aria-label="向主 Agent 提出自然语言需求" />
        <div className="agent-composer-footer"><small>{simulationEnabled ? "上传 PDF 或发送需求以启动 Mock Supervisor" : "开启模拟链路后，上传 PDF 或发送需求以启动演示"}</small><button type="submit" disabled={!simulationEnabled || !request.trim() || isRunning} aria-label="发送给主 Agent" title="发送给主 Agent"><Send size={16} /></button></div>
      </form>
    </aside>
  );
}

function AgentFeedItem({ event, progress }: { event: AgentEvent; progress?: AgentStageProgress }) {
  if (event.kind === "thought") {
    return <div className="agent-thought"><Brain size={13} /><div><strong>主 Agent 思考</strong><ThoughtStream text={event.detail} /></div></div>;
  }

  const status = progress?.status ?? (event.status === "running" ? "processing" : event.status === "failed" ? "failed" : "done");
  const icon = status === "failed" ? <XCircle size={15} /> : status === "done" ? <Check size={15} /> : <Circle size={13} className="agent-wait-circle" />;
  const agentTitle = progress?.agentName ?? event.title;
  const stateLabel = status === "processing" ? "处理中" : status === "done" ? "已完成" : status === "failed" ? "失败" : "等待处理";
  return <article className={`agent-step agent-step-${status} agent-event-${event.kind}`}><span className="agent-step-status">{icon}</span><div><header><strong>{agentTitle}</strong><span>{stateLabel}</span></header><p>{event.detail}</p><footer><span>{event.stage}</span><time>{event.timestamp}</time></footer></div></article>;
}

function ThoughtStream({ text }: { text: string }) {
  const [visibleText, setVisibleText] = useState("");

  useEffect(() => {
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setVisibleText(text.slice(0, index));
      if (index >= text.length) window.clearInterval(timer);
    }, 24);
    return () => window.clearInterval(timer);
  }, [text]);

  return <p>{visibleText}{visibleText.length < text.length ? <span className="thought-cursor" aria-hidden="true">▌</span> : null}</p>;
}
