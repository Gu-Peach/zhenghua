import { useEffect, useRef, useState } from "react";

/** Pace already received text independently of network chunks and completion events. */
export function useTypewriterText(target: string, halted = false) {
  const [visible, setVisible] = useState("");
  const [immediate, setImmediate] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const shown = useRef("");
  const clock = useRef({ last: 0, credit: 0 });

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => { setReducedMotion(media.matches); if (media.matches) setImmediate(true); };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);

  useEffect(() => {
    if (halted || immediate || reducedMotion) return;
    // Code points keep emoji/surrogate pairs intact. A replaced answer starts a fresh buffer.
    const characters = Array.from(target);
    let count = target.startsWith(shown.current) ? Array.from(shown.current).length : 0;
    let frame: number;
    const tick = (now: number) => {
      const elapsed = clock.current.last ? Math.min(64, now - clock.current.last) : 16;
      clock.current.last = now;
      const remaining = characters.length - count;
      const rate = Math.min(300, 75 + Math.max(0, remaining - 180) / 8);
      clock.current.credit += elapsed * rate / 1000;
      const advance = Math.floor(clock.current.credit);
      if (advance > 0) {
        clock.current.credit -= advance;
        count = Math.min(characters.length, count + advance);
        const next = characters.slice(0, count).join("");
        shown.current = next;
        setVisible(next);
      }
      if (count < characters.length) frame = requestAnimationFrame(tick);
      else clock.current = { last: 0, credit: 0 };
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, halted, immediate, reducedMotion]);

  const text = immediate || reducedMotion ? target : visible;
  return { text, typing: !halted && text !== target, finish: () => setImmediate(true) };
}
