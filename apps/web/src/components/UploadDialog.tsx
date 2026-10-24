import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { AlertCircle, ArrowRight, Check, ChevronRight, FileText, Layers3, Loader2, RefreshCw, Upload, X } from "lucide-react";
import { projectApi, type ProfileOption } from "@/apis/projects";
import "@/assets/upload-dialog.css";

export function UploadDialog({ file, onClose, onSaved }: { file: File; onClose: () => void; onSaved: (id: string) => void }) {
  const [options, setOptions] = useState<ProfileOption[] | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const submission = useRef<{ key: string; profile: string } | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const tooLarge = file.size > 200 * 1024 * 1024;
  const fileSize = file.size < 1024 * 1024 ? `${Math.ceil(file.size / 1024)} KB` : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  const selectedRule = options?.find(option => option.profile_key === selected);

  useEffect(() => {
    const previousFocus = document.activeElement;
    closeButton.current?.focus();
    return () => { if (previousFocus instanceof HTMLElement) previousFocus.focus(); };
  }, []);

  useEffect(() => {
    let active = true;
    projectApi.publishedProfiles()
      .then(rows => { if (active) { setOptions(rows); setError(""); } })
      .catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [retry]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving || !selected || tooLarge) return;
    setSaving(true);
    setError("");
    if (submission.current?.profile !== selected) submission.current = { key: crypto.randomUUID(), profile: selected };
    try { const response = await projectApi.upload(file, selected, submission.current.key); onSaved(response.project_id); }
    catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && !saving) { event.stopPropagation(); onClose(); }
    if (event.key !== "Tab") return;
    const focusable = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled):checked, [tabindex="0"]');
    const first = focusable?.[0];
    const last = focusable?.[focusable.length - 1];
    if (!first) { event.preventDefault(); dialog.current?.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  return <div className="modal-backdrop upload-backdrop">
    <section ref={dialog} className="upload-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-heading" aria-describedby="upload-description" tabIndex={-1} onKeyDown={handleKeyDown}>
      <header className="upload-dialog-header">
        <span className="upload-heading-icon" aria-hidden="true"><Upload size={22} /></span>
        <div><h2 id="upload-heading">保存 PDF</h2><p>选择图纸规则，开始提取线表</p></div>
        <button ref={closeButton} type="button" className="icon-button" disabled={saving} onClick={onClose} aria-label="关闭上传"><X size={19} /></button>
      </header>

      <form className="upload-dialog-form" onSubmit={submit} aria-busy={saving}>
        <div className="upload-dialog-content">
          <div className={`upload-file-card${tooLarge ? " upload-file-invalid" : ""}`}>
            <span className="upload-file-icon" aria-hidden="true"><FileText size={26} /><span>PDF</span></span>
            <div className="upload-file-copy"><strong title={file.name}>{file.name}</strong><span>{fileSize}<span aria-hidden="true">·</span>PDF 图纸</span></div>
            <span className="upload-file-state">{saving ? "正在保存" : "待上传"}</span>
          </div>
          {tooLarge ? <p className="upload-feedback upload-error" role="alert"><AlertCircle size={16} />文件超过200MB限制，请选择较小的 PDF。</p> : null}

          <fieldset className="upload-rules" disabled={saving}>
            <legend><Layers3 size={17} aria-hidden="true" />图纸规则<span className="upload-required">必选</span></legend>
            <p className="upload-rules-hint">选择与图纸格式对应的规则，用于识别端子和连接关系。</p>
            {options === null && !error ? <div className="upload-rule-placeholder" role="status"><Loader2 size={19} className="spin" aria-hidden="true" /><span>正在读取规则…</span></div>
              : options?.length === 0 ? <div className="upload-rule-placeholder"><Layers3 size={22} aria-hidden="true" /><strong>暂无可用规则</strong><span>没有已上传的规则包，请先在规则配置智能体中发布规则。</span></div>
                : <div className="upload-rule-options">
                  {options?.map(option => <label key={option.profile_key} className={`upload-rule-card${selected === option.profile_key ? " is-selected" : ""}`}>
                    <input type="radio" name="upload-profile" value={option.profile_key} checked={selected === option.profile_key} onChange={() => setSelected(option.profile_key)} required />
                    <span className="upload-rule-icon" aria-hidden="true"><Layers3 size={19} /></span>
                    <span className="upload-rule-copy"><strong>{option.display_name}</strong><span>版本 {option.profile_version}</span></span>
                    <span className="upload-rule-indicator" aria-hidden="true">{selected === option.profile_key ? <Check size={12} /> : null}</span>
                  </label>)}
                </div>}
          </fieldset>

          {error ? <div className="upload-feedback upload-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><div><p>{error}</p>{options === null ? <button type="button" className="upload-retry" onClick={() => { setError(""); setRetry(n => n + 1); }}><RefreshCw size={14} />重试读取规则</button> : null}</div></div> : null}

          <div className="upload-next">
            <ol aria-label="保存后的处理流程"><li>拆分图纸</li><li><ChevronRight size={13} aria-hidden="true" />提取连接</li><li><ChevronRight size={13} aria-hidden="true" />生成线表</li></ol>
            <p id="upload-description">文件保存成功后将自动拆页并提取线表，处理结果逐步显示。</p>
          </div>
        </div>

        <footer className="upload-dialog-footer">
          <p className={selectedRule ? "upload-selection" : "upload-selection is-pending"}>{selectedRule ? <><Check size={15} aria-hidden="true" /><span>已选择：{selectedRule.display_name}</span></> : "请选择一项图纸规则"}</p>
          <div><button type="button" className="secondary-button" disabled={saving} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={saving || !selected || tooLarge}>{saving ? <><Loader2 size={16} className="spin" aria-hidden="true" />正在保存 PDF…</> : <>保存到项目<ArrowRight size={16} aria-hidden="true" /></>}</button></div>
        </footer>
      </form>
    </section>
  </div>;
}
