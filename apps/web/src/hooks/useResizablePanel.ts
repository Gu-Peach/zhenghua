import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type RefObject } from "react";

export function useResizablePanel(panel: RefObject<HTMLElement | null>, anchor: (position: { left: number; top: number } | null) => void) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const active = useRef<{ pointer: number; x: number; y: number; width: number; height: number } | null>(null);
  function fit(width: number, height: number) {
    const box = panel.current?.getBoundingClientRect();
    const maxWidth = Math.max(0, innerWidth - 8 - (box?.left ?? 8));
    const maxHeight = Math.max(0, innerHeight - 8 - (box?.top ?? 8));
    setSize({ width: Math.min(maxWidth, Math.max(340, width)), height: Math.min(maxHeight, Math.max(320, height)) });
  }
  useEffect(() => {
    const resize = () => setSize(current => current ? { width: Math.min(current.width, innerWidth - 16), height: Math.min(current.height, innerHeight - 16) } : null);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  function stop(event: PointerEvent<HTMLElement>) {
    if (active.current?.pointer !== event.pointerId) return;
    active.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  return { style: size ?? {}, handleProps: {
    "aria-label": "缩放来源解释窗口", title: "拖动调整窗口大小；方向键调整，Home恢复大小",
    onPointerDown(event: PointerEvent<HTMLElement>) {
      if (event.button !== 0) return;
      const box = panel.current?.getBoundingClientRect(); if (!box) return;
      event.preventDefault(); event.stopPropagation();
      // Anchor the top-left before changing dimensions of a right/bottom aligned panel.
      anchor({ left: box.left, top: box.top });
      active.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, width: box.width, height: box.height };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerMove(event: PointerEvent<HTMLElement>) {
      const start = active.current; if (!start || start.pointer !== event.pointerId) return;
      if (!(event.buttons & 1)) { stop(event); return; }
      fit(start.width + event.clientX - start.x, start.height + event.clientY - start.y);
    },
    onPointerUp: stop, onPointerCancel: stop, onLostPointerCapture: stop,
    onKeyDown(event: KeyboardEvent<HTMLElement>) {
      const box = panel.current?.getBoundingClientRect(); if (!box) return;
      if (event.key === "Home") { event.preventDefault(); setSize(null); anchor(null); return; }
      const delta: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
      const offset = delta[event.key]; if (!offset) return;
      event.preventDefault(); anchor({ left: box.left, top: box.top }); fit(box.width + offset[0], box.height + offset[1]);
    },
  } };
}
