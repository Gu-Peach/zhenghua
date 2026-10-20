import { expect, test, type Page } from "@playwright/test";
import { expandProjectTree, expandWorkspace } from "./tree-navigation";

const id = "gcr-relations-fixture";
const source = `/projects/${id}?workspace=gcr-work&drawing=gcr101&view=relations`;
async function fixture(page: Page, options: { denied?: boolean; fail?: boolean; gate?: Promise<void>; longName?: boolean; unrelated?: boolean } = {}) {
  const calls: string[] = [];
  const detail = { id, name: options.unrelated ? "其他项目" : `1002001693大车卷盘图纸${options.longName ? "很长的项目名称用于核验关联图谱与目录布局".repeat(8) : ""}`,
    owner_id: "owner", status: "ready", updated_at: "2026-10-20", source_saved: false, standard_profile: "zh_gantry_reel", batch_id: "batch",
    workspaces: [{ id: "gcr-work", code: "GCR.1", name: "GCR.1", drawings: [
      { id: "gcr101", workspace_id: "gcr-work", workspace_page: "GCR101", pdf_page_number: 2, status: "scanned" },
      { id: "gcr102", workspace_id: "gcr-work", workspace_page: "GCR102", pdf_page_number: 3, status: "scanned" },
    ] }] };
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url()); const p = url.pathname;
    if (p.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "测试", role: "工程师" }, accessToken: "fixture", expiresIn: 3600 } });
    if (p === "/api/v1/capabilities") return route.fulfill({ json: { extraction: false, explain: false, supervisor: false } });
    calls.push(`${route.request().method()} ${p}`);
    if (p === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (p === `/api/v1/projects/${id}`) {
      if (options.gate) await options.gate;
      if (options.fail || options.denied) return route.fulfill({ status: options.denied ? 403 : 503, json: { detail: { message: options.denied ? "没有项目访问权限" : "项目服务暂时不可用" } } });
      return route.fulfill({ json: detail });
    }
    if (p.endsWith("/connections")) return route.fulfill({ json: { items: [], offset: 0, limit: 100, has_more: false, batch_id: "batch" } });
    return route.fulfill({ status: 404, json: {} });
  });
  return calls;
}

test("GCR101图谱、10条端子、两个Mock项目往返及刷新，无模拟业务请求或写入", async ({ page }) => {
  const calls = await fixture(page); await page.goto(source);
  const table = page.getByRole("table", { name: "跨项目端子对应关系" });
  await expect(table.locator("tbody tr")).toHaveCount(10);
  await expect(table.locator("tbody tr").first()).toContainText("XD10:13");
  await expect(table.locator("tbody tr").nth(4)).toContainText("XD21:7");
  await expect(table.locator("tbody tr").nth(8)).toContainText("N-BAR");
  await expect(page.getByLabel("GCR101 跨项目端子关联图谱")).toBeVisible();
  await page.getByRole("button", { name: /^Mock/ }).click();
  await expect(page.locator(".mock-project-folder .project-node")).toHaveCount(2);
  await expect(page.locator(".mock-project-folder .project-action")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("relations-desktop.png") });
  await page.getByLabel("按线号查看关联").getByRole("button", { name: "0262", exact: true }).click();
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await table.getByRole("link", { name: "003C03", exact: true }).first().click();
  await expect(page).toHaveURL(/mock-gcr-low-voltage.*drawing=mock-lv-control/);
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(page.getByRole("button", { name: "重新扫描所选范围" })).toHaveCount(0);
  await page.reload(); await expect(table.locator("tbody tr")).toHaveCount(3);
  await page.getByRole("link", { name: "返回 GCR101", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${id}.*drawing=gcr101`));
  await expect(table.locator("tbody tr")).toHaveCount(10);
  await page.locator(".relation-project-link").filter({ hasText: "照明配电系统" }).click();
  await expect(page).toHaveURL(/mock-gcr-lighting.*drawing=mock-light-aux/);
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await page.goBack(); await expect(table.locator("tbody tr")).toHaveCount(10);
  expect(calls.filter(call => call.includes("mock-"))).toEqual([]);
  expect(calls.every(call => call.startsWith("GET "))).toBe(true);
});

test("目录直接进入Mock、选择图纸和返回自动定位GCR101", async ({ page }) => {
  const calls = await fixture(page); await page.goto(source);
  await page.getByRole("button", { name: /^Mock/ }).click();
  await page.locator(".mock-project-folder").getByRole("link", { name: "低压配电系统（Mock）", exact: true }).click();
  const table = page.getByRole("table", { name: "跨项目端子对应关系" });
  await expect(table.locator("tbody tr")).toHaveCount(7);
  await expandProjectTree(page); await expandWorkspace(page, "003.C");
  await page.getByRole("button", { name: /^003C01 模拟图纸/ }).click();
  await expect(table.locator("tbody tr")).toHaveCount(4);
  await page.getByRole("link", { name: "返回 GCR101", exact: true }).click();
  await expect(table.locator("tbody tr")).toHaveCount(10);
  await expect(page.getByRole("button", { name: /^GCR101 PDF/ })).toHaveAttribute("aria-current", "page");
  expect(calls.filter(call => call.includes("mock-"))).toEqual([]);
});

test("非GCR101空态，切换导航仍保持原有答案对比与线表入口", async ({ page }) => {
  await fixture(page); await page.goto(source);
  await page.getByRole("button", { name: /^GCR102 PDF/ }).click();
  await expect(page.getByText("当前图纸暂无关联项目", { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" })).toHaveCount(0);
  await page.getByRole("button", { name: "答案对比", exact: true }).click();
  await expect(page.getByRole("region", { name: "临时答案对比" })).toBeVisible();
  await page.getByRole("button", { name: "线表工作区", exact: true }).click();
  await expect(page.getByRole("heading", { name: "线表结果" })).toBeVisible();
  await page.getByRole("button", { name: "关联项目", exact: true }).click();
  await page.getByRole("button", { name: "图纸预览", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "图纸校验面板" })).toBeVisible();
});

test("390px窄屏与长项目名可读、图谱键盘导航且页面不横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page, { longName: true }); await page.goto(source);
  const region = page.getByRole("region", { name: "关联项目", exact: true });
  await expect(region.getByRole("table").locator("tbody tr")).toHaveCount(10);
  const link = page.locator(".relation-project-link").first(); await link.focus(); await expect(link).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await region.scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("relations-mobile-long.png"), fullPage: true });
  await link.press("Enter"); await expect(page).toHaveURL(/mock-gcr-low-voltage/);
});

test("加载、失败、无权限不展示关联事实，其他项目无Mock目录", async ({ page }) => {
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { gate }); await page.goto(source);
  await expect(page.getByText("正在读取项目数据…")).toBeVisible();
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" })).toHaveCount(0); release();
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" }).locator("tbody tr")).toHaveCount(10);
  await fixture(page, { fail: true }); await page.goto(source);
  await expect(page.getByRole("alert")).toContainText("项目服务暂时不可用");
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" })).toHaveCount(0);
  await fixture(page, { denied: true }); await page.goto(source);
  await expect(page.getByRole("alert")).toContainText("没有项目访问权限");
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" })).toHaveCount(0);
  await fixture(page, { denied: true }); await page.goto("/projects/mock-gcr-lighting");
  await expect(page.getByRole("alert")).toContainText("没有项目访问权限");
  await expect(page.getByRole("table", { name: "跨项目端子对应关系" })).toHaveCount(0);
  await fixture(page, { unrelated: true }); await page.goto(source);
  await expect(page.getByText("当前图纸暂无关联项目", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Mock/ })).toHaveCount(0);
});

test("登录页桌面和窄屏保持原有表单且不展示Mock入口", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录工程工作台" })).toBeVisible();
  await expect(page.getByLabel("邮箱", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("login-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("密码", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("login-mobile.png"), fullPage: true });
});
