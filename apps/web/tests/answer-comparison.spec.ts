import { expandProjectTree, expandWorkspace } from "./tree-navigation";
import { test, expect, type Page } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { readSheet } from "read-excel-file/node";
import { parseAnswerSheets, compareAnswerPage, type AnswerRow } from "../src/apis/answer-comparison";
import type { WiringRow } from "../src/apis/types";

const headers = ["页码", "原理号", "端子排", "起点元件", "起点描述", "起点端子", "终点元件", "终点描述", "终点端子", "电流", "色标", "备注"];
const cells = ["002C01", "N001", "X1", "A", "起点", "1", "B", "终点", "2", 0, "红", ""];
const book = () => parseAnswerSheets("fixture.xlsx", [{ sheet: "答案", data: [headers, cells] }]);
function actual(answer: AnswerRow, id = "row"): WiringRow { return { ...answer, id, drawingId: "drawing", workspaceId: "work", voltageLevel: "", status: "confirmed", confidence: 0 }; }

test("答案映射保留0，只继承连续页码，空行后缺页码报错", () => {
  const imported = parseAnswerSheets("file.xlsx", [{ sheet: "Sheet", data: [headers, cells, [null, "N002", "X2", "A", "", "3", "B", "", "4", 0]] }]);
  expect(imported.count).toBe(2); expect(imported.pages["002C01"][1].current).toBe("0");
  expect(imported.fields).not.toContain("voltageLevel");
  expect(() => parseAnswerSheets("file.xlsx", [{ sheet: "Sheet", data: [headers, cells, [], [null, "N003", null, "A", "", "3", "B", "", "4"]] }])).toThrow("缺少页码");
});

test("同页逐字段比较，端子符号/方向和零值严格保留", () => {
  const imported = book(); const answer = imported.pages["002C01"][0];
  expect(compareAnswerPage([answer], [actual(answer)], imported.fields)[0].status).toBe("same");
  const result = compareAnswerPage([answer], [{ ...actual(answer), startTerminal: "XD:1", current: "" }], imported.fields);
  expect(result[0].status).toBe("different"); expect(result[0].differences).toEqual(["startTerminal", "current"]);
});

test("重复原理号优先端点唯一匹配，歧义不按顺序强配", () => {
  const imported = book(); const a = imported.pages["002C01"][0]; const b = { ...a, sourceRow: 3, startTerminal: "3", endTerminal: "4" };
  const reversed = compareAnswerPage([a, b], [actual(b, "second"), actual(a, "first")], imported.fields);
  expect(reversed.map(row => row.status)).toEqual(["same", "same"]);
  const ambiguous = compareAnswerPage([a, b], [{ ...actual(a, "x"), startTerminal: "8" }, { ...actual(b, "y"), startTerminal: "9" }], imported.fields);
  expect(ambiguous).toHaveLength(4); expect(ambiguous.every(row => row.status === "ambiguous")).toBe(true);
});

test("漏提、多提按数量核对，相同重复记录不被去重吞掉", () => {
  const imported = book(); const a = imported.pages["002C01"][0];
  expect(compareAnswerPage([a, { ...a, sourceRow: 3 }], [actual(a)], imported.fields).map(row => row.status)).toEqual(["same", "missing"]);
  expect(compareAnswerPage([a], [actual(a), { ...actual(a, "extra"), lineNumber: "NEW" }], imported.fields).map(row => row.status)).toEqual(["same", "extra"]);
});


const sourceFile = path.resolve("../../docs/test/1641.xlsx");
const projectId = "fixture-answer-project", otherId = "other-project";
async function setup(page: Page, options: { fail?: boolean; gate?: Promise<void>; paginated?: boolean; denied?: boolean } = {}) {
  const imported = parseAnswerSheets("1641.xlsx", [{ sheet: "Sheet1", data: await readSheet(sourceFile) }]);
  const pageName = Object.keys(imported.pages)[0]; const nextPage = Object.keys(imported.pages)[1];
  const sample = imported.pages[pageName]; const offsets: number[] = []; const writes: string[] = [];
  const detail = { id: projectId, name: "1002001641 PERU TPP 1 STS", owner_id: "owner", status: "ready", updated_at: "2026-10-19", source_saved: false, batch_id: "batch", workspaces: [{ id: "work", code: "002.C", name: "002.C", drawings: [{ id: "drawing", workspace_id: "work", pdf_page_number: 1, workspace_page: pageName, status: "scanned" }, { id: "drawing-two", workspace_id: "work", pdf_page_number: 2, workspace_page: nextPage, status: "scanned" }] }] };
  const dbRow = (row: AnswerRow, index: number) => ({ connection_id: `row-${index}`, project_id: projectId, drawing_id: "drawing", workspace_id: "work", workspace_name: "002.C", workspace_page: pageName, pdf_page_number: 1, row_order: index, record_version: 1, principle_number: row.lineNumber, start_code: row.startCode, start_description: row.startDescription, start_terminal: row.startTerminal, end_code: row.endCode, end_description: row.endDescription, end_terminal: index === 1 ? "WRONG:9" : row.endTerminal, terminal_strip: row.terminalStrip, current_value: row.current, color_mark: row.colorMark, remark: row.remark, needs_review: false, is_cross_page: false });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(); const url = new URL(request.url()); const p = url.pathname;
    if (p.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "测试", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (p === "/api/v1/capabilities") return route.fulfill({ json: { extraction: false, explain: false, supervisor: false } });
    if (request.method() !== "GET") writes.push(p);
    if (p === "/api/v1/projects") return route.fulfill({ json: [detail, { ...detail, id: otherId, name: "其他项目" }] });
    if (p === `/api/v1/projects/${projectId}`) return route.fulfill(options.denied ? { status: 403, json: { detail: { message: "没有项目访问权限" } } } : { json: detail });
    if (p === `/api/v1/projects/${otherId}`) return route.fulfill({ json: { ...detail, id: otherId, name: "其他项目" } });
    if (p.endsWith("/connections")) {
      const isComparison = url.searchParams.has("drawing_id");
      if (isComparison && options.gate) await options.gate;
      if (isComparison && options.fail) return route.fulfill({ status: 503, json: { detail: { message: "暂时不可用" } } });
      const offset = Number(url.searchParams.get("offset") ?? 0); if (isComparison) offsets.push(offset);
      if (url.searchParams.get("drawing_id") && url.searchParams.get("drawing_id") !== "drawing") return route.fulfill({ json: { items: [], has_more: false, batch_id: "batch", offset, limit: 100 } });
      const rows = options.paginated ? Array.from({ length: 105 }, (_, index) => dbRow(sample[index % sample.length], index)) : sample.slice(0, -1).map(dbRow);
      return route.fulfill({ json: { items: rows.slice(offset, offset + 100), has_more: rows.length > offset + 100, batch_id: "batch", offset, limit: 100 } });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${projectId}`);
  await page.getByRole("button", { name: "答案对比", exact: true }).click();
  return { imported, offsets, writes };
}

test.describe("真实答案的本地导入界面", () => {
  test.skip(!existsSync(sourceFile), "本地答案属于用户数据，未提交仓库；缺文件环境跳过此只读验收。");
  test("上下原顺序结果表，移除统计控制区，切目录保留、跨项目隔离和刷新清空", async ({ page }) => {
    const { writes } = await setup(page);
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles(sourceFile);
    const panel = page.getByRole("region", { name: "临时答案对比" });
    const upper = panel.getByRole("table", { name: "提取结果", exact: true });
    const lower = panel.getByRole("table", { name: "标准答案", exact: true });
    await expect(upper.locator("tbody tr")).toHaveCount(5); await expect(lower.locator("tbody tr")).toHaveCount(6);
    await expect(upper.locator("tbody tr").nth(1)).toContainText("WRONG:9");
    await expect(lower.locator("tbody tr").nth(1)).not.toContainText("WRONG:9");
    const panes = panel.locator(".answer-pane");
    const upperBox = (await panes.nth(0).boundingBox())!; const lowerBox = (await panes.nth(1).boundingBox())!;
    expect(upperBox.y + upperBox.height).toBeLessThanOrEqual(lowerBox.y + 1);
    await expect(panel.getByText("仅看差异", { exact: true })).toHaveCount(0);
    await expect(panel.getByRole("combobox")).toHaveCount(0);
    await expect(panel.getByRole("columnheader", { name: "对比状态" })).toHaveCount(0);
    await expect(panel.getByRole("columnheader", { name: "数据来源" })).toHaveCount(0);
    await expect(panel.locator(".answer-counts, .answer-header, .answer-hint, .answer-controls")).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath("answer-stacked-desktop.png") });
    await expandProjectTree(page); await expandWorkspace(page, "002.C");
    await page.getByRole("button", { name: /^002C02 PDF/ }).click();
    await expect(page.getByRole("table", { name: "标准答案", exact: true }).locator("tbody tr")).toHaveCount(8);
    await expect(page.getByRole("button", { name: "更换答案XLSX", exact: true })).toHaveAttribute("title", /1641.xlsx/);
    await page.getByRole("link", { name: "其他项目", exact: true }).click();
    await expect(page).toHaveURL(`/projects/${otherId}`);
    await expect(page.getByRole("button", { name: "修改项目名称 其他项目", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "答案对比", exact: true }).click();
    await expect(page.getByText("请导入标准答案")).toBeVisible();
    await page.getByRole("link", { name: "1002001641 PERU TPP 1 STS", exact: true }).click();
    await expect(page.getByRole("button", { name: "更换答案XLSX", exact: true })).toHaveAttribute("title", /1641.xlsx/);
    await page.reload(); await page.getByRole("button", { name: "答案对比", exact: true }).click();
    await expect(page.getByText("请导入标准答案")).toBeVisible(); expect(writes).toEqual([]);
  });
  test("超过100条全页读取，上下独立分页，横向滚动同步且窄屏不撑开页面", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const { offsets } = await setup(page, { paginated: true });
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles(sourceFile);
    const upper = page.getByRole("table", { name: "提取结果", exact: true });
    const lower = page.getByRole("table", { name: "标准答案", exact: true });
    await expect(upper.locator("tbody tr")).toHaveCount(50); expect(offsets).toContain(100);
    await page.getByRole("button", { name: "提取结果下一页", exact: true }).click();
    await expect(page.locator(".answer-footer")).toContainText("2 / 3");
    await expect(lower.locator("tbody tr")).toHaveCount(6);
    const scrolls = page.locator(".answer-table-scroll");
    await scrolls.nth(0).evaluate(element => { element.scrollLeft = 250; });
    await expect.poll(() => scrolls.nth(1).evaluate(element => element.scrollLeft)).toBe(250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.locator(".answer-comparison").scrollIntoViewIfNeeded();
    await expect(page.getByRole("heading", { name: "提取结果", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "标准答案", exact: true })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("answer-stacked-mobile.png") });
  });
  test("加载与失败只影响提取区，答案仍可查看，坏文件不覆盖，清除可重导", async ({ page }) => {
    let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
    await setup(page, { fail: true, gate });
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles(sourceFile);
    await expect(page.getByText("正在读取提取结果…")).toBeVisible();
    await expect(page.locator(".answer-counts")).toHaveCount(0); release();
    await expect(page.getByRole("alert")).toContainText("读取失败");
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles({ name: "bad.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("invalid") });
    await expect(page.getByText(/无法读取XLSX/)).toBeVisible();
    await expect(page.getByRole("button", { name: "更换答案XLSX", exact: true })).toHaveAttribute("title", /1641.xlsx/);
    await page.getByRole("button", { name: "清除答案" }).click();
    await expect(page.getByText("请导入标准答案")).toBeVisible();
  });
  for (const scenario of ["short", "duplicate", "batch"] as const) test(`全页读取拒绝不完整快照：${scenario}`, async ({ page }) => {
    await setup(page);
    await page.route("**/connections?**", route => {
      const url = new URL(route.request().url());
      if (!url.searchParams.has("drawing_id")) return route.fallback();
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const count = scenario === "short" ? 1 : scenario === "duplicate" ? 2 : 100;
      return route.fulfill({ json: { items: Array.from({ length: count }, (_, i) => ({ connection_id: scenario === "duplicate" ? "same" : `row-${offset}-${i}`, drawing_id: "drawing", workspace_id: "work" })), batch_id: offset ? "new-batch" : "old-batch", offset, limit: 100, has_more: scenario !== "duplicate" && !offset } });
    });
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles(sourceFile);
    await page.getByRole("button", { name: "刷新提取结果", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("读取失败");
    await expect(page.locator(".answer-counts")).toHaveCount(0);
  });
  test("退出登录清空临时答案，同账号再次登录也需重导", async ({ page }) => {
    await setup(page);
    await page.locator('input[aria-label="导入答案XLSX"]').setInputFiles(sourceFile);
    await expect(page.getByRole("button", { name: "更换答案XLSX", exact: true })).toHaveAttribute("title", /1641.xlsx/);
    await page.locator(".account-trigger").click();
    await page.getByRole("button", { name: "退出登录", exact: true }).click();
    await expect(page).toHaveURL("/login");
    await page.getByLabel("邮箱", { exact: true }).fill("fixture@example.invalid");
    await page.getByLabel("密码", { exact: true }).fill("fixture-password");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(page).toHaveURL(`/projects/${projectId}`);
    await page.getByRole("button", { name: "答案对比", exact: true }).click();
    await expect(page.getByText("请导入标准答案")).toBeVisible();
  });
  test("无权限不展示答案入口或项目对比数据", async ({ page }) => {
    await page.route("**/api/v1/**", route => {
      const p = new URL(route.request().url()).pathname;
      if (p.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "测试" }, accessToken: "fixture" } });
      if (p === "/api/v1/projects") return route.fulfill({ json: [] });
      return route.fulfill({ status: 403, json: { detail: { message: "没有项目访问权限" } } });
    });
    await page.goto(`/projects/${projectId}`); await expect(page.getByRole("alert")).toContainText("没有项目访问权限");
    await expect(page.getByRole("region", { name: "临时答案对比" })).toHaveCount(0);
  });
});
