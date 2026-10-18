import { FileImage, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";
import type { Drawing, ProjectDetail } from "@/apis/types";
import { projectApi } from "@/apis/projects";
import type { DrawingMarker } from "@/apis/drawing-evidence";
import { useDrawingNavigation } from "@/hooks/useDrawingNavigation";

export function DrawingPreview({ project, drawing, targetTerminal, role, markers = [], notes = [] }: { project: ProjectDetail; drawing: Drawing | null; targetTerminal?: string; role?: "source" | "target"; markers?: DrawingMarker[]; notes?: string[] }) {
  const [renewedUrl, setRenewedUrl] = useState<string | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false); const [error, setError] = useState("");
  const url = renewedUrl ?? drawing?.imageUrl;
  const { canvasRef, frameRef, zoom, setZoom, dragging, navigation } = useDrawingNavigation(!!url && failedUrl !== url);
  async function refreshImage() {
    if (!drawing) return;
    setReloading(true); setError("");
    try { const fresh = await projectApi.drawing(drawing.id); setRenewedUrl(fresh.imageUrl ?? null); setFailedUrl(null); }
    catch (reason) { setError(String(reason)); }
    finally { setReloading(false); }
  }
  return <section className="drawing-preview" aria-label={role === "target" || targetTerminal ? "目标页预览" : "原页预览"}>
    <div className="preview-toolbar"><div><FileImage size={17} /><span title={`${project.name} / ${drawing?.drawingPage ?? "待选择"}${targetTerminal ? ` · 终点 ${targetTerminal}` : ""}`}>{role === "target" || targetTerminal ? "目标页" : "原页"} · {project.name} / {drawing?.drawingPage ?? "待选择"}{targetTerminal ? ` · 终点 ${targetTerminal}` : ""}</span></div><div className="preview-actions"><button type="button" onClick={() => setZoom(zoom - .25)} aria-label="缩小"><ZoomOut size={17} /></button><button type="button" className="preview-zoom-value" title="滚轮缩放，按住中键拖动；点击恢复100%" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button><button type="button" onClick={() => setZoom(zoom + .25)} aria-label="放大"><ZoomIn size={17} /></button></div></div>
    <div ref={canvasRef} className={`drawing-canvas ${dragging ? "is-panning" : ""}`} {...navigation} onMouseDown={event => { if (event.button === 1) event.preventDefault(); }} onAuxClick={event => event.preventDefault()} title="滚轮缩放 · 按住鼠标中键拖动">{url && drawing && failedUrl !== url ? <div ref={frameRef} className="evidence-image-frame" style={{ width: `${zoom * 100}%` }}>
      <img src={url} alt={`${project.name} / 业务页 ${drawing.drawingPage} / PDF ${drawing.pdfPage}`} draggable={false} onError={() => setFailedUrl(url)} />
      {markers.map(marker => <span key={marker.kind} className={`terminal-marker terminal-marker-${marker.kind} ${marker.x > .65 ? "label-left" : ""}`} style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} role="img" aria-label={marker.label} data-marker-kind={marker.kind} title={`${marker.label} · (${marker.x}, ${marker.y})`}><i /><b>{marker.label}</b></span>)}
    </div> : <div className="preview-empty"><FileImage size={24} /><strong>{failedUrl ? "图纸加载失败或签名已过期" : drawing ? "该图纸尚未注册图片" : "请选择图纸查看原页"}</strong>{drawing ? <button type="button" disabled={reloading} onClick={() => void refreshImage()}>{reloading ? "正在刷新…" : "刷新图纸链接"}</button> : <span>只显示真实图纸，无模拟图片。</span>}{error ? <p role="alert">{error}</p> : null}</div>}</div>
    {notes.length ? <p className="coordinate-note" role="status">{notes.join("；")}</p> : null}
    <footer className="preview-footer">PDF 物理页 {drawing?.pdfPage ?? "-"} · 业务页 {drawing?.drawingPage ?? "-"}{drawing?.referenceNote ? <span title={drawing.referenceNote}> · 历史来源证据</span> : null}</footer>
  </section>;
}
