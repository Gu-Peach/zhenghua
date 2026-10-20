import { useEffect, useState } from "react";
import { legacyFullRescan, rescans, type RescanRun, type RescanEvidenceImage, type RescanRemovedRow } from "@/apis/rescan";
import { ConnectionChangeList } from "./ConnectionChangeList";
import { DrawingLightbox, type LightboxImage } from "./DrawingLightbox";

const labels: Record<string, string> = { queued: "重扫已入队，等待 Worker", preparing: "读取原图、关联图与历史规则", scan: "重新扫描", completion: "定向补全", page_completed: "本页候选已保存", ready: "重扫候选已就绪", finished: "处理结束", failed: "重扫失败", cancelled: "重扫已取消" };


function RemovedRows({ rows }: { rows: RescanRemovedRow[] }) {
  const [page, setPage] = useState(0);
  return <details className="replacement-removals"><summary>将删除的旧结果：{rows.length} 行</summary>
    <ConnectionChangeList changes={rows.slice(page * 25, (page + 1) * 25)} removal />
    {rows.length > 25 ? <nav aria-label="待删除旧行分页"><button type="button" disabled={page === 0} onClick={() => setPage(n => n - 1)}>上一组旧行</button><span>第 {page + 1} 组</span><button type="button" disabled={(page + 1) * 25 >= rows.length} onClick={() => setPage(n => n + 1)}>下一组旧行</button></nav> : null}
  </details>;
}
export function RescanTask({ initial, disabled, onBusy, onDecision, onProgress, onExplain, decideCandidate }: { initial: RescanRun; disabled: boolean; onBusy: (busy: boolean) => void; onDecision: (run: RescanRun) => void; onProgress?: () => void; onExplain?: (id: string) => void; decideCandidate?: (accepted: boolean) => Promise<RescanRun> }) {
  const [run, setRun] = useState<RescanRun | null>(initial); const [error, setError] = useState(""); const [saving, setSaving] = useState(false); const [page, setPage] = useState(0); const [retry, setRetry] = useState(0);
  const [images, setImages] = useState<RescanEvidenceImage[]>([]);
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { onProgress?.(); }, [run, images, error, onProgress]);
  useEffect(() => {
    if (!run || !["ready", "applied", "rejected"].includes(run.status)) return;
    const abort = new AbortController();
    rescans.evidence(run, abort.signal).then(items => { if (!abort.signal.aborted) setImages(items); }).catch(() => {});
    return () => abort.abort();
  }, [run]);
  useEffect(() => { let alive = true; let timer: number | undefined; const abort = new AbortController();
    const read = async () => {
      try { const current = await rescans.get(initial.project_id, initial.id, abort.signal); if (!alive) return; setRun(current); setLoaded(true); setError(""); if (["queued", "running"].includes(current.status)) timer = window.setTimeout(() => void read(), 2000); }
      catch (reason) { if (alive) { setRun(null); setLoaded(false); setError(String(reason)); } }
    };
    void read(); return () => { alive = false; abort.abort(); window.clearTimeout(timer); };
  }, [initial.project_id, initial.id, retry]);
  async function decide(accepted: boolean | null) {
    if (!run || saving || disabled || accepted !== null && !run.checksum || accepted && (!loaded || legacyFullRescan(run))) return;
    setSaving(true); onBusy(true); setError("");
    try { const current = accepted === null ? await rescans.cancel(run) : decideCandidate ? await decideCandidate(accepted) : await rescans.decide(run, accepted); setRun(current); onDecision(current); }
    catch (reason) { setError(`${String(reason)}。请刷新任务；范围或版本变化时需重新重扫。`); }
    finally { setSaving(false); onBusy(false); }
  }
  const changes = run?.candidate?.changes ?? [];
  const replacement = run?.candidate?.replacement;
  const removed = replacement?.removed ?? [];
  const incompatible = !!run && run.status === "ready" && (legacyFullRescan(run) || run.request.result_mode === "replace_scope" && !replacement);
  return <section className="explain-edit-proposal" aria-label="重扫任务与结果">
    <div className="proposal-heading"><h3>重扫修改预览</h3><span className={`proposal-status ${run?.status ?? "failed"}`}>{run?.status === "ready" ? "待你确认" : run?.status === "applied" ? "已保存" : run?.status === "rejected" ? "已拒绝" : run?.status === "failed" ? "执行失败" : run?.status === "cancelled" ? "已取消" : run ? "处理中" : "读取失败"}</span></div>
    {run ? <><p role="status">{run.status === "applied" ? replacement ? `范围结果已替换：删除旧结果 ${removed.length} 行，写入新结果 ${changes.length} 行。` : "重扫结果已保存，记录所属页与工作区保持不变。" : run.status === "rejected" ? "已拒绝重扫候选，线表保持原值。" : labels[run.stage] ?? run.stage}</p>
      <p>规则：{String(run.profile.key)} · {String(run.profile.version)} · 范围：{run.request.scope.workspace_code ?? run.request.scope.drawing_page ?? `${run.request.scope.connection_ids?.length ?? 0} 条连接`}</p>
      {run.status === "running" && typeof run.progress?.pdf_page_number === "number" && <p>正在处理 PDF 第 {run.progress?.pdf_page_number} 页</p>}
      {["queued", "running"].includes(run.status) ? <><p>正在生成候选，正式线表尚未改动。关闭窗口不会取消任务。</p><button type="button" disabled={disabled || saving} onClick={() => void decide(null)}>取消重扫</button></> : null}
      {run.error && <p role="alert">{run.error}</p>}
      {run.candidate ? <>{replacement ? <><p>替换方式：完整替换所选范围。确认后删除 {removed.length} 条旧结果，写入 {changes.length} 条新结果，范围外不变。</p>{!changes.length && removed.length ? <p className="explain-gap" role="alert">本次没有新结果，确认后所选范围将被清空。</p> : null}<div className="proposal-counts"><span>删除旧记录 <strong>{removed.length} 行</strong></span><span>写入新记录 <strong>{changes.length} 行</strong></span></div><RemovedRows rows={removed} /><h4>将写入的新结果：{changes.length} 行</h4></> : <p>{legacyFullRescan(run) ? "历史合并结果（未执行范围替换）" : "局部修订"}：拟修改 {changes.length} 行；未唯一匹配 {(run.candidate.unmatched_ids ?? []).length} 行。</p>}
        {incompatible ? <p role="alert">旧版或不完整的全量候选不能执行范围替换，请重新发起重扫；原数据尚未改动。</p> : null}
        {images.length > 0 && <details className="rescan-image-evidence"><summary>重扫使用的原图与细节图（原图最多展示8张）</summary><div>{images.map(image => <figure key={image.id}>{image.image_url ? <button type="button" className="drawing-thumbnail" aria-label={`放大查看 ${image.title}`} onClick={() => setLightbox({ url: image.image_url!, title: image.title })}><img src={image.image_url} alt={image.title} /></button> : <span>图片暂不可用</span>}<figcaption>{image.title}</figcaption></figure>)}</div></details>}
        <ConnectionChangeList changes={changes.slice(page * 25, (page + 1) * 25)} />
        {changes.length > 25 && <nav aria-label="重扫结果分页"><button type="button" disabled={page === 0} onClick={() => setPage(n => n - 1)}>上一组</button><span>第 {page + 1} 组</span><button type="button" disabled={(page + 1) * 25 >= changes.length} onClick={() => setPage(n => n + 1)}>下一组</button></nav>}
        {(run.candidate.warnings ?? []).map((warning, i) => <p className="explain-gap" key={i}>{warning}</p>)}
        {onExplain && run.status !== "ready" && <button type="button" disabled={disabled || saving} onClick={() => onExplain(run.id)}>解释这次重扫差异</button>}
        {run.status === "ready" && <><p>{replacement ? "确认将一次性删除上述全部旧结果并写入新结果；写入失败时整体回滚。" : "仅替换所选行或字段；无法唯一定位的行保持原值，范围外不变。"}</p><div className="explain-edit-actions rescan-actions">{onExplain && <button type="button" aria-label="解释这次重扫差异" disabled={disabled || saving} onClick={() => onExplain(run.id)}>解释差异</button>}<button type="button" className="primary-button" aria-label={replacement ? `确认范围替换 删除${removed.length}行 写入${changes.length}行` : `确认重扫结果 ${changes.length} 行`} disabled={disabled || saving || !loaded || incompatible || !changes.length && !removed.length} onClick={() => void decide(true)}>{replacement ? `确认替换（删除${removed.length}行／写入${changes.length}行）` : `确认重扫结果 ${changes.length} 行`}</button><button type="button" disabled={disabled || saving} onClick={() => void decide(false)}>拒绝重扫结果</button></div></>}
      </> : null}
    </> : null}
    {error ? <p role="alert">{error}<button type="button" disabled={saving} onClick={() => setRetry(n => n + 1)}>刷新重扫任务</button></p> : null}
    {lightbox ? <DrawingLightbox image={lightbox} onClose={() => setLightbox(null)} /> : null}
  </section>;
}
