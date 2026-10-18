import { useEffect, useState } from "react";
import { rescans, type RescanRun, type RescanEvidenceImage } from "@/apis/rescan";
import { editFieldNames } from "@/apis/explain-edits";
import { DrawingLightbox, type LightboxImage } from "./DrawingLightbox";

const labels: Record<string, string> = { queued: "重扫已入队，等待 Worker", preparing: "读取原图、关联图与历史规则", scan: "重新扫描", completion: "定向补全", page_completed: "本页候选已保存", ready: "重扫候选已就绪", finished: "处理结束", failed: "重扫失败", cancelled: "重扫已取消" };
const text = (value: unknown) => value == null ? "空值" : typeof value === "boolean" ? value ? "是" : "否" : typeof value === "object" ? JSON.stringify(value) : String(value);
export function RescanTask({ initial, disabled, onBusy, onDecision, onProgress, onExplain }: { initial: RescanRun; disabled: boolean; onBusy: (busy: boolean) => void; onDecision: (run: RescanRun) => void; onProgress?: () => void; onExplain?: (id: string) => void }) {
  const [run, setRun] = useState<RescanRun | null>(initial); const [error, setError] = useState(""); const [saving, setSaving] = useState(false); const [page, setPage] = useState(0); const [retry, setRetry] = useState(0);
  const [images, setImages] = useState<RescanEvidenceImage[]>([]);
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  useEffect(() => { onProgress?.(); }, [run, images, error, onProgress]);
  useEffect(() => {
    if (!run || !["ready", "applied", "rejected"].includes(run.status)) return;
    const abort = new AbortController();
    rescans.evidence(run, abort.signal).then(items => { if (!abort.signal.aborted) setImages(items); }).catch(() => {});
    return () => abort.abort();
  }, [run]);
  useEffect(() => { let alive = true; let timer: number | undefined; const abort = new AbortController();
    const read = async () => {
      try { const current = await rescans.get(initial.project_id, initial.id, abort.signal); if (!alive) return; setRun(current); setError(""); if (["queued", "running"].includes(current.status)) timer = window.setTimeout(() => void read(), 2000); }
      catch (reason) { if (alive) { setRun(null); setError(String(reason)); } }
    };
    void read(); return () => { alive = false; abort.abort(); window.clearTimeout(timer); };
  }, [initial.project_id, initial.id, retry]);
  async function decide(accepted: boolean | null) {
    if (!run || saving || disabled || accepted !== null && !run.checksum) return;
    setSaving(true); onBusy(true); setError("");
    try { const current = accepted === null ? await rescans.cancel(run) : await rescans.decide(run, accepted); setRun(current); onDecision(current); }
    catch (reason) { setError(`${String(reason)}。请刷新任务；范围或版本变化时需重新重扫。`); }
    finally { setSaving(false); onBusy(false); }
  }
  const changes = run?.candidate?.changes ?? [];
  return <section className="explain-edit-proposal" aria-label="重扫任务与结果">
    <h3>提取 Agent 重扫</h3>
    {run ? <><p role="status">{run.status === "applied" ? "重扫结果已保存，记录所属页与工作区保持不变。" : run.status === "rejected" ? "已拒绝重扫候选，线表保持原值。" : labels[run.stage] ?? run.stage}</p>
      <p>规则：{String(run.profile.key)} · {String(run.profile.version)} · 范围：{run.request.scope.workspace_code ?? run.request.scope.drawing_page ?? `${run.request.scope.connection_ids?.length ?? 0} 条连接`}</p>
      {run.status === "running" && typeof run.progress?.pdf_page_number === "number" && <p>正在处理 PDF 第 {run.progress?.pdf_page_number} 页</p>}
      {["queued", "running"].includes(run.status) ? <><p>正在生成候选，正式线表尚未改动。关闭窗口不会取消任务。</p><button type="button" disabled={disabled || saving} onClick={() => void decide(null)}>取消重扫</button></> : null}
      {run.error && <p role="alert">{run.error}</p>}
      {run.candidate ? <><p>拟修改／新增 {changes.length} 行；未唯一匹配 {(run.candidate.unmatched_ids ?? []).length} 行。</p>
        {images.length > 0 && <details className="rescan-image-evidence"><summary>重扫使用的原图与细节图（原图最多展示8张）</summary><div>{images.map(image => <figure key={image.id}>{image.image_url ? <button type="button" className="drawing-thumbnail" aria-label={`放大查看 ${image.title}`} onClick={() => setLightbox({ url: image.image_url!, title: image.title })}><img src={image.image_url} alt={image.title} /></button> : <span>图片暂不可用</span>}<figcaption>{image.title}</figcaption></figure>)}</div></details>}
        <div className="explain-edit-table"><table><thead><tr><th>原理号／操作</th><th>字段</th><th>修改前</th><th>修改后</th></tr></thead><tbody>{changes.slice(page * 25, (page + 1) * 25).flatMap(change => Object.entries(change.after).map(([field, value], i) => <tr key={`${change.connection_id}:${field}`}><td title={change.connection_id}>{i === 0 ? <>{change.principle_number ?? change.connection_id}<small>{change.action === "insert" ? "新增候选" : "更新原行"} · {change.source_drawing_page}</small></> : ""}</td><td>{editFieldNames[field] ?? field}</td><td>{change.action === "insert" ? "原记录不存在" : text(change.before?.[field])}</td><td>{text(value)}</td></tr>))}</tbody></table></div>
        {changes.length > 25 && <nav aria-label="重扫结果分页"><button type="button" disabled={page === 0} onClick={() => setPage(n => n - 1)}>上一组</button><span>第 {page + 1} 组</span><button type="button" disabled={(page + 1) * 25 >= changes.length} onClick={() => setPage(n => n + 1)}>下一组</button></nav>}
        {(run.candidate.warnings ?? []).map((warning, i) => <p className="explain-gap" key={i}>{warning}</p>)}
        {onExplain && run.status !== "ready" && <button type="button" disabled={disabled || saving} onClick={() => onExplain(run.id)}>解释这次重扫差异</button>}
        {run.status === "ready" && <><p>仅提交以上候选，不自动删除未再次识别的记录。请核对端点及图纸定位。</p><div className="explain-edit-actions rescan-actions">{onExplain && <button type="button" aria-label="解释这次重扫差异" disabled={disabled || saving} onClick={() => onExplain(run.id)}>解释差异</button>}<button type="button" disabled={disabled || saving || !changes.length} onClick={() => void decide(true)}>确认重扫结果 {changes.length} 行</button><button type="button" disabled={disabled || saving} onClick={() => void decide(false)}>拒绝重扫结果</button></div></>}
      </> : null}
    </> : null}
    {error ? <p role="alert">{error}<button type="button" disabled={saving} onClick={() => setRetry(n => n + 1)}>刷新重扫任务</button></p> : null}
    {lightbox ? <DrawingLightbox image={lightbox} onClose={() => setLightbox(null)} /> : null}
  </section>;
}
