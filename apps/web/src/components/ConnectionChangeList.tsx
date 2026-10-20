import { ChevronRight } from "lucide-react";
import { editFieldNames } from "@/apis/explain-edits";

type ChangeRow = {
  connection_id: string;
  principle_number?: string | null;
  source_drawing_page?: string | null;
  workspace_code?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  action?: string;
};

function cell(value: unknown): string {
  return value == null ? "空值" : typeof value === "object" ? JSON.stringify(value) : typeof value === "boolean" ? value ? "是" : "否" : String(value);
}

/** Keep every field reviewable without adding a vertical scroll area per record. */
export function ConnectionChangeList({ changes, removal = false }: { changes: ChangeRow[]; removal?: boolean }) {
  return <div className="connection-change-list">{changes.map(change => {
    const fields = Object.keys(removal ? change.before ?? {} : change.after ?? {});
    return <details className="connection-change" key={change.connection_id}>
      <summary><ChevronRight size={15} aria-hidden="true" /><span><strong>{change.principle_number || "连接记录"}</strong><small>{[change.workspace_code, change.source_drawing_page].filter(Boolean).join(" · ") || "所选范围"}</small></span><span className="change-count">{removal ? "删除记录" : change.action === "insert" ? "新增记录" : `${fields.length} 个字段`}</span></summary>
      <div className="connection-fields"><table><caption className="visually-hidden">{change.principle_number || "连接记录"}字段对照</caption><thead><tr><th>字段</th><th>原值</th><th>新值</th></tr></thead><tbody>{fields.map(field => <tr key={field}><th scope="row">{editFieldNames[field] ?? field}</th><td>{change.action === "insert" ? "原记录不存在" : cell(change.before?.[field])}</td><td>{removal ? "删除" : cell(change.after?.[field])}</td></tr>)}</tbody></table></div>
    </details>;
  })}</div>;
}
