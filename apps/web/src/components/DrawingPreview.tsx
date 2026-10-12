import { FileImage, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";
import type { Drawing, ProjectDetail } from "@/apis/types";
import { projectApi } from "@/apis/projects";

export function DrawingPreview({ project, drawing, targetTerminal }: { project: ProjectDetail; drawing: Drawing | null; targetTerminal?: string }) {
  const [zoom, setZoom] = useState(1);
  const [renewedUrl, setRenewedUrl] = useState<string | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState("");
  const url = renewedUrl ?? drawing?.imageUrl;
  async function refreshImage() {
    if (!drawing) return;
    setReloading(true); setError("");
    try { const fresh = await projectApi.drawing(drawing.id); setRenewedUrl(fresh.imageUrl ?? null); setFailedUrl(null); }
    catch (reason) { setError(String(reason)); }
    finally { setReloading(false); }
  }
  return <section className="drawing-preview"><div className="preview-toolbar"><div><FileImage size={17} /><span>{targetTerminal ? "目标页" : "原页"} · {project.name} / {drawing?.drawingPage ?? "待选择"}{targetTerminal ? ` · 终点 ${targetTerminal}` : ""}</span></div><div className="preview-actions"><button type="button" onClick={() => setZoom(z => Math.max(0.25, z - 0.25))} aria-label="缩小"><ZoomOut size={17} /></button><button type="button" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button><button type="button" onClick={() => setZoom(z => Math.min(4, z + 0.25))} aria-label="放大"><ZoomIn size={17} /></button></div></div><div className="drawing-canvas">{url && drawing && failedUrl !== url ? <img src={url} alt={`${project.name} / 业务页 ${drawing.drawingPage} / PDF ${drawing.pdfPage}`} onError={() => setFailedUrl(url)} style={{ width: `${zoom * 100}%`, maxWidth: "none", objectFit: "contain" }} /> : <div className="preview-empty"><FileImage size={24} /><strong>{failedUrl ? "图纸加载失败或签名已过期" : drawing ? "该图纸尚未注册图片" : "请选择图纸查看原页"}</strong>{drawing ? <button type="button" disabled={reloading} onClick={() => void refreshImage()}>{reloading ? "正在刷新…" : "刷新图纸链接"}</button> : <span>只显示真实图纸，无模拟图片。</span>}{error ? <p role="alert">{error}</p> : null}</div>}</div><footer className="preview-footer">PDF 物理页 {drawing?.pdfPage ?? "-"} · 业务页 {drawing?.drawingPage ?? "-"}{drawing?.referenceNote ? <span title={drawing.referenceNote}> · 历史来源证据</span> : null}</footer></section>;
}
