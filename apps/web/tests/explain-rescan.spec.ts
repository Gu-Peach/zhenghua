import { expandProjectTree } from "./tree-navigation";
import { test, expect, type Page } from "@playwright/test";

const project = "00000000-0000-0000-0000-000000000010", row = "00000000-0000-0000-0000-000000000011", runId = "00000000-0000-0000-0000-000000000012", assetId = "00000000-0000-0000-0000-000000000013", newRow = "00000000-0000-0000-0000-000000000015";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6h8AAAAASUVORK5CYII=", "base64");
async function fixture(page: Page, options: { conflict?: boolean; restored?: boolean; uploadFails?: boolean; empty?: boolean; replacement?: boolean; emptyResult?: boolean; legacyFull?: boolean } = {}) {
  let started = !!options.restored, status = options.restored ? "ready" : "queued", version = 1, historyReads = 0;
  let scope: { connection_ids?: string[]; workspace_code?: string } = options.replacement || options.legacyFull ? { workspace_code: "003.C" } : { connection_ids: [row] }; let fields: "all" | "end" = options.replacement || options.legacyFull ? "all" : "end";
  const uploads: Record<string, unknown>[] = [], turns: Record<string, unknown>[] = [], decisions: Record<string, unknown>[] = [];
  const connection = () => ({ connection_id: options.replacement && status === "applied" ? newRow : row, id: options.replacement && status === "applied" ? newRow : row, project_id: project, batch_id: "batch-a", record_version: version, workspace_id: "work", drawing_id: "drawing", workspace_name: "003.C", workspace_page: "003C01", pdf_page_number: 1, source_pdf_page_number: 1, source_drawing_page: "003C01", target_pdf_page_number: 2, start_terminal: "XA:8", end_terminal: status === "applied" ? "X9:2" : "OLD", principle_number: "P1", is_cross_page: true });
  const run = () => ({ id: runId, project_id: project, conversation_id: "00000000-0000-0000-0000-000000000014", batch_id: "batch-a", status, stage: status === "ready" ? "ready" : status === "running" ? "completion" : status,
    request: { scope, fields, instructions: "按细节复核终点", result_mode: options.replacement ? "replace_scope" : "patch" }, profile: { key: "zh", version: "2.1.1", checksum: "sha256:" + "a".repeat(64) }, progress: { pdf_page_number: 1 }, versions: status === "applied" ? options.emptyResult ? {} : { [options.replacement ? newRow : row]: options.replacement ? 1 : 2 } : {}, created_at: "2026-10-18", updated_at: "2026-10-18", checksum: "sha256:" + "b".repeat(64),
    candidate: ["ready", "applied", "rejected"].includes(status) ? { changes: options.emptyResult ? [] : [{ action: options.replacement ? "insert" : "update", connection_id: options.replacement ? newRow : row, record_version: options.replacement ? 0 : 1, source_pdf_page_number: 1, source_drawing_page: "003C01", workspace_code: "003.C", principle_number: "P1", before: options.replacement ? {} : { end_terminal: "OLD" }, after: { end_terminal: "X9:2" } }], replacement: options.replacement ? { version: 1, scanned_pages: [1], removed: [{ connection_id: row, record_version: 1, source_pdf_page_number: 1, source_drawing_page: "003C01", workspace_code: "003.C", principle_number: "P1", before: { start_terminal: "XA:8", end_terminal: "OLD" } }] } : null, warnings: ["坐标按原始完整图定位，细节图仅辅助辨字。"], unmatched_ids: [] } : null });
  await page.route("**/rescan-evidence.svg", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="160"><rect width="300" height="160" fill="white"/><path d="M40 30V100H200" stroke="black" fill="none"/><text x="210" y="105">X9:2</text></svg>' }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", user: { id: "owner", name: "工程师", role: "工程师" }, expiresIn: 3600 } });
    const detail = { id: project, name: "重扫夹具项目", status: "ready", updated_at: "now", standard_profile: "zh", source_saved: false, batch_id: "batch-a", workspaces: [{ id: "work", code: "003.C", name: "003.C", drawings: [{ id: "drawing", workspace_id: "work", workspace_page: "003C01", pdf_page_number: 1, status: "completed" }, { id: "target", workspace_id: "work", workspace_page: "003C02", pdf_page_number: 2, status: "completed" }] }] };
    if (path === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (path === `/api/v1/projects/${project}`) return route.fulfill({ json: detail });
    if (path.endsWith("/connections")) return route.fulfill({ json: { items: options.empty || options.replacement && options.emptyResult && status === "applied" ? [] : [connection()], batch_id: "batch-a", offset: 0, limit: 100, has_more: false } });
    if (path.endsWith("/connection-edits")) return route.fulfill({ json: [] });
    if (path.endsWith("/rescan-assets")) {
      const body = route.request().postDataJSON(); uploads.push(body);
      return options.uploadFails ? route.fulfill({ status: 422, json: { detail: { message: "图片格式无效" } } }) : route.fulfill({ json: { id: assetId, project_id: project, conversation_id: body.conversation_id, role: body.role, pdf_page_number: body.pdf_page_number, width: 1, height: 1, checksum: "sha256:" + "c".repeat(64) } });
    }
    if (path.endsWith("/rescans")) { historyReads++; return route.fulfill({ json: started ? [run()] : [] }); }
    if (path.endsWith("/evidence")) return route.fulfill({ json: [{ id: "page:1", title: "原图 · 003C01 · PDF 1", pdf_page_number: 1, image_url: "/rescan-evidence.svg" }, { id: "page:2", title: "原图 · 003C02 · PDF 2", pdf_page_number: 2, image_url: "/rescan-evidence.svg" }, { id: assetId, title: "用户上传的辅助细节图", image_url: "/rescan-evidence.svg" }] });
    if (path.endsWith(`/rescans/${runId}`)) return route.fulfill({ json: run() });
    if (path.endsWith("/cancel")) { status = "cancelled"; return route.fulfill({ json: run() }); }
    if (path.endsWith("/decision")) {
      const body = route.request().postDataJSON(); decisions.push(body);
      if (options.conflict) return route.fulfill({ status: 409, json: { detail: { message: "数据已变更，请刷新后重试" } } });
      status = body.accepted ? "applied" : "rejected"; if (body.accepted) version = options.replacement ? 1 : 2;
      return route.fulfill({ json: run() });
    }
    if (path.endsWith("/explain/turns/stream")) {
      const body = route.request().postDataJSON(); turns.push(body); const scanning = /重扫|重新扫描/.test(String(body.message)) && !String(body.message).includes("解释已有任务");
      if (scanning) { started = true; status = "running"; if (body.query?.workspace_code) { scope = { workspace_code: body.query.workspace_code }; fields = "all"; } }
      const answer = scanning ? "已提交重扫任务，将读取原图、关联图与细节图，正式线表尚未改变。".repeat(15) : "当前数据库保存的终点为OLD。";
      const event = (type: string, value: object) => `event: ${type}\ndata: ${JSON.stringify({ type, conversation_id: body.conversation_id, turn_id: body.turn_id, ...value })}\n\n`;
      const context = { project_name: "重扫夹具项目", row: connection(), drawings: [], recorded: {}, evidence_path: [], gaps: [] };
      return route.fulfill({ contentType: "text/event-stream", body: event("context", { context }) + (scanning ? event("rescan_started", { rescan: run() }) : "") + event("answer_delta", { delta: answer }) + event("completed", { result: { conversation_id: body.conversation_id, turn_id: body.turn_id, answer, context, drawings: [], rescans: scanning ? [run()] : [], proposals: [], retrievals: [], history_reset: false } }) });
    }
    return route.fulfill({ status: 404, json: { detail: "未定义夹具" } });
  });
  return { uploads, turns, decisions, historyReads: () => historyReads, ready: () => { status = "ready"; } };
}

async function open(page: Page, explain = true) {
  await page.goto(`/projects/${project}`);
  const cell = page.getByRole("cell").filter({ has: page.getByRole("button", { name: "解释端子 XA:8", exact: true }) });
  await cell.hover(); await cell.getByRole("button", { name: "解释端子 XA:8", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  if (explain) {
    await panel.getByLabel("追问来源解释").fill("请解释当前连接的来源");
    await panel.getByRole("button", { name: "发送追问", exact: true }).click();
    await expect(panel.getByLabel("解释回复")).toContainText("当前数据库");
  }
  return panel;
}

test("新窗口可直接重扫，不先发送解释请求", async ({ page }) => {
  const state = await fixture(page);
  const panel = await open(page, false);
  await expect(panel.getByRole("status")).toContainText("发送后开始处理");
  expect(state.turns).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("重新扫描这条连接的终点");
  await panel.getByLabel("追问来源解释").press("Enter");
  await panel.getByRole("button", { name: "立即显示已收到内容", exact: true }).click();
  await expect(panel.getByRole("region", { name: "重扫任务与结果", exact: true })).toBeVisible();
  expect(state.turns).toHaveLength(1);
  expect(state.turns[0]).toMatchObject({ message: "重新扫描这条连接的终点", connection_id: row, allow_rescan: true });
  expect(state.decisions).toHaveLength(0);
});

test("聊天图片随本轮发送后清空，下一轮不携带旧图", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await fixture(page); const panel = await open(page, false);
  await expect(panel.getByText("图纸与附件设置", { exact: true })).toHaveCount(0);
  await expect(panel.getByText("添加细节图", { exact: true })).toHaveCount(0);
  await panel.getByLabel("上传重扫截图", { exact: true }).setInputFiles({ name: "detail.png", mimeType: "image/png", buffer: png });
  await expect(panel.locator(".explain-composer img")).toHaveCount(1);
  expect(state.uploads).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("解释这张图片");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.locator(".explain-turn .explain-user img")).toHaveCount(1);
  await expect(panel.locator(".explain-composer img")).toHaveCount(0);
  await expect(panel.getByLabel("追问来源解释")).toBeEmpty();
  expect(state.uploads).toHaveLength(1);
  expect(state.turns[0].attachment_ids).toEqual([assetId]);
  await expect(panel.getByLabel("解释回复")).toContainText("当前数据库");
  await page.screenshot({ path: test.info().outputPath("explain-sent-image-desktop.png") });
  await panel.getByLabel("追问来源解释").fill("再解释当前连接");
  await panel.getByLabel("追问来源解释").press("Enter");
  await expect.poll(() => state.turns.length).toBe(2);
  expect(state.turns[1].attachment_ids).toBeUndefined();
  await page.screenshot({ path: test.info().outputPath("explain-images-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("explain-images-mobile.png") });
});

async function requestFullScan(page: Page, state: Awaited<ReturnType<typeof fixture>>) {
  const panel = await open(page);
  await panel.getByLabel("追问来源解释").fill("全部重扫当前工作区，替换旧范围");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await panel.getByRole("button", { name: "立即显示已收到内容", exact: true }).last().click();
  state.ready();
  return panel;
}

test("完整范围预览删除旧行并写入新行，确认后追问不查询已删除ID", async ({ page }) => {
  const state = await fixture(page, { replacement: true });
  const panel = await requestFullScan(page, state);
  const confirm = panel.getByRole("button", { name: "确认范围替换 删除1行 写入1行", exact: true });
  await expect(confirm).toBeEnabled();
  await expect(panel.getByText("将删除的旧结果：1 行", { exact: true })).toBeVisible();
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
  expect(state.decisions).toHaveLength(0);
  await page.screenshot({ path: test.info().outputPath("rescan-replacement-preview.png") });
  await confirm.click();
  await expect(panel.getByText("范围结果已替换：删除旧结果 1 行，写入新结果 1 行。", { exact: true })).toBeVisible();
  await expect(page.locator(".result-table").getByRole("cell", { name: "X9:2", exact: true })).toBeVisible();
  expect(state.turns).toHaveLength(2);
  await panel.getByLabel("追问来源解释").fill("现在这一页的新结果是什么");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect.poll(() => state.turns.length).toBe(3);
  expect(state.turns[2].connection_id).toBeUndefined(); expect(state.turns[2].query).toMatchObject({ pdf_page_number: 1 });
  expect(state.turns[2].conversation_id).not.toBe(state.turns[1].conversation_id);
  expect(state.decisions).toHaveLength(1);
});

test("空结果替换清楚提示删空，只有确认才删除原范围", async ({ page }) => {
  const state = await fixture(page, { replacement: true, emptyResult: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const panel = await requestFullScan(page, state);
  await expect(panel.getByRole("alert")).toContainText("所选范围将被清空");
  const confirm = panel.getByRole("button", { name: "确认范围替换 删除1行 写入0行", exact: true });
  await expect(confirm).toBeEnabled();
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("rescan-empty-replacement-mobile.png") });
  await confirm.click();
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toHaveCount(0);
  await expect(panel.getByText("范围结果已替换：删除旧结果 1 行，写入新结果 0 行。", { exact: true })).toBeVisible();
});

test("旧版全量合并候选不能作为范围替换提交，仍可拒绝", async ({ page }) => {
  const state = await fixture(page, { restored: true, legacyFull: true }); const panel = await open(page);
  await panel.getByRole("button", { name: "查看项目重扫记录", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("旧版或不完整的全量候选");
  await expect(panel.getByRole("button", { name: "确认重扫结果 1 行", exact: true })).toBeDisabled();
  expect(state.decisions).toHaveLength(0);
  await panel.getByRole("button", { name: "拒绝重扫结果", exact: true }).click();
  expect(state.decisions[0]).toMatchObject({ accepted: false });
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
});

test("读取持久候选完成前不能确认范围删除", async ({ page }) => {
  const state = await fixture(page, { replacement: true, restored: true });
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/rescans/${runId}`, async route => { await gate; await route.fallback(); });
  const panel = await open(page);
  await panel.getByRole("button", { name: "查看项目重扫记录", exact: true }).click();
  const button = panel.getByRole("button", { name: "确认范围替换 删除1行 写入1行", exact: true });
  await expect(button).toBeDisabled(); expect(state.decisions).toHaveLength(0);
  release(); await expect(button).toBeEnabled();
});

test("聊天图片随重扫发送，先回复后显示进度，确认前保持旧行", async ({ page }) => {
  const state = await fixture(page); const panel = await open(page);
  await panel.getByLabel("上传重扫截图", { exact: true }).setInputFiles({ name: "detail.png", mimeType: "image/png", buffer: png });
  await expect(panel.locator(".explain-composer").getByAltText("detail.png")).toBeVisible();
  expect(state.uploads).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("请重扫这个终点，核对截图里的细节"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByRole("region", { name: "重扫任务与结果" })).toHaveCount(0);
  await panel.getByRole("button", { name: "立即显示已收到内容" }).last().click();
  await expect(panel.getByText("正在生成候选，正式线表尚未改动。", { exact: false })).toBeVisible();
  expect(state.turns.at(-1)?.attachment_ids).toEqual([assetId]); expect(state.uploads[0].pdf_page_number).toBe(1);
  await expect(panel.locator(".explain-composer img")).toHaveCount(0);
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
  state.ready();
  await expect(panel.getByRole("button", { name: "确认重扫结果 1 行", exact: true })).toBeVisible();
  expect(state.decisions).toHaveLength(0);
  await panel.getByText("重扫使用的原图与细节图（原图最多展示8张）", { exact: true }).click();
  await expect(panel.getByAltText("原图 · 003C01 · PDF 1", { exact: true })).toBeVisible();
  await expect(panel.getByAltText("用户上传的辅助细节图", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("rescan-candidate-desktop.png") });
  await panel.getByRole("button", { name: "确认重扫结果 1 行", exact: true }).click();
  await expect(panel.getByText("重扫结果已保存，记录所属页与工作区保持不变。", { exact: true })).toBeVisible();
  await expect(page.locator(".result-table").getByRole("cell", { name: "X9:2", exact: true })).toBeVisible();
  expect(state.decisions[0]).toEqual({ accepted: true, checksum: "sha256:" + "b".repeat(64) });
  await panel.getByRole("button", { name: "解释这次重扫差异", exact: true }).click();
  await expect.poll(() => state.turns.at(-1)?.rescan_id).toBe(runId);
  expect(state.decisions).toHaveLength(1);
});

test("重扫候选冲突不写库，窄屏长文本可查看完整对照", async ({ page }) => {
  const state = await fixture(page, { restored: true, conflict: true }); await page.setViewportSize({ width: 390, height: 844 }); const panel = await open(page);
  await expect(panel.getByRole("region", { name: "重扫任务与结果", exact: true })).toHaveCount(0);
  expect(state.historyReads()).toBe(0); expect(state.turns[0].allow_rescan).toBe(true);
  await panel.getByRole("button", { name: "查看项目重扫记录", exact: true }).click();
  await expect.poll(state.historyReads).toBe(1);
  await panel.getByRole("button", { name: "确认重扫结果 1 行", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("数据已变更");
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("rescan-conflict-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("取消重扫不会修改旧行", async ({ page }) => {
  await fixture(page); const panel = await open(page);
  await panel.getByLabel("追问来源解释").fill("重扫这条连接"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await panel.getByRole("button", { name: "立即显示已收到内容" }).last().click();
  await panel.getByRole("button", { name: "取消重扫", exact: true }).click();
  await expect(panel.getByText("重扫已取消", { exact: true })).toBeVisible();
  await expect(page.locator(".result-table").getByRole("cell", { name: "OLD", exact: true })).toBeVisible();
});

test("粘贴图片校验失败时不携带附件，错误可见", async ({ page }) => {
  const state = await fixture(page, { uploadFails: true }); const panel = await open(page);
  await panel.getByLabel("追问来源解释").evaluate(node => { const data = new DataTransfer(); data.items.add(new File(["bad"], "detail.png", { type: "image/png" })); node.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, clipboardData: data })); });
  expect(state.uploads).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("解释这张图片");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("图片格式无效"); expect(state.uploads).toHaveLength(1);
  await expect(panel.locator(".explain-composer img")).toHaveCount(1);
  await expect(panel.getByLabel("追问来源解释")).toHaveValue("解释这张图片");
  expect(state.turns).toHaveLength(1);
});

test("图片轮次失败重试复用同一附件，新草稿可移除并支持仅图片发送", async ({ page }) => {
  const state = await fixture(page); const panel = await open(page, false);
  let attempts = 0;
  await page.route("**/explain/turns/stream", async route => {
    const body = route.request().postDataJSON(); state.turns.push(body); attempts++;
    const event = attempts === 1 ? "error" : "completed";
    const data = attempts === 1 ? { message: "模拟任务未创建" } : { type: event, conversation_id: body.conversation_id, turn_id: body.turn_id, result: { answer: "图片已收到", drawings: [] } };
    await route.fulfill({ contentType: "text/event-stream", body: `event: ${event}\ndata: ${JSON.stringify(data)}\n\n` });
  });
  await panel.getByLabel("上传重扫截图").setInputFiles({ name: "first.png", mimeType: "image/png", buffer: png });
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("模拟任务未创建");
  await expect(panel.locator(".explain-composer img")).toHaveCount(0);
  await panel.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => state.turns.length).toBe(2);
  expect(state.turns[1].turn_id).toBe(state.turns[0].turn_id);
  expect(state.turns[1].attachment_ids).toEqual([assetId]);
  expect(state.uploads).toHaveLength(1);
  await expect(panel.getByLabel("解释回复")).toContainText("图片已收到");
  await panel.getByRole("button", { name: "放大上传图片 first.png", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "查看图纸 first.png", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toBeVisible();
  await panel.getByLabel("上传重扫截图").setInputFiles({ name: "remove.png", mimeType: "image/png", buffer: png });
  await panel.getByRole("button", { name: "移除图片 remove.png", exact: true }).click();
  await expect(panel.getByRole("button", { name: "发送追问", exact: true })).toBeDisabled();
  await expect(panel.locator(".explain-turn .explain-user img")).toHaveCount(1);
});

test("空线表工作区可从工具栏发起完整重扫，不依赖已有行", async ({ page }) => {
  const state = await fixture(page, { empty: true }); await page.goto(`/projects/${project}`);
  await expandProjectTree(page);
  await page.getByRole("button", { name: /^003\.C 003\.C/ }).click();
  await expect(page.getByRole("button", { name: "重新扫描所选范围", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "重新扫描所选范围", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  await expect.poll(() => state.turns.length).toBe(1);
  await expect(panel.getByLabel("追问来源解释")).toHaveValue("");
  await panel.getByRole("button", { name: "立即显示已收到内容" }).last().click();
  await expect(panel.getByRole("region", { name: "重扫任务与结果" })).toBeVisible();
  expect(state.turns.at(-1)?.query).toMatchObject({ workspace_code: "003.C" });
  expect(String(state.turns.at(-1)?.message)).toContain("包含未提取到线表的图纸");
  expect(state.decisions).toHaveLength(0);
});
