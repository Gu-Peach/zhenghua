import { Loader2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

interface EditableNameProps {
  value: string;
  label: string;
  className?: string;
  to?: string;
  current?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
  onActivate?: () => void;
  onSave?: (name: string) => Promise<void>;
}

export function EditableName({ value, label, className = "", to, current, leading, trailing, onActivate, onSave }: EditableNameProps) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false); const cancelled = useRef(false);
  const pendingNavigation = useRef<ReturnType<typeof setTimeout> | null>(null);
  const input = useRef<HTMLInputElement>(null); const errorId = useId();
  useEffect(() => () => { if (pendingNavigation.current) clearTimeout(pendingNavigation.current); }, []);

  function begin() {
    if (!onSave || lock.current) return;
    if (pendingNavigation.current) clearTimeout(pendingNavigation.current);
    cancelled.current = false; setDraft(value); setError(""); setEditing(true);
  }
  function cancel() { if (lock.current) return; cancelled.current = true; setEditing(false); setError(""); }
  async function save() {
    if (!onSave || lock.current || cancelled.current) return;
    const name = draft.trim();
    if (!name) { setError("项目名称不能为空"); return; }
    if (name === value) { setEditing(false); setError(""); return; }
    lock.current = true; setSaving(true); setError("");
    try { await onSave(name); setEditing(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "名称保存失败，请重试"); requestAnimationFrame(() => input.current?.focus()); }
    finally { lock.current = false; setSaving(false); }
  }
  function activate(event: MouseEvent<HTMLElement>) {
    if (!to) { if (event.detail === 0) begin(); return; }
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    if (!onSave || event.detail === 0) { onActivate?.(); return; }
    // Allow a double-click on an inactive project without navigating/unmounting on its first click.
    event.preventDefault();
    if (pendingNavigation.current) clearTimeout(pendingNavigation.current);
    if (event.detail === 1) pendingNavigation.current = setTimeout(() => { onActivate?.(); navigate(to); }, 240);
  }
  const content = <>{leading}<strong className="inline-name-value">{value}</strong>{trailing}</>;
  if (editing) return <span className={`inline-name inline-name-editor ${className}`}>
    {leading}<input ref={input} aria-label={label} value={draft} maxLength={200} autoFocus disabled={saving} aria-invalid={!!error} aria-describedby={error ? errorId : undefined} title="Enter 保存，Esc 取消，失焦保存" onFocus={event => event.currentTarget.select()} onChange={event => { setDraft(event.target.value); setError(""); }} onBlur={() => { if (!error) void save(); }} onClick={event => event.stopPropagation()} onKeyDown={event => { if (event.nativeEvent.isComposing) return; if (event.key === "Enter") { event.preventDefault(); void save(); } if (event.key === "Escape") { event.preventDefault(); cancel(); } }} />
    {saving ? <Loader2 size={13} className="spin" aria-label="正在保存名称" /> : null}
    {error ? <span id={errorId} role="alert" className="inline-name-error">{error}</span> : null}
  </span>;
  const props = { className: `inline-name ${className}`, title: onSave ? `${value}（双击或按 F2 修改）` : value, onDoubleClick: (event: MouseEvent<HTMLElement>) => { if (onSave) { event.preventDefault(); event.stopPropagation(); begin(); } }, onClick: activate };
  if (to) return <Link {...props} to={to} aria-label={value} aria-current={current ? "page" : undefined} onKeyDown={event => { if (event.key === "F2" && onSave) { event.preventDefault(); begin(); } }}>{content}</Link>;
  return <button {...props} type="button" aria-label={onSave ? `修改${label} ${value}` : value} disabled={!onSave} onKeyDown={event => { if (event.key === "F2") { event.preventDefault(); begin(); } }}>{content}</button>;
}
