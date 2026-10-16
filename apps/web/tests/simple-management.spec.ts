import { test, expect, type Page } from "@playwright/test";

// Explicit HTTP fixtures; the real local DB/Storage path is validated separately.
const projectId = "00000000-0000-0000-0000-000000000010";
const profileId = "00000000-0000-0000-0000-000000000011";
const sourceId = "00000000-0000-0000-0000-000000000012";
const targetId = "00000000-0000-0000-0000-000000000013";
const workspaceId = "00000000-0000-0000-0000-000000000014";
const rowId = "00000000-0000-0000-0000-000000000015";
const drawing = (id: string, page: number) => ({ id, project_id: projectId, workspace_id: workspaceId, pdf_page_number: page, workspace_page: `003C0${page}`, status: "scanned", image_url: "/fixture.png" });

async function fixture(page: Page, options: { empty?: boolean; failList?: boolean; denied?: boolean; failSave?: boolean; noIndex?: boolean; longName?: boolean; loading?: Promise<void>; realtime?: boolean; streamFailures?: number } = {}) {
  let exists = !options.empty;
  let failSave = options.failSave;
  const calls: string[] = []; const keys: string[] = [];
  const detail = { id: projectId, name: options.longName ? "超长项目名称用于验证布局和换行".repeat(10) : "三表回归夹具项目", owner_id: "owner", status: "ready", profile_id: profileId, standard_profile: "zh", updated_at: "2026-10-16", source_saved: true, sources: [{ id: projectId, original_filename: "fixture.pdf", page_count: 2 }], workspaces: options.noIndex ? [] : [{ id: workspaceId, code: "003.C", name: "003.C", drawings: [drawing(sourceId, 1), drawing(targetId, 2)] }], batch_id: options.noIndex ? null : "run-one", extraction_available: false };
  const row = { connection_id: rowId, project_id: projectId, batch_id: "run-one", workspace_id: workspaceId, workspace_name: "003.C", drawing_id: sourceId, workspace_page: "003C01", pdf_page_number: 1, row_order: 0, wire_number: null, record_version: 1, start_code: "+01F10", start_terminal: "XA:8", end_code: "+01F12.1", end_terminal: "XD10:1", is_cross_page: true, needs_review: false };
  let phase = 0; let streamFailures = options.streamFailures ?? 0;
  const progress = () => ({ run_id: "run-one", stage: phase === 0 ? "render" : phase === 1 ? "scan" : phase === 2 ? "completion" : "finished", total_pages: 2, rendered_pages: phase === 0 ? 1 : 2, classified_pages: phase === 0 ? 0 : 2, completed_pages: phase === 3 ? 2 : 0, row_count: phase ? 1 : 0 });
  const payload = () => options.realtime ? { ...detail, status: phase === 3 ? "ready" : "processing", processing: progress(), workspaces: phase === 0 ? [] : detail.workspaces } : detail;
  await page.route("**/fixture.png", route => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYyQAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/v1/**", async route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname;
    calls.push(path);
    if (path.includes("/supervisor/") || path.includes("/runs/")) throw new Error("Data management must not call the old Agent path");
    if (path.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "回归测试工程师", email: "fixture@example.invalid", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (path === "/api/v1/projects") {
      if (options.loading) await options.loading;
      return options.failList ? route.fulfill({ status: 503, json: { detail: { message: "数据服务暂不可用" } } }) : route.fulfill({ json: exists ? [payload()] : [] });
    }
    if (path === "/api/v1/rule-library/local") return route.fulfill({ json: [{ profile_key: "zh", profile_version: "2.1.0", display_name: "振华规则", checksum: "sha256:" + "0".repeat(64) }] });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [{ id: profileId, profile_key: "zh", profile_version: "2.1.0", display_name: "振华规则", checksum: "sha256:" + "0".repeat(64), resource_ref: "local://zh/profile.json", created_at: "2026-10-16", can_delete: true }] });
    if (path === `/api/v1/rule-library/${profileId}`) return route.fulfill({ json: { manifest: {}, files: ["classification", "page_scan", "cross_page"].map(stage => ({ path: `resources/${stage}_prompt.md`, content: `夹具 ${stage} 规则` })), images: [] } });
    if (path === "/api/v1/imports") { exists = true; detail.workspaces = []; detail.batch_id = null; return route.fulfill({ status: 201, json: { project_id: projectId, source_document_id: projectId, attachment_id: projectId, filename: "fixture.pdf", checksum: "sha256:fixture", size: 100, page_count: 2, extraction_started: true } }); }
    if (path === `/api/v1/projects/${projectId}`) {
      if (request.method() === "PATCH") detail.name = request.postDataJSON().name;
      if (request.method() === "DELETE") { exists = false; return route.fulfill({ status: 204 }); }
      return options.denied ? route.fulfill({ status: 403, json: { detail: { message: "没有项目操作权限" } } }) : route.fulfill({ json: payload() });
    }
    if (path.endsWith("/extraction/events") && streamFailures-- > 0) return route.fulfill({ contentType: "text/event-stream", body: "event: unavailable\ndata: {}\n\n" });
    if (path.endsWith("/extraction/events")) return route.fulfill({ contentType: "text/event-stream", body: `id: ${phase}\nevent: refresh\ndata: {}\n\n${phase === 3 ? "event: done\ndata: {}\n\n" : ""}` });
    if (path === `/api/v1/projects/${projectId}/connections`) return route.fulfill({ json: { items: options.noIndex || !detail.workspaces.length || (options.realtime && phase === 0) ? [] : [{ ...row, ...(options.realtime ? { end_terminal: phase >= 2 ? "XD21:7" : null, processing_status: phase === 1 ? "pending_completion" : phase === 2 ? "scanned" : "completed" } : {}) }], batch_id: detail.batch_id, offset: 0, limit: 100, has_more: false } });
    if (path === `/api/v1/connections/${rowId}` && request.method() === "PATCH") {
      keys.push(request.headers()["idempotency-key"]);
      if (failSave) { failSave = false; return route.fulfill({ status: 409, json: { detail: { message: "数据已变更，请刷新后重试" } } }); }
      Object.assign(row, request.postDataJSON().changes); row.record_version += 1;
      return route.fulfill({ json: { connection_id: rowId, batch_id: "run-one", action: "edit", record_version: row.record_version, idempotent: false } });
    }
    if (path.endsWith("/target")) return route.fulfill({ json: drawing(targetId, 2) });
    if (path.startsWith("/api/v1/drawings/")) return route.fulfill({ json: drawing(path.endsWith(sourceId) ? sourceId : targetId, path.endsWith(sourceId) ? 1 : 2) });
    return route.fulfill({ status: 404, json: { detail: { message: "未配置的夹具请求" } } });
  });
  return { calls, keys, advance: (next: number) => { phase = next; } };
}

test("空数据库直接显示完整工作区", async ({ page }) => {
  await fixture(page, { empty: true }); await page.goto("/projects");
  await expect(page.locator(".workbench-app")).toBeVisible();
  await expect(page.locator(".project-sidebar")).toBeVisible();
  await expect(page.locator(".project-list-page")).toHaveCount(0);
  await expect(page.getByText("上传 PDF 创建项目，在此管理图纸和线表。")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("empty.png"), fullPage: true });
});

test("已有项目直接进入首个项目工作区", async ({ page }) => {
  await fixture(page); await page.goto("/projects");
  await expect(page).toHaveURL(`/projects/${projectId}`);
  await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible();
  await expect(page.locator(".project-list-page")).toHaveCount(0);
});

test("空工作区窄屏与规则入口", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, { empty: true }); await page.goto("/projects");
  await expect(page.getByText("上传 PDF 创建项目，在此管理图纸和线表。")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("empty-narrow.png"), fullPage: true });
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await expect(page.getByRole("button", { name: "登记规则引用", exact: true })).toBeVisible();
});

test("侧栏保留重命名和删除，删除后回到空工作区", async ({ page }) => {
  await fixture(page); await page.goto("/projects");
  page.once("dialog", dialog => dialog.accept("新项目名称"));
  await page.getByRole("button", { name: "重命名项目 三表回归夹具项目", exact: true }).click();
  await expect(page.locator(".header-project strong")).toHaveText("新项目名称");
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "删除项目 新项目名称", exact: true }).click();
  await expect(page).toHaveURL("/projects");
  await expect(page.getByText("上传 PDF 创建项目，在此管理图纸和线表。")).toBeVisible();
});

test("加载中、请求失败和无权限均可见", async ({ page }) => {
  let release!: () => void; const pending = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { loading: pending }); await page.goto("/projects", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("正在加载项目…")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("loading.png") }); release();
  await expect(page.getByRole("link", { name: "三表回归夹具项目", exact: true })).toBeVisible();
});

test("列表失败保留重试入口", async ({ page }) => {
  await fixture(page, { failList: true }); await page.goto("/projects");
  await expect(page.getByRole("alert")).toContainText("数据服务暂不可用");
  await expect(page.getByRole("button", { name: "重试", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("failed.png") });
});

test("项目无权限显示错误", async ({ page }) => {
  await fixture(page, { denied: true }); await page.goto(`/projects/${projectId}`);
  await expect(page.getByRole("alert")).toContainText("没有项目操作权限");
  await page.screenshot({ path: test.info().outputPath("denied.png") });
});

for (const narrow of [false, true]) {
  test(`登录和工作台${narrow ? "窄屏" : "桌面"}截图及长文本`, async ({ page }) => {
    await page.setViewportSize(narrow ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
    await fixture(page, { longName: true }); await page.goto("/login");
    await expect(page.getByRole("button", { name: "登录", exact: true })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("login.png"), fullPage: true });
    await page.goto(`/projects/${projectId}`);
    await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("workbench.png"), fullPage: true });
  });
}

test("上传保存后启动提取，AI聊天仍未开放", async ({ page }) => {
  const { calls } = await fixture(page, { empty: true }); await page.goto("/projects");
  await page.locator('input[type="file"]').setInputFiles({ name: "fixture.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-fixture") });
  await expect(page.getByRole("dialog")).toContainText("文件保存成功后将自动拆页并提取线表");
  await expect(page.getByRole("button", { name: "保存到项目", exact: true })).toBeDisabled();
  await page.getByRole("combobox", { name: "图纸规则" }).selectOption("zh");
  await page.getByRole("button", { name: "保存到项目", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${projectId}`);
  await expect(page.getByText("PDF 已保存，尚无图纸索引和提取结果。")).toBeVisible();
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await expect(page.getByText("AI 对话暂未接入", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送给主 Agent" })).toBeDisabled();
  expect(calls.some(path => path.includes("/supervisor/") || path.includes("/runs/"))).toBe(false);
});

test("按批次读取、跨页双图和行内编辑", async ({ page }) => {
  await fixture(page); await page.goto(`/projects/${projectId}`);
  await expect(page.getByText("批次 run-one", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "XD10:1", exact: false }).click();
  await expect(page.locator(".below-previews.with-target")).toBeVisible();
  await page.getByRole("button", { name: "编辑 XA:8", exact: true }).click();
  await page.getByRole("textbox", { name: "终点端子", exact: true }).fill("XD10:2");
  await page.getByRole("textbox", { name: "终点端子", exact: true }).press("Enter");
  await expect(page.getByRole("button", { name: "XD10:2", exact: false })).toBeVisible();
});

test("版本冲突保留草稿，重试复用幂等键", async ({ page }) => {
  const { keys } = await fixture(page, { failSave: true }); await page.goto(`/projects/${projectId}`);
  await page.getByRole("button", { name: "编辑 XA:8", exact: true }).click();
  const terminal = page.getByRole("textbox", { name: "终点端子", exact: true });
  await terminal.fill("XD10:3"); await terminal.press("Enter");
  await expect(page.getByText("数据已变更，请刷新后重试")).toBeVisible();
  await expect(terminal).toHaveValue("XD10:3"); await terminal.press("Enter");
  await expect(page.getByRole("button", { name: "XD10:3", exact: false })).toBeVisible();
  expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1]);
});

test("规则引用与Stage2内部补全预览", async ({ page }) => {
  await fixture(page); await page.goto(`/projects/${projectId}`);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await page.getByRole("button", { name: "查看规则", exact: true }).click();
  await page.getByRole("button", { name: "Stage 2 内部连接补全", exact: true }).click();
  await expect(page.getByText("夹具 cross_page 规则")).toBeVisible();
});


test("拆页等待、初扫与补全结果实时更新且处理期间只读", async ({ page }) => {
  const state = await fixture(page, { realtime: true });
  await page.goto(`/projects/${projectId}`);
  await expect(page.locator(".extraction-progress")).toContainText("正在进行第一阶段处理");
  await expect(page.getByText("当前范围没有线表记录", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("rendering.png"), fullPage: true });
  state.advance(1);
  await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.locator(".row-state")).toHaveText("待补全");
  await expect(page.getByRole("button", { name: "编辑 XA:8", exact: true })).toBeDisabled();
  await expect(page.locator(".workspace-node")).toHaveCount(1);
  state.advance(2);
  await expect(page.getByRole("button", { name: "XD21:7", exact: false })).toBeVisible({ timeout: 10000 });
  await expect(page.locator(".result-table tbody tr")).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath("completion.png"), fullPage: true });
  state.advance(3);
  await expect(page.locator(".extraction-progress")).toHaveCount(0, { timeout: 10000 });
  await expect(page.locator(".row-state")).toHaveText("已完成");
  await expect(page.getByRole("button", { name: "编辑 XA:8", exact: true })).toBeEnabled();
});


test("服务端暂时不可用后重连事件流并补读快照", async ({ page }) => {
  const state = await fixture(page, { realtime: true, streamFailures: 3 });
  await page.goto(`/projects/${projectId}`);
  // React development mounting can abort an initial subscription. Require more than
  // those initial attempts so this verifies an actual reconnect after an unavailable event.
  await expect.poll(() => state.calls.filter(path => path.endsWith("/extraction/events")).length, { timeout: 15000 }).toBeGreaterThan(3);
  state.advance(1);
  await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.locator(".extraction-progress")).not.toContainText("实时连接中断");
});
