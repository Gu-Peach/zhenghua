import { ChevronRight, FileImage, Folder, FolderOpen, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "@/apis/client";
import { projectApi } from "@/apis/projects";
import type { Drawing, ProjectDetail } from "@/apis/types";
import { DrawingPreview } from "./DrawingPreview";

export function DrawingDirectory({ project }: { project: ProjectDetail }) {
  return (
    <section className="drawing-library" aria-label="图纸目录">
      <header><h2>图纸库</h2><p>展开项目和工作区，查看图纸图片</p></header>
      <details className="drawing-folder library-project">
        <summary><ChevronRight className="directory-chevron" size={16} /><FolderOpen size={20} /><strong>{project.name}</strong><span>{project.drawingCount} 张图纸</span></summary>
        <div className="directory-children">
          {project.workspaces.map(workspace => (
            <details className="drawing-folder library-workspace" key={workspace.id}>
              <summary><ChevronRight className="directory-chevron" size={16} /><Folder size={18} /><strong>{workspace.code}</strong>{workspace.name !== workspace.code ? <small>{workspace.name}</small> : null}<span>{workspace.drawings.length} 张图纸</span></summary>
              <div className="directory-children">
                {workspace.drawings.map(drawing => <DrawingFile key={drawing.id} project={project} drawing={drawing} />)}
                {!workspace.drawings.length ? <p className="directory-empty">该工作区暂无图纸。</p> : null}
              </div>
            </details>
          ))}
          {!project.workspaces.length ? <p className="directory-empty" role="status">暂无图纸，页面分类完成后会显示工作区和图片。</p> : null}
        </div>
      </details>
    </section>
  );
}

function DrawingFile({ project, drawing }: { project: ProjectDetail; drawing: Drawing }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <details className="drawing-file" onToggle={event => { if (event.target === event.currentTarget) setExpanded(event.currentTarget.open); }}>
      <summary><ChevronRight className="directory-chevron" size={16} /><FileImage size={18} /><strong>{drawing.drawingPage}</strong><span>PDF 第 {drawing.pdfPage} 页</span></summary>
      {expanded ? <LibraryDrawingPreview project={project} drawingId={drawing.id} /> : null}
    </details>
  );
}

function LibraryDrawingPreview({ project, drawingId }: { project: ProjectDetail; drawingId: string }) {
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    projectApi.drawing(drawingId).then(value => {
      if (active) setDrawing(value);
    }).catch(reason => {
      if (active) setError(reason instanceof ApiError && reason.status === 403 ? "无权访问此图纸。" : `图纸读取失败：${String(reason)}`);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [drawingId, attempt]);
  return (
    <div className="directory-preview">
      {loading ? <p className="directory-loading" role="status"><Loader2 size={16} className="spin" />正在加载图纸…</p> : error ? <div className="directory-error" role="alert"><p>{error}</p><button type="button" onClick={() => { setLoading(true); setError(""); setAttempt(n => n + 1); }}>重试读取图纸</button></div> : <DrawingPreview project={project} drawing={drawing} />}
    </div>
  );
}
