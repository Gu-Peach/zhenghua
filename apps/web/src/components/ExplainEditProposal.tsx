import { useState } from "react";
import { editOperationLabel, explainEdits, changesRecordOrigin, type EditProposal, type EditReceipt } from "@/apis/explain-edits";
import "@/assets/explain-edits.css";
import { ConnectionChangeList } from "./ConnectionChangeList";

export function ExplainEditProposal({ proposal, disabled, onBusy, onDecision, decideCandidate }: { proposal: EditProposal; disabled: boolean; onBusy: (busy: boolean) => void; onDecision: (receipt: EditReceipt) => void; decideCandidate?: (accepted: boolean) => Promise<EditReceipt> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [page, setPage] = useState(0); const [receipt, setReceipt] = useState<EditReceipt | null>(null);
  const status = receipt?.status ?? proposal.status;
  const changes = proposal.changes.slice(page * 25, (page + 1) * 25);
  async function decide(accepted: boolean) {
    if (busy || disabled || accepted && invalidOrigin) return;
    setBusy(true); onBusy(true); setError("");
    try { const result = decideCandidate ? await decideCandidate(accepted) : await explainEdits.decide(proposal.project_id, proposal, accepted); setReceipt(result); onDecision(result); }
    catch (reason) { setError(`${String(reason)}。若行版本或范围已变化，请重新生成修改方案。`); }
    finally { setBusy(false); onBusy(false); }
  }
  const scope = proposal.request.scope;
  const invalidOrigin = changesRecordOrigin(proposal);
  return <section className="explain-edit-proposal" aria-label="线表修改预览">
    <div className="proposal-heading"><h3>线表修改预览</h3><span className={`proposal-status ${status}`}>{status === "pending" ? "待你确认" : status === "applied" ? "已保存" : "已拒绝"}</span></div>
    <p className="proposal-operation">{editOperationLabel(proposal)}</p>
    <p>范围：{scope.workspace_code ? `工作区 ${scope.workspace_code} ` : ""}{scope.drawing_page ? `页 ${scope.drawing_page} ` : ""}{scope.principle_numbers?.length ? `原理号 ${scope.principle_numbers.join("、")} ` : ""}{scope.connection_ids?.length ? `${scope.connection_ids.length} 个指定行 ` : ""}</p>
    <p>匹配 {proposal.matched_count} 行，实际修改 {proposal.changed_count} 行。{proposal.request.reason}</p>
    <ConnectionChangeList changes={changes} />
    {proposal.changes.length > 25 && <nav aria-label="修改预览分页"><button type="button" disabled={busy || page === 0} onClick={() => setPage(n => n - 1)}>上一组</button><span>第 {page + 1} / {Math.ceil(proposal.changes.length / 25)} 组</span><button type="button" disabled={busy || (page + 1) * 25 >= proposal.changes.length} onClick={() => setPage(n => n + 1)}>下一组</button></nav>}
    {status === "pending" ? <><p className="explain-edit-hint">确认后保存以上完整范围的修改；历史提取证据保留。整组交换保留记录所属页和工作区，坐标按自身PDF页号定位。</p><div className="explain-edit-actions"><button type="button" className="primary-button" disabled={disabled || busy || invalidOrigin || !proposal.changed_count} onClick={() => void decide(true)}>确认修改 {proposal.changed_count} 行</button><button type="button" disabled={disabled || busy} onClick={() => void decide(false)}>拒绝修改</button></div></> : <p role="status">{status === "applied" ? `已保存 ${receipt?.changed_count ?? proposal.changed_count} 行修改，历史解释保留；继续追问将读取新结果。` : "已拒绝，此方案未修改线表。"}</p>}
    {status === "pending" && invalidOrigin && <p role="alert">旧方案包含记录所属页或工作区变更，已停用；请重新生成端点修改方案。</p>}
    {status === "applied" && !invalidOrigin && <p role="status">记录所属页、工作区和ID保持不变。</p>}
    {!proposal.changed_count && status === "pending" && <p role="status">没有需要改变的记录，不会写入线表。</p>}
    {busy && <p role="status">正在提交决定…</p>}{error && <p role="alert" className="explain-error">{error}</p>}
  </section>;
}
