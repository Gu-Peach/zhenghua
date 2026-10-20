import { ChevronRight, FileImage, History, ImagePlus, Loader2, MessageCircle, Send, Square, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { toolLabel, toolResultView, type EvidenceDrawing, type ExplainSelection } from "@/apis/explain";
import { useExplainConversation, type ExplainTool } from "@/hooks/useExplainConversation";
import { TypewriterAnswer } from "./TypewriterAnswer";
import { ExplainEditProposal } from "./ExplainEditProposal";
import type { EditProposal } from "@/apis/explain-edits";
import type { RescanPageChoice, RescanRun } from "@/apis/rescan";
import { RescanAttachments, type RescanAttachmentHandle } from "./RescanAttachments";
import { RescanTask } from "./RescanTask";
import { DrawingLightbox, type LightboxImage } from "./DrawingLightbox";
import { ChatIdentity } from "./ChatIdentity";
import { useDraggablePanel } from "@/hooks/useDraggablePanel";
import "@/assets/explain-rescan.css";

function ToolRecord({ tool }: { tool: ExplainTool }) {
  const result = toolResultView(tool.activity);
  return <details className={`explain-tool ${tool.status}`}>
    <summary>{tool.status === "running" ? <Loader2 size={14} className="spin" /> : <Wrench size={14} />}<span>{toolLabel(tool.activity)}</span><small>{tool.status === "running" ? "正在检索" : tool.status === "failed" ? "执行失败" : "已完成"}</small><ChevronRight size={13} /></summary>
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
  const { messages, busy: talking, send, stop, proposals, proposalError, applyDecision, conversationId, rescans, applyRescan, loadRescans, loadingRescans, rescanHistoryError, selectionNotice, currentTitle } = useExplainConversation(projectId, selection);
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  const [editing, setEditing] = useState(false); const [ready, setReady] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState(false); const uploader = useRef<RescanAttachmentHandle>(null);
  const [attachmentCount, setAttachmentCount] = useState(0); const submitting = useRef(false);
  const busy = talking || editing || uploading;
  const [draft, setDraft] = useState(selection.draftMessage ?? "");
  const panel = useRef<HTMLElement>(null); const feed = useRef<HTMLDivElement>(null);
  const movement = useDraggablePanel(panel);
  const follow = useRef(true);
  const scrollToLatest = useCallback(() => { if (follow.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight; }, []);
  useEffect(() => { panel.current?.focus({ preventScroll: true }); }, []);
  useLayoutEffect(() => { scrollToLatest(); }, [messages, proposals, rescans, ready, scrollToLatest]);
  async function submitQuestion() {
    if (busy || submitting.current || (!draft.trim() && !attachmentCount)) return;
    submitting.current = true;
    const question = draft.trim() || "请查看我上传的图片。";
    try {
      const attachments = await uploader.current?.submit();
      if (!attachments) return;
      void send(question, undefined, undefined, true, attachments);
      setDraft(""); follow.current = true;
    } finally { submitting.current = false; }
  }
  function submit(event: FormEvent) { event.preventDefault(); void submitQuestion(); }
  return <section ref={panel} className={`explain-panel ${movement.dragging ? "is-dragging" : ""}`} style={movement.style} role="dialog" aria-modal="false" aria-label="来源解释" tabIndex={-1} onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); onClose(); } }}>
    <header className="explain-header" {...movement.headerProps}><MessageCircle size={19} /><div><strong>来源解释</strong><p title={currentTitle}>{currentTitle}</p></div><button type="button" className="icon-button" aria-label="查看项目重扫记录" title="按需查看项目已有重扫任务，不会启动重扫" disabled={loadingRescans || busy} onClick={() => void loadRescans()}>{loadingRescans ? <Loader2 size={18} className="spin" /> : <History size={18} />}</button><button type="button" className="icon-button" aria-label="关闭来源解释" title="关闭并停止当前解释" onClick={onClose}><X size={19} /></button></header>
    <div ref={feed} className="explain-feed" onScroll={() => { if (feed.current) follow.current = feed.current.scrollHeight - feed.current.scrollTop - feed.current.clientHeight < 70; }}>
      {selectionNotice ? <p className="explain-gap" role="status">{selectionNotice}</p> : null}
      {readOnly ? <p className="explain-gap" role="status">提取处理中，暂不能保存线表修改</p> : null}
      {!messages.length ? <p className="explain-idle" role="status">已选择{selection.title}。输入解释、修改或重扫要求，发送后开始处理。关闭后重新打开会开始新对话。</p> : null}
      {messages.map(message => <article key={message.id} className="explain-turn">
        <div className="explain-user"><ChatIdentity user /><p className="explain-question">{message.question}</p>{message.attachments.length ? <div className="explain-message-images">{message.attachments.map((item, index) => <button key={`${item.id}:${index}`} type="button" aria-label={`放大上传图片 ${item.name}`} onClick={() => setLightbox({ url: item.url, title: item.name })}><img src={item.url} alt={item.name} /></button>)}</div> : null}</div>
        <ChatIdentity />
        <div className="explain-tools">{message.tools.map(tool => <ToolRecord key={tool.activity.id} tool={tool} />)}</div>
        {message.status === "running" ? <div className="explain-working" role="status"><Loader2 size={14} className="spin" />{message.answer ? "正在生成解释…" : "正在分析来源与关联图纸…"}</div> : null}
        {message.historyReset ? <p className="explain-gap">资料已更新，本轮基于最新记录重新解释。</p> : null}
        {message.answer ? <TypewriterAnswer text={message.answer} running={message.status === "running"} halted={message.status === "cancelled"} onProgress={scrollToLatest} onReady={value => setReady(previous => previous[message.id] === value ? previous : { ...previous, [message.id]: value })} /> : null}
        {message.drawings.length ? <section className="explain-evidence" aria-label="关联图纸"><h3>关联图纸 <span>{message.drawings.length}</span></h3><div>{message.drawings.map(drawing => <EvidenceImage key={drawing.key} drawing={drawing} onOpen={setLightbox} />)}</div></section> : null}
        {message.status === "failed" || message.status === "cancelled" ? <div className="explain-error" role={message.status === "failed" ? "alert" : "status"}><span>{message.error ?? "已停止生成，以上内容可能不完整。"}</span><button type="button" disabled={busy} onClick={() => void send(message.question, message.id)}>重试</button></div> : null}
      </article>)}
      {!talking && messages.every(message => !message.answer || ready[message.id]) ? proposals.map(proposal => <ExplainEditProposal key={proposal.proposal_id} proposal={proposal} disabled={busy || readOnly} onBusy={setEditing} onDecision={receipt => { applyDecision(receipt); if (receipt.status === "applied") onModified?.(proposal); }} />) : null}
      {!talking && messages.every(message => !message.answer || ready[message.id]) ? rescans.map(run => <RescanTask key={run.id} initial={run} disabled={busy || readOnly} onBusy={setEditing} onProgress={scrollToLatest} onExplain={id => { void send(`请解释已有任务 ${id} 的重扫差异与原图依据，无需再次启动重扫。`, undefined, id, false); follow.current = true; }} onDecision={current => { applyRescan(current); if (current.status === "applied") onRescanned?.(current); }} />) : null}
      {proposalError ? <p className="explain-gap">待确认方案列表暂不可用：{proposalError}。来源解释仍可使用。</p> : null}
      {rescanHistoryError ? <p className="explain-gap" role="status">{rescanHistoryError}</p> : null}
    </div>
    <form className="explain-composer" onSubmit={submit} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); uploader.current?.addFiles(Array.from(event.dataTransfer.files)); }}>
      <RescanAttachments key={conversationId} ref={uploader} project={projectId} conversation={conversationId} sourcePdf={selection.sourcePdf ?? selection.query?.pdf_page_number ?? (availablePages.length === 1 ? availablePages[0].pdf : undefined)} disabled={busy || readOnly} onCount={setAttachmentCount} onBusy={setUploading} />
      <label className="visually-hidden" htmlFor="explain-question">追问来源解释</label><textarea id="explain-question" value={draft} maxLength={8000} placeholder="输入问题，可粘贴或拖入图片…" rows={2} onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); uploader.current?.addFiles(files); } }} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submitQuestion(); } }} />
      <div className="explain-composer-actions"><button type="button" className="icon-button" aria-label="上传图片" title="上传图片，也可粘贴或拖拽" disabled={busy || readOnly} onClick={() => uploader.current?.open()}><ImagePlus size={17} /></button>{uploading ? <span role="status">正在上传图片…</span> : null}{talking ? <button type="button" aria-label="停止生成" title="停止生成" onClick={stop}><Square size={15} /></button> : <button type="submit" className="primary-button" aria-label="发送追问" title="发送追问" disabled={editing || uploading || (!draft.trim() && !attachmentCount)}><Send size={16} />发送</button>}</div>
    </form>
    {lightbox ? <DrawingLightbox image={lightbox} onClose={() => setLightbox(null)} /> : null}
  </section>;
}
