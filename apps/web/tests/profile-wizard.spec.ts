import { test, expect, type Page } from "@playwright/test";

const draftId = "00000000-0000-0000-0000-000000000090";
const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG8sAAAAASUVORK5CYII=";
const stages = ["classification", "scan", "completion"];
async function fixture(page: Page, options: { publishFail?: boolean; conflict?: boolean; delayed?: Promise<void>; denied?: boolean } = {}) {
  let draft: Record<string, unknown> = { draft_id: draftId, revision: 1, key: "sample", version: "1.0.0", checksum: "sha256:" + "0".repeat(64), attachments: [], files: [], template: { display_name: "新图纸规则" } };
  let candidates: Record<string, Record<string, unknown>> = {}; const confirmed: Record<string, string> = {};
  const confirmations: Record<string, unknown>[] = []; const publications: unknown[] = [];
  const state = () => ({ draft, candidates, confirmed });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname; const method = route.request().method();
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", expiresIn: 3600, user: { id: "owner", name: "测试工程师", role: "工程师" } } });
    if (path === "/api/v1/capabilities") return route.fulfill({ json: { extraction: true, explain: true, profile: true } });
    if (path === "/api/v1/profile/drafts") {
      if (options.denied) return route.fulfill({ status: 403, json: { detail: { message: "无权访问规则草稿" } } });
      if (method === "POST") draft = { ...draft, ...route.request().postDataJSON(), draft_id: draftId };
      return route.fulfill({ json: method === "POST" ? draft : [draft] });
    }
    if (path.endsWith("/wizard")) return route.fulfill({ json: state() });
    if (path.endsWith("/images") && method === "POST") { const body = route.request().postDataJSON(); draft = { ...draft, revision: Number(draft.revision) + 1, attachments: [...draft.attachments as unknown[], { id: body.image_id, filename: body.filename }] }; return route.fulfill({ json: draft }); }
    if (path.includes("/images/")) return route.fulfill({ json: { data_url: "data:image/png;base64," + png } });
    if (path.endsWith("/generate")) {
      if (options.delayed) await options.delayed;
      const body = route.request().postDataJSON(); const stage = path.split("/").at(-2)!;
      const expected = stage === "classification" ? { plant_function: "002.C", drawing_page_number: 3, non_wiring: false } : stage === "scan" ? { units: [{ unit_id: "u1", connections: [{ line_number: "002C0311", start: { terminal: "X3:51", device: "MV-SW2", name: "机房主变出线柜" }, end: null, references: [{ raw: "=080.C/42", target_function: "080.C", target_drawing_page: 42 }] }] }] } : { task_id: "wizard-0-0-0", end: { terminal: "XD21:60", device: "+01F11.3", name: "低压配电柜" } };
      candidates[stage] = { id: body.request_id, stage, description: body.description, rule_text: body.description, cases: [{ id: "case", title: "图纸示例", kind: "positive", images: [{ attachment_id: body.source_image, role: "source_page" }], expected }], model_calls: [] };
      stages.slice(stages.indexOf(stage)).forEach(s => { delete confirmed[s]; if (s !== stage) delete candidates[s]; });
      draft = { ...draft, revision: Number(draft.revision) + 1 }; return route.fulfill({ json: state() });
    }
    if (path.endsWith("/confirm")) {
      if (options.conflict) return route.fulfill({ status: 409, json: { detail: { message: "草稿已更新" } } });
      const body = route.request().postDataJSON(); confirmations.push(body); const stage = path.split("/").at(-2)!;
      const current = candidates[stage]; const cases = current.cases as Record<string, unknown>[];
      candidates = { ...candidates, [stage]: { ...current, rule_text: body.rule_text, cases: cases.map((c, i) => ({ ...c, expected: body.expected[i] })) } };
      confirmed[stage] = body.candidate_id; stages.slice(stages.indexOf(stage) + 1).forEach(s => { delete confirmed[s]; delete candidates[s]; });
      draft = { ...draft, revision: Number(draft.revision) + 1 }; return route.fulfill({ json: state() });
    }
    if (path.endsWith("/publish")) { publications.push(route.request().postDataJSON()); return options.publishFail ? route.fulfill({ status: 503, json: { detail: { message: "规则存储暂不可用" } } }) : route.fulfill({ json: { id: "published", display_name: "新图纸规则", profile_version: "1.0.0" } }); }
    return route.fulfill({ status: 404, json: { detail: "未定义夹具" } });
  });
  return { confirmations, publications, getState: state };
}
async function start(page: Page) {
  await page.goto("/agents/profile?editor=form");
  await page.getByLabel("规则名称", { exact: true }).fill("新图纸规则");
  await page.getByLabel("规则标识", { exact: true }).fill("new_drawing");
  await page.getByRole("button", { name: "新建草稿", exact: true }).click();
  await expect(page.getByRole("button", { name: "发布规则", exact: true })).toBeDisabled();
}
async function generate(page: Page, description: string) { await page.getByLabel("本阶段读取规则", { exact: true }).fill(description); await page.getByRole("button", { name: "根据图片生成规则与答案", exact: true }).click(); await expect(page.getByRole("heading", { name: "核对规则与预期结果" })).toBeVisible(); }
async function upload(page: Page, label: string) { await page.getByLabel(label, { exact: true }).setInputFiles({ name: "sample.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") }); await expect(page.getByRole("img", { name: "原页样图", exact: true })).toBeVisible(); }
async function confirm(page: Page) { await page.getByRole("button", { name: "确认本阶段并保存", exact: true }).click(); await expect(page.getByText("本阶段已确认。", { exact: false })).toBeVisible(); }

test("三步生成、表格修正、刷新恢复和手动发布", async ({ page }) => {
  const state = await fixture(page); await start(page); await upload(page, "上传样例图片");
  await expect(page.getByText("负例可选：提供后会保留并使用，未提供也可发布规则。", { exact: true })).toBeVisible();
  await expect(page.getByText("发布需至少一个负例", { exact: false })).toHaveCount(0);
  await generate(page, "标题栏识别工作区和页号"); await confirm(page);
  await page.getByRole("button", { name: "2. 本页提取", exact: false }).click();
  await generate(page, "斜线为放线标记，箭头确定来源");
  await page.getByLabel("0-0 start terminal", { exact: true }).fill("X3:75");
  await page.screenshot({ path: test.info().outputPath("profile-scan-desktop.png") });
  await confirm(page); expect((state.confirmations[1].expected as { units: { connections: { start: { terminal: string } }[] }[] }[])[0].units[0].connections[0].start.terminal).toBe("X3:75");
  await page.reload(); await page.getByLabel("继续已有草稿").selectOption(draftId);
  await page.getByRole("button", { name: "3. 跨页补全", exact: false }).click();
  await upload(page, "上传目标页图片"); await page.getByLabel("工作区", { exact: true }).fill("080.C"); await page.getByLabel("业务页号", { exact: true }).fill("42");
  await generate(page, "按来源回指沿线读取最近终点"); await page.getByLabel("completion end terminal").fill("XD21:61"); await confirm(page);
  expect(state.publications).toHaveLength(0);
  await page.getByRole("button", { name: "发布规则", exact: true }).click(); await expect(page.getByText("已发布：新图纸规则", { exact: false })).toBeVisible();
  expect(state.publications).toHaveLength(1); await expect(page.getByRole("button", { name: "发布规则", exact: true })).toBeDisabled();
});

test("版本冲突保留用户编辑，不出现已确认状态", async ({ page }) => {
  await fixture(page, { conflict: true }); await start(page); await upload(page, "上传样例图片"); await generate(page, "规则说明"); await page.getByLabel("plant_function", { exact: true }).fill("很长的工作区编号与名称测试".repeat(12));
  await page.getByRole("button", { name: "确认本阶段并保存", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("草稿已更新"); await expect(page.getByLabel("plant_function", { exact: true })).not.toHaveValue("002.C"); await expect(page.getByRole("button", { name: "2. 本页提取", exact: false })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: test.info().outputPath("profile-conflict-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("生成中等待状态与草稿无权限", async ({ page }) => {
  let release!: () => void; const delayed = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { delayed }); await start(page); await upload(page, "上传样例图片");
  await page.getByLabel("本阶段读取规则", { exact: true }).fill("读取说明"); await page.getByRole("button", { name: "根据图片生成规则与答案", exact: true }).click(); await expect(page.getByRole("status").filter({ hasText: "AI正在读取" })).toBeVisible(); await expect(page.getByRole("button", { name: "根据图片生成规则与答案", exact: true })).toBeDisabled(); release();
  await expect(page.getByRole("heading", { name: "核对规则与预期结果" })).toBeVisible();
});

test("规则草稿无权限时如实显示失败", async ({ page }) => {
  await fixture(page, { denied: true }); await page.goto("/agents/profile?editor=form"); await expect(page.getByRole("alert")).toContainText("无权访问");
});

test("发布失败可重试且不显示成功", async ({ page }) => {
  const state = await fixture(page, { publishFail: true });
  Object.assign(state.getState().confirmed, { classification: "a", scan: "b", completion: "c" });
  await page.goto("/agents/profile?editor=form"); await page.getByLabel("继续已有草稿").selectOption(draftId);
  await page.getByRole("button", { name: "发布规则", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("规则存储暂不可用");
  await expect(page.getByText("已发布：", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "发布规则", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "发布规则", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("规则存储暂不可用"); expect(state.publications).toHaveLength(2);
});

test("未登录保护及登录页桌面窄屏", async ({ page }) => {
  await page.route("**/api/v1/**", route => route.fulfill({ status: 401, json: { detail: "请先登录" } }));
  await page.goto("/agents/profile?editor=form"); await expect(page.getByRole("heading", { name: "登录工程工作台" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("profile-login-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: test.info().outputPath("profile-login-mobile.png") });
});
