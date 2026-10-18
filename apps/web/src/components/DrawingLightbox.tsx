import { X, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDrawingNavigation } from "@/hooks/useDrawingNavigation";

export interface LightboxImage { url: string; title: string }

export function DrawingLightbox({ image, onClose }: { image: LightboxImage; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [failed, setFailed] = useState(false);
  const { canvasRef, frameRef, zoom, setZoom, dragging, navigation } = useDrawingNavigation(!failed);
  useEffect(() => {
    const node = dialog.current;
    const previous = document.activeElement;
    node?.showModal();
    return () => { node?.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true }); };
  }, []);
  return createPortal(<dialog ref={dialog} className="drawing-lightbox" aria-label={`查看图纸 ${image.title}`} onKeyDown={event => event.stopPropagation()} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="drawing-lightbox-content">
      <header><strong>{image.title}</strong><div className="preview-actions"><button type="button" aria-label="缩小图纸" onClick={() => setZoom(zoom - .25)}><ZoomOut size={18} /></button><button type="button" className="preview-zoom-value" title="恢复100%缩放" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button><button type="button" aria-label="放大图纸" onClick={() => setZoom(zoom + .25)}><ZoomIn size={18} /></button><button type="button" aria-label="关闭图纸放大" onClick={onClose} autoFocus><X size={20} /></button></div></header>
      <div ref={canvasRef} className={`drawing-canvas ${dragging ? "is-panning" : ""}`} {...navigation} onMouseDown={event => { if (event.button === 1) event.preventDefault(); }} onAuxClick={event => event.preventDefault()}>
        {failed ? <p role="alert">图纸加载失败或链接已过期，请关闭后重新获取资料。</p> : <div ref={frameRef} className="evidence-image-frame" style={{ width: `${zoom * 100}%` }}><img src={image.url} alt={image.title} draggable={false} onError={() => setFailed(true)} /></div>}
      </div>
      <footer>滚轮缩放 · 按住鼠标中键拖动 · Esc 关闭</footer>
    </section>
  </dialog>, document.body);
}
