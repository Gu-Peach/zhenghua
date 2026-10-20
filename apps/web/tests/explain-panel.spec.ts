import { expandProjectTree, expandWorkspace } from "./tree-navigation";
import { test, expect, type Page } from "@playwright/test";
import { createServer, type Server } from "node:http";

const projectId = "00000000-0000-0000-0000-000000000010";
const rowId = "00000000-0000-0000-0000-000000000015";
const sourceId = "00000000-0000-0000-0000-000000000012";
const servers = new Set<Server>();
test("来源聊天支持鼠标和键盘缩放，拖动及窄屏边界正常", async ({ page }) => {
  const state = await fixture(page);
  const panel = await openRow(page, false);
  const handle = panel.getByRole("button", { name: "缩放来源解释窗口" });
  const initial = (await panel.boundingBox())!;
  const point = (await handle.boundingBox())!;
  await page.mouse.move(point.x + point.width / 2, point.y + point.height / 2);
  await page.mouse.down(); await page.mouse.move(point.x - 100, point.y - 80, { steps: 8 }); await page.mouse.up();
  await expect.poll(async () => (await panel.boundingBox())!.width).toBeLessThan(initial.width - 80);
  const smaller = (await panel.boundingBox())!;
  await handle.focus(); await handle.press("ArrowRight");
  await expect.poll(async () => (await panel.boundingBox())!.width).toBeGreaterThan(smaller.width);
  await handle.press("Home");
  await expect.poll(async () => Math.round((await panel.boundingBox())!.width)).toBe(Math.round(initial.width));
  const header = panel.getByLabel("来源解释窗口标题栏");
  await header.focus(); await header.press("ArrowLeft");
  await expect.poll(async () => (await panel.boundingBox())!.x).toBeLessThan(initial.x);
  await page.screenshot({ path: test.info().outputPath("chat-resize-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await handle.focus(); await handle.press("ArrowRight");
  const narrow = (await panel.boundingBox())!;
  expect(narrow.x).toBeGreaterThanOrEqual(0); expect(narrow.x + narrow.width).toBeLessThanOrEqual(390);
  expect(narrow.y + narrow.height).toBeLessThanOrEqual(844);
  await page.screenshot({ path: test.info().outputPath("chat-resize-narrow.png") });
  expect(state.requests).toHaveLength(0);
});
test.afterEach(async () => {
  for (const server of servers) { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
  servers.clear();
});

async function fixture(page: Page, options: { pauseTools?: boolean; pauseAnswer?: boolean; denied?: boolean; brokenImage?: boolean; longAnswer?: boolean; wholeAnswer?: string; completionOnly?: boolean; firstChunk?: string } = {}) {
  // Explicit offline HTTP/SSE fixtures. No real Agent, database or paid model is contacted.
  const requests: Array<Record<string, unknown>> = [];
  let releaseTools = () => {}; let releaseAnswer = () => {};
  let closed = 0; let denied = !!options.denied;
  const toolsGate = options.pauseTools ? new Promise<void>(resolve => { releaseTools = resolve; }) : Promise.resolve();
  const answerGate = options.pauseAnswer ? new Promise<void>(resolve => { releaseAnswer = resolve; }) : Promise.resolve();
  const row = { connection_id: rowId, project_id: projectId, batch_id: "run-one", record_version: 1,
    workspace_id: "work", workspace_name: "003.C", drawing_id: sourceId, workspace_page: "003C01", pdf_page_number: 1,
    start_code: "+01F10", start_terminal: "XA:8", end_terminal: "XD10:1", principle_number: "003C0101", is_cross_page: true };
  const drawing = (pdf: number) => ({ id: pdf === 1 ? sourceId : "target", workspace_id: "work", workspace_page: pdf === 1 ? "003C01" : "004C01", pdf_page_number: pdf, status: "completed", image_url: "/explain-fixture.png" });
  const drawings = [1, 2].map(pdf => ({ role: pdf === 1 ? "source" : "target", pdf_page_number: pdf,
    drawing_page: pdf === 1 ? "003C01" : "004C01", image_url: "/explain-fixture.png", connection_ids: [rowId] }));
  const context = { project_name: "来源解释测试项目", row: { ...row, id: rowId, source_pdf_page_number: 1,
    source_drawing_page: "003C01", target_pdf_page_number: 2 }, drawings, recorded: { source_note: "按放线标记与跨页引用确认" }, evidence_path: [], gaps: [] };
  const server = createServer(async (req, res) => {
    res.setHeader("Access-Control-Allow-Origin", req.headers.origin || "http://127.0.0.1:5186");
    res.setHeader("Access-Control-Allow-Credentials", "true");
    res.setHeader("Access-Control-Allow-Headers", "Authorization,Content-Type");
    if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }
    let raw = ""; for await (const part of req) raw += part.toString();
    const input = JSON.parse(raw) as Record<string, unknown>; requests.push(input);
    if (denied) { res.writeHead(403, { "Content-Type": "application/json" }); res.end(JSON.stringify({ detail: { message: "没有项目访问权限" } })); return; }
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    res.on("close", () => { closed++; });
    const send = (type: string, value: Record<string, unknown>) => { if (!res.destroyed) res.write(`event: ${type}\ndata: ${JSON.stringify({ type, conversation_id: input.conversation_id, turn_id: input.turn_id, ...value })}\n\n`); };
    const pageQuery = input.query as Record<string, unknown> | undefined;
    const selected = pageQuery ? { project_name: context.project_name, batch_id: "run-one", query: pageQuery, rows: [context], drawings, has_more: false, gaps: [] } : context;
    const tool = { id: "initial:" + input.turn_id, name: pageQuery ? "search_connections" : "load_connection", arguments: pageQuery ?? { connection_id: rowId } };
    send("tool_started", { tool });
    await toolsGate; if (res.destroyed) return;
    send("tool_completed", { tool: { ...tool, result: selected } });
    send("context", { context: selected });
    send("tool_started", { tool: { id: "view", name: "view_drawings", arguments: { pdf_page_numbers: [1, 2] } } });
    send("tool_completed", { tool: { id: "view", name: "view_drawings", arguments: { pdf_page_numbers: [1, 2] }, result: { visual_pages: [1, 2] } } });
    const first = options.firstChunk ?? (requests.length > 1 ? `追问回复：${String(input.message)}。` : "这条连接来自原页 003C01，");
    if (!options.completionOnly) send("answer_delta", { delta: options.wholeAnswer ?? first });
    await answerGate; if (res.destroyed) return;
    const last = "沿放线标记读取 XA:8，再通过引用匹配跨页 004C01 的 XD10:1。" + (options.longAnswer ? "很长的端子来源说明XD3:251。".repeat(100) : "");
    if (!options.wholeAnswer && !options.completionOnly) send("answer_delta", { delta: last });
    send("completed", { result: { conversation_id: input.conversation_id, turn_id: input.turn_id, answer: options.wholeAnswer ?? first + last,
      context: selected, drawings, retrievals: [], coverage: [], visual_pages: [1, 2], gaps: [], cached: false, history_reset: false } });
    res.end();
  });
  servers.add(server);
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("Fixture server unavailable");
  await page.route("**/explain-fixture.png", route => options.brokenImage ? route.fulfill({ status: 404 }) : route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYyQAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "测试工程师", email: "fixture@example.invalid", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (path.endsWith("/connection-edits")) return route.fulfill({ json: [] });
    if (path.includes("/explain/")) return route.continue({ url: `http://127.0.0.1:${address.port}/explain` });
    const project = { id: projectId, name: "来源解释测试项目", status: "ready", standard_profile: "zh", updated_at: "2026-10-16", source_saved: false, batch_id: "run-one", workspaces: [{ id: "work", code: "003.C", name: "003.C", drawings: [drawing(1), drawing(2)] }] };
    if (path === "/api/v1/projects") return route.fulfill({ json: [project] });
    if (path === `/api/v1/projects/${projectId}`) return route.fulfill({ json: project });
    if (path.endsWith("/connections")) return route.fulfill({ json: { items: [row], batch_id: "run-one", offset: 0, limit: 100, has_more: false } });
    if (path.includes("/drawings/")) return route.fulfill({ json: drawing(1) });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: { message: "未配置夹具请求" } } });
  });
  return { requests, releaseTools, releaseAnswer, closed: () => closed, permit: () => { denied = false; } };
}

async function openRow(page: Page, explain = true) {
  await page.goto(`/projects/${projectId}`);
  const cell = page.getByRole("cell", { name: "XA:8", exact: false }).filter({ has: page.getByRole("button", { name: "解释端子 XA:8", exact: true }) });
  await cell.hover(); await cell.getByRole("button", { name: "解释端子 XA:8", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  if (explain) {
    await panel.getByLabel("追问来源解释").fill("请解释这条连接的来源");
    await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  }
  return panel;
}

test("普通打开不提交，用户发送后解释，关闭重开是全新会话", async ({ page }) => {
  const state = await fixture(page);
  let panel = await openRow(page, false);
  await expect(panel.getByRole("status")).toContainText("发送后开始处理");
  await panel.getByLabel("追问来源解释").fill("尚未发送的草稿");
  await page.screenshot({ path: test.info().outputPath("explain-idle-desktop.png") });
  expect(state.requests).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("请解释这条连接的来源");
  await panel.getByLabel("追问来源解释").press("Enter");
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  expect(state.requests).toHaveLength(1);
  await panel.getByRole("button", { name: "关闭来源解释", exact: true }).click();
  await page.getByRole("button", { name: "解释端子 XA:8", exact: true }).click();
  panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  await expect(panel.getByRole("status")).toContainText("发送后开始处理");
  await expect(panel.locator(".explain-turn")).toHaveCount(0);
  await expect(panel.getByLabel("追问来源解释")).toBeEmpty();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("explain-idle-mobile.png") });
  expect(state.requests).toHaveLength(1);
  await panel.getByLabel("追问来源解释").fill("请解释新的问题");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(2);
  expect(state.requests[0].conversation_id).not.toBe(state.requests[1].conversation_id);
  expect(state.requests[0].turn_id).not.toBe(state.requests[1].turn_id);
});

test("来源解释标题栏可拖动、键盘移动与恢复，拖动不调用Agent", async ({ page }) => {
  const state = await fixture(page); const panel = await openRow(page);
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  expect(state.requests[0].allow_rescan).toBe(true);
  const before = await panel.boundingBox();
  const header = panel.getByLabel("来源解释窗口标题栏", { exact: true }); const box = await header.boundingBox();
  await page.mouse.move(box!.x + 100, box!.y + 20); await page.mouse.down(); await page.mouse.move(box!.x - 80, box!.y + 5, { steps: 4 }); await page.mouse.up();
  const after = await panel.boundingBox(); expect(after!.x).toBeLessThan(before!.x - 100);
  await expect(panel).not.toHaveClass(/is-dragging/); expect(state.requests).toHaveLength(1);
  await panel.getByLabel("追问来源解释").fill("保留输入草稿");
  await header.focus(); await page.keyboard.press("ArrowLeft");
  expect((await panel.boundingBox())!.x).toBeLessThan(after!.x);
  await expect(panel.getByLabel("追问来源解释")).toHaveValue("保留输入草稿");
  await page.screenshot({ path: test.info().outputPath("explain-draggable-desktop.png") });
  await page.keyboard.press("Home"); expect(Math.abs((await panel.boundingBox())!.x - before!.x)).toBeLessThan(2);
  await page.setViewportSize({ width: 390, height: 844 });
  const narrow = await panel.boundingBox(); expect(narrow!.x).toBeGreaterThanOrEqual(0); expect(narrow!.x + narrow!.width).toBeLessThanOrEqual(390);
  await expect(panel.getByRole("button", { name: "关闭来源解释", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("explain-draggable-mobile.png") });
  expect(state.requests).toHaveLength(1);
});

test("图纸滚轮以指针缩放、中键拖动且目录收起后保留选择", async ({ page }) => {
  await fixture(page); await page.goto(`/projects/${projectId}`);
  await expandProjectTree(page); await expandWorkspace(page, "003.C");
  await page.getByRole("button", { name: /^003C01 PDF/ }).click();
  await page.getByRole("button", { name: "图纸预览", exact: true }).click();
  const preview = page.getByRole("region", { name: "原页预览", exact: true });
  const canvas = preview.locator(".drawing-canvas"), frame = canvas.locator(".evidence-image-frame");
  await expect(frame.locator("img")).toBeVisible();
  const bounds = await canvas.boundingBox();
  const x = bounds!.x + bounds!.width / 2, y = bounds!.y + 80;
  const before = await frame.boundingBox();
  await page.mouse.move(x, y); await page.mouse.wheel(0, -250);
  await expect(preview.locator(".preview-zoom-value")).not.toHaveText("100%");
  const after = await frame.boundingBox();
  expect(after!.width).toBeGreaterThan(before!.width);
  expect(Math.abs((x - before!.x) / before!.width - (x - after!.x) / after!.width)).toBeLessThan(.025);
  const left = await canvas.evaluate(node => node.scrollLeft);
  await page.mouse.down({ button: "middle" }); await page.mouse.move(x - 100, y - 65, { steps: 5 }); await page.mouse.up({ button: "middle" });
  expect(await canvas.evaluate(node => node.scrollLeft)).toBeGreaterThan(left + 70);
  await expect(canvas).not.toHaveClass(/is-panning/);
  await page.getByRole("button", { name: "收起项目目录", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "项目目录", exact: true })).toBeHidden();
  await expect(page.getByRole("button", { name: "展开项目目录", exact: true })).toHaveAttribute("aria-expanded", "false");
  await page.screenshot({ path: test.info().outputPath("drawing-navigation-sidebar-collapsed.png") });
  await page.getByRole("button", { name: "展开项目目录", exact: true }).click();
  await expect(page.getByRole("button", { name: /^003C01 PDF/ })).toHaveClass(/active/);
  await expect(preview.locator(".preview-zoom-value")).not.toHaveText("100%");
});

test("聊天先解释再展示各轮图纸，居中放大支持缩放和Esc返回", async ({ page }) => {
  const state = await fixture(page); const panel = await openRow(page);
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  const first = panel.locator(".explain-turn").first();
  await expect(first.getByRole("region", { name: "关联图纸", exact: true })).toBeVisible();
  expect(await first.evaluate(node => !!(node.querySelector(".explain-answer")!.compareDocumentPosition(node.querySelector(".explain-evidence")!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  const button = first.getByRole("button", { name: /放大查看 原页/ });
  await button.click();
  const lightbox = page.getByRole("dialog", { name: /^查看图纸 原页/ });
  await expect(lightbox).toBeVisible();
  const rect = await lightbox.boundingBox(), screen = page.viewportSize()!;
  expect(Math.abs(rect!.x + rect!.width / 2 - screen.width / 2)).toBeLessThan(2);
  await lightbox.getByRole("button", { name: "放大图纸", exact: true }).click();
  await expect(lightbox.getByRole("button", { name: "125%", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("explain-lightbox-desktop.png") });
  await page.keyboard.press("Escape");
  await expect(lightbox).toHaveCount(0); await expect(panel).toBeVisible(); await expect(button).toBeFocused();
  await panel.getByLabel("追问来源解释").fill("再解释一下端子来源");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.locator(".explain-turn")).toHaveCount(2);
  await expect(panel.getByLabel("解释回复").last()).toContainText("追问回复");
  expect(state.requests).toHaveLength(2);
  expect(await panel.locator(".explain-evidence").evaluateAll(nodes => nodes.every(node => node.parentElement?.classList.contains("explain-turn")))).toBe(true);
  await page.screenshot({ path: test.info().outputPath("explain-inline-evidence-followup.png") });
});

test("窄屏目录折叠和图纸放大关闭可用且不溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page);
  const panel = await openRow(page);
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  await panel.getByRole("button", { name: /放大查看 原页/ }).click();
  const lightbox = page.getByRole("dialog", { name: /^查看图纸/ });
  await expect(lightbox).toBeVisible();
  expect((await lightbox.boundingBox())!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("explain-lightbox-mobile.png") });
  await lightbox.getByRole("button", { name: "关闭图纸放大", exact: true }).click();
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "关闭来源解释", exact: true }).click();
  await page.getByRole("button", { name: "收起项目目录", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "项目目录", exact: true })).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("workbench-sidebar-mobile.png") });
});

test("行悬停打开独立浮窗，先显示工具状态，再流式展示获取链路", async ({ page }) => {
  const state = await fixture(page, { pauseTools: true, pauseAnswer: true });
  const panel = await openRow(page);
  await expect(panel).toBeVisible(); await expect(page.locator(".floating-agent-panel")).not.toBeVisible();
  await expect(panel.getByText("正在分析来源与关联图纸…")).toBeVisible();
  await panel.locator(".explain-tool > summary").first().click();
  await expect(panel.getByText("正在获取资料…")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("explain-loading-desktop.png") });
  state.releaseTools();
  await expect(panel.getByLabel("解释回复")).toHaveText("这条连接来自原页 003C01，");
  await expect(panel.getByText("返回 1 条连接 · 2 张图纸")).toBeVisible();
  state.releaseAnswer();
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  await expect(panel.getByRole("img")).toHaveCount(2);
  await expect(panel.locator(".explain-working")).toHaveCount(0);
  expect(state.requests[0].connection_id).toBe(rowId); expect(state.requests[0].record_version).toBe(1);
  await page.screenshot({ path: test.info().outputPath("explain-row-desktop.png") });
});

test("页码悬停查询整页，并在同一独立会话中追问", async ({ page }) => {
  const state = await fixture(page); await page.goto(`/projects/${projectId}`);
  const button = page.getByRole("button", { name: "解释本页 003C01", exact: true });
  await page.getByRole("cell", { name: "003C01", exact: false }).first().hover(); await button.click();
  const panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  await expect(panel.getByRole("status")).toContainText("发送后开始处理");
  expect(state.requests).toHaveLength(0);
  await panel.getByLabel("追问来源解释").fill("请解释本页连接来源");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  expect(state.requests[0].query).toEqual({ drawing_page: "003C01", pdf_page_number: 1, offset: 0, limit: 50 });
  expect(state.requests[0].connection_id).toBeUndefined();
  await panel.getByLabel("追问来源解释").fill("跨页依据是什么？"); await panel.getByRole("button", { name: "发送追问" }).click();
  await expect(panel.getByLabel("解释回复").last()).toContainText("追问回复：跨页依据是什么？");
  expect(state.requests[0].conversation_id).toBe(state.requests[1].conversation_id);
  expect(state.requests[0].turn_id).not.toBe(state.requests[1].turn_id);
});

test("无权限失败可见，重试沿用turn避免重复会话", async ({ page }) => {
  const state = await fixture(page, { denied: true }); const panel = await openRow(page);
  await expect(panel.getByRole("alert")).toContainText("没有项目访问权限");
  await page.screenshot({ path: test.info().outputPath("explain-denied.png") });
  state.permit(); await panel.getByRole("button", { name: "重试", exact: true }).click();
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  expect(state.requests[0].turn_id).toBe(state.requests[1].turn_id);
});

test("关闭浮窗取消流并恢复入口焦点，重新打开使用新会话", async ({ page }) => {
  const state = await fixture(page, { pauseTools: true }); const panel = await openRow(page);
  await expect(panel.getByText("正在分析来源与关联图纸…")).toBeVisible();
  await panel.getByRole("button", { name: "关闭来源解释" }).click();
  await expect(panel).toHaveCount(0); await expect(page.getByRole("button", { name: "解释端子 XA:8", exact: true })).toBeFocused();
  await expect.poll(state.closed).toBeGreaterThan(0);
  state.releaseTools(); await page.getByRole("button", { name: "解释端子 XA:8", exact: true }).click();
  await panel.getByLabel("追问来源解释").fill("请解释这条连接的来源");
  await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
  expect(state.requests[0].conversation_id).not.toBe(state.requests[1].conversation_id);
});

test("窄屏支持触屏入口、长文本及缺图状态", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, { brokenImage: true, longAnswer: true }); const panel = await openRow(page);
  await expect(panel.getByLabel("解释回复")).toContainText("很长的端子来源说明");
  await panel.getByRole("button", { name: "立即显示已收到内容" }).click();
  await expect(panel.getByText("图纸加载失败或链接过期")).toHaveCount(2);
  const bounds = await panel.boundingBox(); expect(bounds!.x).toBeGreaterThanOrEqual(0); expect(bounds!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("explain-narrow-long.png") });
});

test("停止生成保留部分回答并允许重试", async ({ page }) => {
  const state = await fixture(page, { pauseAnswer: true }); const panel = await openRow(page);
  await expect(panel.getByLabel("解释回复")).toHaveText("这条连接来自原页 003C01，");
  await panel.getByRole("button", { name: "停止生成" }).click();
  await expect(panel.getByText("已停止生成，以上内容可能不完整。")).toBeVisible();
  state.releaseAnswer(); await panel.getByRole("button", { name: "重试", exact: true }).click();
  await expect(panel.getByLabel("解释回复")).toContainText("通过引用匹配跨页");
});

test("登录页桌面与窄屏保持可用", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", route => route.fulfill({ status: 401, json: { detail: "not logged in" } }));
  await page.goto("/login"); await expect(page.locator(".login-page")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("login-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: test.info().outputPath("login-narrow.png") });
});

for (const completionOnly of [false, true]) {
  test(`${completionOnly ? "仅completed全文" : "单次大块delta"}也经过逐字缓冲且可立即显示`, async ({ page }) => {
    const markdown = "前端逐字缓冲测试。".repeat(65) + "\n\n## 连接内容\n\n- **起点端子**：`XD3:251`\n- **终点端子**：`+10-MA51:2`\n\n| 页码 | 类型 |\n| --- | --- |\n| 082R50 | 同页 |";
    await fixture(page, { wholeAnswer: markdown, completionOnly });
    const panel = await openRow(page); const answer = panel.getByLabel("解释回复");
    await expect(answer).toHaveAttribute("data-typing", "true");
    await expect(panel.getByRole("button", { name: "停止生成" })).toHaveCount(0);
    const first = (await answer.innerText()).length;
    expect(first).toBeLessThan(500);
    await expect.poll(async () => (await answer.innerText()).length).toBeGreaterThan(first);
    await expect(answer.getByRole("heading", { name: "连接内容", exact: true })).toHaveCount(0);
    await panel.getByRole("button", { name: "立即显示已收到内容" }).click();
    await expect(answer).toHaveAttribute("data-typing", "false");
    await expect(answer.getByRole("heading", { name: "连接内容", exact: true })).toBeVisible();
    await expect(answer.locator("strong").first()).toHaveText("起点端子");
    await expect(answer.locator("code").first()).toHaveText("XD3:251");
    await expect(answer.getByRole("cell", { name: "082R50" })).toBeVisible();
    expect(await answer.innerText()).not.toContain("**起点端子**");
  });
}

test("减少动态效果时立即呈现安全Markdown，桌面及窄屏排版正常", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const markdown = "这条记录表示一条**同页端子连接**。\n\n## 连接内容\n\n- **原理号**：`082R5001`\n- **起点端子**：`XD3:251`\n- **终点端子**：`+10-MA51:2`\n\n## 获取依据\n\n按放线标记读取两端，未保存的历史过程不作推测。\n\n<script>window.__explainInjected = true</script>\n\n[危险链接](javascript:alert(1))\n\n![不加载模型图片](https://invalid.example/tracker.png)";
  await fixture(page, { wholeAnswer: markdown });
  const panel = await openRow(page); const answer = panel.getByLabel("解释回复");
  await expect(answer.getByRole("heading", { name: "获取依据" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "立即显示已收到内容" })).toHaveCount(0);
  await expect(answer.locator("script, img, a[href^='javascript:']")).toHaveCount(0);
  expect(await page.evaluate(() => "__explainInjected" in window)).toBe(false);
  await page.screenshot({ path: test.info().outputPath("markdown-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("markdown-narrow.png") });
});

test("停止时冻结可见文字，重试重新建立缓冲且不会拆开emoji", async ({ page }) => {
  const prefix = "😀🚀已读取连接资料。".repeat(70);
  const state = await fixture(page, { firstChunk: prefix, pauseAnswer: true });
  const panel = await openRow(page); const answer = panel.getByLabel("解释回复");
  await expect.poll(async () => (await answer.innerText()).length).toBeGreaterThan(5);
  const hasBrokenSurrogate = await answer.evaluate(element => Array.from(element.textContent ?? "").some(value => /^[\uD800-\uDFFF]$/.test(value)));
  expect(hasBrokenSurrogate).toBe(false);
  await panel.getByRole("button", { name: "停止生成" }).click();
  const stopped = await answer.innerText();
  await page.waitForTimeout(180);
  await expect(answer).toHaveText(stopped);
  expect(stopped.length).toBeLessThan(prefix.length);
  await expect(answer).toHaveAttribute("data-typing", "false");
  state.releaseAnswer(); await panel.getByRole("button", { name: "重试", exact: true }).click();
  await expect(answer).toHaveAttribute("data-typing", "true");
  await panel.getByRole("button", { name: "立即显示已收到内容" }).click();
  await expect(answer).toContainText("通过引用匹配跨页");
});
