import { forwardRef, useImperativeHandle, useRef, useState, useEffect } from "react";
import { X } from "lucide-react";
import { rescans } from "@/apis/rescan";
import type { ExplainAttachment } from "@/hooks/useExplainConversation";

export interface RescanAttachmentHandle {
  open: () => void;
  addFiles: (files: File[]) => void;
  submit: () => Promise<ExplainAttachment[] | null>;
}
interface PendingImage { key: string; file: File; url: string; assetId?: string }

export const RescanAttachments = forwardRef<RescanAttachmentHandle, {
  project: string; conversation: string; sourcePdf?: number; disabled: boolean;
  onCount: (count: number) => void; onBusy: (busy: boolean) => void;
}>(function RescanAttachments({ project, conversation, sourcePdf, disabled, onCount, onBusy }, ref) {
  const [items, setItems] = useState<PendingImage[]>([]);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const pending = useRef<PendingImage[]>([]);
  const uploading = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; pending.current.forEach(item => URL.revokeObjectURL(item.url)); };
  }, []);
  function update(next: PendingImage[]) { pending.current = next; setItems(next); onCount(next.length); }
  function addFiles(files: File[]) {
    if (disabled || uploading.current || !files.length) return;
    if (pending.current.length + files.length > 6) { setError("每轮最多上传6张图片"); return; }
    if (files.some(file => !["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 8_000_000)) {
      setError("请上传8MB以内的PNG、JPEG或WebP图片"); return;
    }
    setError("");
    update([...pending.current, ...files.map(file => ({ key: crypto.randomUUID(), file, url: URL.createObjectURL(file) }))]);
  }
  async function submit(): Promise<ExplainAttachment[] | null> {
    if (uploading.current) return null;
    if (!pending.current.length) return [];
    if (disabled) { setError("当前暂不能上传图片，请稍后发送。"); return null; }
    if (!sourcePdf) { setError("请先在项目目录选择一张图纸，再上传图片。"); return null; }
    uploading.current = true; onBusy(true); setError("");
    try {
      for (const item of pending.current) {
        if (!item.assetId) item.assetId = (await rescans.upload(project, conversation, item.file, sourcePdf, "source")).id;
        if (!alive.current) return null;
      }
      const submitted = pending.current.map(item => ({ id: item.assetId!, url: item.url, name: item.file.name }));
      // The conversation owns sent previews; only unsent images are released here.
      update([]);
      return submitted;
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "图片上传失败，请重试。"); return null; }
    finally { uploading.current = false; if (alive.current) onBusy(false); }
  }
  useImperativeHandle(ref, () => ({ open: () => input.current?.click(), addFiles, submit }));
  return <div className="explain-pending-images">
    <input ref={input} type="file" className="visually-hidden" aria-label="上传重扫截图" accept="image/png,image/jpeg,image/webp" multiple onChange={event => { addFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    {items.length ? <ul aria-label="待发送图片">{items.map(item => <li key={item.key}><img src={item.url} alt={item.file.name} /><span title={item.file.name}>{item.file.name}</span><button type="button" disabled={disabled} aria-label={`移除图片 ${item.file.name}`} onClick={() => { setError(""); URL.revokeObjectURL(item.url); update(pending.current.filter(value => value.key !== item.key)); }}><X size={14} /></button></li>)}</ul> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
});
