import { X } from "lucide-react";
import { useState } from "react";

export function ExtractionFailureNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return <div className="inline-error extraction-failure-notice" role="alert">
    <span>{message}</span>
    <button type="button" onClick={onRetry}>重试提取</button>
    <button type="button" className="extraction-notice-close" aria-label="关闭提取提示" title="关闭提取提示" onClick={() => setDismissed(true)}><X size={18} /></button>
  </div>;
}
