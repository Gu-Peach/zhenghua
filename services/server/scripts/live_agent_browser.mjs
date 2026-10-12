// Explicit paid-model acceptance through the real Web -> Server -> existing Agent.
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium, expect: baseExpect } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: 90000 });
const fixture = JSON.parse(process.env.WIRING_BROWSER_FIXTURE);
const browser = await chromium.launch({ channel: "chrome", headless: true });
let project;
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(90000);
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    return route.continue({ url: fixture.api + url.pathname + url.search });
  });
  page.on("response", async response => {
    if (!response.url().includes("/supervisor/turns/stream")) return;
    try {
      const frames = (await response.text()).split(/\r?\n\r?\n/);
      for (const frame of frames) {
        const line = frame.split(/\r?\n/).find(s => s.startsWith("data:"));
        if (!line) continue;
        const data = JSON.parse(line.slice(5));
        const message = data.user_message ?? data.user_event?.user_message;
        if (message) console.log("PUBLIC:", message);
      }
    } catch { /* Navigation can close an observer; task status is separately checked. */ }
  });
  await page.goto(fixture.web + "/login");
  await page.getByLabel("邮箱", { exact: true }).fill(fixture.email);
  await page.getByLabel("密码", { exact: true }).fill(fixture.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "项目目录" })).toBeVisible();
  if (fixture.resumeProject) {
    project = fixture.resumeProject;
    if (fixture.resumeRun) await page.evaluate(({ project, run }) => sessionStorage.setItem(`run:${project}`, run), { project, run: fixture.resumeRun });
    await page.goto(fixture.web + "/projects/" + project);
    console.log("RESUMED PROJECT:", project);
  } else {
    const uploadResponse = page.waitForResponse(r => r.url().includes("/api/v1/imports?") && r.request().method() === "POST");
    await page.locator('input[type="file"]').setInputFiles(fixture.pdf);
    const uploaded = await uploadResponse;
    if (!uploaded.ok()) throw new Error(`Upload failed (${uploaded.status()})`);
    // React navigates immediately on upload completion; CDP may evict that body.
    await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
    project = new URL(page.url()).pathname.split("/").at(-1);
    console.log("PROJECT:", project);
    await expect(page.locator(".agent-step-pending")).toContainText(/确认|类型/);
  }
  await expect(page.getByRole("button", { name: "发送给主 Agent" })).toBeEnabled({ timeout: 1000 }).catch(() => {});
  async function send(message) {
    await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill(message);
    await expect(page.getByRole("button", { name: "发送给主 Agent" })).toBeEnabled();
    await page.getByRole("button", { name: "发送给主 Agent" }).click();
  }
  // Simulated human input uses the normal Supervisor confirmation endpoint;
  // no direct run creation, database write, tool call or rule approval.
  if (!fixture.resumeProject) await send("确认图纸类型为 zh（振华），请执行完整三阶段提取。");
  await expect.poll(() => page.locator(".agent-event-stage.agent-step-done").filter({ hasText: "Stage 3" }).count(), { timeout: 900000 }).toBeGreaterThan(0);
  await expect(page.locator(".agent-streaming")).toHaveCount(0, { timeout: 900000 });
  await expect.poll(() => page.locator(".result-table tbody tr").count(), { timeout: 30000 }).toBeGreaterThan(0);
  const records = await page.evaluate(async id => {
    // Read through the application's authenticated client, not service credentials.
    const { projectApi } = await import("/src/apis/projects.ts");
    return projectApi.connections(id);
  }, project);
  const row = records.items.find(r => r.startTerminal && r.endTerminal);
  if (!row) throw new Error("No identified terminal available for correction acceptance");
  for (const stage of ["Stage 1", "Stage 2", "Stage 3"]) {
    await expect(page.locator(".agent-event-stage.agent-step-done").filter({ hasText: stage })).toHaveCount(1);
  }
  console.log("EXTRACTED:", records.items.length, "rows; revision", records.result_revision);
  await page.screenshot({ path: ".runtime/real-agent/extracted.png", fullPage: true });
  // Deliberate wrong data is introduced via the real manual editor, only on this disposable project.
  await page.getByRole("button", { name: `编辑 ${row.startTerminal}`, exact: true }).first().click();
  await page.getByLabel("终点端子", { exact: true }).fill("ACCEPTANCE_WRONG");
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await send(`工作区${row.page.split(" / ")[0]}第${row.page.split(" / ")[1]}页，线号${row.wireNumber}、起点端子${row.startTerminal}的终点端子错误，请改为${row.endTerminal}。`);
  await expect(page.locator(".agent-step-pending").filter({ hasText: "待确认修订" })).toBeVisible({ timeout: 180000 });
  console.log("CORRECTION: proposal displayed; awaiting normal confirmation");
  const before = await page.evaluate(async id => {
    const { projectApi } = await import("/src/apis/projects.ts");
    return projectApi.connections(id);
  }, project);
  if (before.items.find(r => r.id === row.id)?.endTerminal !== "ACCEPTANCE_WRONG") throw new Error("Correction applied without confirmation");
  await send("确认修改该终点端子，仅提交这次数据修订；不要创建或发布规则候选。");
  await expect.poll(async () => {
    const after = await page.evaluate(async id => {
      const { projectApi } = await import("/src/apis/projects.ts");
      return projectApi.connections(id);
    }, project);
    return after.items.find(r => r.id === row.id)?.endTerminal;
  }, { timeout: 180000 }).toBe(row.endTerminal);
  await expect(page.locator(".agent-streaming")).toHaveCount(0, { timeout: 900000 });
  await expect(page.locator(".agent-feed")).toContainText(/归因|规则建议/, { timeout: 30000 });
  await page.screenshot({ path: ".runtime/real-agent/corrected.png", fullPage: true });
  console.log("PASS: real-model browser upload/type confirmation/three stages/persistence/correction confirmation/stable-ID refresh/diagnosis");
} catch (error) {
  for (const page of browser.contexts().flatMap(context => context.pages())) {
    await page.screenshot({ path: ".runtime/real-agent/failure.png", fullPage: true }).catch(() => {});
    console.error("PUBLIC UI:", await page.locator(".agent-feed").innerText().catch(() => "unavailable"));
  }
  const safe = String(error.message).replaceAll(fixture.password, "[REDACTED]").replaceAll(fixture.email, "[TEMP_USER]");
  console.error(safe);
  process.exitCode = 1;
} finally {
  await browser.close();
}
