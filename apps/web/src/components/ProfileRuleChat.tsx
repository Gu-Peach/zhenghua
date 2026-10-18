import { useEffect, useRef, useState } from "react";
import { ImagePlus, Send, Square, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { profileApi, type ProfileStage } from "@/apis/profile";
import { profileEditorApi, streamProfileEditor, type EditProposal, type EditTurn, type ProfileEditState } from "@/apis/profile-editor";
import { TypewriterAnswer } from "./TypewriterAnswer";

const toolNames: Record<string, string> = { inspect_profile: "读取当前规则", load_profile_context: "加载规则与少样本", read_file: "读取规则文件", view_images: "查看图纸", record_diagnosis: "记录问题依据", propose_edits: "提出修改建议", validate_profile: "校验规则" };
type ActiveTurn = { user: string; answer: string; completed: boolean; images: string[] };
function displayMessage(value: string): string {
  try { const v = JSON.parse(value) as { text?: string; observations?: unknown[] }; return typeof v.text === "string" ? v.text + (v.observations?.length ? `\n\n实际结果/问题：\n${JSON.stringify(v.observations, null, 2)}` : "") : value; } catch { return value; }
}
function messageImages(value: string): string[] {
  try { const data = JSON.parse(value) as { attachment_ids?: string[] }; return Array.isArray(data.attachment_ids) ? data.attachment_ids : []; } catch { return []; }
}
function ToolResult({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  return <pre>{text.length > 16000 ? `${text.slice(0, 16000)}\n…结果较长，仅展示前16000字符。` : text}</pre>;
}
function DiagnosticImage({ draft, image }: { draft: string; image: string }) {
  const [url, setUrl] = useState(""); const [error, setError] = useState(false);
  useEffect(() => { let active = true; profileApi.pixels(draft, image).then(value => { if (active) setUrl(value.data_url); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, [draft, image]);
  return url ? <a href={url} target="_blank" rel="noreferrer"><img className="profile-diagnostic-image" src={url} alt="用户诊断图纸" /></a> : <small>{error ? "诊断图纸暂不可用，可稍后恢复对话查看。" : "正在读取诊断图纸…"}</small>;
}

export function ProfileRuleChat({ state, stage, busy, onBusy, onState, onError, onConfirm }: {
  state: ProfileEditState; stage: ProfileStage; busy: boolean; onBusy: (message: string) => void;
  onState: (value: ProfileEditState) => void; onError: (message: string) => void;
  onConfirm: (proposal: EditProposal, accepted: boolean, publish: boolean) => Promise<void>;
}) {
  const [text, setText] = useState(""); const [result, setResult] = useState(""); const [files, setFiles] = useState<File[]>([]);
  const [active, setActive] = useState<ActiveTurn | null>(null); const [retry, setRetry] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);
  const [tools, setTools] = useState<{ name: string; result?: unknown }[]>([]);
  const pending = useRef<EditTurn | null>(null); const controller = useRef<AbortController | null>(null);
  const uploads = useRef(new Map<File, { id: string; done: boolean }>());
  const input = useRef<HTMLInputElement>(null); const log = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const following = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; controller.current?.abort(); }; }, []);
  const scroll = () => { if (following.current && log.current) log.current.scrollTop = log.current.scrollHeight; };
  function addFiles(selected: FileList | null) {
    if (!selected) return;
    const added = Array.from(selected);
    if (added.some(f => !["image/png", "image/jpeg", "image/webp"].includes(f.type) || f.size > 10 * 1024 * 1024)) { onError("请上传每张不超过10MiB的PNG、JPEG或WebP图片。"); return; }
    if (files.length + added.length > 4) { onError("每轮最多上传4张图纸。"); return; }
    setFiles([...files, ...added]);
  }
  async function run(body: EditTurn, current: ProfileEditState) {
    const abort = new AbortController(); controller.current = abort; setStreaming(true); setRetry(false); onError(""); onBusy("正在分析规则、样图与提取结果…");
    following.current = true;
    setTools([]); setActive({ user: displayMessage(JSON.stringify({ text: body.message, observations: body.observations })), answer: "", completed: false, images: body.attachment_ids ?? [] });
    try {
      for await (const event of streamProfileEditor(current.draft.draft_id, body, abort.signal)) {
        if (!alive.current) return;
        if (event.type === "tool_started") setTools(items => [...items, { name: event.tool ?? "工具" }]);
        if (event.type === "tool_completed") setTools(items => {
          const copy = [...items]; const last = copy.map(t => t.name === event.tool && t.result === undefined).lastIndexOf(true);
          if (last >= 0) copy[last] = { ...copy[last], result: event.detail }; else copy.push({ name: event.tool ?? "工具", result: event.detail });
          return copy;
        });
        if (event.type === "answer_delta") setActive(value => value ? { ...value, answer: value.answer + (event.delta ?? "") } : value);
        if (event.type === "completed" && event.reply) {
          const latest = await profileEditorApi.state(current.draft.draft_id);
          if (!alive.current) return;
          onState(latest); setActive(value => value ? { ...value, answer: event.reply!.answer, completed: true } : value);
          pending.current = null; uploads.current.clear(); setText(""); setResult(""); setResultOpen(false); setFiles([]);
        }
      }
    } catch (error) { if (alive.current) { onError(abort.signal.aborted ? "已停止分析，可重试本轮或恢复草稿查看已保存建议。" : String(error)); setRetry(true); } }
    finally { if (alive.current) { setStreaming(false); onBusy(""); } }
  }
  async function send() {
    if (busy || retry || !text.trim()) return;
    onBusy("正在保存本轮图纸…"); onError("");
    try {
      let draft = (await profileEditorApi.state(state.draft.draft_id)).draft; const ids: string[] = [];
      // Stable IDs avoid duplicated uploads if a transport response is lost.
      for (const file of files) {
        const job = uploads.current.get(file) ?? { id: crypto.randomUUID(), done: false }; uploads.current.set(file, job);
        if (!job.done) { draft = await profileApi.upload(draft, file, job.id); job.done = true; onState(await profileEditorApi.state(draft.draft_id)); }
        ids.push(job.id);
      }
      const current = ids.length ? await profileEditorApi.state(draft.draft_id) : state;
      onState(current);
      const body: EditTurn = { turn_id: crypto.randomUUID(), expected_revision: current.draft.revision, intent: "discuss", message: text.trim(), attachment_ids: ids, focus_stage: stage, observations: result.trim() ? [{ actual_result: result.trim() }] : [] };
      pending.current = body; await run(body, current);
    } catch (error) { onError(String(error)); onBusy(""); }
  }
  const history = active?.completed ? (state.history ?? []).slice(0, -2) : state.history ?? [];
  return <aside className="profile-rule-chat" aria-label="规则辅助编辑">
    <h3>Profile Agent · 辅助编辑</h3><p className="profile-rule-hint">结合当前规则和少样本分析；修改建议需你同意后才会应用。</p>
    <div ref={log} className="profile-rule-log" role="log" aria-label="规则编辑对话" onScroll={event => { const node = event.currentTarget; following.current = node.scrollHeight - node.clientHeight - node.scrollTop < 64; }}>
      {history.map((m, i) => <article key={i} className={`edit-message ${m.role}`}><strong>{m.role === "user" ? "你" : "规则助手"}</strong><Markdown skipHtml remarkPlugins={[remarkGfm]} disallowedElements={["img", "input"]}>{displayMessage(m.content)}</Markdown>{messageImages(m.content).map(id => <DiagnosticImage key={id} draft={state.draft.draft_id} image={id} />)}</article>)}
      {active && <><article className="edit-message user"><strong>你</strong><p>{active.user}</p>{active.images.map(id => <DiagnosticImage key={id} draft={state.draft.draft_id} image={id} />)}</article>
        {tools.map((tool, i) => <details className="profile-tool" key={i}><summary>{tool.result === undefined ? "正在" : "已"}{toolNames[tool.name] ?? tool.name}</summary>{tool.result === undefined ? <pre>处理中…</pre> : <ToolResult value={tool.result} />}</details>)}
        <article className="edit-message assistant"><strong>规则助手</strong><TypewriterAnswer text={active.answer} running={streaming} halted={retry} onProgress={scroll} /></article></>}
    </div>
    <div className="profile-proposals">{(state.proposals ?? []).map(proposal => <article className="profile-proposal" key={proposal.id}>
      <strong>{proposal.summary}</strong>{proposal.findings?.map((f, i) => <p key={i}>{f.explanation}</p>)}
      {(proposal.diffs ?? []).map(diff => <details key={diff.path}><summary>查看修改前后 · {diff.path}</summary><span>修改前</span><pre>{diff.before}</pre><span>修改后</span><pre>{diff.after ?? "删除文件"}</pre></details>)}
      {proposal.status === "pending" ? <div><button type="button" disabled={busy || retry || proposal.base_revision !== state.draft.revision} onClick={() => void onConfirm(proposal, true, true)}>同意修改并发布</button><button type="button" disabled={busy || retry} onClick={() => void onConfirm(proposal, false, false)}>拒绝建议</button>{proposal.base_revision !== state.draft.revision && <p>草稿已更新，请重新分析生成建议。</p>}</div> : <small>{proposal.status === "accepted" ? "已应用到草稿" : "已拒绝"}</small>}
    </article>)}</div>
    {retry && <button type="button" disabled={busy} onClick={() => { if (pending.current) void run(pending.current, state); }}>重试本轮分析</button>}
    <form onSubmit={event => { event.preventDefault(); void send(); }}>
      <label>修改要求或问题<textarea aria-label="规则修改要求" rows={3} maxLength={12000} value={text} disabled={busy || retry} onChange={e => setText(e.target.value)} onPaste={e => { if (e.clipboardData.files.length) { e.preventDefault(); addFiles(e.clipboardData.files); } }} /></label>
      <details open={resultOpen} onToggle={event => setResultOpen(event.currentTarget.open)}><summary>补充当前提取结果（可选）</summary><textarea aria-label="当前提取结果" rows={4} maxLength={12000} placeholder="粘贴JSON或线表内容，并说明哪些字段有问题" value={result} disabled={busy || retry} onChange={e => setResult(e.target.value)} /></details>
      {files.map((file, i) => <span className="profile-edit-attachment" key={`${file.name}:${i}`}>{file.name}<button type="button" aria-label={`移除图纸 ${i + 1}`} disabled={busy || retry} onClick={() => setFiles(files.filter((_, index) => i !== index))}><X size={12} /></button></span>)}
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" multiple className="visually-hidden" aria-label="上传规则诊断图纸" onChange={e => { addFiles(e.target.files); e.target.value = ""; }} disabled={busy || retry} />
      <div className="profile-chat-actions"><button type="button" disabled={busy || retry} onClick={() => input.current?.click()}><ImagePlus size={14} />上传图纸</button>{streaming ? <button type="button" onClick={() => controller.current?.abort()}><Square size={14} />停止</button> : <button type="submit" disabled={busy || retry || !text.trim()}><Send size={14} />发送</button>}</div>
    </form>
  </aside>;
}
