import { forwardRef, useImperativeHandle, useRef, useState, useEffect } from "react";
import { ImagePlus, X } from "lucide-react";
import { rescans, type RescanPageChoice } from "@/apis/rescan";

export interface RescanAttachmentHandle { addFiles: (files: File[]) => void }
export const RescanAttachments = forwardRef<RescanAttachmentHandle, { project: string; conversation: string; pages: RescanPageChoice[]; sourcePdf?: number; targetPdf?: number; disabled: boolean; onChange: (ids: string[]) => void; onBusy: (busy: boolean) => void }>(function RescanAttachments({ project, conversation, pages, sourcePdf, targetPdf, disabled, onChange, onBusy }, ref) {
  const [role, setRole] = useState<"source" | "target">("source"); const [pdf, setPdf] = useState(sourcePdf ?? 0);
  const [items, setItems] = useState<Array<{ id: string; url: string; title: string }>>([]); const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null); const uploading = useRef(false); const urls = useRef<string[]>([]); const alive = useRef(true);
  useEffect(() => { alive.current = true; const allocated = urls.current; return () => { alive.current = false; allocated.forEach(URL.revokeObjectURL); }; }, []);
  async function addFiles(files: File[]) {
    if (disabled || uploading.current || !files.length) return;
    if (!pdf) { setError("请先选择截图所属的原页或关联图纸"); return; }
    if (items.length + files.length > 6) { setError("每轮最多使用6张细节图"); return; }
    uploading.current = true; onBusy(true); setError(""); let next = [...items];
    try {
      for (const file of files) {
        const asset = await rescans.upload(project, conversation, file, pdf, role);
        if (!alive.current) return;
        const url = URL.createObjectURL(file); urls.current.push(url);
        next = [...next.filter(item => item.id !== asset.id), { id: asset.id, url, title: `PDF ${pdf} · ${role === "source" ? "原页" : "关联页"}细节` }];
        setItems(next); onChange(next.map(item => item.id));
      }
    } catch (reason) { if (alive.current) setError(String(reason)); }
    finally { uploading.current = false; if (alive.current) onBusy(false); }
  }
  useImperativeHandle(ref, () => ({ addFiles: files => { void addFiles(files); } }));
  return <section className="rescan-attachments" aria-label="重扫细节图" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void addFiles(Array.from(event.dataTransfer.files)); }}>
    <div><button type="button" disabled={disabled} title="可选择文件、拖拽图片，或在输入框粘贴截图" onClick={() => input.current?.click()}><ImagePlus size={15} />添加细节图</button>
      <label><span className="visually-hidden">截图用途</span><select aria-label="截图用途" value={role} disabled={disabled} onChange={event => { const value = event.target.value as "source" | "target"; setRole(value); setPdf((value === "source" ? sourcePdf : targetPdf) ?? 0); }}><option value="source">原页细节</option><option value="target">关联页细节</option></select></label>
      <label><span className="visually-hidden">截图所属图纸</span><select aria-label="截图所属图纸" value={pdf} disabled={disabled} onChange={event => setPdf(Number(event.target.value))}><option value={0}>选择所属图纸</option>{pages.map(page => <option key={page.pdf} value={page.pdf}>{page.title} · PDF {page.pdf}</option>)}</select></label>
    </div>
    <input ref={input} type="file" className="visually-hidden" aria-label="上传重扫截图" accept="image/png,image/jpeg,image/webp" multiple onChange={event => { void addFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    {items.length ? <><p>截图辅助辨认；重扫仍会读取原图和关联图定位。可拖拽或粘贴图片。</p><ul>{items.map(item => <li key={item.id}><img src={item.url} alt={item.title} /><span>{item.title}</span><button type="button" disabled={disabled} aria-label={`移除此轮${item.title}`} onClick={() => { const next = items.filter(value => value.id !== item.id); setItems(next); onChange(next.map(value => value.id)); URL.revokeObjectURL(item.url); }}><X size={14} /></button></li>)}</ul></> : null}
    {error && <p role="alert">{error}</p>}
  </section>;
});
