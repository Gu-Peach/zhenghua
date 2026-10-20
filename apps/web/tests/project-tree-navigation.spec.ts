import { test, expect, type Page } from "@playwright/test";
import { expandProjectTree, expandWorkspace } from "./tree-navigation";

const project = "tree-project";
async function fixture(page: Page) {
  const workspaces = Array.from({ length: 35 }, (_, index) => ({
    id: `w${index}`, code: `${String(index).padStart(3, "0")}.R`, name: `${String(index).padStart(3, "0")}.R`,
    drawings: Array.from({ length: 20 }, (_, drawing) => ({ id: `d${index}-${drawing}`, workspace_id: `w${index}`, workspace_page: `P${index}-${String(drawing).padStart(2, "0")}`, pdf_page_number: index * 20 + drawing + 1, status: "scanned" })),
  }));
  const detail = { id: project, name: "大型目录测试项目", status: "ready", updated_at: "2026-10-19", source_saved: false, batch_id: "batch", workspaces };
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.includes("/auth/")) return route.fulfill({ json: { user: { id: "owner", name: "测试工程师", role: "工程师" }, accessToken: "fixture" } });
    if (url.pathname === "/api/v1/capabilities") return route.fulfill({ json: { extraction: false, explain: false, supervisor: false } });
    if (url.pathname === "/api/v1/projects") return route.fulfill({ json: [detail] });
    if (url.pathname === `/api/v1/projects/${project}`) return route.fulfill({ json: detail });
    if (url.pathname.endsWith("/connections")) return route.fulfill({ json: { items: [], batch_id: "batch", offset: 0, limit: 100, has_more: false } });
    return route.fulfill({ status: 404, json: {} });
  });
}

test("默认项目和工作区均收起，单个展开不会展开其他工作区", async ({ page }) => {
  await fixture(page); await page.goto(`/projects/${project}`);
  await expect(page.getByRole("button", { name: "展开项目 大型目录测试项目", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".workspace-row")).toHaveCount(0);
  await expandProjectTree(page);
  await expect(page.locator(".workspace-row")).toHaveCount(35);
  await expect(page.locator(".tree-toggle[aria-expanded=true]")).toHaveCount(0);
  await expect(page.locator(".drawing-row")).toHaveCount(0);
  await expandWorkspace(page, "001.R");
  await expect(page.locator(".drawing-row")).toHaveCount(20);
  await expect(page.locator(".tree-toggle[aria-expanded=true]")).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath("tree-default-desktop.png") });
});

test("长目录选择工作区和图纸保留展开与滚动，前进后退跟随选中节点", async ({ page }) => {
  await fixture(page); await page.goto(`/projects/${project}`); await expandProjectTree(page);
  await expandWorkspace(page, "001.R");
  const nav = page.getByRole("navigation", { name: "项目、工作区和图纸" });
  await page.getByRole("button", { name: /^025\.R 025\.R/ }).click();
  await expect(page).toHaveURL(new RegExp("workspace=w25"));
  await expect(page.locator('.tree-select[aria-current="page"]')).toContainText("025.R");
  await expect(page.getByRole("button", { name: "收起001.R", exact: true })).toBeVisible();
  await expect.poll(() => nav.evaluate(element => element.scrollTop)).toBeGreaterThan(500);
  const drawing = page.getByRole("button", { name: /^P25-19 PDF/ });
  await drawing.click();
  await expect(page).toHaveURL(new RegExp("drawing=d25-19"));
  await expect(drawing).toHaveAttribute("aria-current", "page");
  await expect.poll(() => nav.evaluate(element => element.scrollTop)).toBeGreaterThan(500);
  await expect(page.getByRole("button", { name: "收起001.R", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect.poll(async () => {
    const parent = (await nav.boundingBox())!; const row = (await drawing.boundingBox())!;
    return row.y >= parent.y - 1 && row.y + row.height <= parent.y + parent.height + 1;
  }).toBe(true);
  await page.screenshot({ path: test.info().outputPath("tree-follow-desktop.png") });
  await page.goBack(); await expect(page.locator('.tree-select[aria-current="page"]')).toContainText("025.R");
  await expect.poll(() => nav.evaluate(element => element.scrollTop)).toBeGreaterThan(500);
  await page.goForward(); await expect(drawing).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "收起025.R", exact: true }).click();
  await expect(drawing).toHaveCount(0);
  await page.getByRole("button", { name: "展开025.R", exact: true }).click();
  await expect(drawing).toBeVisible();
});

test("深层链接仅展开祖先并定位，窄屏只滚动树容器", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page);
  await page.goto(`/projects/${project}?workspace=w30&drawing=d30-18`);
  const selected = page.getByRole("button", { name: /^P30-18 PDF/ });
  await expect(selected).toHaveAttribute("aria-current", "page");
  await expect(page.locator(".tree-toggle[aria-expanded=true]")).toHaveCount(1);
  await expect(page.locator(".drawing-row")).toHaveCount(20);
  const nav = page.getByRole("navigation", { name: "项目、工作区和图纸" });
  await expect.poll(() => nav.evaluate(element => element.scrollTop)).toBeGreaterThan(500);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: test.info().outputPath("tree-follow-mobile.png") });
});
