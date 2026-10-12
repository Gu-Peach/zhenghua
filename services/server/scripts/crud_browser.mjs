// Real Server/Supabase browser acceptance; secrets are passed in process memory only.
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium, expect } = require("@playwright/test");
const fixture = JSON.parse(process.env.WIRING_BROWSER_FIXTURE);
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  // Only port routing is changed; all requests reach the real API, no fixture replies.
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    return route.continue({ url: fixture.api + url.pathname + url.search });
  });
  await page.goto(fixture.web + "/login");
  await page.getByLabel("邮箱", { exact: true }).fill(fixture.email);
  await page.getByLabel("密码", { exact: true }).fill(fixture.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "项目目录" })).toBeVisible();
  await page.goto(fixture.web + "/projects/" + fixture.project);
  await expect(page.getByRole("button", { name: "新增端子", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "新增端子", exact: true }).click();
  await page.getByLabel("起点端子", { exact: true }).fill("XD3:20");
  await page.getByLabel("终点端子", { exact: true }).fill("X3:20");
  await page.getByLabel("跨页目标（可选）", { exact: true }).selectOption(fixture.target);
  await page.getByRole("button", { name: "确认新增", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑 XD3:20", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑 XD3:20", exact: true }).click();
  await page.getByLabel("终点端子", { exact: true }).fill("X3:21");
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "X3:21", exact: true }).click();
  await expect(page.locator(".below-previews .drawing-preview")).toHaveCount(2);
  await expect(page.locator(".below-previews .drawing-preview img")).toHaveCount(2);
  await page.screenshot({ path: ".runtime/real-browser/real-crud.png", fullPage: true });
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "删除 XD3:20", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑 XD3:20", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "编辑 XD3:1", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "编辑 XD3:1", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "编辑 XD3:20", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "图纸库", exact: true }).click();
  await expect(page.locator(".drawing-index")).toContainText("业务页 1 · PDF 1");
  await page.getByRole("button", { name: "业务页 2 · PDF 2", exact: true }).click();
  await expect(page.locator(".below-previews img")).toHaveCount(1);
  await page.getByRole("button", { name: "规则库", exact: true }).click();
  const rule = page.locator(".rule-row").filter({ has: page.getByText("zh", { exact: true }) });
  await rule.getByRole("button", { name: "查看规则", exact: true }).click();
  const modal = page.getByRole("dialog");
  await expect(modal.getByRole("heading", { level: 2 })).toContainText("真实资源包");
  for (const stage of ["Stage 1 页面分类", "Stage 2 当前页扫描", "Stage 3 跨页补全"]) {
    await modal.getByRole("button", { name: stage, exact: true }).click();
    await expect(modal.locator(".resource-body > pre")).not.toContainText("未提供");
    await expect.poll(async () => (await modal.locator(".resource-body > pre").innerText()).length).toBeGreaterThan(100);
    await expect.poll(() => modal.locator(".rule-example").count()).toBeGreaterThan(0);
    await expect(modal.locator(".rule-example").first().getByRole("heading", { level: 4 })).toBeVisible();
    const images = modal.locator(".sample-grid img");
    await expect.poll(() => images.count()).toBeGreaterThan(0);
    await expect.poll(() => images.evaluateAll(imgs => imgs.every(img => img.complete && img.naturalWidth > 0))).toBe(true);
    const example = modal.locator(".rule-example").first();
    await example.getByText("人工确认的预期结果", { exact: true }).click();
    await expect.poll(() => example.locator("details pre").last().innerText()).not.toBe("");
    await page.screenshot({ path: `.runtime/real-browser/rules-stage-${stage.charAt(6)}.png`, fullPage: true });
  }
  await modal.getByRole("button", { name: "刷新资源链接", exact: true }).click();
  await expect.poll(() => modal.locator(".sample-grid img").evaluateAll(imgs => imgs.length > 0 && imgs.every(img => img.complete && img.naturalWidth > 0))).toBe(true);
  await modal.getByRole("button", { name: "关闭规则面板", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".runtime/real-browser/real-rules-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  console.log("PASS: real browser Auth, CRUD, persisted refresh, drawing index, three-stage Bucket rules/examples/expected/images");
} catch (error) {
  const safe = String(error.message).replaceAll(fixture.password, "[REDACTED]").replaceAll(fixture.email, "[TEMP_USER]");
  console.error(safe);
  process.exitCode = 1;
} finally { await browser.close(); }
