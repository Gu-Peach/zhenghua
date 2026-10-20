import type { WiringRow } from "./types";

export const answerColumns = [
  ["page", "页码"], ["lineNumber", "原理号"], ["voltageLevel", "电压等级"], ["terminalStrip", "端子排"],
  ["startCode", "起点元件"], ["startDescription", "起点描述"], ["startTerminal", "起点端子"],
  ["endCode", "终点元件"], ["endDescription", "终点描述"], ["endTerminal", "终点端子"],
  ["current", "电流"], ["remark", "备注"], ["colorMark", "色标"],
] as const;
export type AnswerField = typeof answerColumns[number][0];
export type AnswerRow = Record<AnswerField, string> & { sourceRow: number; sheet: string };
export interface AnswerBook {
  filename: string;
  count: number;
  fields: AnswerField[];
  pages: Record<string, AnswerRow[]>;
}
export const pageKey = (value: string): string => value.trim().toUpperCase();
const text = (value: unknown): string => value == null ? "" : value instanceof Date ? value.toISOString() : String(value).trim();
const aliases: Record<string, AnswerField> = {
  页码: "page", 图纸页码: "page", 原理号: "lineNumber", 电压等级: "voltageLevel", 端子排: "terminalStrip",
  起点元件: "startCode", 起点代号: "startCode", 起点描述: "startDescription", 起点名称: "startDescription", 起点端子: "startTerminal",
  终点元件: "endCode", 终点代号: "endCode", 终点描述: "endDescription", 终点名称: "endDescription", 终点端子: "endTerminal",
  电流: "current", 备注: "remark", 色标: "colorMark",
};

/** Convert worksheet cells only; never execute formulas or persist the imported workbook. */
export function parseAnswerSheets(filename: string, sheets: { sheet: string; data: unknown[][] }[]): AnswerBook {
  const pages: Record<string, AnswerRow[]> = Object.create(null) as Record<string, AnswerRow[]>;
  let count = 0;
  let fields: AnswerField[] | undefined;
  for (const sheet of sheets) {
    const header = sheet.data.findIndex(row => row.some(cell => aliases[text(cell)] === "page") && row.some(cell => aliases[text(cell)] === "startTerminal") && row.some(cell => aliases[text(cell)] === "endTerminal"));
    if (header < 0) continue;
    const mapping = sheet.data[header].map(cell => aliases[text(cell)]);
    const sheetFields = answerColumns.map(([key]) => key).filter(key => mapping.includes(key));
    if (new Set(mapping.filter(Boolean)).size !== mapping.filter(Boolean).length) throw new Error(`工作表 ${sheet.sheet} 存在重复字段表头，请先整理。`);
    if (fields && fields.join() !== sheetFields.join()) throw new Error("多个答案工作表的字段不一致，请使用相同表头。");
    fields = sheetFields;
    let previousPage = "";
    for (let index = header + 1; index < sheet.data.length; index++) {
      const cells = sheet.data[index];
      if (!cells.some(cell => text(cell))) { previousPage = ""; continue; }
      const row = Object.fromEntries(answerColumns.map(([key]) => [key, ""])) as Record<AnswerField, string>;
      mapping.forEach((key, column) => { if (key) row[key] = text(cells[column]); });
      if (row.page === "页码" || row.startTerminal === "起点端子") { previousPage = ""; continue; }
      row.page ||= previousPage;
      if (!row.page) throw new Error(`工作表 ${sheet.sheet} 第 ${index + 1} 行缺少页码。`);
      previousPage = row.page;
      if (!row.lineNumber && !row.startTerminal && !row.endTerminal) continue;
      const key = pageKey(row.page);
      (pages[key] ??= []).push({ ...row, sourceRow: index + 1, sheet: sheet.sheet });
      if (++count > 50000) throw new Error("单次临时对比最多支持50000条答案，请按项目拆分文件。");
    }
  }
  if (!fields || !count) throw new Error("没有找到答案记录。表头需包含页码、起点端子和终点端子。");
  return { filename, count, fields, pages };
}

export async function importAnswerFile(file: File): Promise<AnswerBook> {
  if (!/\.xlsx$/i.test(file.name)) throw new Error("请选择 .xlsx 格式的答案表。");
  if (file.size > 10 * 1024 * 1024) throw new Error("答案文件最大10MB，请按项目拆分后导入。");
  const { default: readXlsxFile } = await import("read-excel-file/browser");
  let sheets;
  try { sheets = await readXlsxFile(file); }
  catch { throw new Error("无法读取XLSX，请检查文件是否损坏、加密或格式不正确。"); }
  return parseAnswerSheets(file.name, sheets);
}

export interface ComparisonItem {
  answer?: AnswerRow;
  actual?: WiringRow;
  status: "same" | "different" | "missing" | "extra" | "ambiguous";
  differences: AnswerField[];
}
export const comparisonLabels = { same: "一致", different: "有差异", missing: "漏提", extra: "多提", ambiguous: "待匹配" };

/** Match within one business page, keeping duplicate-number ambiguity visible. */
export function compareAnswerPage(answers: AnswerRow[], actuals: WiringRow[], fields: AnswerField[]): ComparisonItem[] {
  const result: ComparisonItem[] = [];
  const remainingAnswers = new Set(answers);
  const remainingActuals = new Set(actuals);
  const compareFields = fields.filter(key => key !== "page");
  const value = (row: AnswerRow | WiringRow, key: AnswerField) => text(row[key]);
  const identity = (row: AnswerRow | WiringRow) => JSON.stringify([value(row, "lineNumber"), value(row, "startCode"), value(row, "startTerminal"), value(row, "endCode"), value(row, "endTerminal")]);
  const signature = (row: AnswerRow | WiringRow) => JSON.stringify(compareFields.map(key => value(row, key)));
  function pair(answer: AnswerRow, actual: WiringRow) {
    remainingAnswers.delete(answer); remainingActuals.delete(actual);
    const differences = compareFields.filter(key => value(answer, key) !== value(actual, key));
    result.push({ answer, actual, differences, status: differences.length ? "different" : "same" });
  }
  // Identical duplicates can be consumed by count; order carries no semantic meaning.
  const exact = new Map<string, WiringRow[]>();
  for (const actual of actuals) { const key = signature(actual); if (!exact.has(key)) exact.set(key, []); exact.get(key)!.push(actual); }
  for (const answer of answers) { const actual = exact.get(signature(answer))?.shift(); if (actual) pair(answer, actual); }
  const uniquePass = (keyOf: (row: AnswerRow | WiringRow) => string) => {
    const left = new Map<string, AnswerRow[]>(); const right = new Map<string, WiringRow[]>();
    for (const answer of remainingAnswers) { const key = keyOf(answer); if (key) { if (!left.has(key)) left.set(key, []); left.get(key)!.push(answer); } }
    for (const actual of remainingActuals) { const key = keyOf(actual); if (key) { if (!right.has(key)) right.set(key, []); right.get(key)!.push(actual); } }
    for (const [key, group] of left) if (group.length === 1 && right.get(key)?.length === 1) pair(group[0], right.get(key)![0]);
  };
  uniquePass(row => row.startTerminal && row.endTerminal ? identity(row) : "");
  uniquePass(row => text(row.lineNumber));
  const answerNumbers = new Set([...remainingAnswers].map(row => text(row.lineNumber)));
  const actualNumbers = new Set([...remainingActuals].map(row => text(row.lineNumber)));
  for (const answer of remainingAnswers) result.push({ answer, differences: [], status: actualNumbers.has(text(answer.lineNumber)) ? "ambiguous" : "missing" });
  for (const actual of remainingActuals) result.push({ actual, differences: [], status: answerNumbers.has(text(actual.lineNumber)) ? "ambiguous" : "extra" });
  return result;
}
