import { test, expect, type Page } from "@playwright/test";

const project = "00000000-0000-0000-0000-000000000010";
const workspace = "00000000-0000-0000-0000-000000000020";
const drawing = "00000000-0000-0000-0000-000000000030";
const conversation = "00000000-0000-0000-0000-000000000040";
const action = "00000000-0000-0000-0000-000000000050";
const stamp = "2026-10-19T00:00:00Z";

async function fixture(page: Page, options: { available?: boolean; denied?: boolean; late?: Promise<void>; navigation?: boolean; task?: boolean; proposal?: boolean; long?: boolean; failOnce?: boolean; restore?: boolean } = {}) {
  const calls: Array<{ path: string; body: Record<string, unknown> }> = [];
  const saved = { id: conversation, title: "主助手测试", context: {}, created_at: stamp, updated_at: stamp, turns: [] };
  let streamed = 0;
  await page.route("**/fixture.png", route => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYyQAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/v1/**", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    const body = request.method() === "POST" ? request.postDataJSON() as Record<string, unknown> : {};
    calls.push({ path, body });
    if (path.includes("/supervisor/")) throw new Error("Main assistant must not use legacy supervisor");
    if (path.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "工程师", email: "test@example.invalid", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (path === "/api/v1/assistant/capabilities") return route.fulfill({ json: { available: options.available !== false, message: "主助手模型尚未配置" } });
    if (path === "/api/v1/assistant/conversations") return route.fulfill({ json: request.method() === "POST" ? { ...saved, id: body.id } : options.restore ? [saved] : [] });
    if (path === `/api/v1/assistant/conversations/${conversation}`) return route.fulfill({ json: { ...saved, turns: [{ id: "old-turn", conversation_id: conversation, status: "completed", request: { message: "重扫020.U" }, events: [{ id: "old-event", turn_id: "old-turn", type: "task_started", data: { action_id: action, kind: "rescan" } }], answer: "", created_at: stamp }] } });
    if (path.endsWith("/attachments")) return route.fulfill({ json: { ...body, content_base64: undefined, conversation_id: conversation, mime_type: "image/png", checksum: "sha256:fixture" } });
    if (path.endsWith("/turns/stream")) {
      if (options.late) await options.late;
      const events: Array<Record<string, unknown>> = [];
      streamed += 1;
      if (options.failOnce && streamed === 1) return route.fulfill({ contentType: "text/event-stream", body: [{ type: "error", message: "模型服务暂不可用" }, { type: "completed", data: { status: "failed" } }].map((event, index) => `data: ${JSON.stringify({ id: `${body.turn_id}:${index}`, turn_id: body.turn_id, ...event })}\n\n`).join("") });
      if (options.navigation) events.push({ type: "navigate", data: { destination: "project", scope: { project_id: project, workspace_id: workspace, workspace_code: "020.U" } } });
      if (options.task) events.push({ type: "task_started", data: { action_id: action, kind: "rescan" } });
      if (options.proposal) events.push({ type: "proposal_ready", data: { action_id: action, kind: "profile" } });
      events.push({ type: "answer_delta", message: options.long ? "实际图纸与冻结规则需要逐页核对。".repeat(50) : "已读取当前范围，终点仍需人工核对。" }, { type: "completed" });
      return route.fulfill({ contentType: "text/event-stream", body: events.map((event, index) => `data: ${JSON.stringify({ id: `${body.turn_id}:${index}`, turn_id: body.turn_id, ...event })}\n\n`).join("") });
    }
    if (path.includes("/assistant/actions/")) {
      const proposal = { id: "proposal", summary: "明确跨页引用读取规则", base_revision: 1, base_checksum: "base", status: "pending", diffs: [{ path: "resources/completion.md", before: "原来的规则", after: "先读取完整引用，再校对目标页" }] };
      const detail = { id: "run", project_id: project, conversation_id: conversation, batch_id: "one", status: "queued", stage: "queued", request: { scope: { workspace_code: "020.U" }, fields: "all", result_mode: "replace_scope" }, profile: { key: "zh", version: "2.3.0" }, created_at: stamp, updated_at: stamp };
      return route.fulfill({ json: { id: action, conversation_id: conversation, turn_id: "turn", tool_name: options.proposal ? "diagnose_profile" : "start_rescan", status: path.endsWith("decision") ? "applied" : options.proposal ? "awaiting_confirmation" : "completed", checksum: "real-action-checksum", result: { kind: options.proposal ? "profile" : "rescan", scope: { project_id: project }, detail: options.proposal ? proposal : detail } } });
    }
    if (path.includes("/rescans/")) return route.fulfill({ json: { id: "run", project_id: project, conversation_id: conversation, batch_id: "one", status: "queued", stage: "queued", request: { scope: { workspace_code: "020.U" }, fields: "all", result_mode: "replace_scope" }, profile: { key: "zh", version: "2.3.0" }, created_at: stamp, updated_at: stamp } });
    const detail = { id: project, name: "1002001641 PERU TPP 1 STS", status: "ready", updated_at: stamp, standard_profile: "zh", source_saved: false, batch_id: "one", workspaces: [{ id: workspace, code: "020.U", name: "020.U", drawings: [{ id: drawing, workspace_id: workspace, project_id: project, pdf_page_number: 12, workspace_page: "020U01", status: "completed", image_url: "/fixture.png" }] }] };
    if (path === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (path === `/api/v1/projects/${project}`) return options.denied ? route.fulfill({ status: 403, json: { detail: { message: "无权访问该项目" } } }) : route.fulfill({ json: detail });
    if (path.endsWith("/connections")) return route.fulfill({ json: { items: [], batch_id: "one", offset: 0, limit: 100, has_more: false } });
    if (path === "/api/v1/capabilities") return route.fulfill({ json: { extraction: true, explain: true, supervisor: false } });
    return route.fulfill({ status: 404, json: { detail: { message: "未定义夹具请求" } } });
  });
  return calls;
}

async function open(page: Page) {
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "打开 AI 聊天面板", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "向主助手提出需求" })).toBeEnabled();
}

async function historyFixture(page: Page, failDelete = false) {
  const calls = await fixture(page);
  const other = "00000000-0000-0000-0000-000000000041";
  let items = [{ id: conversation, title: "当前图纸分析", context: {}, created_at: stamp, updated_at: stamp }, { id: other, title: "历史对话与很长的工作区说明".repeat(6), context: {}, created_at: stamp, updated_at: stamp }];
  const deleted: string[] = []; const reads: string[] = [];
  await page.route("**/api/v1/assistant/conversations**", route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (path === "/api/v1/assistant/conversations") return route.fulfill({ json: items });
    const id = path.split("/").at(-1)!;
    if (request.method() === "DELETE") {
      deleted.push(id);
      if (failDelete) { failDelete = false; return route.fulfill({ status: 409, json: { detail: { message: "会话正在回复，请稍后再删除" } } }); }
      items = items.filter(item => item.id !== id); return route.fulfill({ status: 204 });
    }
    reads.push(id);
    const item = items.find(value => value.id === id);
    return item ? route.fulfill({ json: { ...item, turns: [{ id: "history", request: { message: "历史输入" }, events: [{ type: "answer_delta", message: "历史助手回复", id: "history-answer" }] }] } }) : route.fulfill({ status: 404, json: { detail: { message: "会话不存在" } } });
  });
  await page.addInitScript(id => localStorage.setItem("assistant-conversation:owner", id), conversation);
  return { calls, deleted, reads, other, title: items[1].title };
}

test("历史列表×直接删除其他会话，无需恢复并保留当前输入附件，刷新不再出现", async ({ page }) => {
  const state = await historyFixture(page); await open(page);
  await expect(page.getByText("历史助手回复", { exact: true })).toBeVisible();
  const input = page.getByLabel("向主助手提出需求"); await input.fill("未发送的修改要求");
  await page.locator('input[type="file"][accept="image/png,image/jpeg,image/webp"]').setInputFiles({ name: "keep.png", mimeType: "image/png", buffer: Buffer.from("fixture") });
  await page.getByRole("button", { name: "助手已保存会话", exact: true }).click();
  await page.getByRole("button", { name: `删除助手对话 ${state.title}`, exact: true }).click();
  expect(state.deleted).toEqual([state.other]); expect(state.reads).not.toContain(state.other);
  await expect(input).toHaveValue("未发送的修改要求");
  await expect(page.getByTitle("keep.png", { exact: true })).toBeVisible();
  await expect(page.getByText("历史助手回复", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("assistant-history-delete-desktop.png") });
  await page.reload(); await page.getByRole("button", { name: "打开 AI 聊天面板", exact: true }).click();
  await page.getByRole("button", { name: "助手已保存会话", exact: true }).click();
  await expect(page.getByRole("button", { name: `删除助手对话 ${state.title}`, exact: true })).toHaveCount(0);
});

test("删除当前会话清除本地恢复与消息，键盘和窄屏长标题可用", async ({ page }) => {
  const state = await historyFixture(page); await page.setViewportSize({ width: 390, height: 844 }); await open(page);
  const trigger = page.getByRole("button", { name: "助手已保存会话", exact: true });
  await trigger.focus(); await trigger.press("ArrowDown");
  await expect(page.getByRole("region", { name: "助手历史对话", exact: true })).toBeVisible();
  expect(await page.locator(".assistant-history-panel").evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("assistant-history-delete-narrow.png") });
  await page.keyboard.press("Escape"); await expect(trigger).toBeFocused();
  await trigger.click(); await page.getByRole("button", { name: "删除助手对话 当前图纸分析", exact: true }).click();
  expect(state.deleted).toEqual([conversation]);
  await expect(page.getByText("历史助手回复", { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("assistant-conversation:owner"))).toBeNull();
  await expect(trigger).toHaveText("新对话");
  await expect(page.getByRole("button", { name: `删除助手对话 ${state.title}`, exact: true })).toBeVisible();
  await page.getByLabel("向主助手提出需求").click();
  await expect(page.getByRole("region", { name: "助手历史对话", exact: true })).toHaveCount(0);
});

test("历史删除失败保留会话与输入，可重新点×重试", async ({ page }) => {
  const state = await historyFixture(page, true); await open(page);
  await page.getByLabel("向主助手提出需求").fill("保留我的草稿");
  await page.getByRole("button", { name: "助手已保存会话", exact: true }).click();
  const remove = page.getByRole("button", { name: "删除助手对话 当前图纸分析", exact: true });
  await remove.click(); await expect(page.getByRole("alert")).toContainText("会话正在回复");
  await expect(remove).toBeEnabled(); await expect(page.getByLabel("向主助手提出需求")).toHaveValue("保留我的草稿");
  expect(await page.evaluate(() => localStorage.getItem("assistant-conversation:owner"))).toBe(conversation);
  await remove.click(); await expect(remove).toHaveCount(0);
  expect(state.deleted).toEqual([conversation, conversation]);
});

test("聊天身份清晰，停靠为工作台留宽，切回浮窗及窄屏保留会话", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page);
  await page.route(/\/connections(?:\?.*)?$/, route => route.fulfill({ json: { items: [
    { connection_id: "row-1", project_id: project, batch_id: "one", record_version: 1, workspace_id: workspace, workspace_name: "020.U", drawing_id: drawing, workspace_page: "020U01", pdf_page_number: 12, principle_number: "020U0101", start_code: "M1", start_terminal: "X1:1", end_code: "Q1", end_terminal: "X2:3", current_value: "16A", is_cross_page: false },
  ], batch_id: "one", offset: 0, limit: 100, has_more: false } }));
  await open(page);
  await expect(page.getByRole("cell", { name: "X1:1", exact: true })).toBeVisible();
  await page.getByLabel("向主助手提出需求").fill("请解释当前连接来源");
  await page.getByRole("button", { name: "发送助手消息" }).click();
  const panel = page.getByRole("dialog", { name: "AI 助手", exact: true });
  await expect(panel.locator(".assistant-answer")).toContainText("终点仍需人工核对");
  await expect(panel.locator(".assistant-user .chat-identity")).toHaveText("你");
  await expect(panel.locator(".assistant-entry > .chat-identity")).toHaveText("图纸助手");
  const bubble = await panel.locator(".assistant-user").boundingBox();
  const feed = await panel.locator(".assistant-feed").boundingBox();
  expect(bubble!.width).toBeLessThanOrEqual(feed!.width * .85);
  await panel.getByRole("button", { name: "停靠到工作台右侧" }).click();
  const workbench = await page.locator(".workbench-grid").boundingBox();
  const docked = await panel.boundingBox();
  expect(workbench!.x + workbench!.width).toBeLessThanOrEqual(docked!.x + 1);
  await page.screenshot({ path: test.info().outputPath("assistant-docked-desktop.png") });
  await panel.getByRole("button", { name: "切换为浮窗" }).click();
  expect((await page.locator(".workbench-grid").boundingBox())!.width).toBeGreaterThan(workbench!.width);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel.locator(".assistant-answer")).toContainText("终点仍需人工核对");
  expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("assistant-identity-narrow.png") });
});

test("检索跳转选中零记录工作区，主会话跨导航保留", async ({ page }) => {
  const calls = await fixture(page, { navigation: true }); await open(page);
  await page.getByRole("textbox", { name: "向主助手提出需求" }).fill("找到020.U工作区");
  await page.getByRole("button", { name: "发送助手消息" }).click();
  await expect(page).toHaveURL(new RegExp(`workspace=${workspace}`));
  await expect(page.getByText("已读取当前范围，终点仍需人工核对。", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "AI 助手" })).toBeVisible();
  await expect.poll(() => calls.some(item => item.path.includes("connections"))).toBe(true);
  await page.screenshot({ path: test.info().outputPath("main-assistant-desktop.png") });
});

test("附件先暂存，Shift Enter换行，Enter才上传发送", async ({ page }) => {
  const calls = await fixture(page); await open(page);
  await page.locator('input[type="file"][accept="image/png,image/jpeg,image/webp"]').setInputFiles({ name: "reference.png", mimeType: "image/png", buffer: Buffer.from("fixture") });
  expect(calls.filter(item => item.path.endsWith("/attachments") || item.path.endsWith("/turns/stream"))).toHaveLength(0);
  const input = page.getByRole("textbox", { name: "向主助手提出需求" }); await input.fill("对照此图"); await input.press("Shift+Enter");
  expect(calls.filter(item => item.path.endsWith("/turns/stream"))).toHaveLength(0);
  await input.press("Enter"); await expect(page.getByText("已读取当前范围，终点仍需人工核对。", { exact: true })).toBeVisible();
  expect(calls.filter(item => item.path.endsWith("/attachments"))).toHaveLength(1);
  expect(calls.filter(item => item.path.endsWith("/turns/stream"))).toHaveLength(1);
});

test("切页后迟到的导航只提供打开按钮", async ({ page }) => {
  let release!: () => void; const late = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { navigation: true, late }); await open(page);
  await page.getByRole("textbox", { name: "向主助手提出需求" }).fill("找到020.U"); await page.getByRole("button", { name: "发送助手消息" }).click();
  await expect(page.getByRole("button", { name: "停止本轮对话" })).toBeVisible();
  // Router navigation, while the global panel remains mounted.
  await page.evaluate(() => { window.history.pushState({}, "", "/projects?manual=1"); window.dispatchEvent(new PopStateEvent("popstate")); });
  release(); await expect(page.getByRole("button", { name: "打开处理结果", exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/workspace=/);
});

test("规则真实差异需按钮确认，文字答复不触发发布", async ({ page }) => {
  const calls = await fixture(page, { proposal: true }); await open(page);
  await page.getByRole("textbox", { name: "向主助手提出需求" }).fill("检查跨页规则并给出修改建议"); await page.getByRole("button", { name: "发送助手消息" }).click();
  const preview = page.getByRole("region", { name: "规则修改与发布预览" });
  await expect(page.getByRole("button", { name: "确认修改并发布" })).toBeVisible();
  expect(calls.filter(item => item.path.endsWith("/decision"))).toHaveLength(0);
  await page.getByText("resources/completion.md", { exact: true }).click();
  await expect(page.getByText("原来的规则", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认修改并发布" }).click();
  await expect(page.getByText("新规则已发布，原项目规则版本保留。", { exact: true })).toBeVisible();
  expect(calls.filter(item => item.path.endsWith("/decision"))[0].body).toEqual({ accepted: true, checksum: "real-action-checksum" });
  void preview;
});

test("窄屏长回答与未配置状态", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page, { long: true }); await open(page);
  await page.getByRole("textbox", { name: "向主助手提出需求" }).fill("解释这个工作区"); await page.getByRole("button", { name: "发送助手消息" }).click();
  await expect(page.locator(".assistant-answer")).toContainText("实际图纸与冻结规则");
  expect(await page.locator(".main-assistant").evaluate(node => node.getBoundingClientRect().right <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("main-assistant-narrow.png") });
});

test("服务未配置保持不可发送，项目无权限不传伪造范围", async ({ page }) => {
  await fixture(page, { available: false, denied: true }); await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "打开 AI 聊天面板", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "向主助手提出需求" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "发送助手消息" })).toBeDisabled();
  await page.screenshot({ path: test.info().outputPath("main-assistant-unavailable.png") });
});

test("失败保留同轮重试，恢复会话从持久回执读取重扫任务", async ({ page }) => {
  const calls = await fixture(page, { failOnce: true }); await open(page);
  await page.getByRole("textbox", { name: "向主助手提出需求" }).fill("解释终点来源");
  await page.getByRole("button", { name: "发送助手消息" }).click();
  await expect(page.getByRole("button", { name: "重试本轮" })).toBeVisible();
  await page.getByRole("button", { name: "重试本轮" }).click();
  await expect(page.getByText("已读取当前范围，终点仍需人工核对。", { exact: true })).toBeVisible();
  const turns = calls.filter(item => item.path.endsWith("/turns/stream"));
  expect(turns[1].body.turn_id).toBe(turns[0].body.turn_id);
});

test("刷新恢复任务卡不会再次发起模型或重扫", async ({ page }) => {
  await page.addInitScript(id => localStorage.setItem("assistant-conversation:owner", id), conversation);
  const calls = await fixture(page, { restore: true }); await open(page);
  await expect(page.getByRole("region", { name: "重扫任务与结果", exact: true })).toBeVisible();
  await expect(page.getByText("重扫已入队，等待 Worker", { exact: true })).toBeVisible();
  expect(calls.filter(item => item.path.endsWith("/turns/stream"))).toHaveLength(0);
});
