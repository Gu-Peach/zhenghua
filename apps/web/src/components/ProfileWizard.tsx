import { useEffect, useRef, useState } from "react";
import { Check, Plus, RefreshCw, Upload } from "lucide-react";
import { profileApi, type Expected, type ProfileCandidate, type ProfileDraft, type ProfileStage, type ProfileState, type TargetImage } from "@/apis/profile";
import { ProfileExpectedEditor } from "./ProfileExpectedEditor";
import "@/assets/profile-wizard.css";

const stages: { id: ProfileStage; title: string; help: string }[] = [
  { id: "classification", title: "1. 拆分与页面分类", help: "上传一张样图，说明工作区、业务页号的位置和读取方式。项目名始终取PDF文件名。" },
  { id: "scan", title: "2. 本页提取", help: "上传一张包含跨页连接的样图，说明放线标记、起终点方向和跨页地址如何读取。端子规则沿用通用模板。" },
  { id: "completion", title: "3. 跨页补全", help: "使用已确认初扫的原页，上传相关目标页并填写工作区和业务页号，说明引用匹配和终点读取方式。" },
];

export function ProfileWizard() {
  const [drafts, setDrafts] = useState<ProfileDraft[]>([]); const [state, setState] = useState<ProfileState | null>(null);
  const [stage, setStage] = useState<ProfileStage>("classification"); const [error, setError] = useState("");
  const [busy, setBusy] = useState(""); const [name, setName] = useState(""); const [key, setKey] = useState("");
  const [published, setPublished] = useState(""); const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [editorEpoch, setEditorEpoch] = useState(0);
  async function load() { try { setDrafts(await profileApi.list()); setError(""); } catch (e) { setError(String(e)); } finally { setLoaded(true); } }
  useEffect(() => { let active = true; profileApi.list().then(value => { if (active) { setDrafts(value); setLoaded(true); } }).catch(e => { if (active) { setError(String(e)); setLoaded(true); } }); return () => { active = false; }; }, []);
  async function action(label: string, work: () => Promise<void>) { setBusy(label); setError(""); try { await work(); } catch (e) { setError(String(e)); } finally { setBusy(""); } }
  async function open(id: string) { await action("正在恢复草稿…", async () => { setState(await profileApi.state(id)); setPublished(""); setStage("classification"); setDirty(false); setEditorEpoch(n => n + 1); }); }
  function changed(next: ProfileState) { setState(next); setPublished(""); setDirty(false); setDrafts(items => [next.draft, ...items.filter(d => d.draft_id !== next.draft.draft_id)]); }
  const candidate = state?.candidates?.[stage];
  return <section className="profile-wizard" aria-label="规则创建与发布">
    <header><h2>创建提取规则</h2><p>按三个阶段填写静态模板。AI先生成规则和答案草稿，确认后保存；最后由你点击发布。</p></header>
    <fieldset disabled={!!busy} className="profile-create"><legend>新建规则草稿</legend><label>规则名称<input value={name} maxLength={120} onChange={e => setName(e.target.value)} placeholder="例如：新型号电气图纸" /></label><label>规则标识<input value={key} maxLength={64} pattern="[a-z][a-z0-9_-]*" onChange={e => setKey(e.target.value)} placeholder="例如：sample_electrical" /></label><button type="button" className="primary-button" disabled={!name.trim() || !/^[a-z][a-z0-9_-]{0,63}$/.test(key)} onClick={() => void action("正在创建草稿…", async () => { const draft = await profileApi.create(key, name.trim()); changed(await profileApi.state(draft.draft_id)); setStage("classification"); })}><Plus size={15} />新建草稿</button></fieldset>
    <div className="profile-resume"><label>继续已有草稿<select disabled={!!busy} value={state?.draft.draft_id ?? ""} onChange={e => { if (e.target.value) void open(e.target.value); }}><option value="">选择草稿</option>{drafts.map(d => <option key={d.draft_id} value={d.draft_id}>{d.template?.display_name ?? d.key} · {d.version} · 修订{d.revision}</option>)}</select></label><button type="button" disabled={!!busy} onClick={() => void (state ? open(state.draft.draft_id) : load())}><RefreshCw size={14} />刷新草稿</button></div>
    {!loaded && <p role="status">正在读取规则草稿…</p>}
    {error && <p role="alert" className="inline-error">{error}。已有保存内容会保留；版本冲突时请刷新草稿。</p>}
    {busy && <p role="status" className="profile-progress">{busy}</p>}
    {state && <>
      <p>{state.draft.template?.display_name} · {state.draft.version} · 修订{state.draft.revision} · {published ? "已发布" : "草稿"}</p>
      <nav className="profile-steps" aria-label="规则创建步骤">{stages.map((item, index) => <button type="button" key={item.id} disabled={!!busy || dirty || stages.slice(0, index).some(s => !state.confirmed?.[s.id])} aria-current={stage === item.id ? "step" : undefined} onClick={() => setStage(item.id)}>{state.confirmed?.[item.id] ? <Check size={14} /> : null}{item.title}</button>)}</nav>
      {dirty && <p role="status">当前有未保存的修改，请确认保存；刷新草稿会重新读取已保存内容。</p>}
      <StageEditor key={`${state.draft.draft_id}-${stage}-${candidate?.id ?? "new"}-${editorEpoch}`} state={state} stage={stage} candidate={candidate} busy={!!busy} action={action} onChange={changed} onDirty={setDirty} />
      <footer className="profile-publish"><p>发布后可在 Extraction Agent 的提取 Skills 和上传PDF的规则列表中使用；已有项目保持原规则版本。</p><button type="button" className="primary-button" disabled={!!busy || dirty || stages.some(s => !state.confirmed?.[s.id]) || !!published} onClick={() => void action("正在校验并发布规则包…", async () => { const receipt = await profileApi.publish(state.draft); setPublished(`${receipt.display_name} · ${receipt.profile_version}`); })}>发布规则</button>{published && <p role="status">已发布：{published}</p>}</footer>
    </>}
  </section>;
}

function StageEditor({ state, stage, candidate, busy, action, onChange, onDirty }: { state: ProfileState; stage: ProfileStage; candidate?: ProfileCandidate; busy: boolean; action: (label: string, work: () => Promise<void>) => Promise<void>; onChange: (next: ProfileState) => void; onDirty: (value: boolean) => void }) {
  const [description, setDescription] = useState(candidate?.description ?? "");
  const [rule, setRule] = useState(candidate?.rule_text ?? "");
  const [expected, setExpected] = useState<Expected[]>(candidate?.cases.map(c => c.expected) ?? []);
  const scanSource = state.candidates?.scan?.cases[0]?.images[0]?.attachment_id;
  const [source, setSource] = useState(stage === "completion" ? scanSource ?? "" : candidate?.cases[0]?.images[0]?.attachment_id ?? state.draft.attachments?.[0]?.id ?? "");
  const [targets, setTargets] = useState<TargetImage[]>(candidate?.request?.targets ?? candidate?.cases.flatMap(c => c.images.filter(img => img.role === "target_page").map(img => ({ attachment_id: img.attachment_id, function: String((c.input?.reference as Expected | undefined)?.target_function ?? ""), page: Number((c.input?.reference as Expected | undefined)?.target_drawing_page ?? 1) }))).filter((item, index, all) => all.findIndex(t => t.attachment_id === item.attachment_id) === index) ?? []);
  const generation = useRef({ fingerprint: "", id: crypto.randomUUID() });
  const [negatives, setNegatives] = useState<string[]>(candidate?.request?.negative_images ?? (stage === "completion" ? [] : candidate?.cases.filter(c => c.kind === "negative").map(c => c.images[0].attachment_id)) ?? []);
  const inputsDirty = !!candidate && (description !== candidate.description || source !== candidate.cases[0]?.images[0]?.attachment_id || (!!candidate.request && (JSON.stringify(targets) !== JSON.stringify(candidate.request.targets ?? []) || JSON.stringify(negatives) !== JSON.stringify(candidate.request.negative_images ?? []))));
  useEffect(() => { onDirty(!!candidate && (inputsDirty || rule !== candidate.rule_text || JSON.stringify(expected) !== JSON.stringify(candidate.cases.map(c => c.expected)))); }, [candidate, inputsDirty, rule, expected, onDirty]);
  const selected = stages.find(s => s.id === stage)!;
  async function upload(files: FileList | null, negative = false) {
    if (!files?.length) return;
    await action("正在保存样例图片…", async () => { let draft = state.draft; const added: string[] = []; for (const file of Array.from(files)) { draft = await profileApi.upload(draft, file); added.push(draft.attachments![draft.attachments!.length - 1].id); } onChange({ ...state, draft }); if (negative) setNegatives(list => [...list, ...added].slice(0, 3)); else if (stage === "completion") setTargets(list => [...list, ...added.map(id => ({ attachment_id: id, function: "", page: 1 }))]); else setSource(added[added.length - 1]); });
  }
  return <fieldset disabled={busy} className="profile-stage"><legend>{selected.title}</legend><p>{selected.help}</p>
    <label className="profile-upload"><Upload size={15} />{stage === "completion" ? "上传目标页图片" : "上传样例图片"}<input aria-label={stage === "completion" ? "上传目标页图片" : "上传样例图片"} type="file" accept="image/png,image/jpeg,image/webp" multiple={stage === "completion"} onChange={e => { void upload(e.target.files); e.target.value = ""; }} /></label>
    <label>来源样图<select value={source} disabled={stage === "completion"} onChange={e => setSource(e.target.value)}><option value="">选择图片</option>{state.draft.attachments?.map(a => <option value={a.id} key={a.id}>{a.filename}</option>)}</select></label>
    {stage !== "completion" && <><label>添加不应提取的负例图片（可选，最多3张）<input type="file" accept="image/png,image/jpeg,image/webp" disabled={negatives.length >= 3} onChange={e => { void upload(e.target.files, true); e.target.value = ""; }} /></label>{negatives.map(id => <div key={id}><span>{state.draft.attachments?.find(a => a.id === id)?.filename} · 负例</span><button type="button" onClick={() => setNegatives(negatives.filter(n => n !== id))}>移除负例</button></div>)}<p className="profile-hint">负例可选：提供后会保留并使用，未提供也可发布规则。</p></>}
    <div className="profile-images">{source && <ProfileImage draft={state.draft.draft_id} image={source} label="原页样图" />}{negatives.map((id, index) => <ProfileImage key={id} draft={state.draft.draft_id} image={id} label={`负例样图 ${index + 1}`} />)}{targets.map(t => <ProfileImage key={t.attachment_id} draft={state.draft.draft_id} image={t.attachment_id} label={`目标页 ${t.function}/${t.page}`} />)}</div>
    {stage === "completion" && <><label>添加已上传的目标图片<select value="" onChange={e => { const id = e.target.value; if (id && !targets.some(t => t.attachment_id === id)) setTargets([...targets, { attachment_id: id, function: "", page: 1 }]); }}><option value="">选择目标页</option>{state.draft.attachments?.filter(a => a.id !== source).map(a => <option key={a.id} value={a.id}>{a.filename}</option>)}</select></label>{targets.map((target, index) => <div key={target.attachment_id} className="profile-target"><span>目标页 {index + 1}</span><label>工作区<input value={target.function} onChange={e => setTargets(targets.map((t, i) => i === index ? { ...t, function: e.target.value } : t))} /></label><label>业务页号<input type="number" min={1} value={target.page} onChange={e => setTargets(targets.map((t, i) => i === index ? { ...t, page: Number(e.target.value) } : t))} /></label><button type="button" onClick={() => setTargets(targets.filter((_, i) => i !== index))}>移除目标页</button></div>)}</>}
    <label>本阶段读取规则<textarea value={description} maxLength={8000} rows={4} onChange={e => setDescription(e.target.value)} placeholder="描述图中哪些标记需要读取、如何定位，以及哪些内容不能提取。" /></label>
    <button type="button" className="primary-button" disabled={!source || !description.trim() || (stage === "completion" && (!targets.length || targets.some(t => !t.function.trim() || t.page < 1)))} onClick={() => void action("AI正在读取图片并生成本阶段规则与答案，请稍候…", async () => {
      const fingerprint = JSON.stringify([state.draft.revision, description, source, targets, negatives]);
      if (generation.current.fingerprint !== fingerprint) generation.current = { fingerprint, id: crypto.randomUUID() };
      onChange(await profileApi.generate(state.draft, stage, description, source, targets.map(t => ({ ...t, function: t.function.trim() })), generation.current.id, stage === "completion" ? [] : negatives));
    })}>根据图片生成规则与答案</button>
    {candidate && <section className="profile-candidate"><h3>核对规则与预期结果</h3><label>规则说明（可修改，最多4000字）<textarea rows={5} value={rule} maxLength={4000} onChange={e => setRule(e.target.value)} /></label>
      {candidate.cases.map((c, index) => <article key={c.id}><h4>{c.title}</h4>{c.input && <details><summary>原页连接与跨页引用</summary><pre>{JSON.stringify(c.input, null, 2)}</pre></details>}<ProfileExpectedEditor stage={stage} value={expected[index]} onChange={next => setExpected(expected.map((value, i) => i === index ? next : value))} /></article>)}
      {inputsDirty && <p role="status">样图、描述或目标页已变更，请先重新生成规则与答案。</p>}
      <button type="button" className="primary-button" disabled={!rule.trim() || inputsDirty} onClick={() => void action("正在保存确认的规则、案例和答案…", async () => onChange(await profileApi.confirm(state.draft, stage, candidate, rule, expected)))}>确认本阶段并保存</button>{state.confirmed?.[stage] && <p role="status">本阶段已确认。重新生成或修改前序阶段会要求再次确认后续步骤。</p>}
    </section>}
  </fieldset>;
}

function ProfileImage({ draft, image, label }: { draft: string; image: string; label: string }) {
  const [url, setUrl] = useState(""); const [error, setError] = useState("");
  useEffect(() => { let active = true; profileApi.pixels(draft, image).then(data => { if (active) setUrl(data.data_url); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [draft, image]);
  return <figure><figcaption>{label}</figcaption>{error ? <p role="alert">图片读取失败：{error}</p> : url ? <a href={url} target="_blank" rel="noreferrer" aria-label={`放大${label}`}><img src={url} alt={label} /></a> : <p role="status">正在加载图片…</p>}</figure>;
}
