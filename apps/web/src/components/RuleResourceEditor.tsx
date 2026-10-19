import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { MessagesSquare, X } from "lucide-react";
import { projectApi, type RulePackage } from "@/apis/projects";
import { ruleStages } from "@/apis/rule-resources";
import { skillName } from "@/apis/agents";
import { profileEditorApi, type EditProposal, type ProfileEditState } from "@/apis/profile-editor";
import type { ProfileStage } from "@/apis/profile";
import type { RuleLibraryItem } from "@/apis/types";
import "@/assets/profile-rule-editor.css";

const ProfileRuleChat = lazy(() => import("./ProfileRuleChat").then(module => ({ default: module.ProfileRuleChat })));
const roles: Record<string, string> = { source_page: "来源页", target_page: "目标页", drawing_page: "图纸页" };
type Editing = { path: string; text: string; before: string; revision: number; checksum: string };

export function RuleResources({ rule, onClose, asSkill = false, onChanged }: { rule: RuleLibraryItem; onClose: () => void; asSkill?: boolean; onChanged?: (notice?: string) => Promise<void> }) {
  const [original, setOriginal] = useState<RulePackage | null>(null); const [state, setState] = useState<ProfileEditState | null>(null);
  const [error, setError] = useState(""); const [tab, setTab] = useState(0); const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(""); const [chat, setChat] = useState(false); const [editing, setEditing] = useState<Editing | null>(null);
  const [notice, setNotice] = useState(""); const latest = useRef<ProfileEditState | null>(null);
  const opening = useRef<Promise<ProfileEditState> | null>(null); const saveJob = useRef<{ key: string; id: string } | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  function update(value: ProfileEditState) { latest.current = value; if (alive.current) { setState(value); setOriginal(null); } }
  useEffect(() => {
    let active = true;
    projectApi.package(rule.id).then(data => { if (active && !latest.current) { setOriginal(data); setError(""); } }).catch(e => { if (active && !latest.current) setError(String(e)); });
    return () => { active = false; };
  }, [rule.id, refresh]);
  const data = state?.package ?? original;
  const stages = data ? ruleStages(data) : []; const stage = stages[tab];
  const canEdit = rule.canDelete && !!rule.checksum;
  const blocked = !!busy;
  async function ensure(): Promise<ProfileEditState> {
    if (latest.current) return latest.current;
    if (!canEdit) throw new Error("仅规则所有者可以编辑，请先确认规则归属。");
    if (!opening.current) {
      const key = `profile-edit:${rule.id}:${rule.checksum}`;
      const id = sessionStorage.getItem(key) ?? crypto.randomUUID(); sessionStorage.setItem(key, id);
      opening.current = profileEditorApi.open(rule.id, rule.checksum!, id).then(value => { update(value); return value; }).finally(() => { opening.current = null; });
    }
    return opening.current;
  }
  async function action(message: string, task: () => Promise<void>) {
    if (busy) return; setBusy(message); setError("");
    try { await task(); } catch (e) { if (alive.current) setError(String(e)); }
    finally { if (alive.current) setBusy(""); }
  }
  function close() { if (busy || editing) { setError("请先完成当前操作，或取消未保存的编辑。"); return; } onClose(); }
  async function begin(path: string) {
    if (busy || editing || !canEdit) return;
    await action("正在建立或恢复编辑草稿…", async () => {
      const current = await ensure(); const file = current.package.files.find(f => f.path === path);
      if (!file) throw new Error("草稿中没有对应文本，请刷新资源。");
      setEditing({ path, text: file.content, before: file.content, revision: current.draft.revision, checksum: file.checksum });
    });
  }
  async function save() {
    if (!editing || !latest.current) return;
    const edit = editing;
    const key = JSON.stringify([edit.revision, edit.path, edit.checksum, edit.text]);
    if (saveJob.current?.key !== key) saveJob.current = { key, id: crypto.randomUUID() };
    await action("正在保存草稿修改…", async () => {
      const base = { ...latest.current!, draft: { ...latest.current!.draft, revision: edit.revision } };
      update(await profileEditorApi.save(base, [{ path: edit.path, before_checksum: edit.checksum, content: edit.text, operation: "write" }], saveJob.current!.id));
      setEditing(null); setNotice("修改已保存到草稿；核对后可发布新版本。");
    });
  }
  async function publish(current: ProfileEditState) {
    const accepted = current.validation.ready ? current : await profileEditorApi.accept(current);
    update(accepted);
    if (!accepted.validation.ready) throw new Error((accepted.validation.issues ?? []).map(i => i.message).join("；"));
    const row = await profileEditorApi.publish(accepted);
    sessionStorage.removeItem(`profile-edit:${rule.id}:${rule.checksum}`);
    const status = `已发布 ${row.profile_version}，已替换规则入口。${row.previous_version_retained ? "旧版仍被项目或任务引用，保留其固定版本。" : row.cleanup_pending ? "旧包清理暂未完成，下次发布时会重试。" : "闲置旧包已清理。"}`;
    setNotice(status); await onChanged?.(status);
  }
  async function confirm(proposal: EditProposal, accepted: boolean, release: boolean) {
    await action(accepted ? "正在应用确认的修改…" : "正在拒绝建议…", async () => {
      const current = await ensure(); const next = await profileEditorApi.confirm(current, proposal.id, accepted); update(next);
      if (accepted && release) await publish(next);
    });
  }
  function content(path: string | undefined, text: string, label: string) {
    if (!path) return <pre>{text}</pre>;
    if (editing?.path === path) return <div className="rule-text-editor"><label>{label}<textarea autoFocus aria-label={`编辑${label}`} value={editing.text} maxLength={300000} rows={14} disabled={blocked} onChange={e => setEditing({ ...editing, text: e.target.value })} onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); setEditing(null); } if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void save(); } }} /></label><p>公共提取约束保持受保护。Ctrl+Enter 保存，Esc 取消。</p><button type="button" disabled={blocked || editing.text === editing.before} onClick={() => void save()}>保存草稿修改</button><button type="button" disabled={blocked} onClick={() => { setEditing(null); setError(""); }}>取消编辑</button></div>;
    return <pre className={canEdit ? "rule-editable" : ""} tabIndex={canEdit ? 0 : undefined} role={canEdit ? "button" : undefined} aria-label={canEdit ? `双击编辑${label}` : undefined} title={canEdit ? "双击编辑，或按 Enter" : undefined} onDoubleClick={() => void begin(path)} onKeyDown={e => { if (e.key === "Enter") void begin(path); }}>{text}</pre>;
  }
  const confirmable = state && (state.validation.issues ?? []).every(i => ["EDITS_UNCONFIRMED", "EXPECTED_UNCONFIRMED"].includes(i.code));
  return <div className="modal-backdrop"><section className={`resource-modal${chat ? " resource-modal-editing" : ""}`} role="dialog" aria-modal="true" aria-labelledby="rule-heading">
    <header><h2 id="rule-heading">{rule.name}{asSkill ? ` · ${skillName(rule.key)}` : ""} · {state ? `${state.draft.version} 编辑草稿` : rule.version} · {asSkill ? "提取 Skill" : "规则引用"}</h2><div><button type="button" disabled={blocked || !!editing} onClick={() => void action("正在恢复最新内容…", async () => { if (state) update(await profileEditorApi.state(state.draft.draft_id)); else setRefresh(n => n + 1); })}>刷新资源</button><button type="button" disabled={blocked || !!editing || !canEdit} onClick={() => void action("正在加载规则编辑上下文…", async () => { await ensure(); setChat(value => !value); })}><MessagesSquare size={16} />{chat ? "收起辅助编辑" : "AI 辅助编辑"}</button><button type="button" onClick={close} aria-label="关闭规则面板"><X size={18} /></button></div></header>
    {error && <p className="inline-error" role="alert">{error}<button type="button" disabled={blocked || !!editing} onClick={() => void action("正在恢复草稿…", async () => { const current = await ensure(); update(await profileEditorApi.state(current.draft.draft_id)); })}>恢复编辑草稿</button></p>}
    {busy && <p className="profile-edit-progress" role="status">{busy}</p>}{notice && <p className="profile-edit-notice" role="status">{notice}</p>}
    <div className="resource-editor-layout"><section className="resource-main" aria-label="规则内容">
      <nav className="content-tabs" aria-label="提取规则">{["Stage 1 页面分类", "Stage 2 当前页扫描", "Stage 2 内部连接补全"].map((title, i) => <button key={title} type="button" disabled={blocked || !!editing} className={tab === i ? "active" : ""} onClick={() => setTab(i)}>{title}</button>)}</nav>
      <div className="resource-body">{!stage ? <p>正在校验并加载规则资源…</p> : <>
        <p className="profile-rule-hint">{canEdit ? "双击规则或样例内容可手动编辑；旁侧助手可以结合图纸和实际提取结果分析问题。" : "当前规则仅供查看，所有者可进行编辑。"}</p>
        {state?.draft.warnings?.filter(warning => warning.includes("旧字段定义")).map(warning => <p role="status" key={warning}>{warning}</p>)}
        <h3>规则 Prompt</h3>{content(stage.promptPath, stage.prompt, "本阶段规则")}
        <h3>本阶段实际样例 · {stage.examples.length}</h3>{stage.description ? <p>{stage.description}</p> : null}
        {stage.examples.map(example => <article className="rule-example" key={example.id}>
          <h4>{example.title}</h4><small>样例 ID：{example.id}</small>{example.description ? <p>{example.description}</p> : null}
          <div className="sample-grid">{example.images.map(img => <figure key={img.path}>{img.url ? <img src={img.url} alt={`${example.title} · ${roles[img.role] ?? img.role}`} /> : <p role="alert">资源包缺少图片：{img.path}</p>}<figcaption><strong>{roles[img.role] ?? img.role}</strong> · {img.path}{img.note ? <p>{img.note}</p> : null}</figcaption></figure>)}</div>
          {example.input ? <details><summary>任务上下文</summary>{content(example.inputPath, example.input, `${example.title}任务上下文`)}</details> : null}
          {example.expected ? <details><summary>人工确认的预期结果</summary>{content(example.expectedPath, example.expected, `${example.title}预期结果`)}</details> : <p>本资源包未提供该样例的 expected JSON。</p>}
        </article>)}
        {!stage.examples.length && <p>此阶段尚无 manifest 登记的样例，不将其他阶段图片当作该阶段样例。</p>}
        {stage.readme && <details><summary>样例包说明</summary>{content(stage.readmePath, stage.readme, "样例说明")}</details>}
      </>}</div>
      {state && <footer className="profile-edit-footer"><span>来源版本 {rule.version} → 待发布 {state.draft.version}</span>{(state.validation.issues ?? []).map((issue, i) => <p key={i}>{issue.message}</p>)}<button type="button" disabled={blocked || !!editing || !state.changed || (!state.validation.ready && !confirmable)} onClick={() => void action("正在校验并发布新版…", async () => { await publish(state); })}>确认修改并发布新版</button></footer>}
    </section>
    {chat && state && <Suspense fallback={<p>正在加载规则助手…</p>}><ProfileRuleChat state={state} stage={(["classification", "scan", "completion"] as ProfileStage[])[tab]} busy={blocked || !!editing} onBusy={setBusy} onState={update} onError={setError} onConfirm={confirm} /></Suspense>}
    </div>
  </section></div>;
}
