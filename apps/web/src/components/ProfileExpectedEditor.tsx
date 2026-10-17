import type { Expected, ProfileStage } from "@/apis/profile";

type Part = string | number;
function object(value: unknown): Expected { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Expected : {}; }
function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function text(value: unknown): string { return value == null ? "" : String(value); }
const endpoint = { device: null, name: null, terminal: null, terminal_strip: null };
const labels: Record<string, string> = { plant_function: "工作区", drawing_function: "工作区", drawing_page_number: "业务页号", drawing_object_location: "元件位置", pdf_page_number: "PDF物理页号", blank: "空白页", non_wiring: "非接线图", needs_review: "需要复核", reason: "说明", confidence: "置信度", units: "连接组", connections: "连接", unit_id: "连接组标识", line_number: "原理号", start: "起点", end: "终点", device: "元件", name: "描述", terminal: "端子", references: "跨页引用", raw: "引用原文", target_function: "目标工作区", target_drawing_page: "目标业务页号", task_id: "任务标识", current: "电流", remark: "备注", source_note: "来源说明" };

export function ProfileExpectedEditor({ stage, value, onChange }: { stage: ProfileStage; value: Expected; onChange: (value: Expected) => void }) {
  function write(path: Part[], next: unknown) {
    const copy = structuredClone(value);
    let current: Record<string | number, unknown> = copy;
    path.slice(0, -1).forEach(part => { const item = current[part]; if (item == null) current[part] = {}; current = current[part] as Record<string | number, unknown>; });
    current[path[path.length - 1]] = next;
    onChange(copy);
  }
  function field(path: Part[], current: unknown, label: string) {
    return <input aria-label={label} value={text(current)} onChange={event => write(path, event.target.value || null)} />;
  }
  function details(node: unknown, path: Part[] = []): React.ReactNode {
    if (Array.isArray(node)) return node.map((item, index) => <div className="profile-json-group" key={index}>{details(item, [...path, index])}</div>);
    if (node && typeof node === "object") return Object.entries(object(node)).map(([key, item]) => <div key={key} className="profile-field"><label>{[...path, key].map(p => labels[p] ?? p).join(" / ")}</label>{item && typeof item === "object" ? details(item, [...path, key]) : typeof item === "boolean" ? <input aria-label={[...path, key].join(".")} type="checkbox" checked={item} onChange={event => write([...path, key], event.target.checked)} /> : typeof item === "number" || key === "drawing_page_number" || key === "target_drawing_page" ? <input aria-label={[...path, key].join(".")} type="number" value={text(item)} onChange={event => write([...path, key], event.target.value === "" ? null : Number(event.target.value))} /> : key === "task_id" ? <span>{text(item)}（固定）</span> : field([...path, key], item, [...path, key].join("."))}</div>);
    return null;
  }
  return <div className="profile-expected">
    {stage === "classification" ? <div className="profile-metadata">{details(value)}</div> : <div className="profile-table-scroll"><table className="profile-answer-table"><thead><tr>{["原理号", "起点元件", "起点描述", "起点端子", "终点元件", "终点描述", "终点端子", "跨页引用", "电流", "备注", "操作"].map(name => <th key={name}>{name}</th>)}</tr></thead><tbody>
      {(stage === "scan" ? array(value.units).flatMap((unit, ui) => array(object(unit).connections).map((row, ci) => ({ row: object(row), path: ["units", ui, "connections", ci] as Part[], key: `${ui}-${ci}` }))) : [{ row: value, path: [] as Part[], key: "completion" }]).map(({ row, path, key }) => <tr key={key}>
        <td>{stage === "scan" ? field([...path, "line_number"], row.line_number, `${key} 原理号`) : "指定连接"}</td>
        {["start", "end"].flatMap(side => ["device", "name", "terminal"].map(name => <td key={`${side}-${name}`}>{stage === "completion" && side === "start" ? "已冻结" : field([...path, side, name], object(row[side])[name], `${key} ${side} ${name}`)}</td>))}
        <td>{stage === "scan" ? <>{array(row.references).map((ref, ri) => <div key={ri} className="profile-reference">{field([...path, "references", ri, "raw"], object(ref).raw, `${key} 引用${ri + 1} 原文`)}{field([...path, "references", ri, "target_function"], object(ref).target_function, `${key} 引用${ri + 1} 工作区`)}<input aria-label={`${key} 引用${ri + 1} 业务页号`} type="number" min={1} value={text(object(ref).target_drawing_page)} onChange={e => write([...path, "references", ri, "target_drawing_page"], e.target.value ? Number(e.target.value) : null)} /><button type="button" onClick={() => write([...path, "references"], array(row.references).filter((_, i) => i !== ri))}>移除此引用</button></div>)}<button type="button" onClick={() => write([...path, "references"], [...array(row.references), { raw: null, target_function: null, target_drawing_page: null }])}>添加跨页引用</button></> : "任务引用已固定"}</td>
        <td>{field([...path, "current"], row.current, `${key} 电流`)}</td><td>{field([...path, stage === "scan" ? "remark" : "source_note"], row[stage === "scan" ? "remark" : "source_note"], `${key} 备注`)}</td>
        <td>{stage === "scan" ? <><button type="button" onClick={() => write([...path, "end"], null)}>清空终点</button><button type="button" onClick={() => { const parts = path.slice(0, -1); const units = array(value.units); const rows = array(object(units[Number(path[1])]).connections); write(parts, rows.filter((_, index) => index !== path[3])); }}>删除本行</button></> : "—"}</td>
      </tr>)}
    </tbody></table></div>}
    {stage === "scan" ? <button type="button" onClick={() => { const units = structuredClone(array(value.units)); if (!units.length) units.push({ unit_id: "user-unit-1", connections: [] }); const last = object(units[units.length - 1]); last.connections = [...array(last.connections), { start: { ...endpoint }, end: null, references: [], endpoint_role: "source", line_number: null }]; write(["units"], units); }}>补充遗漏连接</button> : null}
    {stage !== "classification" ? <details><summary>查看／编辑完整阶段字段（含跨页地址、坐标和不确定项）</summary><div className="profile-metadata">{details(value)}</div></details> : null}
    <p className="profile-hint">空白表示未确认；跨页初扫终点保持空白。修改的内容会直接生成 expected.json。</p>
  </div>;
}
