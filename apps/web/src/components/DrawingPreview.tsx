import { Crosshair, FileImage, LocateFixed, ZoomIn, ZoomOut } from "lucide-react";
import type { Drawing, ProjectDetail } from "@/apis/types";

export function DrawingPreview({ project, drawing, targetTerminal }: { project: ProjectDetail; drawing: Drawing | null; targetTerminal?: string }) {
  const fallback = project.workspaces.flatMap((workspace) => workspace.drawings).find((item) => item.imageUrl);
  const visible = drawing?.imageUrl ? drawing : drawing ? null : fallback;
  return (
    <section className="drawing-preview">
      <div className="preview-toolbar">
        <div><FileImage size={17} /><span>{drawing ? `${project.name} / 图纸 ${drawing.drawingPage}` : "项目图纸预览"}</span></div>
        <div className="preview-actions"><button type="button" aria-label="缩小" title="缩小"><ZoomOut size={17} /></button><span>适应窗口</span><button type="button" aria-label="放大" title="放大"><ZoomIn size={17} /></button><button type="button" aria-label="定位来源" title="定位来源"><LocateFixed size={17} /></button></div>
      </div>
      <div className="drawing-canvas">
        {visible?.imageUrl ? (
          <div className="drawing-image-frame">
            <img src={visible.imageUrl} alt={`${project.name} 图纸 ${visible.drawingPage}`} className="drawing-image" />
            <span className="evidence-marker marker-start"><Crosshair size={15} />起点 XA:1</span>
            {targetTerminal ? <span className="evidence-marker marker-end"><Crosshair size={15} />终点 {targetTerminal}</span> : null}
          </div>
        ) : drawing ? <div className="drawing-image-frame mock-drawing-frame">
          <div className="mock-drawing-label"><FileImage size={15} /><span>Mock 图纸预览 · {drawing.drawingPage}</span></div>
          <svg viewBox="0 0 1100 650" role="img" aria-label={`模拟图纸 ${drawing.drawingPage}`}>
            <g fill="none" stroke="#9ba6b2" strokeWidth="2"><path d="M120 160H430V310H710V490H940" /><path d="M430 310V440H610" /><path d="M710 490V260H940" /><path d="M120 160V380H260" /></g>
            <g fill="#fff" stroke="#708091" strokeWidth="2"><rect x="92" y="128" width="56" height="64" /><rect x="402" y="282" width="56" height="56" /><rect x="682" y="462" width="56" height="56" /><rect x="910" y="230" width="62" height="60" /></g>
            <g fill="#44566b" fontFamily="Arial, sans-serif" fontSize="18"><text x="95" y="118">+01F12</text><text x="405" y="267">X21</text><text x="684" y="447">{targetTerminal ?? "X3"}</text><text x="910" y="215">{drawing.name}</text><text x="160" y="147">24VDC</text></g>
            <g fill="#fff3dc" stroke="#d99a31" strokeWidth="3"><circle cx="710" cy="490" r="18" /></g>
            <path d="M710 490h-30m30 0v-30" fill="none" stroke="#d99a31" strokeWidth="4" />
          </svg>
          {targetTerminal ? <span className="evidence-marker marker-end mock-target-marker"><Crosshair size={15} />目标端子 {targetTerminal}</span> : null}
          <span className="mock-sheet-watermark">示意数据</span>
        </div> : <div className="preview-empty"><FileImage size={30} /><strong>暂无图纸预览</strong><span>该项目尚未完成拆页。</span></div>}
      </div>
      <div className="preview-footer"><span>PDF 物理页 {drawing?.pdfPage ?? visible?.pdfPage ?? "-"}</span><span>业务页 {drawing?.drawingPage ?? visible?.drawingPage ?? "-"}</span><span>{drawing && !drawing.imageUrl ? "Mock 图纸与索引定位" : targetTerminal ? "跨页目标端子定位" : "来源证据"}</span></div>
    </section>
  );
}
