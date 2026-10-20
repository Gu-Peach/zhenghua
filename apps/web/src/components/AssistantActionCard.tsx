import { useEffect, useState } from "react";
import { assistantApi, type AssistantAction } from "@/apis/assistant";
import type { RescanRun } from "@/apis/rescan";
import type { EditProposal, EditReceipt } from "@/apis/explain-edits";
import type { components } from "@/apis/generated";
import { useAssistantStore } from "@/stores/assistant-store";
import { ExplainEditProposal } from "./ExplainEditProposal";
import { RescanTask } from "./RescanTask";

export function AssistantActionCard({ id }: { id: string }) {
  const [action, setAction] = useState<AssistantAction | null>(null);
  const [error, setError] = useState(""); const [retry, setRetry] = useState(0); const [busy, setBusy] = useState(false);
  useEffect(() => { let alive = true; assistantApi.action(id).then(value => { if (alive) { setAction(value); setError(""); } }).catch(reason => { if (alive) setError(String(reason)); }); return () => { alive = false; }; }, [id, retry]);
  async function decide(accepted: boolean) {
    if (!action) throw new Error("方案未加载");
    const updated = await assistantApi.decide(action, accepted);
    setAction(updated); useAssistantStore.getState().refreshResults();
    return { ...updated, result: updated.result ?? {} };
  }
  const result = action?.result ?? {}; const detail = result.detail;
  return <div className="assistant-action-card">
    {!action && !error ? <p role="status">正在读取操作回执…</p> : null}
    {action && result.kind === "rescan" && detail ? <RescanTask initial={detail as RescanRun} disabled={busy} onBusy={setBusy} onDecision={() => { useAssistantStore.getState().refreshResults(); }} decideCandidate={async accepted => (await decide(accepted)).result.detail as RescanRun} /> : null}
    {action && result.kind === "connection_edit" && detail ? <ExplainEditProposal proposal={detail as EditProposal} disabled={busy} onBusy={setBusy} onDecision={() => {}} decideCandidate={async accepted => (await decide(accepted)).result.receipt as EditReceipt} /> : null}
    {action && result.kind === "profile" && detail ? <section aria-label="规则修改与发布预览">
      <div className="proposal-heading"><h3>规则修改建议</h3><span className={`proposal-status ${action.status === "awaiting_confirmation" ? "pending" : action.status}`}>{action.status === "applied" ? "已发布" : action.status === "rejected" ? "已拒绝" : "待你确认"}</span></div><p>{(detail as components["schemas"]["Proposal"]).summary}</p>
      <p>诊断使用项目原规则；以下差异基于最新可编辑版本。确认后应用此方案并发布新版本，原项目仍绑定旧版本。</p>
      {(detail as components["schemas"]["Proposal"]).diffs?.map(diff => <details key={diff.path}><summary>{diff.path}</summary><strong>修改前</strong><pre>{diff.before ?? "不存在"}</pre><strong>修改后</strong><pre>{diff.after ?? "删除文件"}</pre></details>)}
      {action.status === "applied" || action.status === "rejected" ? <p role="status">{action.status === "applied" ? "新规则已发布，原项目规则版本保留。" : "已拒绝修改建议。"}</p> : <div className="assistant-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => { setBusy(true); setError(""); void decide(true).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>确认修改并发布</button><button type="button" disabled={busy} onClick={() => { setBusy(true); void decide(false).catch(reason => setError(String(reason))).finally(() => setBusy(false)); }}>拒绝建议</button></div>}
    </section> : null}
    {error ? <p role="alert">{error}<button type="button" disabled={busy} onClick={() => { setError(""); setRetry(n => n + 1); }}>重新读取方案</button></p> : null}
  </div>;
}
