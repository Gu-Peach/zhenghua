import type { components } from "./generated";
import type { WiringRow } from "./types";

export type ConnectionChanges = components["schemas"]["ConnectionFields"];

export const editableConnectionFields = [
  { key: "principle_number", view: "lineNumber", label: "原理号", maxLength: 500, shared: false },
  { key: "voltage_level", view: "voltageLevel", label: "电压等级", maxLength: 100, shared: false },
  { key: "terminal_strip", view: "terminalStrip", label: "端子排", maxLength: 100, shared: false },
  { key: "start_code", view: "startCode", label: "起点代号", maxLength: 500, shared: false },
  { key: "start_description", view: "startDescription", label: "起点描述", maxLength: 4000, shared: false },
  { key: "start_terminal", view: "startTerminal", label: "起点端子", maxLength: 500, shared: false },
  { key: "end_code", view: "endCode", label: "终点代号", maxLength: 500, shared: false },
  { key: "end_description", view: "endDescription", label: "终点描述", maxLength: 4000, shared: false },
  { key: "end_terminal", view: "endTerminal", label: "终点端子", maxLength: 500, shared: false },
  { key: "current_value", view: "current", label: "电流", maxLength: 100, shared: false },
  { key: "remark", view: "remark", label: "备注", maxLength: 4000, shared: false },
  { key: "color_mark", view: "colorMark", label: "色标", maxLength: 100, shared: false },
] as const;

export type EditableConnectionKey = typeof editableConnectionFields[number]["key"];
export type ConnectionDraft = Record<EditableConnectionKey, string>;

export function connectionDraft(row: WiringRow): ConnectionDraft {
  return Object.fromEntries(editableConnectionFields.map(field => [field.key, String(row[field.view] ?? "")])) as ConnectionDraft;
}

export function changedConnectionFields(row: WiringRow, draft: ConnectionDraft): ConnectionChanges {
  const changes: ConnectionChanges = {};
  for (const field of editableConnectionFields) {
    const value = draft[field.key].trim();
    if (value !== String(row[field.view] ?? "")) changes[field.key] = value || null;
  }
  return changes;
}
