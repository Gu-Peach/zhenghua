import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type RefObject } from "react";

export function useDraggablePanel(panel: RefObject<HTMLElement | null>) {
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const active = useRef<{ pointer: number; x: number; y: number; left: number; top: number } | null>(null);
  const clamp = (left: number, top: number) => {
    const box = panel.current?.getBoundingClientRect();
    return { left: Math.max(8, Math.min(left, innerWidth - (box?.width ?? 0) - 8)), top: Math.max(8, Math.min(top, innerHeight - (box?.height ?? 0) - 8)) };
  };
  useEffect(() => {
    const resize = () => setPosition(value => {
      if (!value) return value;
      const box = panel.current?.getBoundingClientRect();
      return { left: Math.max(8, Math.min(value.left, innerWidth - (box?.width ?? 0) - 8)), top: Math.max(8, Math.min(value.top, innerHeight - (box?.height ?? 0) - 8)) };
    });
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [panel]);
  const stop = (event: PointerEvent<HTMLElement>) => {
    if (active.current?.pointer !== event.pointerId) return;
    active.current = null; setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return { dragging, setPosition, style: position ? { ...position, right: "auto", bottom: "auto" } as CSSProperties : undefined, headerProps: {
    tabIndex: 0,
    title: "拖动标题栏移动窗口，也可聚焦后用方向键移动，Home恢复位置",
    "aria-label": "来源解释窗口标题栏",
    onPointerDown: (event: PointerEvent<HTMLElement>) => {
      if (event.button !== 0 || (event.target as Element).closest("button,a,input,select,textarea")) return;
      const box = panel.current?.getBoundingClientRect();
      if (!box) return;
      event.preventDefault();
      active.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, left: box.left, top: box.top };
      event.currentTarget.setPointerCapture(event.pointerId); setDragging(true);
    },
    onPointerMove: (event: PointerEvent<HTMLElement>) => {
      const start = active.current;
      if (!start || start.pointer !== event.pointerId) return;
      if (!(event.buttons & 1)) { stop(event); return; }
      setPosition(clamp(start.left + event.clientX - start.x, start.top + event.clientY - start.y));
    },
    onPointerUp: stop, onPointerCancel: stop, onLostPointerCapture: stop,
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
      if (event.target !== event.currentTarget) return;
      const box = panel.current?.getBoundingClientRect();
      if (!box) return;
      if (event.key === "Home") { event.preventDefault(); setPosition(null); }
      const offset: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
      if (offset[event.key]) { event.preventDefault(); const [x, y] = offset[event.key]; setPosition(clamp(box.left + x, box.top + y)); }
    },
  } };
}
