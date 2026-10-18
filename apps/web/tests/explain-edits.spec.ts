import { test, expect, type Page } from "@playwright/test";

const project = "00000000-0000-0000-0000-000000000010";
const rowId = "00000000-0000-0000-0000-000000000011";
const draftId = "00000000-0000-0000-0000-000000000012";
async function fixture(page: Page, options: { conflict?: boolean; restored?: boolean; many?: boolean; denied?: boolean; processing?: boolean; repair?: boolean; repairFails?: boolean; moved?: boolean; swap?: boolean } = {}) {
  let version = 1; let terminal = "XD10:1"; let status = "pending"; let deleted = false;
  const decisions: Record<string, unknown>[] = []; const turns: Record<string, unknown>[] = []; const deletions: Record<string, unknown>[] = [];
  const changes = Array.from({ length: options.many ? 26 : 1 }, (_, i) => ({ connection_id: i ? `00000000-0000-0000-0000-${String(i + 40).padStart(12, "0")}` : rowId, record_version: 1, principle_number: `P${i + 1}`, before: { end_terminal: "XD10:1", end_terminal_coordinates: { x: .2, y: .4, pdf_page_number: 1 }, ...(options.moved ? { source_drawing_page: "003C01", source_pdf_page_number: 1, workspace_code: "003.C" } : {}) }, after: { end_terminal: "10:1", end_terminal_coordinates: null, ...(options.moved ? { source_drawing_page: "006M01", source_pdf_page_number: 2, workspace_code: "006.M" } : {}) } }));
  const proposal = () => ({ proposal_id: draftId, project_id: project, batch_id: "batch-a", checksum: "sha256:" + "a".repeat(64), status,
    request: { scope: { workspace_code: "003.C" }, operation: options.moved || options.swap ? { kind: "swap_endpoints" } : { kind: "remove_terminal_prefix", endpoint: "end", prefix: "XD" }, reason: "用户明确修改" }, matched_count: changes.length + 1, changed_count: changes.length, changes, created_at: "2026-10-18T00:00:00Z", expires_at: "2026-10-19T00:00:00Z" });

  const row = () => ({ connection_id: rowId, project_id: project, batch_id: "batch-a", record_version: version, workspace_id: "work", workspace_name: "003.C", drawing_id: "drawing", workspace_page: "003C01", pdf_page_number: 1, principle_number: "P1", start_code: "A", start_terminal: "XA:8", end_terminal: terminal, is_cross_page: false });
  const context = () => ({ project_name: "修改测试项目", row: { ...row(), id: rowId, source_pdf_page_number: 1 }, drawings: [], recorded: {}, evidence_path: [], gaps: [] });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", expiresIn: 3600, user: { id: "owner", name: "工程师", role: "工程师" } } });
    const detail = { id: project, name: "修改测试项目", status: options.processing ? "processing" : "ready", updated_at: "2026-10-18", standard_profile: "zh", source_saved: false, batch_id: "batch-a", workspaces: [{ id: "work", code: "003.C", name: "003.C", drawings: [{ id: "drawing", workspace_id: "work", workspace_page: "003C01", pdf_page_number: 1, status: "completed" }] }, ...(options.moved ? [{ id: "target-work", code: "006.M", name: "006.M", drawings: [{ id: "target-drawing", workspace_id: "target-work", workspace_page: "006M01", pdf_page_number: 2, status: "completed" }] }] : [])] };
    if (path === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (path === `/api/v1/projects/${project}`) return route.fulfill({ json: detail });
    if (path.endsWith("/connections")) {
      const filters = new URL(route.request().url()).searchParams;
      const moved = options.moved && status === "applied";
      const items = [
        ...deleted ? [] : [{ ...row(), ...(moved ? { drawing_id: "target-drawing", workspace_id: "target-work", workspace_page: "006M01", pdf_page_number: 2 } : {}) }],
      ].filter(item => (!filters.get("drawing_id") || item.drawing_id === filters.get("drawing_id")) && (!filters.get("workspace_id") || item.workspace_id === filters.get("workspace_id")));
      return route.fulfill({ json: { items, batch_id: "batch-a", offset: 0, limit: 100, has_more: false } });
    }
    if (path.endsWith(`/connections/${rowId}`) && route.request().method() === "DELETE") { deletions.push(route.request().postDataJSON()); deleted = true; return route.fulfill({ json: { connection_id: rowId, batch_id: "batch-a", action: "remove", record_version: version, idempotent: false } }); }
    if (path.endsWith("/connection-edits")) return route.fulfill({ json: options.restored && status === "pending" && !deleted ? [proposal()] : [] });
    if (path.endsWith("/decision")) {
      const body = route.request().postDataJSON(); decisions.push(body);
      if (options.denied || options.conflict) return route.fulfill({ status: options.denied ? 403 : 409, json: { detail: { message: options.denied ? "没有项目操作权限" : "数据已变更，请刷新后重试" } } });
      status = body.accepted ? "applied" : "rejected"; if (body.accepted) { version = 2; terminal = "10:1"; }
      return route.fulfill({ json: { proposal_id: draftId, project_id: project, batch_id: "batch-a", status, changed_count: body.accepted ? changes.length : 0, versions: body.accepted ? { [rowId]: 2 } : {}, idempotent: false } });
    }
    if (path.endsWith("/explain/turns/stream")) {
      const body = route.request().postDataJSON(); turns.push(body); const editing = String(body.message).includes("XD前缀");
      const answer = editing ? "我已按003.C工作区生成逐行修改对照，尚未保存。".repeat(35) : "当前保存的终点是 " + terminal + "。";
      const event = (type: string, data: object) => `event: ${type}\ndata: ${JSON.stringify({ type, conversation_id: body.conversation_id, turn_id: body.turn_id, ...data })}\n\n`;
      const repair = editing && (options.repair || options.repairFails) ? event("answer_delta", { delta: "已生成虚构修改预览，不实内容应被撤回" }) + event("answer_reset", { delta: "" }) : "";
      if (editing && options.repairFails) return route.fulfill({ contentType: "text/event-stream", body: event("context", { context: context() }) + repair + "event: error\ndata: " + JSON.stringify({ message: "模型未生成可确认的修改方案，线表未改动。请重试。" }) + "\n\n" });
      return route.fulfill({ contentType: "text/event-stream", body: event("context", { context: context() }) + repair + (editing ? event("edit_proposal", { proposal: proposal() }) : "") + event("answer_delta", { delta: answer }) + event("completed", { result: { conversation_id: body.conversation_id, turn_id: body.turn_id, answer, context: context(), retrievals: [], drawings: [], gaps: [], proposals: editing ? [proposal()] : [], history_reset: version > 1 } }) });
    }
    return route.fulfill({ status: 404, json: { detail: "未定义夹具" } });
  });
  return { decisions, turns, deletions };
}
async function open(page: Page, navigate = true) {
  if (navigate) await page.goto(`/projects/${project}`);
  const cell = page.getByRole("cell").filter({ has: page.getByRole("button", { name: "解释端子 XA:8", exact: true }) });
  await cell.hover(); await cell.getByRole("button", { name: "解释端子 XA:8", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "来源解释", exact: true });
  await expect(panel.getByLabel("解释回复")).toContainText("当前保存的终点");
  return panel;
}
async function propose(page: Page) {
  const panel = await open(page);
  await panel.getByLabel("追问来源解释").fill("把003.C工作区终点的XD前缀去掉"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByLabel("解释回复").last()).toHaveAttribute("data-typing", "true");
  await expect(panel.getByRole("region", { name: "线表修改预览" })).toHaveCount(0);
  await panel.getByRole("button", { name: "立即显示已收到内容" }).last().click();
  await expect(panel.getByRole("region", { name: "线表修改预览" })).toBeVisible();
  return panel;
}

test("先显示回答再展示逐行对照，确认后刷新表格并用新行版本追问", async ({ page }) => {
  const state = await fixture(page); const panel = await propose(page);
  expect(state.decisions).toHaveLength(0);
  await expect(panel.getByRole("cell", { name: "XD10:1", exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: "确认修改 1 行", exact: true })).toBeInViewport();
  await page.screenshot({ path: test.info().outputPath("explain-edit-preview-desktop.png") });
  await panel.getByRole("button", { name: "确认修改 1 行", exact: true }).click(); await expect(panel.getByText("已保存 1 行修改", { exact: false })).toBeVisible();
  await expect(page.locator(".result-table").getByRole("cell", { name: "10:1", exact: true })).toBeVisible();
  await panel.getByLabel("追问来源解释").fill("解释修改后的值"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect.poll(() => state.turns.at(-1)?.record_version).toBe(2);
  expect(state.decisions[0]).toEqual({ accepted: true, checksum: "sha256:" + "a".repeat(64) });
});

test("整组交换后留在原页和工作区，搜索筛选及行ID保持", async ({ page }) => {
  await fixture(page, { swap: true, restored: true });
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "003C01 PDF 第 1 页 completed", exact: true }).click();
  await page.getByLabel("搜索线表").fill("P1");
  const panel = await open(page, false);
  await panel.getByRole("button", { name: "确认修改 1 行", exact: true }).click();
  await expect(panel.getByText("记录所属页、工作区和ID保持不变。", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "关闭来源解释", exact: true }).click();
  await expect(page.locator(".result-table").getByRole("cell", { name: "P1", exact: true })).toBeVisible();
  await expect(page.locator(".result-table").getByText("003C01", { exact: true })).toBeVisible();
  await expect(page.getByLabel("搜索线表")).toHaveValue("P1");
  await expect(page.getByRole("button", { name: "003C01 PDF 第 1 页 completed", exact: true })).toHaveClass(/active/);
  await page.screenshot({ path: test.info().outputPath("explain-swap-keeps-origin-desktop.png") });
});

test("旧迁页方案停用，不能点击确认导致行离开当前页", async ({ page }) => {
  const state = await fixture(page, { moved: true, restored: true });
  const panel = await open(page);
  await expect(panel.getByRole("alert")).toContainText("旧方案包含记录所属页或工作区变更");
  await expect(panel.getByRole("button", { name: "确认修改 1 行", exact: true })).toBeDisabled();
  expect(state.decisions).toHaveLength(0);
});

test("永久删行后关闭旧解释与修改方案，重新加载仍为空", async ({ page }) => {
  const state = await fixture(page, { restored: true });
  const panel = await open(page);
  await expect(panel.getByRole("region", { name: "线表修改预览" })).toBeVisible();
  page.once("dialog", dialog => { expect(dialog.message()).toContain("永久删除"); return dialog.accept(); });
  await page.getByRole("button", { name: "删除 XA:8", exact: true }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.locator(".result-table")).toHaveCount(0);
  expect(state.deletions).toEqual([{ record_version: 1, confirmed: true }]);
  await page.reload();
  await expect(page.getByText("当前范围没有线表记录", { exact: true })).toBeVisible();
});

test("拒绝修改不会刷新成新值", async ({ page }) => {
  const state = await fixture(page); const panel = await propose(page);
  await panel.getByRole("button", { name: "拒绝修改", exact: true }).click(); await expect(panel.getByText("已拒绝，此方案未修改线表。", { exact: true })).toBeVisible();
  expect(state.decisions[0].accepted).toBe(false); await expect(page.locator(".result-table").getByRole("cell", { name: "XD10:1", exact: true })).toBeVisible();
});

for (const denied of [false, true]) test(`提交${denied ? "无权限" : "版本冲突"}保留预览且不伪造成功`, async ({ page }) => {
  await fixture(page, { conflict: !denied, denied }); const panel = await propose(page);
  await panel.getByRole("button", { name: "确认修改 1 行", exact: true }).click(); await expect(panel.getByRole("alert")).toContainText(denied ? "没有项目操作权限" : "数据已变更");
  await expect(panel.getByText("已保存 1 行修改", { exact: false })).toHaveCount(0); await expect(page.locator(".result-table").getByRole("cell", { name: "XD10:1", exact: true })).toBeVisible();
});

test("刷新恢复待确认方案，全部变更可翻页，窄屏不溢出", async ({ page }) => {
  await fixture(page, { restored: true, many: true }); await page.setViewportSize({ width: 390, height: 844 });
  const panel = await open(page); const preview = panel.getByRole("region", { name: "线表修改预览" });
  await expect(preview).toBeVisible(); await expect(preview.getByText("匹配 27 行，实际修改 26 行。", { exact: false })).toBeVisible();
  await preview.getByRole("button", { name: "下一组", exact: true }).click(); await expect(preview.getByRole("cell", { name: "P26", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("explain-edit-preview-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("提取中保留解释，禁止提交已有修改方案", async ({ page }) => {
  const state = await fixture(page, { restored: true, processing: true }); const panel = await open(page);
  await expect(panel.getByText("提取处理中，暂不能保存线表修改", { exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: "确认修改 1 行", exact: true })).toBeDisabled();
  expect(state.decisions).toHaveLength(0);
});

test("撤回口述假预览，真实方案返回后才显示确认按钮", async ({ page }) => {
  const state = await fixture(page, { repair: true }); const panel = await propose(page);
  await expect(panel.getByLabel("解释回复").last()).not.toContainText("虚构修改预览");
  await expect(panel.getByRole("button", { name: "确认修改 1 行", exact: true })).toBeVisible();
  expect(state.decisions).toHaveLength(0);
});

test("补调仍未生成方案时提示失败，输入确认不会出现可提交方案", async ({ page }) => {
  const state = await fixture(page, { repairFails: true }); const panel = await open(page);
  await panel.getByLabel("追问来源解释").fill("把003.C工作区终点的XD前缀去掉"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("未生成可确认的修改方案");
  await expect(panel.getByText("虚构修改预览", { exact: false })).toHaveCount(0);
  await expect(panel.getByRole("region", { name: "线表修改预览" })).toHaveCount(0);
  await panel.getByLabel("追问来源解释").fill("确认"); await panel.getByRole("button", { name: "发送追问", exact: true }).click();
  await expect.poll(() => state.turns.at(-1)?.message).toBe("确认");
  await expect(panel.getByRole("region", { name: "线表修改预览" })).toHaveCount(0);
  expect(state.decisions).toHaveLength(0);
});
