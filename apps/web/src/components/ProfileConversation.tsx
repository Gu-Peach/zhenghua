import { ChatIdentity } from "./ChatIdentity";
import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, ImagePlus, Loader2, Plus, RefreshCw, Send, Square, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { profileApi, streamProfileConversation, expectedOverview, type Expected, type ProfileCandidate, type ProfileConversationState, type ProfileConversationTurn, type ProfileDraft, type ProfileStage } from "@/apis/profile";
import { ProfileExpectedEditor } from "./ProfileExpectedEditor";
import { SavedProfileConversations } from "./SavedProfileConversations";
import { TypewriterAnswer } from "./TypewriterAnswer";
import "@/assets/profile-wizard.css";
import "@/assets/profile-conversation.css";

const steps: { id: ProfileStage; name: string; question: string }[] = [
  { id: "classification", name: "拆分与页面分类", question: "拖入图纸图片或PDF，我会根据样图解释工作区、业务页号和分页命名的识别链路，生成规则供你修改和确认。PDF仅随机抽两页。" },
  { id: "scan", name: "本页提取", question: "我会优先沿用已有样图，说明如何定位放线标记、沿线找端子、判断方向并读取字段；缺少接线证据时再请你补图。" },
  { id: "completion", name: "跨页补全", question: "请上传第二阶段原图对应的跨页图纸，我会沿用已确认起点，核对目标页并说明连接依据。" },
];
type PendingImage = { id: string; file: File; url: string; uploaded: boolean };

export function ProfileConversation() {
  const [drafts, setDrafts] = useState<ProfileDraft[]>([]);
  const [state, setState] = useState<ProfileConversationState | null>(null);
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  const [stage, setStage] = useState<ProfileStage>("classification");
  const [text, setText] = useState(""); const [images, setImages] = useState<PendingImage[]>([]);
  const [pendingPdf, setPendingPdf] = useState<File | null>(null);
  const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [published, setPublished] = useState("");
  const [live, setLive] = useState<{ body: ProfileConversationTurn; answer: string } | null>(null);
  const [lastSentId, setLastSentId] = useState(""); const [retry, setRetry] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [pdfRetry, setPdfRetry] = useState(false);
  const [dragging, setDragging] = useState(false);
  const pdfInput = useRef<HTMLInputElement>(null);
  const pdfJob = useRef<{ file: File; id: string; message: string; stage: ProfileStage } | null>(null);
  const controller = useRef<AbortController | null>(null); const operation = useRef(0);
  const pending = useRef<ProfileConversationTurn | null>(null); const uploaded = useRef<PendingImage[]>([]);
  const newDraft = useRef<{ id: string; key: string; name: string } | null>(null);
  const transcript = useRef<HTMLDivElement>(null); const fileInput = useRef<HTMLInputElement>(null);
  const following = useRef(true);
  const scroll = useCallback(() => { const node = transcript.current; if (node && following.current) node.scrollTop = node.scrollHeight; }, []);
  useEffect(() => { let active = true; profileApi.list().then(list => { if (active) setDrafts(list); }).catch(e => { if (active) setError(String(e)); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  useEffect(() => () => { operation.current++; controller.current?.abort(); pdfJob.current = null; uploaded.current.forEach(item => URL.revokeObjectURL(item.url)); }, []);
  useEffect(scroll, [state?.messages?.length, live?.answer, busy, scroll]);
  function clearImages() { uploaded.current.forEach(item => URL.revokeObjectURL(item.url)); uploaded.current = []; setImages([]); setPendingPdf(null); }
  function apply(next: ProfileConversationState) {
    setState(next); setDraft(next.wizard.draft); setStage(next.stage); setReviewDirty(false);
    setDrafts(list => [next.wizard.draft, ...list.filter(d => d.draft_id !== next.wizard.draft.draft_id)]);
  }
  async function restore(id: string) {
    const version = ++operation.current; controller.current?.abort(); setStreaming(false); setBusy("正在恢复已保存的对话…"); setError(""); setNotice("");
    try { const next = await profileApi.conversation(id); if (operation.current !== version) return; apply(next); setLive(null); setRetry(false); pending.current = null; setPublished(""); setText(""); clearImages(); setPdfRetry(false); pdfJob.current = null; }
    catch (e) { if (operation.current === version) setError(String(e)); }
    finally { if (operation.current === version) setBusy(""); }
  }
  function reset() { operation.current++; controller.current?.abort(); setBusy(""); setNotice(""); setStreaming(false); setReviewDirty(false); setPdfRetry(false); pdfJob.current = null; setState(null); setDraft(null); setStage("classification"); setText(""); clearImages(); setLive(null); setError(""); setPublished(""); setRetry(false); pending.current = null; newDraft.current = null; }
  async function deleteConversation(target: ProfileDraft) {
    const current = draft?.draft_id === target.draft_id ? draft : target;
    if (busy || !window.confirm(`删除“${current.template?.display_name ?? current.key}”这条规则会话？将从保存列表移除，已发布规则不受影响。`)) return;
    const version = ++operation.current; setBusy("正在删除规则会话…"); setError(""); setNotice("");
    try {
      await profileApi.remove(current);
      if (operation.current !== version) return;
      setDrafts(list => list.filter(item => item.draft_id !== current.draft_id));
      if (draft?.draft_id === current.draft_id) reset();
      setNotice("规则会话已删除。");
    } catch (e) { if (operation.current === version) setError(String(e)); }
    finally { if (operation.current === version) setBusy(""); }
  }
  function addImages(files: FileList | File[] | null): boolean {
    if (!files) return false;
    if (pendingPdf) { setError("请先移除待发送的PDF，再添加图片；不要混合上传。"); return false; }
    const selected = Array.from(files);
    if (uploaded.current.length + selected.length > 4) { setError("每轮最多上传4张图片，请分批提供。"); return false; }
    if (selected.some(f => !["image/png", "image/jpeg", "image/webp"].includes(f.type) || !f.size || f.size > 10 * 1024 * 1024)) { setError("请使用不超过10MiB的PNG、JPEG或WebP图片。"); return false; }
    uploaded.current = [...uploaded.current, ...selected.map(file => ({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file), uploaded: false }))]; setImages([...uploaded.current]); setError("");
    return true;
  }
  async function ensureDraft(filename: string, version: number): Promise<ProfileDraft> {
    if (draft) return draft;
    const name = `${filename.replace(/\.[^.]+$/, "")}规则`.slice(0, 120);
    if (newDraft.current?.name !== name) { const id = crypto.randomUUID(); newDraft.current = { id, key: `custom_${id.replaceAll("-", "").slice(0, 16)}`, name }; }
    const identity = newDraft.current;
    const created = await profileApi.create(identity.key, identity.name, identity.id);
    if (operation.current !== version) throw new DOMException("对话已切换", "AbortError");
    setDraft(created); setDrafts(list => [created, ...list.filter(d => d.draft_id !== created.draft_id)]);
    const next = await profileApi.conversation(created.draft_id);
    if (operation.current !== version) throw new DOMException("对话已切换", "AbortError");
    apply(next); return next.wizard.draft;
  }
  function queuePdf(file: File) {
    if (uploaded.current.length) { setError("请先移除待发送的图片，再添加PDF；不要混合上传。"); return; }
    if (!file.size || file.size > 50 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf")) { setError("请上传不超过50MiB的有效PDF文件。"); return; }
    setPendingPdf(file); setError("");
  }
  function acceptDrop(files: FileList) {
    if (busy || retry || pdfRetry || reviewDirty || published) { setError("请先完成或恢复当前操作，再上传新的图纸。"); return; }
    const list = Array.from(files); if (!list.length) return;
    const pdfs = list.filter(file => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length) {
      if (list.length !== 1 || uploaded.current.length) { setError("每次请单独拖入一份PDF，或最多4张图片；不要混合上传。"); return; }
      queuePdf(pdfs[0]); return;
    }
    addImages(list);
  }
  async function run(body: ProfileConversationTurn, current: ProfileDraft) {
    const version = ++operation.current; const abort = new AbortController(); controller.current = abort;
    pending.current = body; following.current = true; setLive({ body, answer: "" }); setLastSentId(body.turn_id!); setStreaming(true); setBusy("正在理解你的说明…"); setError(""); setRetry(false);
    let advance: ProfileConversationState | null = null;
    try {
      for await (const event of streamProfileConversation(current.draft_id, body, abort.signal)) {
        if (operation.current !== version) return;
        if (event.type === "progress") setBusy(event.message ?? "正在读取图片…");
        if (event.type === "answer_delta") setLive(value => value ? { ...value, answer: value.answer + (event.delta ?? "") } : value);
        if (event.type === "completed" && event.state) {
          apply(event.state); setLive(null); pending.current = null; setText(""); clearImages();
          const previous = body.stage ?? stage;
          if (event.state.stage !== previous && event.state.wizard.confirmed?.[previous]) advance = event.state;
        }
      }
      if (abort.signal.aborted) throw new Error("已停止接收。可以恢复对话核对已保存内容，或重试本轮。");
      if (advance && operation.current === version) {
        await run({ turn_id: crypto.randomUUID(), revision: advance.wizard.draft.revision, stage: advance.stage,
          message: "上一阶段已确认，请优先沿用已提供的真实样图，自动生成当前阶段规则并说明处理链路；证据不足时明确告诉我需要补充什么，不要跳过确认。", attachment_ids: [] }, advance.wizard.draft);
      }
    } catch (e) { if (operation.current === version) { setError(abort.signal.aborted ? "已停止接收。可恢复对话或重试本轮。" : String(e)); setRetry(true); } }
    finally { if (operation.current === version) { setBusy(""); setStreaming(false); controller.current = null; } }
  }
  async function submit() {
    if (busy || retry || pdfRetry || reviewDirty) return;
    if (pendingPdf) { await samplePdf(pendingPdf); return; }
    if (!draft && !uploaded.current.length) {
      const version = ++operation.current;
      const name = text.trim(); if (!name || name.length > 120) { setError("请先给规则起一个120字以内的名称。"); return; }
      if (newDraft.current?.name !== name) { const id = crypto.randomUUID(); newDraft.current = { id, key: `custom_${id.replaceAll("-", "").slice(0, 16)}`, name }; }
      setBusy("正在创建规则对话…"); setError("");
      try { const identity = newDraft.current; const created = await profileApi.create(identity.key, identity.name, identity.id); if (operation.current !== version) return; setDraft(created); setDrafts(list => [created, ...list.filter(d => d.draft_id !== created.draft_id)]); const next = await profileApi.conversation(created.draft_id); if (operation.current !== version) return; apply(next); setText(""); }
      catch (e) { if (operation.current === version) setError(String(e)); } finally { if (operation.current === version) setBusy(""); } return;
    }
    if (!text.trim() && !uploaded.current.length) return;
    setBusy("正在保存样图…"); setError("");
    const version = ++operation.current;
    try {
      let current = draft ?? await ensureDraft(uploaded.current[0].file.name, version);
      for (const image of uploaded.current) { if (!image.uploaded) { current = await profileApi.upload(current, image.file, image.id); if (operation.current !== version) return; uploaded.current = uploaded.current.map(item => item.id === image.id ? { ...item, uploaded: true } : item); setImages([...uploaded.current]); setDraft(current); } }
      await run({ turn_id: crypto.randomUUID(), revision: current.revision, message: text.trim() || "请读取这些图片并生成规则供我核对。", attachment_ids: uploaded.current.map(i => i.id), stage }, current);
    } catch (e) { if (operation.current === version) { setError(String(e)); setBusy(""); } }
  }
  async function samplePdf(file: File, requestId: string = crypto.randomUUID(), message = text.trim(), requestedStage = stage) {
    if (busy || reviewDirty || retry || published || images.length) return;
    if (!file.size || file.size > 50 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf")) { setError("请上传不超过50MiB的有效PDF文件。"); return; }
    const version = ++operation.current; const abort = new AbortController(); controller.current = abort;
    pdfJob.current = { file, id: requestId, message, stage: requestedStage }; setPdfRetry(false); setStreaming(true);
    setBusy("正在读取PDF页数，随机选出两页并渲染样图…"); setError("");
    try {
      const current = await ensureDraft(file.name, version);
      if (abort.signal.aborted) throw new Error("PDF抽样已停止");
      const result = await profileApi.samplePdf(current, file, requestId, abort.signal, requestedStage);
      if (operation.current !== version) return; if (abort.signal.aborted) throw new Error("PDF抽样已停止");
      setDraft(result.draft);
      const next = await profileApi.conversation(current.draft_id);
      if (operation.current !== version) return; if (abort.signal.aborted) throw new Error("PDF抽样已停止");
      if (next.pdf_sample?.request_id !== result.sample.request_id) throw new Error("草稿中的PDF样本已更新，请恢复对话后重试。");
      apply(next); pdfJob.current = null; clearImages();
      await run({ turn_id: crypto.randomUUID(), revision: next.wizard.draft.revision, stage: requestedStage,
        message: message || `请根据《${result.sample.filename}》实际抽取的两页自动生成当前阶段规则，并解释识别链路。未提供的页面不要猜测。`,
        attachment_ids: result.sample.pages.map(page => page.attachment_id) }, next.wizard.draft);
    } catch (e) { if (operation.current === version) { setError(abort.signal.aborted ? "已停止PDF抽样请求，可重试同一次抽样或恢复对话。" : String(e)); setPdfRetry(true); } }
    finally { if (operation.current === version) { setBusy(""); setStreaming(false); controller.current = null; } }
  }
  async function publish() {
    if (!draft || !state?.publish_ready) return;
    setBusy("正在校验并发布规则包…"); setError("");
    try { const receipt = await profileApi.publish(draft); setPublished(`${receipt.display_name} · ${receipt.profile_version}`); }
    catch (e) { setError(String(e)); } finally { setBusy(""); }
  }
  const candidate = state?.wizard.candidates?.[stage];
  const confirmed = !!state?.wizard.confirmed?.[stage];
  const review = candidate ? <CandidateReview key={`${candidate.id}:${state?.wizard.draft.revision}`} stage={stage} candidate={candidate} confirmed={confirmed} disabled={!!busy || !!published || retry || pdfRetry || images.length > 0 || !!pendingPdf} onDirty={setReviewDirty} onConfirm={async (rule, expected) => {
    if (!draft) return;
    await run({ turn_id: crypto.randomUUID(), revision: draft.revision, stage, message: "确认本阶段并保存",
      confirmation: { revision: draft.revision, candidate_id: candidate.id, rule_text: rule, expected } }, draft);
  }} /> : null;
  const messages = [...(state?.messages ?? [])];
  if (live) messages.push({ id: live.body.turn_id!, role: "user", text: live.body.message || "请读取这些图片", stage, attachment_ids: live.body.attachment_ids ?? [], created_at: "" }, { id: `live-${live.body.turn_id}`, role: "assistant", text: live.answer, stage, attachment_ids: [], created_at: "" });
  return <section className="profile-wizard profile-chat" aria-label="对话创建提取规则" data-dragging={dragging || undefined} onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={event => { event.preventDefault(); setDragging(false); void acceptDrop(event.dataTransfer.files); }}>
    <header className="profile-chat-heading"><div><h2>对话创建提取规则</h2><p>{draft ? `${draft.template?.display_name ?? draft.key} · ${draft.key} · ${draft.version}` : "拖入图纸或PDF，由助手逐步说明识别链路，确认后继续。"}</p></div><button type="button" className="primary-button" disabled={!!busy} onClick={reset}><Plus size={15} />新建对话</button></header>
    <div className="profile-resume"><SavedProfileConversations drafts={drafts} selected={draft} disabled={!!busy} loading={loading} onSelect={id => void restore(id)} onDelete={deleteConversation} />{draft && <div className="profile-resume-actions"><button type="button" disabled={!!busy} onClick={() => void restore(draft.draft_id)}><RefreshCw size={14} />恢复对话</button></div>}</div>
    {notice && <p role="status">{notice}</p>}
    {state?.pdf_sample && <p className="profile-pdf-sample" role="status">已从《{state.pdf_sample.filename}》（共{state.pdf_sample.page_count}页）随机抽取 PDF 物理页 {state.pdf_sample.pages.map(page => page.pdf_page_number).join("、")}。只保留选中样图，不缓存原PDF或其余页面。{state.pdf_sample.notice}</p>}
    {!draft && !messages.length && <div className="profile-upload-guide"><ImagePlus size={24} aria-hidden="true" /><div><strong>从一张图纸开始配置规则</strong><p>添加图片或 PDF → 说明识别要求 → 逐阶段核对并确认</p></div><button type="button" className="secondary-button" disabled={!!busy || loading} onClick={() => pdfInput.current?.click()}>选择 PDF</button></div>}
    <div ref={transcript} className="profile-transcript" role="log" aria-label="规则配置对话" aria-live="polite" onScroll={event => { const node = event.currentTarget; following.current = node.scrollHeight - node.clientHeight - node.scrollTop < 64; }}>
      <article className="profile-message assistant"><ChatIdentity name="规则配置助手" /><p>{draft ? steps.find(s => s.id === stage)?.question : "你好，请直接拖入图纸图片或PDF。我会根据图纸生成规则、说明识别链路，听取你的修改意见，确认后继续。也可以先输入规则名称。"}</p></article>
      {messages.map((message, index) => { const userId = message.role === "user" ? message.id : messages[index - 1]?.id; const animated = message.role === "assistant" && userId === lastSentId; return <article className={`profile-message ${message.role}`} key={`${userId}:${message.role}`}><ChatIdentity user={message.role === "user"} name="规则配置助手" />
        {animated ? <TypewriterAnswer text={message.text} running={!!busy} halted={retry} onProgress={scroll} /> : <Markdown skipHtml remarkPlugins={[remarkGfm]} disallowedElements={["img", "input"]} components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{message.text}</Markdown>}
        {!!message.attachment_ids?.length && <div className="profile-chat-images">{message.attachment_ids.map(image => <ChatImage key={image} draft={draft!.draft_id} image={image} />)}</div>}
      </article>; })}
      {review}
      {busy && <p className="profile-progress" role="status"><Loader2 size={14} className="spin" />{busy}</p>}
    </div>
    {error && <div className="inline-error" role="alert">{error}{retry && draft && <button type="button" disabled={!!busy} onClick={() => { if (pending.current) void run(pending.current, draft); }}>重试本轮</button>}</div>}
    {pdfRetry && <button type="button" disabled={!!busy} onClick={() => { const job = pdfJob.current; if (job) void samplePdf(job.file, job.id, job.message, job.stage); }}>重试PDF抽样</button>}
    <form aria-label="图纸或PDF上传区" className={`profile-chat-composer${dragging ? " is-dragging" : ""}`} onSubmit={event => { event.preventDefault(); void submit(); }}>
      {dragging && <p className="profile-drop-hint">松开添加附件，点击发送或按Enter后读取</p>}
      {pendingPdf && <div className="profile-pending-pdf"><FileUp size={18} aria-hidden="true" /><span>{pendingPdf.name}</span><button type="button" disabled={!!busy || pdfRetry} aria-label={`移除 ${pendingPdf.name}`} onClick={() => setPendingPdf(null)}><X size={14} /></button></div>}
      {!!images.length && <div className="profile-pending-images">{images.map(image => <figure key={image.id}><img src={image.url} alt={image.file.name} /><figcaption>{image.file.name}</figcaption><button type="button" disabled={!!busy || retry} aria-label={`移除 ${image.file.name}`} onClick={() => { URL.revokeObjectURL(image.url); uploaded.current = uploaded.current.filter(i => i.id !== image.id); setImages([...uploaded.current]); }}><X size={13} /></button></figure>)}</div>}
      <textarea aria-label="给规则助手的消息" value={text} disabled={!!busy || retry || pdfRetry || reviewDirty || !!published} maxLength={8000} rows={3} placeholder={!draft ? "拖入图纸或PDF，也可以先输入规则名称…" : "提出修改意见或补充图纸，确认后继续…"} onChange={event => setText(event.target.value)} onPaste={event => { if (event.clipboardData.files.length) { event.preventDefault(); addImages(event.clipboardData.files); } }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />
      <div className="profile-composer-actions">
        <small>添加图纸/PDF后点击发送 · Enter发送 · Shift+Enter换行</small>
        <input ref={pdfInput} type="file" accept="application/pdf,.pdf" className="visually-hidden" aria-label="上传PDF" disabled={!!busy || retry || pdfRetry || reviewDirty || !!published || images.length > 0} onChange={event => { if (event.target.files?.[0]) queuePdf(event.target.files[0]); event.target.value = ""; }} />
        <button type="button" className="profile-icon-button" aria-label="上传PDF并随机抽取两页" title="上传PDF并随机抽取两页；原PDF不保存，用于当前识别步骤" disabled={!!busy || retry || pdfRetry || reviewDirty || !!published || images.length > 0} onClick={() => pdfInput.current?.click()}><FileUp size={18} /></button>
        <input ref={fileInput} type="file" multiple accept="image/png,image/jpeg,image/webp" className="visually-hidden" aria-label="上传对话图片" disabled={!!busy || retry || pdfRetry || reviewDirty || !!published} onChange={event => { addImages(event.target.files); event.target.value = ""; }} />
        <button type="button" className="profile-icon-button" aria-label="上传图片" title="上传图片（PNG、JPEG或WebP，每张不超过10MiB）" disabled={!!busy || retry || pdfRetry || reviewDirty || !!published} onClick={() => fileInput.current?.click()}><ImagePlus size={18} /></button>
        {streaming ? <button type="button" onClick={() => controller.current?.abort()}><Square size={14} />停止</button> : <button type="submit" className="primary-button" disabled={!!busy || retry || pdfRetry || reviewDirty || !!published || (!text.trim() && !images.length && !pendingPdf) }><Send size={15} />发送</button>}
      </div>
    </form>
    {state && Object.keys(state.wizard.confirmed ?? {}).length === 3 && <footer className="profile-publish"><h3>{state.publish_ready ? "规则已确认，可以发布" : "规则已确认，请检查以下问题"}</h3>{state.issues?.map((issue, index) => <p key={index}>{issue}</p>)}<p>发布后可在提取Skills和上传PDF时使用。已有项目保留原规则版本。</p><button type="button" className="primary-button" disabled={!!busy || !state.publish_ready || !!published || retry || pdfRetry || images.length > 0 || !!pendingPdf} onClick={() => void publish()}>发布规则</button>{published && <p role="status">已发布：{published}</p>}</footer>}
  </section>;
}

function ChatImage({ draft, image }: { draft: string; image: string }) {
  const [url, setUrl] = useState(""); const [error, setError] = useState("");
  useEffect(() => { let active = true; profileApi.pixels(draft, image).then(data => { if (active) setUrl(data.data_url); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [draft, image]);
  return error ? <p role="alert">图片读取失败：{error}</p> : url ? <a href={url} target="_blank" rel="noreferrer"><img src={url} alt="对话样图" /></a> : <span>正在读取样图…</span>;
}

function CandidateReview({ stage, candidate, confirmed, disabled, onConfirm, onDirty }: { stage: ProfileStage; candidate: ProfileCandidate; confirmed: boolean; disabled: boolean; onConfirm: (rule: string, expected: Expected[]) => Promise<void>; onDirty: (dirty: boolean) => void }) {
  const [rule, setRule] = useState(candidate.rule_text); const [expected, setExpected] = useState(candidate.cases.map(c => c.expected));
  const dirty = rule !== candidate.rule_text || JSON.stringify(expected) !== JSON.stringify(candidate.cases.map(c => c.expected));
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  return <section className="profile-chat-review" aria-label="本阶段读图结果"><h3>{steps.find(item => item.id === stage)?.name}：{confirmed ? "已确认" : "请核对识别链路与结果"}</h3>
    {candidate.readings?.map(reading => <div key={reading.case_id} className="profile-reading"><p>{reading.summary}</p>{reading.wire_marker && <p><strong>放线标记：</strong>{reading.wire_marker}</p>}{!!reading.evidence_steps?.length && <><strong>图纸证据与连接路径</strong><ol>{reading.evidence_steps.map((step, index) => <li key={index}>{step}</li>)}</ol></>}</div>)}
    <p>可以在聊天中指出哪里需要修改，也可以展开表格直接修正。确认后才会保存本阶段规则与 Expected JSON。</p>
    {dirty && <p role="status">表格有未保存的修改，请确认保存后继续对话。<button type="button" disabled={disabled} onClick={() => { setRule(candidate.rule_text); setExpected(candidate.cases.map(c => c.expected)); }}>取消表格修改</button></p>}
    <p className="profile-rule-summary">{rule}</p>
    <div className="profile-observed-connections">{candidate.cases.flatMap((c, index) => expectedOverview(stage, expected[index], c.input).map((line, item) => <p key={`${c.id}:${item}`}>{line}</p>))}</div>
    <details><summary>修改本阶段规则说明</summary><label>本阶段规则说明<textarea value={rule} maxLength={4000} disabled={disabled || confirmed} rows={3} onChange={e => setRule(e.target.value)} /></label></details>
    <details><summary>查看和修改识别结果</summary>{candidate.cases.map((c, index) => <article key={c.id}><h4>{c.title}</h4>{c.input && <details><summary>已确认原页连接与跨页引用</summary><pre>{JSON.stringify(c.input, null, 2)}</pre></details>}<fieldset disabled={disabled || confirmed}><ProfileExpectedEditor stage={stage} value={expected[index]} onChange={next => setExpected(values => values.map((value, i) => i === index ? next : value))} /></fieldset><details><summary>Expected JSON</summary><pre>{JSON.stringify(expected[index], null, 2)}</pre></details></article>)}</details>
    {!confirmed && <button type="button" className="primary-button" disabled={disabled || !rule.trim()} onClick={() => void onConfirm(rule, expected)}>确认本阶段并保存</button>}
  </section>;
}



