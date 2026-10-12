import { MessageSquare, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { AiPanel, type AiPanelProps } from "./AiPanel";

export function FloatingAgentPanel({ initiallyOpen = false, ...props }: AiPanelProps & { initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  const [seenCount, setSeenCount] = useState(props.events.length);
  const launcher = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const panelId = useId();
  const unread = open ? 0 : Math.max(0, props.events.length - seenCount);
  const pending = props.events.some(event => event.status === "pending");

  useEffect(() => { if (open) panel.current?.focus({ preventScroll: true }); }, [open]);
  function close() {
    setSeenCount(props.events.length);
    setOpen(false);
    launcher.current?.focus({ preventScroll: true });
  }

  return (
    <>
      <section ref={panel} id={panelId} className="floating-agent-panel" hidden={!open} role="dialog" aria-modal="false" aria-label="AI 助手" tabIndex={-1} onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); close(); } }}>
        <AiPanel {...props} isVisible={open} onClose={close} />
      </section>
      <button ref={launcher} type="button" className={`agent-launcher ${props.isRunning ? "is-running" : ""}`} aria-controls={panelId} aria-expanded={open} aria-label={open ? "关闭 AI 聊天面板" : "打开 AI 聊天面板"} title={open ? "关闭 AI 聊天面板" : "打开 AI 聊天面板"} onClick={() => { if (open) close(); else { setSeenCount(props.events.length); setOpen(true); } }}>
        {open ? <X size={23} /> : <MessageSquare size={23} />}
        {!open && (props.isRunning || pending || unread > 0) ? <span className="agent-launcher-badge" aria-label={props.isRunning ? "任务执行中" : pending ? "有待确认消息" : `${unread} 条新消息`}>{props.isRunning ? <span className="launcher-running-dot" /> : unread > 99 ? "99+" : unread || "!"}</span> : null}
      </button>
    </>
  );
}
