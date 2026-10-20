import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import { answerColumns, importAnswerFile, pageKey, type AnswerRow } from "@/apis/answer-comparison";
import { projectApi } from "@/apis/projects";
import type { ProjectDetail, WiringRow } from "@/apis/types";
import { useAnswerStore } from "@/stores/answer-store";
import { useSessionStore } from "@/stores/session-store";
import "@/assets/answer-comparison.css";

export function AnswerComparison({ project, drawingId, workspaceId, revision }: {
  project: ProjectDetail; drawingId: string | null; workspaceId: string | null; revision: number;
}) {
  const book = useAnswerStore(state => state.books[project.id]);
  const fileInput = useRef<HTMLInputElement>(null);
  const upperScroll = useRef<HTMLDivElement>(null); const lowerScroll = useRef<HTMLDivElement>(null);
  const [importing, setImporting] = useState(false); const [importError, setImportError] = useState("");
  const [retry, setRetry] = useState(0);
  const [snapshot, setSnapshot] = useState<{ key: string; rows?: WiringRow[]; error?: string }>({ key: "" });
  const drawings = project.workspaces.filter(workspace => !workspaceId || workspace.id === workspaceId).flatMap(workspace => workspace.drawings);
  const drawing = drawings.find(item => item.id === drawingId) ?? drawings.find(item => book?.pages[pageKey(item.drawingPage)]) ?? drawings[0];
  const selectedDrawingId = drawing?.id;
  const answers = drawing ? book?.pages[pageKey(drawing.drawingPage)] : undefined;
  const requestKey = `${selectedDrawingId}:${revision}:${retry}`;
  const ready = snapshot.key === requestKey && !!snapshot.rows;
  useEffect(() => {
    if (!selectedDrawingId) return;
    let cancelled = false;
    projectApi.comparisonRows(project.id, selectedDrawingId, () => cancelled)
      .then(rows => { if (!cancelled) setSnapshot({ key: requestKey, rows }); })
      .catch(reason => { if (!cancelled) setSnapshot({ key: requestKey, error: String(reason) }); });
    return () => { cancelled = true; };
  }, [selectedDrawingId, project.id, requestKey]);
  const columns = answerColumns.filter(([key]) => !book || book.fields.includes(key));
  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    const owner = useSessionStore.getState().session?.user.id;
    setImporting(true); setImportError("");
    try {
      const imported = await importAnswerFile(file);
      if (!owner || owner !== useSessionStore.getState().session?.user.id) return;
      useAnswerStore.getState().put(project.id, imported);
    } catch (reason) { setImportError(reason instanceof Error ? reason.message : "答案导入失败，请重试。"); }
    finally { setImporting(false); }
  }
  const failed = snapshot.key === requestKey ? snapshot.error : undefined;
  return <section className="answer-comparison" aria-label="临时答案对比">
    <input ref={fileInput} type="file" accept=".xlsx" aria-label="导入答案XLSX" className="visually-hidden" onChange={event => void importFile(event)} />
    {importError ? <p role="alert" className="inline-error">{importError}</p> : null}
    <ResultPane key={`actual:${selectedDrawingId}`} title="提取结果" columns={columns} rows={ready ? snapshot.rows! : []} scrollRef={upperScroll} onScroll={left => { if (lowerScroll.current && lowerScroll.current.scrollLeft !== left) lowerScroll.current.scrollLeft = left; }} actions={
      <button type="button" className="icon-button" aria-label="刷新提取结果" title="刷新提取结果" onClick={() => setRetry(value => value + 1)}><RefreshCw size={16} /></button>
    } empty={failed ? <p role="alert">读取失败：{failed}<button type="button" onClick={() => setRetry(value => value + 1)}>重试</button></p> : <p role="status">{!drawing ? "请在左侧选择图纸" : !ready ? "正在读取提取结果…" : project.status === "processing" ? "正在提取…" : "本页暂无提取结果"}</p>} />
    <ResultPane key={`answer:${selectedDrawingId}:${book?.filename}`} title="标准答案" columns={columns} rows={answers ?? []} scrollRef={lowerScroll} onScroll={left => { if (upperScroll.current && upperScroll.current.scrollLeft !== left) upperScroll.current.scrollLeft = left; }} actions={<>
      <button type="button" className="icon-button" aria-label={book ? "更换答案XLSX" : "导入答案XLSX"} title={book ? `更换答案：${book.filename}` : "导入答案XLSX"} disabled={importing} onClick={() => fileInput.current?.click()}>{importing ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}</button>
      {book ? <button type="button" className="icon-button" aria-label="清除答案" title="清除答案" disabled={importing} onClick={() => { useAnswerStore.getState().remove(project.id); setImportError(""); }}><Trash2 size={16} /></button> : null}
    </>} empty={<p role="status">{importing ? "正在读取答案…" : !book ? "请导入标准答案" : !drawing ? "请在左侧选择图纸" : "本页暂无标准答案"}</p>} />
  </section>;
}

function ResultPane({ title, columns, rows, actions, empty, scrollRef, onScroll }: {
  title: string; columns: (typeof answerColumns)[number][]; rows: (WiringRow | AnswerRow)[];
  actions: ReactNode; empty: ReactNode; scrollRef: React.RefObject<HTMLDivElement | null>; onScroll: (left: number) => void;
}) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(rows.length / 50)); const currentPage = Math.min(page, pageCount - 1);
  return <section className="answer-pane" aria-label={title}>
    <header className="answer-pane-header"><h2>{title}</h2><div className="answer-actions">{actions}</div></header>
    <div className="answer-table-scroll" ref={scrollRef} onScroll={event => onScroll(event.currentTarget.scrollLeft)}>
      <table className="answer-table" aria-label={title} style={{ width: `${columns.length * 130}px` }}><thead><tr>{columns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>
        {rows.slice(currentPage * 50, currentPage * 50 + 50).map((row, index) => <tr key={"id" in row ? row.id : `${row.sheet}:${row.sourceRow}:${index}`}>{columns.map(([key]) => <td key={key}>{row[key] || "—"}</td>)}</tr>)}
      </tbody></table>{!rows.length ? <div className="answer-empty">{empty}</div> : null}
    </div>
    {pageCount > 1 ? <footer className="answer-footer"><button type="button" aria-label={`${title}上一页`} disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>上一页</button><span>{currentPage + 1} / {pageCount}</span><button type="button" aria-label={`${title}下一页`} disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>下一页</button></footer> : null}
  </section>;
}
