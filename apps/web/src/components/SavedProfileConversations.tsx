import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Trash2 } from "lucide-react";
import type { ProfileDraft } from "@/apis/profile";

type Props = {
  drafts: ProfileDraft[];
  selected: ProfileDraft | null;
  disabled: boolean;
  loading: boolean;
  onSelect: (id: string) => void;
  onDelete: (draft: ProfileDraft) => Promise<void>;
};

export function SavedProfileConversations({ drafts, selected, disabled, loading, onSelect, onDelete }: Props) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const name = (draft: ProfileDraft) => `${draft.template?.display_name ?? draft.key} · 修订${draft.revision}`;

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  return <div ref={container} className="profile-saved-conversations" onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (event.key === "Escape" && open) { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
  }}>
    <label htmlFor={`${id}-trigger`}>继续已有草稿</label>
    <button ref={trigger} id={`${id}-trigger`} type="button" className="profile-saved-trigger" aria-label="继续已有草稿" aria-expanded={open} aria-controls={`${id}-panel`} disabled={disabled || loading} onClick={() => setOpen(!open)} onKeyDown={event => {
      if (event.key === "ArrowDown") {
        event.preventDefault(); setOpen(true);
        requestAnimationFrame(() => panel.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus());
      }
    }}>
      <span>{loading ? "正在读取草稿…" : selected ? name(selected) : "选择已保存的规则对话"}</span><ChevronDown size={16} aria-hidden="true" />
    </button>
    {open && <div ref={panel} id={`${id}-panel`} className="profile-saved-panel" role="region" aria-label="已保存的规则对话">
      {drafts.length ? <ul>{drafts.map(draft => <li key={draft.draft_id}>
        <button type="button" className="profile-saved-open" disabled={disabled} aria-current={selected?.draft_id === draft.draft_id ? "true" : undefined} aria-label={`打开会话 ${name(draft)}`} title={name(draft)} onClick={() => { setOpen(false); onSelect(draft.draft_id); }}>
          <span>{name(draft)}</span>{selected?.draft_id === draft.draft_id && <Check size={15} aria-hidden="true" />}
        </button>
        <button type="button" className="profile-icon-button profile-delete-conversation" disabled={disabled} aria-label={`删除会话 ${name(draft)}`} title={`删除会话 ${name(draft)}`} onClick={async () => { await onDelete(draft); requestAnimationFrame(() => trigger.current?.focus()); }}><Trash2 size={16} aria-hidden="true" /></button>
      </li>)}</ul> : <p>暂无已保存的规则会话</p>}
    </div>}
  </div>;
}
