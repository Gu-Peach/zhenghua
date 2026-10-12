import { test, expect } from "@playwright/test";

// Explicit HTTP fixtures, never a production fallback. No paid models or real user data.
const project = "10000000-0000-4000-8000-000000000001";
const source = "10000000-0000-4000-8000-000000000002";
const target = "10000000-0000-4000-8000-000000000003";
const ws = "10000000-0000-4000-8000-000000000004";
const result = "10000000-0000-4000-8000-000000000005";
const packageId = "10000000-0000-4000-8000-000000000006";
const drawing = (id: string, page: string) => ({ id, project_id: project, workspace_id: ws, workspace_page: page, pdf_page_number: Number(page), status: "scanned", image_url: "/demo/zh-002c-11.png" });
const detail = { id: project, owner_id: "fixture", name: "验收工程", status: "ready", updated_at: "2026-10-12T00:00:00Z", sources: [{ id: source, original_filename: "fixture.pdf" }], workspaces: [{ id: ws, name: "002.C", code: "002.C", drawings: [drawing(source, "1"), drawing(target, "2")] }], result: { id: result, version: 1, revision: 1, profile: { key: "zh" } } };
const rows = [1, 2].map(n => ({ connection_id: `10000000-0000-4000-8000-00000000001${n}`, project_id: project, workspace_id: ws, workspace_name: "002.C", drawing_id: source, workspace_page: "1", pdf_page_number: 1, wiring_unit_id: "unit1", wire_number: 1000, core_order: n, result_version_id: result, result_version: 1, result_revision: 1, record_version: 1, principle_number: `002C00${n}`, start_terminal: `XD3:${n}`, end_terminal: `X3:${n}`, is_cross_page: n === 1 ? "cross_page" : "same_page", needs_review: false, status: "confirmed" }));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/auth/refresh") ? { user: { id: "fixture", name: "测试工程师", email: "fixture@example.invalid", role: "工程师" }, accessToken: "fixture" }
      : path === "/api/v1/projects" ? [detail]
      : path === `/api/v1/projects/${project}` ? detail
      : path.endsWith("/connections") ? { items: rows, offset: 0, limit: 100, has_more: false, result_version_id: result, result_version: 1, result_revision: 1 }
      : path.endsWith("/target") ? drawing(target, "2")
      : path.includes("/drawings/") ? drawing(source, "1")
      : path === "/api/v1/rule-library" ? [{ id: packageId, profile_key: "zh", profile_version: "1.0.0", package_checksum: "sha256:fixture", status: "active", created_at: "2026-10-12" }]
      : path.includes("/rule-library/") ? { manifest: {}, files: [...["classification", "page_scan", "cross_page"].map(stage => ({ path: `resources/${stage}_prompt.md`, content: `${stage}真实规则测试文本` })), { path: "resources/wiring_examples/manifest.json", content: JSON.stringify({ stage3_cases: [{ id: "target-case", title: "跨页目标页样例", expected: "stage3/expected.json", images: [{ path: "images/case.png", role: "target_page", note: "只读取任务指定目标页" }] }] }) }, { path: "resources/wiring_examples/stage3/expected.json", content: '{"end":{"terminal":"X3:1"}}' }], images: [{ path: "resources/wiring_examples/images/case.png", url: "/demo/zh-002c-11.png" }] }
      : { result_revision: 2 };
    await route.fulfill({ json });
  });
});

test("规则建议一次确认后直接启用，不出现评测审核提示", async ({ page }) => {
  const run = "confirmed-rule-fixture";
  let confirmed = false;
  await page.route("**/api/v1/supervisor/turns/stream", async route => {
    confirmed = route.request().postDataJSON().message === "确认规则修改";
    const response = { receipt: { agent_run_id: run }, user_event: { user_message: confirmed ? "规则修改已启用" : "请确认规则建议", requires_input: !confirmed } };
    await route.fulfill({ contentType: "text/event-stream", body: `event: response\ndata: ${JSON.stringify(response)}\n\n` });
  });
  await page.route(`**/api/v1/runs/${run}/events/stream?**`, route => route.fulfill({ contentType: "text/event-stream", body: "" }));
  await page.route(`**/api/v1/runs/${run}`, route => route.fulfill({ json: { run: { status: confirmed ? "SUCCEEDED" : "WAITING_INPUT" } } }));
  await page.route(`**/api/v1/runs/${run}/artifacts`, route => route.fulfill({ json: { items: confirmed ? [
    { kind: "profile_candidate_pending", candidate: { status: "DRAFT" } },
    { kind: "profile_rule_update", candidate: { status: "ACTIVE", summary: "跨页终点保留 X3: 前缀", operations: [{ relative_path: "resources/cross_page_prompt.md" }] } },
  ] : [{ kind: "improvement_diagnosis", candidate_recommended: true, diagnoses: [{ recommended_change: "保留完整端子标识" }] }] } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  const input = page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" });
  await input.fill("请归因规则问题");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".agent-feed")).toContainText("待确认规则建议");
  await input.fill("确认规则修改");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".agent-feed")).toContainText("规则修改已生效");
  await expect(page.locator(".agent-feed")).not.toContainText("需要离线评测");
  await page.screenshot({ path: "../../.runtime/web-tests/confirmed-rules-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/confirmed-rules-mobile.png", fullPage: true });
});

test("规则包创建注册、冲突重试与删除确认", async ({ page }) => {
  const customId = "10000000-0000-4000-8000-000000000077";
  let created = false; let attempts = 0; let deletes = 0;
  await page.route("**/api/v1/rule-library", async route => {
    if (route.request().method() === "POST") {
      const data = route.request().postDataJSON();
      expect(data.base_package_id).toBe(packageId);
      expect(data.prompts.page_scan_prompt).toContain("自定义扫描约束");
      expect(data.confirmed).toBe(true);
      attempts++;
      if (attempts === 1) return route.fulfill({ status: 409, json: { detail: { message: "规则标识已占用，请使用新的标识" } } });
      created = true;
      return route.fulfill({ status: 201, json: { id: customId, profile_key: "custom", status: "active", registered: true } });
    }
    await route.fulfill({ json: [{ id: packageId, profile_key: "zh", profile_version: "1.0.0", package_checksum: "sha256:fixture", status: "active", created_at: "2026-10-12", can_delete: false }, ...(created ? [{ id: customId, profile_key: "custom", profile_version: "1.0.0", package_checksum: "sha256:custom", status: "active", created_at: "2026-10-12", can_delete: true }] : [])] });
  });
  await page.route(`**/api/v1/rule-library/${packageId}`, route => route.fulfill({ json: { manifest: {}, files: [
    { path: "profile.json", content: JSON.stringify({ resources: { classification_prompt: "stage1.md", page_scan_prompt: "stage2.md", cross_page_prompt: "stage3.md", routing_rules: "rules.json" } }) },
    ...[1, 2, 3].map(stage => ({ path: `stage${stage}.md`, content: `阶段${stage}模板规则` })),
    { path: "rules.json", content: JSON.stringify({ detection: { summary: "图框规则", strong_signals: ["模板特征"] } }) },
  ], images: [] } }));
  await page.route(`**/api/v1/rule-library/${customId}?confirmed=true`, async route => {
    expect(route.request().method()).toBe("DELETE"); deletes++; created = false;
    await route.fulfill({ json: { id: customId, status: "retired", historical_resources_retained: true } });
  });
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await page.getByRole("button", { name: "新建规则包", exact: true }).click();
  await expect(page.getByLabel("规则标识")).toBeVisible();
  await page.getByLabel("规则标识").fill("occupied");
  await page.getByLabel("规则名称").fill("长规则名称".repeat(25));
  await page.getByLabel("说明", { exact: true }).fill("用于人工验收，继承真实图片样例。".repeat(20));
  await page.getByText("Stage 2 当前页扫描 Prompt", { exact: true }).click();
  await page.getByLabel("Stage 2 当前页扫描 Prompt").fill("自定义扫描约束：只提取指定端子。");
  await page.getByLabel("确认创建并注册为可用规则包").check();
  await page.screenshot({ path: "../../.runtime/web-tests/rule-create-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/rule-create-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await page.getByRole("button", { name: "创建并注册", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("规则标识已占用");
  await page.getByLabel("规则标识").fill("custom");
  await page.getByRole("button", { name: "创建并注册", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "删除规则包 zh", exact: true })).toHaveCount(0);
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "删除规则包 custom", exact: true }).click();
  expect(deletes).toBe(0);
  page.once("dialog", async dialog => { expect(dialog.message()).toContain("历史资源会保留"); await dialog.accept(); });
  await page.getByRole("button", { name: "删除规则包 custom", exact: true }).click();
  await expect(page.getByRole("button", { name: "删除规则包 custom", exact: true })).toHaveCount(0);
  expect(attempts).toBe(2); expect(deletes).toBe(1);
});

test("切换项目保留框架和目录顺序，不重拉目录；箭头仅折叠当前数据", async ({ page }) => {
  const other = "10000000-0000-4000-8000-000000000070";
  const second = { ...detail, id: other, name: "第二项目", updated_at: "2030-01-01T00:00:00Z" };
  let listReads = 0;
  let releaseDetails: () => void = () => {};
  const detailsReady = new Promise<void>(resolve => { releaseDetails = resolve; });
  await page.route("**/api/v1/projects", route => { listReads++; return route.fulfill({ json: [detail, second] }); });
  await page.route(`**/api/v1/projects/${other}`, async route => { await detailsReady; await route.fulfill({ json: second }); });
  await page.route(`**/api/v1/projects/${other}/connections?**`, route => route.fulfill({ json: { items: rows.map(row => ({ ...row, project_id: other, start_terminal: "SECOND:1" })), offset: 0, limit: 100, has_more: false, result_version_id: result, result_revision: 1, result_version: 1 } }));
  await page.goto(`/projects/${project}`);
  const sidebar = page.locator(".project-sidebar");
  await expect(sidebar.getByRole("link", { name: "第二项目", exact: true })).toBeVisible();
  const originalReads = listReads;
  const originalOrder = await sidebar.locator(".project-folder-link").allTextContents();
  await sidebar.getByRole("link", { name: "第二项目", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${other}`);
  await expect(page.locator(".project-context-bar")).toContainText("第二项目");
  await expect(sidebar).toBeVisible();
  await expect(page.locator(".state-page")).toHaveCount(0);
  await expect(page.locator(".project-main").getByRole("status")).toContainText("正在读取项目数据");
  await expect(page.locator(".result-table")).toHaveCount(0);
  expect(await sidebar.locator(".project-folder-link").allTextContents()).toEqual(originalOrder);
  await page.screenshot({ path: "../../.runtime/web-tests/project-switch-loading-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(sidebar).toBeVisible();
  await page.screenshot({ path: "../../.runtime/web-tests/project-switch-loading-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await page.setViewportSize({ width: 1280, height: 720 });
  releaseDetails();
  await expect(page.locator(".result-table tbody tr").first()).toContainText("SECOND:1");
  expect(listReads).toBe(originalReads);
  expect(await sidebar.locator(".project-folder-link").allTextContents()).toEqual(originalOrder);
  await expect(sidebar.getByText("打开项目", { exact: true })).toHaveCount(0);
  await sidebar.getByRole("button", { name: "收起项目 第二项目" }).click();
  await expect(sidebar.locator(".workspace-row")).toHaveCount(0);
  await expect(page).toHaveURL(`/projects/${other}`);
  await expect(page.locator(".result-table tbody tr").first()).toContainText("SECOND:1");
  await sidebar.getByRole("button", { name: "展开项目 第二项目" }).click();
  await expect(sidebar.locator(".workspace-row")).toBeVisible();
  await sidebar.getByRole("link", { name: "验收工程", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${project}`);
  await expect(page.locator(".result-table tbody tr").first()).toContainText("XD3:1");
  expect(listReads).toBe(originalReads);
  expect(await sidebar.locator(".project-folder-link").allTextContents()).toEqual(originalOrder);
});

test("图纸库按项目和工作区展开图片，原地预览", async ({ page }) => {
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  const directory = page.getByRole("region", { name: "图纸目录", exact: true });
  await expect(directory.locator(".library-project > summary")).toContainText("验收工程");
  await expect(directory.locator(".library-workspace > summary")).not.toBeVisible();
  await directory.locator(".library-project > summary").click();
  await directory.locator(".library-workspace > summary").click();
  await expect(directory.locator(".drawing-file > summary").first()).toContainText("图纸 1.png");
  await directory.locator(".drawing-file > summary").first().click();
  await expect(directory.locator(".drawing-preview img")).toBeVisible();
  await expect(page.getByRole("button", { name: "图纸库", exact: true })).toHaveClass("active");
  await expect(page).toHaveURL(`/projects/${project}`);
  await page.screenshot({ path: "../../.runtime/web-tests/drawing-library-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/drawing-library-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
});

test("跨工作区的图片按需读取，展开不改变线表过滤", async ({ page }) => {
  const otherWorkspace = "10000000-0000-4000-8000-000000000008";
  const filters: Array<{ workspace: string | null; drawing: string | null }> = [];
  let targetReads = 0;
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.pathname.endsWith("/connections")) filters.push({ workspace: url.searchParams.get("workspace_id"), drawing: url.searchParams.get("drawing_id") });
  });
  await page.route(`**/api/v1/drawings/${target}`, route => {
    targetReads++;
    return route.fulfill({ json: { ...drawing(target, "2"), workspace_id: otherWorkspace } });
  });
  await page.route(`**/api/v1/projects/${project}`, route => route.fulfill({ json: {
    ...detail, workspaces: [
      { ...detail.workspaces[0], drawings: [drawing(source, "1")] },
      { id: otherWorkspace, name: "006.M", code: "006.M", drawings: [{ ...drawing(target, "2"), workspace_id: otherWorkspace }] },
    ],
  } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  const directory = page.getByRole("region", { name: "图纸目录", exact: true });
  await directory.locator(".library-project > summary").click();
  const folder = directory.locator(".library-workspace").filter({ has: page.locator("summary strong", { hasText: "006.M" }) });
  await folder.locator(":scope > summary").click();
  expect(targetReads).toBe(0);
  await folder.locator(".drawing-file > summary").click();
  await expect(folder.locator(".drawing-preview img")).toHaveAttribute("alt", "验收工程 / 业务页 2 / PDF 2");
  expect(targetReads).toBeGreaterThanOrEqual(1);
  expect(filters.every(filter => filter.workspace === null && filter.drawing === null)).toBe(true);
  await expect(page.getByRole("button", { name: "图纸库", exact: true })).toHaveClass("active");
  await directory.locator(".library-project > summary").click();
  await expect(folder).not.toBeVisible();
});

test("没有已发布分类的项目显示图纸目录空态", async ({ page }) => {
  await page.route(`**/api/v1/projects/${project}`, route => route.fulfill({ json: { ...detail, workspaces: [] } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  await page.locator(".library-project > summary").click();
  await expect(page.getByRole("status")).toContainText("暂无图纸，页面分类完成后会显示工作区和图片。");
});

test("图纸目录内展示权限失败并允许重试", async ({ page }) => {
  let reads = 0;
  let permitted = false;
  await page.route(`**/api/v1/drawings/${target}`, route => {
    reads++;
    return !permitted ? route.fulfill({ status: 403, json: { detail: "权限不足" } }) : route.fulfill({ json: drawing(target, "2") });
  });
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  await page.locator(".library-project > summary").click();
  await page.locator(".library-workspace > summary").click();
  const file = page.locator(".drawing-file").nth(1);
  await file.locator(":scope > summary").click();
  await expect(file.getByRole("alert")).toContainText("无权访问此图纸。");
  const deniedReads = reads;
  permitted = true;
  await file.getByRole("button", { name: "重试读取图纸" }).click();
  await expect(file.locator(".drawing-preview img")).toBeVisible();
  expect(reads).toBeGreaterThan(deniedReads);
});

test("悬浮聊天开关和 Escape 保留草稿且不挤占工作区", async ({ page }) => {
  await page.goto(`/projects/${project}`);
  await expect(page.getByRole("dialog", { name: "AI 助手" })).toHaveCount(0);
  const before = await page.locator(".project-main").boundingBox();
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  const panel = page.getByRole("dialog", { name: "AI 助手" });
  await expect(panel).toBeVisible();
  await expect(panel.locator(".agent-current-stage")).toHaveCount(0);
  await expect(panel.getByText("当前阶段", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "关闭 AI 聊天面板" })).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("尚未发送的纠错需求");
  await page.getByRole("button", { name: "收起聊天窗口" }).click();
  await expect(page.getByRole("button", { name: "打开 AI 聊天面板" })).toBeFocused();
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await expect(page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" })).toHaveValue("尚未发送的纠错需求");
  const after = await page.locator(".project-main").boundingBox();
  expect(after!.width).toBe(before!.width);
  await expect(panel).toHaveCSS("position", "fixed");
  await page.screenshot({ path: "../../.runtime/web-tests/floating-chat-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "发送给主 Agent" })).toBeVisible();
  const mobile = await panel.boundingBox();
  expect(mobile!.x).toBeGreaterThanOrEqual(0);
  expect(mobile!.x + mobile!.width).toBeLessThanOrEqual(390);
  expect(mobile!.y + mobile!.height).toBeLessThanOrEqual(844);
  await page.screenshot({ path: "../../.runtime/web-tests/floating-chat-mobile.png", fullPage: true });
  await panel.press("Escape");
  await expect(panel).not.toBeVisible();
  await expect(page.getByRole("button", { name: "打开 AI 聊天面板" })).toBeFocused();
});

test("规则库将旧 ABB draft 响应按可用规则展示", async ({ page }) => {
  await page.route("**/api/v1/rule-library", route => route.fulfill({ json: [
    { id: packageId, profile_key: "abb", profile_version: "1.1.2", package_checksum: "sha256:fixture", status: "draft", created_at: "2026-10-12", can_delete: false },
  ] }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await expect(page.getByText("可用", { exact: true })).toBeVisible();
  await expect(page.getByText("草稿", { exact: true })).toHaveCount(0);
  await expect(page.getByText("所有登录用户共享规则包，存储后可直接查看与提取")).toBeVisible();
  await page.screenshot({ path: "../../.runtime/web-tests/rule-library-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/rule-library-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
});

test("规则模板加载失败可重试，空库禁止创建", async ({ page }) => {
  let attempts = 0;
  await page.route(`**/api/v1/rule-library/${packageId}`, route => {
    attempts++;
    return route.fulfill({ status: 503, json: { detail: { message: "模板暂时不可用" } } });
  });
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await page.getByRole("button", { name: "新建规则包", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("模板暂时不可用");
  const beforeRetry = attempts;
  await page.getByRole("button", { name: "重新读取模板" }).click();
  await expect.poll(() => attempts).toBeGreaterThan(beforeRetry);
  await page.getByRole("button", { name: "关闭新建规则包" }).click();
  await page.route("**/api/v1/rule-library", route => route.fulfill({ json: [] }));
  await page.reload();
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await page.getByRole("button", { name: "新建规则包", exact: true }).click();
  await expect(page.getByText("没有可用的完整规则模板。")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建并注册", exact: true })).toHaveCount(0);
});

test("真实接口适配：页/线号组首、跨页下方预览、编辑和三阶段资源", async ({ page }) => {
  await page.goto(`/projects/${project}`);
  await expect(page.getByRole("heading", { name: "验收工程" })).toBeVisible();
  await expect(page.locator(".project-context-bar").getByRole("heading", { name: "验收工程" })).toBeVisible();
  await expect(page.locator(".project-overview")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "全部工作区", exact: true })).toHaveCount(0);
  const sidebar = page.locator(".project-sidebar");
  await expect(sidebar.getByText("fixture.pdf", { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText("原始文件 · fixture.pdf", { exact: true })).toHaveCount(0);
  await sidebar.getByRole("button", { name: "收起项目 验收工程" }).click();
  await expect(sidebar.locator(".workspace-row")).toHaveCount(0);
  await sidebar.getByRole("button", { name: "展开项目 验收工程" }).click();
  await expect(sidebar.locator(".workspace-row")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "线号", exact: true })).toBeVisible();
  const bodyRows = page.locator(".result-table tbody tr");
  await expect(bodyRows).toHaveCount(2);
  const add = page.getByRole("button", { name: "新增端子", exact: true });
  await expect(add).toBeEnabled();
  expect(await add.textContent()).toBe("");
  const toolbarBox = await page.locator(".table-toolbar").boundingBox();
  const addBox = await add.boundingBox();
  expect(toolbarBox!.x + toolbarBox!.width - addBox!.x - addBox!.width).toBeLessThanOrEqual(20);
  await page.route("**/api/v1/projects/*/wiring-units", route => route.fulfill({ json: [] }));
  await add.click();
  await expect(page.getByRole("dialog", { name: "新增端子", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭新增端子" }).click();
  await expect(bodyRows.nth(0).getByRole("button", { name: "002.C / 1" })).toBeVisible();
  await expect(bodyRows.nth(1).getByRole("button", { name: "002.C / 1" })).toHaveCount(0);
  await page.getByRole("button", { name: "X3:1", exact: true }).click();
  await expect(page.locator(".below-previews .drawing-preview")).toHaveCount(2);
  await expect(page.locator(".below-previews")).toContainText("终点 X3:1");
  await expect(page.locator(".result-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑 XD3:1" }).click();
  await page.getByLabel("终点端子", { exact: true }).fill("X3:99");
  const saving = page.waitForRequest(r => r.method() === "PATCH" && r.url().includes("/connections/"));
  await page.getByRole("button", { name: "保存本行修改" }).click();
  const req = await saving;
  expect(req.postDataJSON().changes.end_terminal).toBe("X3:99");
  expect(req.postDataJSON().record_version).toBe(1);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  await page.getByRole("button", { name: "查看规则" }).click();
  await page.getByRole("button", { name: "Stage 3 跨页补全" }).click();
  await expect(page.locator(".resource-body")).toContainText("cross_page真实规则测试文本");
  await expect(page.locator(".sample-grid img")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "跨页目标页样例" })).toBeVisible();
  await expect(page.getByText("只读取任务指定目标页", { exact: true })).toBeVisible();
  await page.getByText("人工确认的预期结果", { exact: true }).click();
  await expect(page.locator(".rule-example pre")).toContainText("X3:1");
  await page.getByRole("button", { name: "关闭规则面板" }).click();
  await page.getByRole("button", { name: "线表工作区", exact: true }).click();
  await page.screenshot({ path: "../../.runtime/web-tests/workbench-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/workbench-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
});

test("登录页与失败/空态", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("邮箱", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../.runtime/web-tests/login-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/web-tests/login-mobile.png" });
  await page.route("**/api/v1/projects/*/connections?**", route => route.fulfill({ json: { items: [], offset: 0, limit: 100, has_more: false } }));
  await page.goto(`/projects/${project}`);
  await expect(page.getByText("当前范围没有线表记录")).toBeVisible();
});

test("导航和搜索按容器居中，单元格 Enter 保存及 Esc 取消", async ({ page }) => {
  let endpoint = "X3:2";
  let revision = 1;
  const writes: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/projects/*/connections?**", route => route.fulfill({ json: { items: rows.map((row, index) => ({ ...row, end_terminal: index === 1 ? endpoint : row.end_terminal, record_version: revision })), offset: 0, limit: 100, has_more: false, result_version_id: result, result_revision: revision, result_version: 1 } }));
  await page.route("**/api/v1/connections/*", route => {
    const body = route.request().postDataJSON();
    writes.push(body); endpoint = body.changes.end_terminal; revision++;
    return route.fulfill({ json: { result_revision: revision } });
  });
  await page.goto(`/projects/${project}`);
  const tableRows = page.locator(".result-table tbody tr");
  await expect(tableRows).toHaveCount(2);
  for (const [container, child] of [[".project-context-bar", ".project-resource-nav"], [".table-toolbar", ".library-search"]]) {
    const outer = await page.locator(container).boundingBox();
    const inner = await page.locator(`${container} ${child}`).boundingBox();
    expect(Math.abs(outer!.x + outer!.width / 2 - inner!.x - inner!.width / 2)).toBeLessThanOrEqual(1);
  }
  await tableRows.nth(1).locator("td").nth(1).dblclick();
  await expect(page.locator(".editing-cell input")).toHaveCount(0);
  await tableRows.nth(1).locator("td").nth(10).dblclick();
  const end = page.getByRole("textbox", { name: "终点端子", exact: true });
  await expect(end).toBeFocused();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await end.fill("X3:99");
  await page.screenshot({ path: "../../.runtime/web-tests/inline-edit-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await end.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../../.runtime/web-tests/inline-edit-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await end.press("Enter");
  await expect(page.locator(".editing-cell input")).toHaveCount(0);
  await expect(tableRows.nth(1).locator("td").nth(10)).toHaveText("X3:99");
  expect(writes[0]).toMatchObject({ result_version_id: result, result_revision: 1, record_version: 1, changes: { end_terminal: "X3:99" } });
  expect(Object.keys(writes[0].changes as object)).toEqual(["end_terminal"]);
  await tableRows.nth(1).locator("td").nth(2).dblclick();
  const principle = page.getByRole("textbox", { name: "原理号", exact: true });
  await expect(principle).toBeFocused();
  await principle.press("Tab");
  const voltage = page.getByRole("textbox", { name: "电压等级", exact: true });
  await expect(voltage).toBeFocused();
  await voltage.fill("220V");
  await voltage.press("Escape");
  await expect(page.locator(".editing-cell input")).toHaveCount(0);
  expect(writes).toHaveLength(1);
});

test("行内保存失败保留草稿，重试复用幂等标识，空值映射为 null", async ({ page }) => {
  const keys: string[] = [];
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/connections/*", route => {
    keys.push(route.request().headers()["idempotency-key"]);
    bodies.push(route.request().postDataJSON());
    return keys.length === 1 ? route.fulfill({ status: 503, json: { detail: { message: "保存暂不可用" } } }) : route.fulfill({ json: { result_revision: 2 } });
  });
  await page.goto(`/projects/${project}`);
  await expect(page.locator(".result-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑 XD3:2", exact: true }).click();
  await page.getByRole("textbox", { name: "终点端子", exact: true }).fill("");
  await page.getByRole("textbox", { name: "电压等级", exact: true }).fill("220V");
  await page.getByRole("button", { name: "保存本行修改" }).click();
  await expect(page.getByRole("alert")).toContainText("保存暂不可用");
  await expect(page.getByRole("textbox", { name: "电压等级", exact: true })).toHaveValue("220V");
  await expect(page.getByRole("textbox", { name: "终点端子", exact: true })).toHaveValue("");
  await page.getByRole("textbox", { name: "电压等级", exact: true }).press("Enter");
  await expect(page.locator(".editing-cell input")).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
  expect(bodies[0]).toEqual(bodies[1]);
  expect(bodies[0].changes).toEqual({ voltage_level: "220V", end_terminal: null });
});

test("后台刷新不替换编辑基线，版本冲突留住草稿并可取消刷新", async ({ page }) => {
  let revision = 1;
  let endpoint = "X3:2";
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/projects/*/connections?**", route => route.fulfill({ json: { items: rows.map((row, index) => ({ ...row, end_terminal: index === 1 ? endpoint : row.end_terminal, record_version: revision })), offset: 0, limit: 100, has_more: false, result_version_id: result, result_revision: revision, result_version: 1 } }));
  await page.route("**/api/v1/supervisor/turns/stream", route => route.fulfill({ contentType: "text/event-stream", body: `event: response\ndata: ${JSON.stringify({ receipt: null, user_event: { user_message: "状态已刷新" } })}\n\n` }));
  await page.route("**/api/v1/connections/*", route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 409, json: { detail: { message: "数据已变更，请刷新后重试" } } });
  });
  await page.goto(`/projects/${project}`);
  await expect(page.locator(".result-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑 XD3:2", exact: true }).click();
  await page.getByRole("textbox", { name: "终点端子", exact: true }).fill("我的草稿");
  revision = 2; endpoint = "其他人已改";
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("查询状态");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".table-footer")).toContainText("r2");
  await page.getByRole("button", { name: "收起聊天窗口" }).click();
  const end = page.getByRole("textbox", { name: "终点端子", exact: true });
  await expect(end).toHaveValue("我的草稿");
  await end.press("Enter");
  await expect(page.getByRole("alert")).toContainText("数据已变更");
  await expect(end).toHaveValue("我的草稿");
  expect(submitted).toMatchObject({ result_revision: 1, record_version: 1 });
  await page.getByRole("button", { name: "取消编辑并刷新" }).click();
  await expect(page.locator(".editing-cell input")).toHaveCount(0);
  await expect(page.locator(".result-table tbody tr").nth(1).locator("td").nth(10)).toHaveText("其他人已改");
});

test("上传触发真实接口、人工类型确认与三阶段事件卡片", async ({ page }) => {
  const runId = "10000000-0000-4000-8000-000000000099";
  const messages: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/imports?**", route => route.fulfill({ json: { project_id: project, attachment_id: source } }));
  await page.route("**/api/v1/supervisor/turns/stream", async route => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    messages.push(payload);
    const response = messages.length === 1 ? { receipt: null, user_event: { user_message: "检测为 zh，请确认类型。", requires_input: true } } : { receipt: { agent_run_id: runId }, user_event: { user_message: "确认完成，开始三阶段。" } };
    await route.fulfill({ contentType: "text/event-stream", body: `event: message\ndata: ${JSON.stringify({ event_type: "SUPERVISOR_PLAN", user_message: "读取图纸首页并规划处理", occurred_at: "2026-10-12" })}\n\nevent: response\ndata: ${JSON.stringify(response)}\n\n` });
  });
  await page.route(`**/api/v1/runs/${runId}/events/stream?**`, route => route.fulfill({ contentType: "text/event-stream", body: ["PAGE_CLASSIFICATION", "PAGE_SCAN", "CROSS_PAGE_COMPLETION"].flatMap((stage, i) => ["STAGE_STARTED", "STAGE_COMPLETED"].map((event, j) => `id: ${i * 2 + j}\nevent: ${event}\ndata: ${JSON.stringify({ seq: i * 2 + j, agent_run_id: runId, stage, event_type: event, message: `${stage} ${event}`, occurred_at: "2026-10-12" })}\n\n`)).join("") }));
  await page.route(`**/api/v1/runs/${runId}`, route => route.fulfill({ json: { run: { status: "SUCCEEDED" } } }));
  await page.route(`**/api/v1/runs/${runId}/artifacts`, route => route.fulfill({ json: { items: [] } }));
  await page.goto("/projects");
  await page.locator('input[type="file"]').setInputFiles({ name: "fixture.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\nfixture") });
  await expect(page.getByRole("heading", { name: "验收工程" })).toBeVisible();
  await expect.poll(() => messages.length).toBe(1);
  expect(messages[0].attachment_ids).toEqual([source]);
  expect(messages[0].user_id).toBeUndefined();
  await expect(page.getByText("检测为 zh，请确认类型。", { exact: true })).toBeVisible();
  await expect(page.locator(".agent-step-pending")).toContainText("等待用户确认");
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("确认 zh，请提取");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".agent-step-done").filter({ hasText: "Stage 3" }).first()).toBeVisible();
  expect(messages.length).toBe(2);
  const panel = await page.locator(".ai-panel").textContent();
  expect(panel).toContain("Stage 1"); expect(panel).toContain("Stage 2"); expect(panel).toContain("Stage 3");
  await expect(page.locator(".agent-event-stage")).toHaveCount(3);
  await expect(page.getByRole("dialog", { name: "AI 助手" })).toHaveCSS("position", "fixed");
  await expect(page.getByRole("separator", { name: "调整 Agent 面板宽度" })).toHaveCount(0);
});

test("聊天关闭期间继续订阅进度，重开不重复发起任务", async ({ page }) => {
  const runId = "10000000-0000-4000-8000-000000000098";
  let turns = 0; const cursors: string[] = [];
  let finishStage: () => void = () => {};
  const finish = new Promise<void>(resolve => { finishStage = resolve; });
  await page.route("**/api/v1/supervisor/turns/stream", async route => {
    turns++;
    await route.fulfill({ contentType: "text/event-stream", body: `event: response\ndata: ${JSON.stringify({ receipt: { agent_run_id: runId }, user_event: { user_message: "已开始当前页重识别。" } })}\n\n` });
  });
  await page.route(`**/api/v1/runs/${runId}/events/stream?**`, async route => {
    const cursor = new URL(route.request().url()).searchParams.get("after_seq")!;
    cursors.push(cursor);
    if (cursor !== "-1") await finish;
    const e = cursor === "-1" ? { seq: 0, event_type: "STAGE_STARTED", stage: "PAGE_SCAN", message: "扫描开始" } : { seq: 1, event_type: "STAGE_COMPLETED", stage: "PAGE_SCAN", message: "扫描已完成" };
    await route.fulfill({ contentType: "text/event-stream", body: `event: ${e.event_type}\ndata: ${JSON.stringify({ ...e, agent_run_id: runId, occurred_at: "2026-10-12" })}\n\n` });
  });
  await page.route(`**/api/v1/runs/${runId}`, route => route.fulfill({ json: { run: { status: cursors.length > 1 ? "SUCCEEDED" : "RUNNING" } } }));
  await page.route(`**/api/v1/runs/${runId}/artifacts`, route => route.fulfill({ json: { items: [] } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("重新识别当前连接");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".agent-event-stage")).toContainText("扫描开始");
  await page.getByRole("button", { name: "收起聊天窗口" }).click();
  await expect(page.getByRole("dialog", { name: "AI 助手" })).toHaveCount(0);
  finishStage();
  await expect(page.getByRole("button", { name: "打开 AI 聊天面板" }).locator(".agent-launcher-badge")).toBeVisible();
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await expect(page.locator(".agent-event-stage")).toContainText("扫描已完成");
  await expect(page.locator(".agent-event-stage")).toHaveCount(1);
  expect(cursors).toEqual(["-1", "0"]);
  expect(turns).toBe(1);
});

test("纠错阶段卡片、人工确认后刷新真实结果及归因说明", async ({ page }) => {
  const correction = "10000000-0000-4000-8000-000000000090";
  const improvement = "10000000-0000-4000-8000-000000000091";
  const proposal = `${correction}:result-proposal`;
  let accepted = false;
  const turns: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/projects/*/connections?**", route => route.fulfill({ json: { items: rows.map(r => ({ ...r, end_terminal: accepted && r.core_order === 1 ? "X3:9" : r.end_terminal })), offset: 0, limit: 100, has_more: false, result_version_id: result, result_version: 1, result_revision: accepted ? 2 : 1 } }));
  await page.route("**/api/v1/supervisor/turns/stream", async route => {
    const input = route.request().postDataJSON() as Record<string, unknown>;
    turns.push(input);
    if (turns.length === 2) { expect(input.target_hint).toEqual({ proposal_id: proposal }); accepted = true; }
    await route.fulfill({ contentType: "text/event-stream", body: `event: response\ndata: ${JSON.stringify({ receipt: { agent_run_id: accepted ? improvement : correction }, user_event: { user_message: accepted ? "修订已提交，开始归因。" : "正在重新识别指定连接。" } })}\n\n` });
  });
  await page.route(`**/api/v1/runs/${correction}/events/stream?**`, route => route.fulfill({ contentType: "text/event-stream", body: ["STAGE_STARTED", "STAGE_COMPLETED"].map((event_type, seq) => `event: ${event_type}\ndata: ${JSON.stringify({ seq, agent_run_id: correction, stage: "PAGE_SCAN", event_type, message: "当前页纠错", occurred_at: "2026-10-12" })}\n\n`).join("") }));
  await page.route(`**/api/v1/runs/${improvement}/events/stream?**`, route => route.fulfill({ contentType: "text/event-stream", body: `event: RUN_COMPLETED\ndata: ${JSON.stringify({ seq: 0, agent_run_id: improvement, event_type: "RUN_COMPLETED", message: "归因已完成", occurred_at: "2026-10-12" })}\n\n` }));
  await page.route(`**/api/v1/runs/${correction}`, route => route.fulfill({ json: { run: { status: "NEEDS_REVIEW" } } }));
  await page.route(`**/api/v1/runs/${improvement}`, route => route.fulfill({ json: { run: { status: "SUCCEEDED" } } }));
  await page.route(`**/api/v1/runs/${correction}/artifacts`, route => route.fulfill({ json: { items: [{ kind: "result_proposal", proposal_id: proposal }] } }));
  await page.route(`**/api/v1/runs/${improvement}/artifacts`, route => route.fulfill({ json: { items: [{ kind: "improvement_diagnosis", candidate_recommended: false, diagnoses: [{ category: "MODEL_PERCEPTION_ERROR", explanation: "规则无问题，模型读取了相邻线路。" }] }] } }));
  await page.route("**/api/v1/proposals/**", route => route.fulfill({ json: { feedback_id: "feedback-fixture", operations: [{ target_id: rows[0].connection_id, before: { end_terminal: "X3:1" }, after: { end_terminal: "X3:9" } }], committed_result_version_id: null } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("button", { name: "打开 AI 聊天面板" }).click();
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("重新识别 XD3:1 的终点端子");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.locator(".agent-step-pending")).toContainText("待确认修订");
  await expect(page.getByRole("button", { name: "X3:1", exact: true })).toBeVisible();
  expect(accepted).toBe(false);
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("确认修改");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
  await expect(page.getByRole("button", { name: "X3:9", exact: true })).toBeVisible();
  await expect(page.locator(".agent-feed")).toContainText("纠错归因结果");
  await expect(page.locator(".agent-feed")).toContainText("规则无问题，模型读取了相邻线路。");
  expect(turns.length).toBe(2);
});
