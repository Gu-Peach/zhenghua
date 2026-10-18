import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from "react";

/** Scroll-based navigation keeps the image and normalized evidence markers together. */
export function useDrawingNavigation(enabled = true) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoomValue] = useState(1);
  const zoomRef = useRef(1);
  const pending = useRef<{ left: number; top: number } | null>(null);
  const drag = useRef<{ pointer: number; x: number; y: number; left: number; top: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function setZoom(value: number, clientX?: number, clientY?: number) {
    const next = Math.max(.25, Math.min(4, value));
    const canvas = canvasRef.current, frame = frameRef.current;
    if (canvas && frame) {
      const bounds = frame.getBoundingClientRect(), viewport = canvas.getBoundingClientRect();
      const x = clientX ?? viewport.left + canvas.clientWidth / 2;
      const y = clientY ?? viewport.top + canvas.clientHeight / 2;
      const ratio = next / zoomRef.current;
      pending.current = { left: canvas.scrollLeft + (x - bounds.left) * (ratio - 1), top: canvas.scrollTop + (y - bounds.top) * (ratio - 1) };
    }
    zoomRef.current = next; setZoomValue(next);
  }
  const changeZoom = useRef(setZoom);
  useLayoutEffect(() => { changeZoom.current = setZoom; });
  useLayoutEffect(() => {
    if (pending.current && canvasRef.current) {
      canvasRef.current.scrollLeft = pending.current.left;
      canvasRef.current.scrollTop = pending.current.top;
      pending.current = null;
    }
  }, [zoom]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !enabled) return;
    const wheel = (event: WheelEvent) => {
      if (!frameRef.current || !event.deltaY) return;
      event.preventDefault();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1);
      changeZoom.current(zoomRef.current * Math.exp(-Math.max(-300, Math.min(300, delta)) * .002), event.clientX, event.clientY);
    };
    canvas.addEventListener("wheel", wheel, { passive: false });
    return () => canvas.removeEventListener("wheel", wheel);
  }, [enabled]);

  function stop(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.pointer !== event.pointerId) return;
    drag.current = null; setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  return { canvasRef, frameRef, zoom, setZoom, dragging, navigation: {
    onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
      if (!enabled || event.button !== 1 || !frameRef.current) return;
      event.preventDefault();
      const canvas = event.currentTarget;
      drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, left: canvas.scrollLeft, top: canvas.scrollTop };
      canvas.setPointerCapture(event.pointerId); setDragging(true);
    },
    onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
      const active = drag.current;
      if (!active || active.pointer !== event.pointerId) return;
      if (!(event.buttons & 4)) { stop(event); return; }
      event.preventDefault();
      event.currentTarget.scrollLeft = active.left - (event.clientX - active.x);
      event.currentTarget.scrollTop = active.top - (event.clientY - active.y);
    },
    onPointerUp: stop, onPointerCancel: stop, onLostPointerCapture: stop,
  } };
}
