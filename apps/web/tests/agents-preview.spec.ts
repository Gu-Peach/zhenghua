import { test, expect, type Page } from "@playwright/test";

const project = "00000000-0000-0000-0000-000000000010";
const source = "00000000-0000-0000-0000-000000000011";
const target = "00000000-0000-0000-0000-000000000012";
const third = "00000000-0000-0000-0000-000000000013";
const rowId = "00000000-0000-0000-0000-000000000014";
const anotherRow = "00000000-0000-0000-0000-000000000015";
const ruleId = "00000000-0000-0000-0000-000000000016";

async function fixture(page: Page, options: { samePage?: boolean; swapped?: boolean; coordinates?: "missing" | "mismatch" | "invalid"; failTarget?: boolean; slowTarget?: Promise<void>; failCapabilities?: boolean; loggedOut?: boolean; brokenImage?: boolean } = {}) {
  const calls: string[] = [];
  const image = (id: string, pdf: number) => ({ id, project_id: project, workspace_id: "work", pdf_page_number: pdf, workspace_page: `003C0${pdf}`, status: "completed", image_url: "/preview-fixture.svg" });
  const rows = [
    { connection_id: rowId, project_id: project, batch_id: "run-one", workspace_id: "work", workspace_name: "003.C", drawing_id: source, workspace_page: "003C01", pdf_page_number: 1, row_order: 0, record_version: 1, start_terminal: "XA:8", end_terminal: "XD10:1", principle_number: "003C0101", wire_number: "1000", current_value: "160A", is_cross_page: !options.samePage, target_pdf_page_number: options.samePage ? null : 2,
      start_terminal_coordinates: options.coordinates === "missing" ? null : { x: options.coordinates === "invalid" ? 2 : .25, y: .35, pdf_page_number: options.coordinates === "mismatch" ? 99 : 1 },
      end_terminal_coordinates: options.coordinates === "missing" ? null : { x: .72, y: .62, pdf_page_number: options.samePage ? 1 : 2 } },
    { connection_id: anotherRow, project_id: project, batch_id: "run-one", workspace_id: "work", workspace_name: "003.C", drawing_id: third, workspace_page: "003C03", pdf_page_number: 3, row_order: 1, record_version: 1, start_terminal: "XB:2", end_terminal: "XB:3", principle_number: "003C0301", wire_number: "1001", current_value: "80A", is_cross_page: false,
      start_terminal_coordinates: { x: .8, y: .25, pdf_page_number: 3 }, end_terminal_coordinates: { x: .18, y: .7, pdf_page_number: 3 } },
  ];
  if (options.swapped) {
    [rows[0].start_terminal_coordinates, rows[0].end_terminal_coordinates] = [rows[0].end_terminal_coordinates, rows[0].start_terminal_coordinates];
  }
  await page.route("**/preview-fixture.svg", route => options.brokenImage ? route.fulfill({ status: 404 }) : route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="white"/><path d="M250 210 H720 V372" stroke="#536c7b" fill="none" stroke-width="3"/><text x="250" y="195" font-size="20">XA:8</text><text x="720" y="405" font-size="20">XD10:1</text></svg>' }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname; calls.push(path);
    if (path.includes("/auth/")) return options.loggedOut ? route.fulfill({ status: 401, json: { detail: "not logged in" } }) : route.fulfill({ json: { user: { id: "owner", name: "校验工程师", email: "fixture@example.invalid", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (path === "/api/v1/capabilities") return options.failCapabilities ? route.fulfill({ status: 503, json: { detail: { message: "能力接口不可用" } } }) : route.fulfill({ json: { extraction: true, explain: true, supervisor: false } });
    const detail = { id: project, name: "图纸校验夹具项目", status: "ready", updated_at: "2026-10-17", standard_profile: "zh", source_saved: false, batch_id: "run-one", workspaces: [{ id: "work", code: "003.C", name: "003.C", drawings: [image(source, 1), image(target, 2), image(third, 3)] }] };
    if (path === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (path === `/api/v1/projects/${project}`) return route.fulfill({ json: detail });
    if (path.endsWith("/connections")) return route.fulfill({ json: { items: rows, batch_id: "run-one", offset: 0, limit: 100, has_more: false } });
    if (path.endsWith("/target")) {
      if (options.slowTarget) await options.slowTarget;
      return options.failTarget ? route.fulfill({ status: 404, json: { detail: { message: "未找到目标页" } } }) : route.fulfill({ json: image(target, 2) });
    }
    if (path.startsWith("/api/v1/drawings/")) return route.fulfill({ json: path.endsWith(third) ? image(third, 3) : path.endsWith(target) ? image(target, 2) : image(source, 1) });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [{ id: ruleId, profile_key: "zh", profile_version: "2.1.1", display_name: "振华提取规则", resource_ref: "storage://project-assets/profiles/owner/zh/2.1.1/package.zip", checksum: "sha256:" + "0".repeat(64), created_at: "2026-10-17" }] });
    if (path === `/api/v1/rule-library/${ruleId}`) return route.fulfill({ json: { manifest: {}, files: ["classification", "page_scan", "cross_page"].map(stage => ({ path: `resources/${stage}_prompt.md`, content: `夹具 ${stage} 规则` })), images: [] } });
    return route.fulfill({ status: 404, json: { detail: { message: "未定义夹具请求" } } });
  });
  return { calls };
}

async function workbench(page: Page) { await page.goto(`/projects/${project}`); await expect(page.getByRole("cell", { name: "XA:8", exact: true })).toBeVisible(); }
async function agentCenter(page: Page) { await page.locator(".account-trigger").click(); await page.getByRole("button", { name: "智能体中心", exact: true }).click(); }

test("默认线表占满高度，移除线号、规则库和底部图纸；预览时保持同一张表", async ({ page }) => {
  const state = await fixture(page); await workbench(page);
  await expect(page.getByRole("columnheader", { name: "线号", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "规则库", exact: true })).toHaveCount(0);
  await expect(page.locator(".drawing-preview")).toHaveCount(0);
  expect(state.calls.some(path => path.includes("/drawings/"))).toBe(false);
  const shell = await page.locator(".result-table-shell").boundingBox(); expect(shell!.height).toBeGreaterThan(350);
  await page.getByRole("button", { name: "图纸预览", exact: true }).click();
  await expect(page.locator(".result-table th")).toHaveText(["页码", "原理号", "起点端子", "终点端子", "电流"]);
  await expect(page.getByRole("region", { name: "原页预览" })).toBeVisible();
  await expect(page.locator(".results-section tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "线表工作区", exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "起点描述" })).toBeVisible();
  await expect(page.locator(".drawing-preview")).toHaveCount(0);
  const next = await page.getByRole("button", { name: "下一页", exact: true }).boundingBox();
  const launcher = await page.getByRole("button", { name: "打开 AI 聊天面板", exact: true }).boundingBox();
  expect(next!.x + next!.width).toBeLessThanOrEqual(launcher!.x);
  await page.screenshot({ path: test.info().outputPath("full-table-desktop.png") });
});

test("跨页上下图纸标出所选两端，缩放后坐标与图像保持一致", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  const original = page.getByRole("region", { name: "原页预览" }); const destination = page.getByRole("region", { name: "目标页预览" });
  await expect(original.getByRole("img", { name: "起点 XA:8", exact: true })).toBeVisible();
  await expect(destination.getByRole("img", { name: "终点 XD10:1", exact: true })).toBeVisible();
  await expect(original.locator(".terminal-marker-end")).toHaveCount(0);
  const originalBox = await original.boundingBox(); const destinationBox = await destination.boundingBox();
  expect(destinationBox!.y).toBeGreaterThan(originalBox!.y + originalBox!.height - 2);
  async function checkPosition() {
    const frame = await original.locator(".evidence-image-frame").boundingBox();
    const marker = await original.locator(".terminal-marker-start").boundingBox();
    expect(Math.abs(marker!.x + marker!.width / 2 - frame!.x - frame!.width * .25)).toBeLessThan(2);
    expect(Math.abs(marker!.y + marker!.height / 2 - frame!.y - frame!.height * .35)).toBeLessThan(2);
  }
  await expect(original.locator(".evidence-image-frame img")).toHaveJSProperty("naturalWidth", 1000);
  await checkPosition(); await original.getByRole("button", { name: "放大", exact: true }).click(); await checkPosition();
  await page.screenshot({ path: test.info().outputPath("cross-page-markers-desktop.png") });
});

test("预览分隔条支持拖拽键盘与恢复比例，缩放工具栏不溢出", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await fixture(page); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  const divider = page.getByRole("separator", { name: "调整线表与图纸宽度" });
  const table = page.locator(".results-section");
  const initial = await table.boundingBox();
  const handle = await divider.boundingBox(); expect(handle).not.toBeNull();
  await page.mouse.move(handle!.x + handle!.width / 2, handle!.y + 60);
  await page.mouse.down(); await page.mouse.move(handle!.x + 150, handle!.y + 60, { steps: 8 }); await page.mouse.up();
  expect((await table.boundingBox())!.width).toBeGreaterThan(initial!.width + 100);
  await divider.focus(); await page.keyboard.press("Home");
  const minimum = (await table.boundingBox())!.width;
  await page.keyboard.press("ArrowRight"); expect((await table.boundingBox())!.width).toBeGreaterThan(minimum);
  await page.keyboard.press("End");
  expect((await page.locator(".connection-preview").boundingBox())!.width).toBeGreaterThanOrEqual(279);
  const original = page.getByRole("region", { name: "原页预览" });
  for (let n = 0; n < 12; n++) await original.getByRole("button", { name: "放大", exact: true }).click();
  const percentage = original.getByRole("button", { name: "400%", exact: true });
  await expect(percentage).toBeVisible();
  expect(await percentage.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await expect(original.locator(".preview-toolbar")).toHaveJSProperty("scrollWidth", await original.locator(".preview-toolbar").evaluate(node => node.clientWidth));
  await percentage.click(); await expect(original.getByRole("button", { name: "100%", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("resized-preview-desktop.png") });
  await divider.dblclick(); expect(Math.abs((await table.boundingBox())!.width - initial!.width)).toBeLessThan(2);
  await divider.focus(); await page.keyboard.press("ArrowLeft");
  const chosen = (await table.boundingBox())!.width;
  await page.getByRole("button", { name: "线表工作区", exact: true }).click(); await expect(divider).toHaveCount(0);
  await page.getByRole("button", { name: "图纸预览", exact: true }).click();
  expect(Math.abs((await table.boundingBox())!.width - chosen)).toBeLessThan(2);
  await page.setViewportSize({ width: 900, height: 900 });
  expect((await page.locator(".connection-preview").boundingBox())!.width).toBeGreaterThanOrEqual(279);
});

test("同页连接在原图标出两端，不请求目标图", async ({ page }) => {
  const state = await fixture(page, { samePage: true }); await workbench(page);
  await page.getByRole("button", { name: "XA:8", exact: true }).click();
  const original = page.getByRole("region", { name: "原页预览" });
  await expect(original.locator(".terminal-marker")).toHaveCount(2);
  await expect(page.getByText("同页连接：两端在上方原页标注")).toBeVisible();
  expect(state.calls.some(path => path.endsWith("/target"))).toBe(false);
});

test("端点交换后原页显示终点、跨页显示起点，按坐标自身页号标注", async ({ page }) => {
  await fixture(page, { swapped: true }); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  const original = page.getByRole("region", { name: "原页预览" });
  const destination = page.getByRole("region", { name: "目标页预览" });
  await expect(original.getByRole("img", { name: "终点 XD10:1", exact: true })).toBeVisible();
  await expect(destination.getByRole("img", { name: "起点 XA:8", exact: true })).toBeVisible();
  await expect(destination.locator(".preview-toolbar")).not.toContainText("终点 XD10:1");
  await expect(original.locator(".coordinate-note")).toHaveCount(0);
  await expect(destination.locator(".coordinate-note")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("swapped-endpoints-kept-page.png") });
});

for (const coordinates of ["missing", "mismatch", "invalid"] as const) test(`坐标${coordinates}时不猜测位置`, async ({ page }) => {
  await fixture(page, { coordinates }); await workbench(page);
  await page.getByRole("button", { name: "XA:8", exact: true }).click();
  const original = page.getByRole("region", { name: "原页预览" });
  await expect(original.locator(".terminal-marker-start")).toHaveCount(0);
  await expect(original.locator(".coordinate-note")).toContainText(coordinates === "missing" ? "未保存坐标" : coordinates === "mismatch" ? "所属PDF页不匹配" : "坐标无效");
});

test("目标页失败保留原图，切换连接后旧跨页响应不覆盖新原页", async ({ page }) => {
  let release!: () => void; const pending = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { slowTarget: pending }); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  await expect(page.getByText("正在读取图纸…")).toBeVisible();
  await page.getByRole("button", { name: "XB:2", exact: true }).click();
  const original = page.getByRole("region", { name: "原页预览" });
  await expect(original.getByRole("img", { name: "起点 XB:2", exact: true })).toBeVisible();
  release();
  await expect(original).toContainText("003C03"); await expect(page.getByRole("region", { name: "目标页预览" })).toHaveCount(0);
});

test("目标页404保留原页及起点，图纸失败状态可见", async ({ page }) => {
  await fixture(page, { failTarget: true }); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("目标页读取失败");
  await expect(page.getByRole("region", { name: "原页预览" }).getByRole("img", { name: "起点 XA:8", exact: true })).toBeVisible();
});

test("智能体中心展示三个真实能力状态，提取Skill沿用规则ID和版本", async ({ page }) => {
  await fixture(page); await workbench(page); await agentCenter(page);
  await expect(page).toHaveURL("/agents"); await expect(page.locator(".agent-card")).toHaveCount(3);
  await expect(page.getByText("1.0.0", { exact: true })).toHaveCount(3);
  await expect(page.locator(".agent-card").filter({ hasText: "Profile Agent" })).toContainText("待接入");
  await page.screenshot({ path: test.info().outputPath("agent-center-desktop.png") });
  await page.getByRole("link", { name: /图纸提取智能体/ }).click();
  await expect(page.getByText("zh_extraction", { exact: true })).toBeVisible();
  await expect(page.getByText(/版本 2.1.1/)).toBeVisible();
  await page.getByRole("textbox", { name: "搜索提取规则" }).fill("zh_extraction");
  await page.getByRole("button", { name: "查看规则", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("zh_extraction");
  await page.getByRole("button", { name: "Stage 2 内部连接补全", exact: true }).click();
  await expect(page.getByText("夹具 cross_page 规则", { exact: true })).toBeVisible();
});

test("状态接口失败与智能体路由权限不伪造可用状态", async ({ page }) => {
  await fixture(page, { failCapabilities: true }); await page.goto("/agents");
  await expect(page.getByRole("alert")).toContainText("状态读取失败");
  await expect(page.locator(".agent-card")).toHaveCount(0);
});

test("未登录无法进入智能体中心", async ({ page }) => {
  await fixture(page, { loggedOut: true }); await page.goto("/agents/extraction");
  await expect(page).toHaveURL("/login");
});

test("窄屏按上下布局保留线表和双图，智能体卡片不溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page); await workbench(page);
  await page.getByRole("button", { name: "XD10:1", exact: true }).click();
  await expect(page.getByRole("region", { name: "目标页预览" })).toBeVisible();
  const table = await page.locator(".results-section").boundingBox(); const preview = await page.locator(".connection-preview").boundingBox();
  expect(preview!.y).toBeGreaterThanOrEqual(table!.y + table!.height - 2);
  expect(preview!.width).toBeLessThanOrEqual(390);
  await expect(page.getByRole("separator", { name: "调整线表与图纸宽度" })).toBeHidden();
  for (const toolbar of await page.locator(".connection-preview .preview-toolbar").all()) {
    expect(await toolbar.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    expect((await toolbar.boundingBox())!.height).toBeLessThan(80);
  }
  await page.screenshot({ path: test.info().outputPath("preview-narrow.png"), fullPage: true });
  await agentCenter(page); await expect(page.locator(".agent-card")).toHaveCount(3);
  await page.screenshot({ path: test.info().outputPath("agent-center-narrow.png"), fullPage: true });
});
