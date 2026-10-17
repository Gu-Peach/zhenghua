import { ChevronRight, FileImage, Loader2, MessageCircle, Send, Square, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { toolLabel, toolResultView, type EvidenceDrawing, type ExplainSelection } from "@/apis/explain";
import { useExplainConversation, type ExplainTool } from "@/hooks/useExplainConversation";
import { TypewriterAnswer } from "./TypewriterAnswer";

function ToolRecord({ tool }: { tool: ExplainTool }) {
  const result = toolResultView(tool.activity);
  return <details className={`explain-tool ${tool.status}`}>
    <summary>{tool.status === "running" ? <Loader2 size={14} className="spin" /> : <Wrench size={14} />}<span>{toolLabel(tool.activity)}</span><ChevronRight size={13} /></summary>
    <div className="explain-tool-result"><p>{tool.status === "running" ? "正在获取资料…" : tool.status === "failed" && !tool.activity.error ? "工具未完成，详见下方提示。" : result.summary}</p>
      {result.connections.length ? <ul>{result.connections.map(row => <li key={row.id}><span>{row.number}</span><span>{row.start} → {row.end}</span></li>)}</ul> : null}
      {result.pages.length ? <p>{result.pages.join(" · ")}</p> : null}
      {result.gaps.map((gap, index) => <p key={index} className="explain-gap">{gap}</p>)}
      {tool.activity.result ? <details className="explain-raw"><summary>完整工具结果</summary><pre>{result.json}</pre></details> : null}
    </div>
  </details>;
}

function EvidenceImage({ drawing }: { drawing: EvidenceDrawing }) {
  const [failedUrl, setFailedUrl] = useState("");
  const available = drawing.url && drawing.url !== failedUrl;
  return <figure className="explain-drawing">
    {available ? <a href={drawing.url} target="_blank" rel="noopener noreferrer" title="打开原图"><img src={drawing.url} alt={`${drawing.role} ${drawing.title}`} onError={() => setFailedUrl(drawing.url!)} /></a> : <div className="explain-image-empty"><FileImage size={20} /><span>{drawing.url ? "图纸加载失败或链接过期" : "图纸尚不可用"}</span></div>}
    <figcaption><span>{drawing.role}</span>{drawing.title}</figcaption>
  </figure>;
}

export function ExplainPanel({ projectId, selection, onClose }: { projectId: string; selection: ExplainSelection; onClose: () => void }) {
  const { messages, drawings, busy, send, stop } = useExplainConversation(projectId, selection);
  const [draft, setDraft] = useState("");
  const panel = useRef<HTMLElement>(null); const feed = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const scrollToLatest = useCallback(() => { if (follow.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight; }, []);
  useEffect(() => { panel.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => { scrollToLatest(); }, [messages, drawings, scrollToLatest]);
  function submit(event: FormEvent) { event.preventDefault(); if (!busy && draft.trim()) { void send(draft.trim()); setDraft(""); follow.current = true; } }
  return <section ref={panel} className="explain-panel" role="dialog" aria-modal="false" aria-label="来源解释" tabIndex={-1} onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); onClose(); } }}>
    <header className="explain-header"><MessageCircle size={19} /><div><strong>来源解释</strong><p title={selection.title}>{selection.title}</p></div><button type="button" className="icon-button" aria-label="关闭来源解释" title="关闭并停止当前解释" onClick={onClose}><X size={19} /></button></header>
    <div ref={feed} className="explain-feed" onScroll={() => { if (feed.current) follow.current = feed.current.scrollHeight - feed.current.scrollTop - feed.current.clientHeight < 70; }}>
      {messages.map(message => <article key={message.id} className="explain-turn">
        <p className="explain-question">{message.question}</p>
        <div className="explain-tools">{message.tools.map(tool => <ToolRecord key={tool.activity.id} tool={tool} />)}</div>
        {message.status === "running" ? <div className="explain-working" role="status"><Loader2 size={14} className="spin" />{message.answer ? "正在生成解释…" : "正在分析来源与关联图纸…"}</div> : null}
        {message.historyReset ? <p className="explain-gap">资料已更新，本轮基于最新记录重新解释。</p> : null}
        {message.answer ? <TypewriterAnswer text={message.answer} running={message.status === "running"} halted={message.status === "cancelled"} onProgress={scrollToLatest} /> : null}
        {message.status === "failed" || message.status === "cancelled" ? <div className="explain-error" role={message.status === "failed" ? "alert" : "status"}><span>{message.error ?? "已停止生成，以上内容可能不完整。"}</span><button type="button" disabled={busy} onClick={() => void send(message.question, message.id)}>重试</button></div> : null}
      </article>)}
      {drawings.length ? <section className="explain-evidence" aria-label="关联图纸"><h3>关联图纸 <span>{drawings.length}</span></h3><div>{drawings.map(drawing => <EvidenceImage key={drawing.key} drawing={drawing} />)}</div></section> : null}
    </div>
    <form className="explain-composer" onSubmit={submit}><label className="visually-hidden" htmlFor="explain-question">追问来源解释</label><textarea id="explain-question" value={draft} maxLength={8000} placeholder="继续询问这条连接或本页的提取依据…" rows={2} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!busy && draft.trim()) { void send(draft.trim()); setDraft(""); follow.current = true; } } }} />
      <div><span>只读解释 · 不修改线表</span>{busy ? <button type="button" aria-label="停止生成" title="停止生成" onClick={stop}><Square size={15} /></button> : <button type="submit" aria-label="发送追问" title="发送追问" disabled={!draft.trim()}><Send size={16} /></button>}</div>
    </form>
  </section>;
}
