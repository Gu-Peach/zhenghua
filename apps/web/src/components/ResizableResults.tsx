import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";

/** Keep the table/preview ratio locally; constrain it to the available workspace. */
export function ResizableResults({ primary, secondary }: { primary: ReactNode; secondary: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; share: number } | null>(null);
  const [width, setWidth] = useState(0);
  const [share, setShare] = useState(50);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const available = Math.max(1, width - 8);
  const minimum = width ? Math.min(50, Math.max(20, 280 / available * 100)) : 50;
  const maximum = 100 - minimum;
  const clamp = (value: number) => Math.max(minimum, Math.min(maximum, value));
  const current = clamp(share);
  function finish(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  return <div ref={container} className={`workbench-results ${secondary ? "with-preview" : ""}`} style={{ "--table-share": `${current}fr`, "--drawing-share": `${100 - current}fr` } as CSSProperties}>
    {primary}
    {secondary ? <><div className="preview-resizer" role="separator" aria-label="调整线表与图纸宽度" aria-orientation="vertical" aria-valuemin={Math.round(minimum)} aria-valuemax={Math.round(maximum)} aria-valuenow={Math.round(current)} aria-valuetext={`线表 ${Math.round(current)}%，图纸 ${Math.round(100 - current)}%`} tabIndex={0} title="拖动调整宽度，双击恢复；方向键微调"
      onPointerDown={event => {
        if (event.button !== 0 || !event.isPrimary) return;
        event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { id: event.pointerId, x: event.clientX, share: current };
      }}
      onPointerMove={event => {
        const start = drag.current;
        if (start?.id === event.pointerId) setShare(clamp(start.share + (event.clientX - start.x) / available * 100));
      }} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={() => { drag.current = null; }} onDoubleClick={() => setShare(50)}
      onKeyDown={event => {
        const next = { ArrowLeft: current - 2, ArrowRight: current + 2, Home: minimum, End: maximum }[event.key];
        if (next !== undefined) { event.preventDefault(); setShare(clamp(next)); }
      }} />{secondary}</> : null}
  </div>;
}
