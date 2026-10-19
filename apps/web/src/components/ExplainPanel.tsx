import { ChevronRight, FileImage, History, Loader2, MessageCircle, Send, Square, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { toolLabel, toolResultView, type EvidenceDrawing, type ExplainSelection } from "@/apis/explain";
import { useExplainConversation, type ExplainTool } from "@/hooks/useExplainConversation";
import { TypewriterAnswer } from "./TypewriterAnswer";
import { ExplainEditProposal } from "./ExplainEditProposal";
import type { EditProposal } from "@/apis/explain-edits";
import type { RescanPageChoice, RescanRun } from "@/apis/rescan";
import { RescanAttachments, type RescanAttachmentHandle } from "./RescanAttachments";
import { RescanTask } from "./RescanTask";
import { DrawingLightbox, type LightboxImage } from "./DrawingLightbox";
import { useDraggablePanel } from "@/hooks/useDraggablePanel";
import "@/assets/explain-rescan.css";

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

function EvidenceImage({ drawing, onOpen }: { drawing: EvidenceDrawing; onOpen: (image: LightboxImage) => void }) {
  const [failedUrl, setFailedUrl] = useState("");
  const available = drawing.url && drawing.url !== failedUrl;
  return <figure className="explain-drawing">
    {available ? <button type="button" className="drawing-thumbnail" aria-label={`放大查看 ${drawing.role} ${drawing.title}`} onClick={() => onOpen({ url: drawing.url!, title: `${drawing.role} ${drawing.title}` })}><img src={drawing.url} alt={`${drawing.role} ${drawing.title}`} onError={() => setFailedUrl(drawing.url!)} /></button> : <div className="explain-image-empty"><FileImage size={20} /><span>{drawing.url ? "图纸加载失败或链接过期" : "图纸尚不可用"}</span></div>}
    <figcaption><span>{drawing.role}</span>{drawing.title}</figcaption>
  </figure>;
}

export function ExplainPanel({ projectId, selection, onClose, onModified, onRescanned, availablePages = [], readOnly = false }: { projectId: string; selection: ExplainSelection; onClose: () => void; onModified?: (proposal: EditProposal) => void; onRescanned?: (run: RescanRun) => void; availablePages?: RescanPageChoice[]; readOnly?: boolean }) {
  const { messages, busy: talking, send, stop, proposals, proposalError, applyDecision, conversationId, rescans, setAttachmentIds, applyRescan, loadRescans, loadingRescans, rescanHistoryError, selectionNotice, currentTitle } = useExplainConversation(projectId, selection);
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  const [editing, setEditing] = useState(false); const [ready, setReady] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState(false); const uploader = useRef<RescanAttachmentHandle>(null);
  const busy = talking || editing || uploading;
  const [draft, setDraft] = useState(selection.draftMessage ?? "");
  const panel = useRef<HTMLElement>(null); const feed = useRef<HTMLDivElement>(null);
  const movement = useDraggablePanel(panel);
  const follow = useRef(true);
  const scrollToLatest = useCallback(() => { if (follow.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight; }, []);
  useEffect(() => { panel.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => { scrollToLatest(); }, [messages, proposals, rescans, ready, scrollToLatest]);
  function submit(event: FormEvent) { event.preventDefault(); if (!busy && draft.trim()) { void send(draft.trim()); setDraft(""); follow.current = true; } }
  return <section ref={panel} className={`explain-panel ${movement.dragging ? "is-dragging" : ""}`} style={movement.style} role="dialog" aria-modal="false" aria-label="来源解释" tabIndex={-1} onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); onClose(); } }}>
    <header className="explain-header" {...movement.headerProps}><MessageCircle size={19} /><div><strong>来源解释</strong><p title={currentTitle}>{currentTitle}</p></div><button type="button" className="icon-button" aria-label="查看项目重扫记录" title="按需查看项目已有重扫任务，不会启动重扫" disabled={loadingRescans || busy} onClick={() => void loadRescans()}>{loadingRescans ? <Loader2 size={18} className="spin" /> : <History size={18} />}</button><button type="button" className="icon-button" aria-label="关闭来源解释" title="关闭并停止当前解释" onClick={onClose}><X size={19} /></button></header>
    <div ref={feed} className="explain-feed" onScroll={() => { if (feed.current) follow.current = feed.current.scrollHeight - feed.current.scrollTop - feed.current.clientHeight < 70; }}>
      {selectionNotice ? <p className="explain-gap" role="status">{selectionNotice}</p> : null}
      {selection.skipInitial && !messages.length ? <p className="explain-gap">已选择{selection.title}。可先添加细节图并补充要求，再发送重扫请求；结果确认前线表保持原值。</p> : null}
      {messages.map(message => <article key={message.id} className="explain-turn">
        <p className="explain-question">{message.question}</p>
        <div className="explain-tools">{message.tools.map(tool => <ToolRecord key={tool.activity.id} tool={tool} />)}</div>
        {message.drawings.length ? <section className="explain-evidence" aria-label="关联图纸"><h3>关联图纸 <span>{message.drawings.length}</span></h3><div>{message.drawings.map(drawing => <EvidenceImage key={drawing.key} drawing={drawing} onOpen={setLightbox} />)}</div></section> : null}
        {message.status === "running" ? <div className="explain-working" role="status"><Loader2 size={14} className="spin" />{message.answer ? "正在生成解释…" : "正在分析来源与关联图纸…"}</div> : null}
        {message.historyReset ? <p className="explain-gap">资料已更新，本轮基于最新记录重新解释。</p> : null}
        {message.answer ? <TypewriterAnswer text={message.answer} running={message.status === "running"} halted={message.status === "cancelled"} onProgress={scrollToLatest} onReady={value => setReady(previous => previous[message.id] === value ? previous : { ...previous, [message.id]: value })} /> : null}
        {message.status === "failed" || message.status === "cancelled" ? <div className="explain-error" role={message.status === "failed" ? "alert" : "status"}><span>{message.error ?? "已停止生成，以上内容可能不完整。"}</span><button type="button" disabled={busy} onClick={() => void send(message.question, message.id)}>重试</button></div> : null}
      </article>)}
      {!talking && messages.every(message => !message.answer || ready[message.id]) ? proposals.map(proposal => <ExplainEditProposal key={proposal.proposal_id} proposal={proposal} disabled={busy || readOnly} onBusy={setEditing} onDecision={receipt => { applyDecision(receipt); if (receipt.status === "applied") onModified?.(proposal); }} />) : null}
      {!talking && messages.every(message => !message.answer || ready[message.id]) ? rescans.map(run => <RescanTask key={run.id} initial={run} disabled={busy || readOnly} onBusy={setEditing} onProgress={scrollToLatest} onExplain={id => { void send(`请解释已有任务 ${id} 的重扫差异与原图依据，无需再次启动重扫。`, undefined, id, false); follow.current = true; }} onDecision={current => { applyRescan(current); if (current.status === "applied") onRescanned?.(current); }} />) : null}
      {proposalError ? <p className="explain-gap">待确认方案列表暂不可用：{proposalError}。来源解释仍可使用。</p> : null}
      {rescanHistoryError ? <p className="explain-gap" role="status">{rescanHistoryError}</p> : null}
    </div>
    <form className="explain-composer" onSubmit={submit}>
      <RescanAttachments key={conversationId} ref={uploader} project={projectId} conversation={conversationId} pages={availablePages} sourcePdf={selection.sourcePdf} targetPdf={selection.targetPdf} disabled={busy || readOnly} onChange={setAttachmentIds} onBusy={setUploading} />
      <label className="visually-hidden" htmlFor="explain-question">追问来源解释</label><textarea id="explain-question" value={draft} maxLength={8000} placeholder="解释来源、提出修改，或要求重新扫描；可粘贴细节图…" rows={2} onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); uploader.current?.addFiles(files); } }} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!busy && draft.trim()) { void send(draft.trim()); setDraft(""); follow.current = true; } } }} />
      <div><span>{readOnly ? "提取处理中，暂不能保存线表修改" : uploading ? "正在上传细节图…" : "可解释与提出修改 · 确认后保存线表"}</span>{talking ? <button type="button" aria-label="停止生成" title="停止生成" onClick={stop}><Square size={15} /></button> : <button type="submit" aria-label="发送追问" title="发送追问" disabled={editing || uploading || !draft.trim()}><Send size={16} /></button>}</div>
    </form>
    {lightbox ? <DrawingLightbox image={lightbox} onClose={() => setLightbox(null)} /> : null}
  </section>;
}
