import { test, expect, type Page } from "@playwright/test";

// Explicit HTTP fixtures; the real local DB/Storage path is validated separately.
const projectId = "00000000-0000-0000-0000-000000000010";
const profileId = "00000000-0000-0000-0000-000000000011";
const sourceId = "00000000-0000-0000-0000-000000000012";
const targetId = "00000000-0000-0000-0000-000000000013";
const workspaceId = "00000000-0000-0000-0000-000000000014";
const rowId = "00000000-0000-0000-0000-000000000015";
const anotherProjectId = "00000000-0000-0000-0000-000000000016";
const drawing = (id: string, page: number) => ({ id, project_id: projectId, workspace_id: workspaceId, pdf_page_number: page, workspace_page: `003C0${page}`, status: "scanned", image_url: "/fixture.png" });

async function fixture(page: Page, options: { empty?: boolean; failList?: boolean; denied?: boolean; failSave?: boolean; noIndex?: boolean; longName?: boolean; loading?: Promise<void>; realtime?: boolean; streamFailures?: number; treeOrder?: boolean; failRename?: boolean; renameGate?: Promise<void>; anotherProject?: boolean } = {}) {
  let exists = !options.empty;
  let failSave = options.failSave;
  const calls: string[] = []; const keys: string[] = [];
  const renames: Array<{ project: string; name: string }> = []; let failRename = !!options.failRename;
  const detail = { id: projectId, name: options.longName ? "超长项目名称用于验证布局和换行".repeat(10) : "三表回归夹具项目", owner_id: "owner", status: "ready", profile_id: profileId, standard_profile: "zh", updated_at: "2026-10-16", source_saved: true, sources: [{ id: projectId, original_filename: "fixture.pdf", page_count: 2 }], workspaces: options.noIndex ? [] : [{ id: workspaceId, code: "003.C", name: "003.C", drawings: [drawing(sourceId, 1), drawing(targetId, 2)] }], batch_id: options.noIndex ? null : "run-one", extraction_available: false };
  const row = { connection_id: rowId, project_id: projectId, batch_id: "run-one", workspace_id: workspaceId, workspace_name: "003.C", drawing_id: sourceId, workspace_page: "003C01", pdf_page_number: 1, row_order: 0, wire_number: null, record_version: 1, start_code: "+01F10", start_terminal: "XA:8", end_code: "+01F12.1", end_terminal: "XD10:1", is_cross_page: true, needs_review: false };
  if (options.treeOrder) detail.workspaces = [
    { id: "work-082", code: "082.R", name: "082.R", drawings: [{ ...drawing(sourceId, 1), workspace_page: "082R50" }] },
    { id: "work-006-m", code: "006.M", name: "006.M", drawings: [
      { ...drawing("m10", 2), workspace_page: "006M10" }, { ...drawing("m2", 4), workspace_page: "006M2" },
      { ...drawing("m01", 5), workspace_page: "006M01" },
    ] },
    { id: "work-006-c", code: "006.C", name: "006.C", drawings: [{ ...drawing("c01", 3), workspace_page: "006C01" }] },
  ];
  const another = { ...detail, id: anotherProjectId, name: "第二项目" };
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
      return options.failList ? route.fulfill({ status: 503, json: { detail: { message: "数据服务暂不可用" } } }) : route.fulfill({ json: exists ? [payload(), ...(options.anotherProject ? [another] : [])] : [] });
    }
    if (path === "/api/v1/rule-library/local") return route.fulfill({ json: [{ profile_key: "zh", profile_version: "2.1.0", display_name: "振华规则", checksum: "sha256:" + "0".repeat(64) }] });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [{ id: profileId, profile_key: "zh", profile_version: "2.1.0", display_name: "振华规则", checksum: "sha256:" + "0".repeat(64), resource_ref: "local://zh/profile.json", created_at: "2026-10-16", can_delete: true }] });
    if (path === `/api/v1/rule-library/${profileId}`) return route.fulfill({ json: { manifest: {}, files: ["classification", "page_scan", "cross_page"].map(stage => ({ path: `resources/${stage}_prompt.md`, content: `夹具 ${stage} 规则` })), images: [] } });
    if (path === "/api/v1/imports") { exists = true; detail.workspaces = []; detail.batch_id = null; return route.fulfill({ status: 201, json: { project_id: projectId, source_document_id: projectId, attachment_id: projectId, filename: "fixture.pdf", checksum: "sha256:fixture", size: 100, page_count: 2, extraction_started: true } }); }
    if (path === `/api/v1/projects/${projectId}` || path === `/api/v1/projects/${anotherProjectId}`) {
      const selected = path.endsWith(anotherProjectId) ? another : detail;
      if (request.method() === "PATCH") {
        renames.push({ project: selected.id, name: request.postDataJSON().name });
        if (failRename) { failRename = false; return route.fulfill({ status: 503, json: { detail: { message: "项目名称保存失败，请重试" } } }); }
        if (options.renameGate) await options.renameGate;
        selected.name = request.postDataJSON().name;
      }
      if (request.method() === "DELETE") { exists = false; return route.fulfill({ status: 204 }); }
      return options.denied ? route.fulfill({ status: 403, json: { detail: { message: "没有项目操作权限" } } }) : route.fulfill({ json: selected === another ? another : payload() });
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
    if (path.startsWith("/api/v1/drawings/")) return route.fulfill({ json: detail.workspaces.flatMap(workspace => workspace.drawings).find(d => path.endsWith(d.id)) ?? drawing(sourceId, 1) });
    return route.fulfill({ status: 404, json: { detail: { message: "未配置的夹具请求" } } });
  });
  return { calls, keys, renames, advance: (next: number) => { phase = next; } };
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

test("侧栏双击原地改名并保留删除，删除后回到空工作区", async ({ page }) => {
  await fixture(page); await page.goto("/projects");
  await page.getByRole("link", { name: "三表回归夹具项目", exact: true }).dblclick();
  await page.getByRole("textbox", { name: "项目名称", exact: true }).fill("新项目名称");
  await page.getByRole("textbox", { name: "项目名称", exact: true }).press("Enter");
  await expect(page.locator(".header-project strong")).toHaveText("新项目名称");
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "删除项目 新项目名称", exact: true }).click();
  await expect(page).toHaveURL("/projects");
  await expect(page.getByText("上传 PDF 创建项目，在此管理图纸和线表。")).toBeVisible();
});

test("原地改名校验空值、Esc取消及失败后保留草稿重试", async ({ page }) => {
  const state = await fixture(page, { failRename: true });
  await page.addInitScript(() => { window.prompt = () => { throw new Error("Rename must not use window.prompt"); }; });
  await page.goto(`/projects/${projectId}`);
  await expect(page.getByRole("button", { name: /重命名项目/ })).toHaveCount(0);
  const link = page.getByRole("link", { name: "三表回归夹具项目", exact: true });
  await link.dblclick(); const input = page.getByRole("textbox", { name: "项目名称", exact: true });
  await input.fill("  "); await input.press("Enter");
  await expect(page.getByRole("alert")).toHaveText("项目名称不能为空"); expect(state.renames).toHaveLength(0);
  await input.press("Escape"); await expect(input).toHaveCount(0);
  await link.dblclick(); await input.fill("改名失败后的草稿"); await input.press("Enter");
  await expect(page.getByRole("alert")).toHaveText("项目名称保存失败，请重试");
  await expect(input).toHaveValue("改名失败后的草稿"); expect(state.renames).toHaveLength(1);
  await input.press("Enter");
  await expect(page.locator(".header-project strong")).toHaveText("改名失败后的草稿");
  expect(state.renames).toHaveLength(2);
  await page.reload(); await expect(page.getByRole("link", { name: "改名失败后的草稿", exact: true })).toBeVisible();
});

test("当前项目标题可双击修改，失焦只保存一次且保存中禁用输入", async ({ page }) => {
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const state = await fixture(page, { renameGate: gate }); await page.goto(`/projects/${projectId}`);
  await page.locator(".context-project-name").dblclick();
  const input = page.getByRole("textbox", { name: "项目名称", exact: true });
  await input.fill("  标题改名  "); await input.press("Tab");
  await expect(input).toBeDisabled(); expect(state.renames).toEqual([{ project: projectId, name: "标题改名" }]);
  await page.screenshot({ path: test.info().outputPath("project-name-saving.png") });
  release(); await expect(page.locator(".header-project strong")).toHaveText("标题改名");
  await expect(page.getByRole("link", { name: "标题改名", exact: true })).toBeVisible();
  expect(state.renames).toHaveLength(1);
});

test("非当前项目双击改名不跳转，键盘与单击导航仍可用", async ({ page }) => {
  const state = await fixture(page, { anotherProject: true }); await page.goto(`/projects/${projectId}`);
  await page.getByRole("link", { name: "第二项目", exact: true }).dblclick();
  await expect(page).toHaveURL(`/projects/${projectId}`);
  const input = page.getByRole("textbox", { name: "项目名称", exact: true });
  await input.fill("第二项目新名称"); await input.press("Enter");
  const link = page.getByRole("link", { name: "第二项目新名称", exact: true });
  await expect(link).toBeVisible(); await expect(link).toHaveAttribute("href", `/projects/${anotherProjectId}`);
  await expect(page.locator(".project-folder-link .inline-name-value")).toHaveText(["三表回归夹具项目", "第二项目新名称"]);
  await expect(page).toHaveURL(`/projects/${projectId}`);
  expect(state.renames).toEqual([{ project: anotherProjectId, name: "第二项目新名称" }]);
  await link.focus(); await link.press("F2"); await expect(input).toBeFocused();
  await input.press("Escape"); await link.click(); await expect(page).toHaveURL(`/projects/${anotherProjectId}`);
});

test("工作区和图纸编号自然升序，树与图纸库使用简名且不改变PDF物理页", async ({ page }) => {
  await fixture(page, { treeOrder: true }); await page.goto(`/projects/${projectId}`);
  await expect(page.locator(".workspace-row strong")).toHaveText(["006.C", "006.M", "082.R"]);
  const motor = page.locator(".workspace-node").filter({ has: page.locator(".workspace-row strong", { hasText: "006.M" }) });
  await expect(motor.locator(".drawing-row strong")).toHaveText(["006M01", "006M2", "006M10"]);
  await expect(motor.locator(".drawing-row small")).toHaveText(["PDF 第 5 页", "PDF 第 4 页", "PDF 第 2 页"]);
  await motor.locator(".tree-select").dblclick();
  await expect(page.getByRole("textbox", { name: "项目名称", exact: true })).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("tree-ascending-desktop.png") });
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  await page.locator(".library-project > summary").click();
  await expect(page.locator(".library-workspace > summary > strong")).toHaveText(["006.C", "006.M", "082.R"]);
  await expect(page.locator(".drawing-file > summary > strong")).toHaveText(["006C01", "006M01", "006M2", "006M10", "082R50"]);
});

test("窄屏项目名原地编辑、长文本和失败提示可见", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, { failRename: true, treeOrder: true }); await page.goto(`/projects/${projectId}`);
  await page.getByRole("link", { name: "三表回归夹具项目", exact: true }).dblclick();
  const input = page.getByRole("textbox", { name: "项目名称", exact: true });
  await input.fill("用于检查名称原地编辑的长项目名称".repeat(10)); await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("项目名称保存失败");
  await expect(input).toHaveAttribute("maxlength", "200");
  const bounds = await input.boundingBox(); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("tree-inline-name-narrow.png"), fullPage: true });
});

test("增量提取刷新后仍按编号升序显示目录和图纸", async ({ page }) => {
  const state = await fixture(page, { realtime: true, treeOrder: true });
  await page.goto(`/projects/${projectId}`);
  await expect(page.locator(".workspace-row")).toHaveCount(0);
  state.advance(1);
  await expect(page.locator(".workspace-row strong")).toHaveText(["006.C", "006.M", "082.R"]);
  state.advance(3);
  await expect(page.getByText("处理完成", { exact: true })).toBeVisible();
  await expect(page.locator(".workspace-row strong")).toHaveText(["006.C", "006.M", "082.R"]);
  await expect(page.locator(".drawing-row strong")).toHaveText(["006C01", "006M01", "006M2", "006M10", "082R50"]);
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
