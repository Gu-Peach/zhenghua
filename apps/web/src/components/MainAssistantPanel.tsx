import { Bot, FileUp, ImagePlus, Loader2, MessageSquare, PanelRightClose, PanelRightOpen, Plus, RefreshCw, Send, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { assistantApi, assistantDestination, streamAssistant, type AssistantConversation, type AssistantEvent, type AssistantTurn } from "@/apis/assistant";
import { projectApi } from "@/apis/projects";
import { useAssistantStore } from "@/stores/assistant-store";
import { useSessionStore } from "@/stores/session-store";
import { AssistantActionCard } from "./AssistantActionCard";
import { ChatIdentity } from "./ChatIdentity";
import { SavedAssistantConversations } from "./SavedAssistantConversations";
import "@/assets/assistant.css";

type PendingFile = { id: string; file: File; page: string; role: "source" | "target" | "detail" | "pdf" };
type Entry = { id: string; message: string; events: AssistantEvent[] };
const fromConversation = (value: AssistantConversation): Entry[] => value.turns?.map(turn => ({ id: turn.id, message: turn.request.message, events: turn.events ?? [] })) ?? [];
const toolLabels: Record<string, string> = { find_targets: "检索项目与图纸", navigate_to: "打开所选范围", read_scope: "读取图纸与结果", search_connections: "检索线表", explain_scope: "解释 Agent", start_rescan: "创建重扫候选任务", diagnose_profile: "规则诊断 Agent", propose_connection_edit: "生成线表修订方案", list_rule_packages: "查询数据库规则", get_task_status: "查询任务状态", cancel_task: "取消任务", open_agent_page: "打开智能体", start_document_extraction: "创建PDF提取任务", export_project: "导出项目线表" };

export function MainAssistantPanel() {
  const [docked, setDocked] = useState(false);
  const [open, setOpen] = useState(false); const [available, setAvailable] = useState(false); const [availability, setAvailability] = useState("正在检查服务…");
  const [conversation, setConversation] = useState<AssistantConversation | null>(null); const [list, setList] = useState<AssistantConversation[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]); const [message, setMessage] = useState(""); const [files, setFiles] = useState<PendingFile[]>([]);
  const [busy, setBusy] = useState(false); const [restoring, setRestoring] = useState(true); const [error, setError] = useState(""); const [retry, setRetry] = useState(0);
  const [lastTurn, setLastTurn] = useState<AssistantTurn | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const deletingLock = useRef(false); const selectionVersion = useRef(0);
  const scope = useAssistantStore(state => state.scope); const hidden = useAssistantStore(state => state.hidden);
  const user = useSessionStore(state => state.session?.user.id);
  const controller = useRef<AbortController | null>(null); const imageInput = useRef<HTMLInputElement>(null); const pdfInput = useRef<HTMLInputElement>(null);
  const feed = useRef<HTMLDivElement>(null); const launcher = useRef<HTMLButtonElement>(null); const textarea = useRef<HTMLTextAreaElement>(null);
  const route = useLocation(); const navigate = useNavigate(); const currentRoute = useRef(route.pathname + route.search);
  const handled = useRef(new Set<string>());
  useEffect(() => { currentRoute.current = route.pathname + route.search; }, [route]);
  useEffect(() => { if (open) textarea.current?.focus(); }, [open]);
  useEffect(() => { feed.current?.scrollTo({ top: feed.current.scrollHeight }); }, [entries, busy]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!open || !user) return;
    let alive = true;
    const version = selectionVersion.current;
    void assistantApi.capabilities().then(value => { if (alive) { setAvailable(value.available); setAvailability(value.message || (value.available ? "已接入" : "主助手暂不可用")); } }).catch(reason => { if (alive) { setAvailable(false); setAvailability(String(reason)); } });
    void assistantApi.list().then(async items => {
      if (!alive || version !== selectionVersion.current) return; setList(items);
      const saved = localStorage.getItem(`assistant-conversation:${user}`);
      if (saved && !conversation && items.some(item => item.id === saved)) {
        setRestoring(true);
        try { const value = await assistantApi.get(saved); if (alive && version === selectionVersion.current) { setConversation(value); setEntries(fromConversation(value)); } }
        finally { if (alive && version === selectionVersion.current) setRestoring(false); }
      }
      else if (saved && !items.some(item => item.id === saved)) localStorage.removeItem(`assistant-conversation:${user}`);
    }).catch(reason => { if (alive && version === selectionVersion.current) setError(String(reason)); }).finally(() => { if (alive && version === selectionVersion.current) setRestoring(false); });
    return () => { alive = false; };
    // A refresh rechecks capabilities without replacing an active streamed conversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user, retry]);
  function close() { setOpen(false); launcher.current?.focus(); }
  function addFiles(incoming: FileList | File[]) {
    if (deletingLock.current || restoring) return;
    setError("");
    const accepted: PendingFile[] = [];
    for (const file of Array.from(incoming)) {
      const pdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
      if (!pdf && !["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError("支持PDF、PNG、JPEG和WebP"); continue; }
      if (file.size > (pdf ? 50 * 1024 * 1024 : 8_000_000)) { setError(pdf ? "PDF不能超过50MiB" : "图片不能超过8MB"); continue; }
      accepted.push({ id: crypto.randomUUID(), file, page: "", role: pdf ? "pdf" : "detail" });
    }
    setFiles(previous => [...previous, ...accepted].slice(0, 6));
  }
  async function selectConversation(id: string) {
    if (busy || restoring || deletingLock.current) return; setError(""); setLastTurn(null);
    const version = ++selectionVersion.current;
    if (!id) { setConversation(null); setEntries([]); setFiles([]); setMessage(""); if (user) localStorage.removeItem(`assistant-conversation:${user}`); return; }
    setRestoring(true);
    try { const value = await assistantApi.get(id); if (version !== selectionVersion.current) return; setConversation(value); setEntries(fromConversation(value)); setFiles([]); setMessage(""); if (user) localStorage.setItem(`assistant-conversation:${user}`, id); }
    catch (reason) { if (version === selectionVersion.current) setError(String(reason)); } finally { if (version === selectionVersion.current) setRestoring(false); }
  }
  async function deleteConversation(item: AssistantConversation) {
    if (busy || restoring || deletingLock.current) return;
    deletingLock.current = true; setDeleting(item.id); setError(""); ++selectionVersion.current;
    try {
      await assistantApi.remove(item.id);
      setList(previous => previous.filter(value => value.id !== item.id));
      if (conversation?.id === item.id) { setConversation(null); setEntries([]); setMessage(""); setFiles([]); setLastTurn(null); }
      if (user && localStorage.getItem(`assistant-conversation:${user}`) === item.id) localStorage.removeItem(`assistant-conversation:${user}`);
    } catch (reason) { setError(String(reason)); }
    finally { deletingLock.current = false; setDeleting(null); }
  }
  async function run(existing?: AssistantTurn) {
    if (controller.current || busy || restoring || deletingLock.current || !available || !existing && !message.trim() && !files.length) return;
    ++selectionVersion.current;
    setBusy(true); setError(""); const abort = new AbortController(); controller.current = abort;
    let saved = conversation; const startedRoute = currentRoute.current;
    try {
      if (!saved) {
        saved = await assistantApi.create(crypto.randomUUID(), (message.trim() || "图纸处理").slice(0, 60));
        setConversation(saved); setList(previous => [saved!, ...previous]);
        if (user) localStorage.setItem(`assistant-conversation:${user}`, saved.id);
      }
      let body = existing;
      if (!body) {
        const ids: string[] = [];
        for (const item of files) {
          const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error("文件读取失败")); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.readAsDataURL(item.file); });
          const uploaded = await assistantApi.upload(saved.id, { id: item.id, filename: item.file.name, content_base64: content, role: item.role, pdf_page_number: item.page ? Number(item.page) : null });
          ids.push(uploaded.id);
        }
        body = { turn_id: crypto.randomUUID(), message: message.trim() || "请查看附件并帮助我处理；信息不足时先说明需要补充什么。", scope, attachment_ids: ids };
      }
      setLastTurn(body); const turn = body;
      setEntries(previous => [...previous.filter(item => item.id !== turn.turn_id), { id: turn.turn_id!, message: turn.message, events: [] }]);
      for await (const event of streamAssistant(saved.id, body, abort.signal)) {
        setEntries(previous => previous.map(item => item.id === turn.turn_id ? { ...item, events: item.events.some(value => value.id === event.id) ? item.events : [...item.events, event] } : item));
        if (event.type === "navigate" && !handled.current.has(event.id!)) {
          handled.current.add(event.id!); const value = event.data ?? {};
          if (currentRoute.current === startedRoute) {
            const target = assistantDestination(value);
            if (target) { currentRoute.current = target; navigate(target); }
            else if (value.destination === "export" && typeof (value.scope as { project_id?: string })?.project_id === "string") await projectApi.exportXlsx((value.scope as { project_id: string }).project_id);
          }
        }
      }
      setMessage(""); setFiles([]); setLastTurn(null);
    } catch (reason) { setError(abort.signal.aborted ? "本轮已停止。已创建的重扫任务仍可在会话中查看。" : String(reason)); }
    finally { setBusy(false); controller.current = null; }
  }
  const unreadTasks = entries.flatMap(item => item.events).filter(event => event.type === "task_started" || event.type === "proposal_ready").length;
  return <div hidden={hidden}>
    <section className={`floating-agent-panel main-assistant${docked ? " is-docked" : ""}`} hidden={!open || hidden} role="dialog" aria-modal="false" aria-label="AI 助手" onKeyDown={event => { if (event.key === "Escape") close(); }}>
      <header className="assistant-heading"><span className="chat-avatar"><Bot size={18} /></span><strong>电气图纸与线表助手</strong><span className={`assistant-availability${available ? " is-available" : ""}`}>{busy ? "处理中" : available ? "已接入" : "未就绪"}</span><button type="button" className="icon-button assistant-dock-toggle" aria-label={docked ? "切换为浮窗" : "停靠到工作台右侧"} title={docked ? "切换为浮窗" : "停靠到工作台右侧"} aria-pressed={docked} onClick={() => setDocked(value => !value)}>{docked ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}</button><button type="button" className="icon-button" disabled={busy || restoring || !!deleting} aria-label="刷新助手状态" title="刷新助手状态" onClick={() => setRetry(n => n + 1)}><RefreshCw size={17} /></button><button type="button" className="icon-button" aria-label="关闭 AI 助手" title="关闭 AI 助手" onClick={close}><X size={18} /></button></header>
      <div className="assistant-conversations"><SavedAssistantConversations items={list} selected={conversation} disabled={busy || restoring} deleting={deleting} onSelect={id => void selectConversation(id)} onDelete={deleteConversation} /><button type="button" className="secondary-button" disabled={busy || restoring || !!deleting} title="新对话" aria-label="新建助手对话" onClick={() => void selectConversation("")}><Plus size={16} />新建对话</button></div>
      <div ref={feed} className="assistant-feed" aria-live="polite">
        {conversation?.has_more && conversation.next_offset != null ? <button type="button" disabled={busy || restoring || !!deleting} onClick={() => { const version = selectionVersion.current; void assistantApi.get(conversation.id, conversation.next_offset!).then(value => { if (version !== selectionVersion.current) return; setEntries(previous => [...fromConversation(value), ...previous]); setConversation(value); }).catch(reason => { if (version === selectionVersion.current) setError(String(reason)); }); }}>加载更早对话</button> : null}
        {!entries.length ? <div className="assistant-empty"><span className="chat-avatar"><Bot size={22} /></span><strong>从图纸到线表，随时协助你</strong><p>查找项目与工作区、解释连接来源，或提出重扫和规则修改需求。</p><small>修改会先生成预览，由你确认后保存。</small></div> : null}
        {entries.map(entry => <article className="assistant-entry" key={entry.id}><div className="assistant-user"><ChatIdentity user /><p>{entry.message}</p></div>
          <ChatIdentity />
          {entry.events.some(event => event.type === "tool_started") ? <details className="assistant-tool-log"><summary>本轮处理记录 · {entry.events.some(event => event.type === "error" || event.data?.error) ? "执行失败" : entry.events.some(event => event.type === "completed") ? "已完成" : "正在处理"}</summary>{entry.events.filter(event => ["tool_started", "tool_completed"].includes(event.type)).map(event => <p key={event.id}>{toolLabels[String(event.data?.name)] ?? "业务工具"} · {event.type === "tool_started" ? "开始" : event.data?.error ? String(event.data.error) : "已完成"}</p>)}</details> : null}
          {entry.events.filter(event => event.type === "tool_completed").flatMap(event => (event.data?.sources as Array<Record<string, unknown>> ?? []).map((source, index) => { const target = assistantDestination(source); return target ? <button type="button" key={`${event.id}:${index}`} onClick={() => navigate(target)}>来源：{String(source.label)}</button> : null; }))}
          {entry.events.some(event => event.type === "answer_delta") ? <div className="assistant-answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.events.filter(event => event.type === "answer_delta").map(event => event.message).join("")}</ReactMarkdown></div> : null}
          {entry.events.filter(event => ["navigate", "selection_required", "task_started", "proposal_ready", "error"].includes(event.type)).map(event => {
            const data = event.data ?? {}; const target = assistantDestination(data);
            if (event.type === "error") return <p key={event.id} role="alert">{event.message}</p>;
            if (event.type === "navigate") return target ? <button type="button" key={event.id} onClick={() => navigate(target)}>打开{String((data.scope as { project_name?: string })?.project_name ?? "处理结果")}</button> : null;
            if (event.type === "selection_required") return <div key={event.id} aria-label="检索候选">{(data.targets as Array<{ label: string; scope: Record<string, unknown> }> ?? []).map((item, index) => <button type="button" key={index} disabled={busy || restoring || !!deleting} onClick={() => { setMessage(`请定位并打开此目标：${item.label}，标识信息：${JSON.stringify(item.scope)}`); textarea.current?.focus(); }}>{item.label}</button>)}</div>;
            return typeof data.action_id === "string" ? <AssistantActionCard key={data.action_id} id={data.action_id} /> : null;
          })}
        </article>)}
        {busy ? <p role="status"><Loader2 size={15} className="spin" />正在处理请求…</p> : null}
      </div>
      {error ? <p role="alert" className="assistant-error">{error}{lastTurn && !busy ? <button type="button" onClick={() => void run(lastTurn)}>重试本轮</button> : null}</p> : null}
      <form className="assistant-composer" onSubmit={event => { event.preventDefault(); void run(); }} onDragOver={event => { event.preventDefault(); }} onDrop={event => { event.preventDefault(); if (!busy) addFiles(event.dataTransfer.files); }}>
        {files.map(item => <div className="assistant-file" key={item.id}><span title={item.file.name}>{item.file.name}</span>{item.role !== "pdf" ? <><input type="number" min="1" aria-label={`${item.file.name}对应PDF物理页`} placeholder="PDF页（可选）" value={item.page} disabled={busy || restoring || !!deleting} onChange={event => setFiles(previous => previous.map(value => value.id === item.id ? { ...value, page: event.target.value } : value))} /><select aria-label={`${item.file.name}参考图类型`} value={item.role} disabled={busy || restoring || !!deleting} onChange={event => setFiles(previous => previous.map(value => value.id === item.id ? { ...value, role: event.target.value as PendingFile["role"] } : value))}><option value="detail">细节图</option><option value="source">原页</option><option value="target">目标页</option></select></> : null}<button type="button" className="icon-button" aria-label={`移除 ${item.file.name}`} disabled={busy || restoring || !!deleting} onClick={() => setFiles(previous => previous.filter(value => value.id !== item.id))}><X size={14} /></button></div>)}
        <textarea ref={textarea} aria-label="向主助手提出需求" disabled={!available || busy || restoring || !!deleting} value={message} placeholder={available ? "输入需求，可拖入图纸或PDF…" : availability} onChange={event => setMessage(event.target.value)} onPaste={event => { const images = Array.from(event.clipboardData.files); if (images.length && !busy) { event.preventDefault(); addFiles(images); } }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void run(); } }} />
        <footer><small>{scope.workspace_code ?? scope.project_name ?? "全局会话"} · Enter发送</small><input className="visually-hidden" ref={pdfInput} type="file" accept="application/pdf" multiple onChange={event => { if (event.target.files) addFiles(event.target.files); event.target.value = ""; }} /><input className="visually-hidden" ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={event => { if (event.target.files) addFiles(event.target.files); event.target.value = ""; }} /><button type="button" className="icon-button" aria-label="添加PDF附件" disabled={busy || !available} onClick={() => pdfInput.current?.click()}><FileUp size={18} /></button><button type="button" className="icon-button" aria-label="添加图片附件" disabled={busy || !available} onClick={() => imageInput.current?.click()}><ImagePlus size={18} /></button>{busy ? <button type="button" aria-label="停止本轮对话" onClick={() => controller.current?.abort()}><Square size={16} /></button> : <button type="submit" className="primary-button" aria-label="发送助手消息" disabled={!available || restoring || !!deleting || !message.trim() && !files.length}><Send size={17} />发送</button>}</footer>
      </form>
    </section>
    <button ref={launcher} className="agent-launcher" type="button" aria-label={open ? "关闭 AI 聊天面板" : "打开 AI 聊天面板"} aria-expanded={open} onClick={() => open ? close() : setOpen(true)}>{open ? <X size={23} /> : <MessageSquare size={23} />}{!open && (busy || unreadTasks > 0) ? <span className="agent-launcher-badge">{busy ? "…" : unreadTasks}</span> : null}</button>
  </div>;
}
