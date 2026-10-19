import { test, expect, type Page } from "@playwright/test";

const id = "00000000-0000-0000-0000-000000000102";
const key = "custom_561305c668af4db3";
async function fixture(page: Page, options: { denied?: boolean; conflict?: boolean; failOnce?: boolean; delayed?: Promise<void> } = {}) {
  let name = "test";
  const writes: unknown[] = [];
  const row = () => ({ id, profile_key: key, display_name: name, profile_version: "1.0.0", checksum: "sha256:" + "0".repeat(64), resource_ref: `storage://project-assets/profiles/owner/${key}/1.0.0/${"0".repeat(64)}.zip`, can_rename: !options.denied, can_delete: !options.denied, created_at: "2026-10-19" });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", expiresIn: 3600, user: { id: "owner", name: "测试工程师", role: "工程师" } } });
    if (path === "/api/v1/capabilities") return route.fulfill({ json: { extraction: true, profile: true } });
    if (path === "/api/v1/projects") return route.fulfill({ json: [] });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [row()] });
    if (path === `/api/v1/rule-library/${id}` && method === "PATCH") {
      const body = route.request().postDataJSON(); writes.push(body);
      if (options.delayed) await options.delayed;
      if (options.conflict || (options.failOnce && writes.length === 1)) return route.fulfill({ status: options.conflict ? 409 : 503, json: { detail: { message: options.conflict ? "规则名称已变化，请刷新后重试" : "保存暂时失败" } } });
      name = body.display_name; return route.fulfill({ json: row() });
    }
    if (path === `/api/v1/rule-library/${id}`) return route.fulfill({ json: { manifest: {}, files: [], images: [] } });
    return route.fulfill({ status: 404, json: { detail: "未定义夹具" } });
  });
  await page.goto("/agents/extraction");
  await expect(page.locator(".rule-row-copy strong")).toHaveText("test");
  return { writes };
}

test("规则显示名可保存和刷新，内部标识与版本保持", async ({ page }) => {
  const data = await fixture(page);
  await page.getByRole("button", { name: "修改规则名称 test", exact: true }).click();
  await page.getByRole("textbox", { name: "规则名称", exact: true }).fill("  大车卷盘规则  ");
  await page.getByRole("textbox", { name: "规则名称", exact: true }).press("Enter");
  await expect(page.locator(".rule-row-copy strong")).toHaveText("大车卷盘规则");
  expect(data.writes).toEqual([{ display_name: "大车卷盘规则", expected_display_name: "test" }]);
  await expect(page.getByText(`${key}_extraction`, { exact: true })).toBeVisible();
  await expect(page.getByText(/版本 1.0.0/)).toBeVisible();
  await page.reload(); await expect(page.locator(".rule-row-copy strong")).toHaveText("大车卷盘规则");
  await page.getByRole("button", { name: "查看规则", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("大车卷盘规则");
});

test("规则改名空白校验、Esc取消及失败保留输入重试", async ({ page }) => {
  const data = await fixture(page, { failOnce: true });
  await page.getByRole("button", { name: "修改规则名称 test", exact: true }).click();
  const input = page.getByRole("textbox", { name: "规则名称", exact: true });
  await input.fill("   "); await input.press("Enter"); await expect(page.getByRole("alert")).toContainText("名称不能为空");
  expect(data.writes).toEqual([]);
  await input.fill("暂时名称"); await input.press("Escape"); await expect(input).toHaveCount(0); expect(data.writes).toEqual([]);
  await page.getByRole("button", { name: "修改规则名称 test", exact: true }).click();
  await input.fill("重试名称"); await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("保存暂时失败"); await expect(input).toHaveValue("重试名称");
  await page.getByRole("button", { name: "保存规则名称", exact: true }).click();
  await expect(page.locator(".rule-row-copy strong")).toHaveText("重试名称"); expect(data.writes).toHaveLength(2);
});

test("非所有者没有改名入口，冲突时不丢输入", async ({ page }) => {
  await fixture(page, { denied: true }); await expect(page.getByRole("button", { name: /^修改规则名称/ })).toHaveCount(0);
  await page.unroute("**/api/v1/**"); await fixture(page, { conflict: true });
  await page.getByRole("button", { name: "修改规则名称 test", exact: true }).click();
  await page.getByRole("textbox", { name: "规则名称", exact: true }).fill("冲突输入");
  await page.getByRole("button", { name: "保存规则名称", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("规则名称已变化");
  await expect(page.getByRole("textbox", { name: "规则名称", exact: true })).toHaveValue("冲突输入");
});

for (const width of [1440, 390]) test(`规则名称长文本编辑布局 ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 960 }); await fixture(page);
  await page.getByRole("button", { name: "修改规则名称 test", exact: true }).click();
  await page.getByRole("textbox", { name: "规则名称", exact: true }).fill("图纸规则名称".repeat(18));
  await expect(page.getByRole("textbox", { name: "规则名称", exact: true })).toHaveAttribute("maxlength", "120");
  await page.screenshot({ path: test.info().outputPath(`rule-name-edit-${width}.png`), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
