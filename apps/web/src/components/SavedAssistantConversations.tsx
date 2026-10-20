import { Check, ChevronDown, Loader2, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { AssistantConversation } from "@/apis/assistant";

export function SavedAssistantConversations({ items, selected, disabled, deleting, onSelect, onDelete }: {
  items: AssistantConversation[];
  selected: AssistantConversation | null;
  disabled: boolean;
  deleting: string | null;
  onSelect: (id: string) => void;
  onDelete: (item: AssistantConversation) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null); const trigger = useRef<HTMLButtonElement>(null); const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return <div ref={root} className="assistant-history" onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false); }} onKeyDown={event => {
    if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    <button ref={trigger} type="button" className="assistant-history-trigger" aria-label="助手已保存会话" aria-expanded={open} aria-controls={`${id}-history`} disabled={disabled || !!deleting} title={selected?.title ?? "选择历史对话"} onClick={() => setOpen(value => !value)} onKeyDown={event => {
      if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); requestAnimationFrame(() => panel.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus()); }
    }}><span>{selected?.title ?? "新对话"}</span><ChevronDown size={16} aria-hidden="true" /></button>
    {open && <div ref={panel} id={`${id}-history`} className="assistant-history-panel" role="region" aria-label="助手历史对话">
      <ul><li><button type="button" className="assistant-history-open" disabled={disabled || !!deleting} onClick={() => { setOpen(false); onSelect(""); }}>新对话</button></li>
        {items.map(item => <li key={item.id}>
          <button type="button" className="assistant-history-open" disabled={disabled || !!deleting} aria-current={selected?.id === item.id ? "true" : undefined} aria-label={`打开助手对话 ${item.title}`} title={item.title} onClick={() => { setOpen(false); onSelect(item.id); }}><span>{item.title}</span>{selected?.id === item.id && <Check size={15} aria-hidden="true" />}</button>
          <button type="button" className="icon-button quiet-danger" disabled={disabled || !!deleting} aria-label={`删除助手对话 ${item.title}`} title={`永久删除对话：${item.title}`} onClick={async () => { await onDelete(item); requestAnimationFrame(() => trigger.current?.focus()); }}>{deleting === item.id ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <X size={16} aria-hidden="true" />}</button>
        </li>)}
      </ul>{!items.length && <p>暂无历史对话</p>}
    </div>}
  </div>;
}
