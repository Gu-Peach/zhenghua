import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";

const profile = "00000000-0000-0000-0000-000000000080";
const newer = "00000000-0000-0000-0000-000000000081";
const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG8sAAAAASUVORK5CYII=";
const digest = (text: string) => "sha256:" + createHash("sha256").update(text).digest("hex");
async function fixture(page: Page, options: { conflict?: boolean; failStreamOnce?: boolean; publishFailOnce?: boolean; readonly?: boolean; denied?: boolean; retained?: boolean } = {}) {
  const baseChecksum = digest("base-package"); let published = false; let streamCalls = 0;
  const saves: Record<string, unknown>[] = []; const turns: Record<string, unknown>[] = []; const uploads: unknown[] = []; const publications: unknown[] = [];
  const manifest = { key: "sample", version: "1.0.1", resources: { classification_prompt: "resources/classification.md", page_scan_prompt: "resources/scan.md", cross_page_prompt: "resources/completion.md", classification_examples: "resources/classification_examples", wiring_examples: "resources/wiring_examples" } };
  const texts = { "profile.json": JSON.stringify(manifest), "resources/classification.md": "按标题栏读取工作区和页号", "resources/scan.md": "按放线标记读取真实端子", "resources/completion.md": "匹配回指后读取终点", "resources/classification_examples/manifest.json": JSON.stringify({ cases: [{ id: "sample", title: "实际样图", images: [{ path: "sample.png", role: "source_page" }], expected: "expected.json" }] }), "resources/classification_examples/expected.json": JSON.stringify({ plant_function: "006.M", drawing_page_number: 1 }), "resources/wiring_examples/manifest.json": JSON.stringify({ stage2_cases: [], stage3_cases: [] }) };
  const draft: Record<string, unknown> = { draft_id: "00000000-0000-0000-0000-000000000090", revision: 1, key: "sample", version: "1.0.1", checksum: digest("draft"), files: Object.keys(texts), attachments: [], source: { profile_id: profile, version: "1.0.0", checksum: baseChecksum } };
  const resourcePackage = { manifest, files: Object.entries(texts).map(([path, content]) => ({ path, content, checksum: digest(content) })), images: [{ path: "resources/classification_examples/sample.png", url: "data:image/png;base64," + png }] };
  const state = { draft, package: resourcePackage, validation: { ready: true, issues: [] as { code: string; message: string }[] }, changed: false, proposals: [] as Record<string, unknown>[], history: [] as { role: string; content: string }[] };
  const row = () => ({ id: published ? newer : profile, profile_key: "sample", profile_version: published ? "1.0.1" : "1.0.0", display_name: "样例规则", checksum: baseChecksum, resource_ref: "storage://project-assets/profiles/fixture.zip", can_delete: !options.readonly });
  const changed = () => { draft.revision = Number(draft.revision) + 1; state.changed = true; state.validation = { ready: false, issues: [{ code: "EDITS_UNCONFIRMED", message: "当前修改尚未确认" }] }; };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname; const method = route.request().method();
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", expiresIn: 3600, user: { id: "owner", name: "测试工程师", role: "工程师" } } });
    if (path === "/api/v1/capabilities") return route.fulfill({ json: { extraction: true, explain: true, profile: true } });
    if (path === "/api/v1/rule-library") return route.fulfill({ json: [row()] });
    if (path.startsWith("/api/v1/rule-library/")) return route.fulfill({ json: resourcePackage });
    if (path.includes("/references/") && path.endsWith("/draft")) {
      if (options.denied) return route.fulfill({ status: 403, json: { detail: { message: "只能编辑自己的规则" } } });
      const body = route.request().postDataJSON(); expect(body.base_checksum).toBe(baseChecksum); draft.draft_id = body.draft_id; return route.fulfill({ json: state });
    }
    if (path.endsWith("/editor")) return route.fulfill({ json: state });
    if (path.endsWith("/editor/files")) {
      const body = route.request().postDataJSON(); saves.push(body);
      if (options.conflict) return route.fulfill({ status: 409, json: { detail: { message: "草稿已更新，请重新读取" } } });
      for (const edit of body.edits) { const file = resourcePackage.files.find(f => f.path === edit.path)!; expect(edit.before_checksum).toBe(file.checksum); file.content = edit.content; file.checksum = digest(edit.content); }
      changed(); return route.fulfill({ json: state });
    }
    if (path.endsWith("/images") && method === "POST") { const body = route.request().postDataJSON(); uploads.push(body); draft.attachments = [...draft.attachments as unknown[], { id: body.image_id, filename: body.filename, path: "attachments/" + body.image_id + ".png" }]; draft.revision = Number(draft.revision) + 1; return route.fulfill({ json: draft }); }
    if (path.includes("/images/")) return route.fulfill({ json: { data_url: "data:image/png;base64," + png } });
    if (path.endsWith("/editor/turns/stream")) {
      const body = route.request().postDataJSON(); turns.push(body); streamCalls++;
      if (options.failStreamOnce && streamCalls === 1) return route.fulfill({ contentType: "text/event-stream", body: 'event: error\ndata: {"code":"MODEL_FAILED","message":"分析暂时失败"}\n\n' });
      const file = resourcePackage.files.find(f => f.path === "resources/scan.md")!;
      const proposal = { id: crypto.randomUUID(), draft_id: draft.draft_id, base_revision: draft.revision, base_checksum: draft.checksum, summary: "不添加图纸未标注的前缀", status: "pending", findings: [{ category: "rule_issue", explanation: "结合规则与用户结果，应只保留图中实际端子。", evidence: [] }], edits: [{ path: file.path, before_checksum: file.checksum, content: file.content + "\n不添加GTR前缀" }], diffs: [{ path: file.path, before: file.content, after: file.content + "\n不添加GTR前缀" }] };
      state.proposals = [proposal]; const answer = "已读取当前规则和少样本，并结合你给出的图纸与实际提取结果形成修改建议。请核对差异后决定是否采用。";
      state.history.push({ role: "user", content: body.message }, { role: "assistant", content: answer });
      const event = (type: string, data: Record<string, unknown>) => `event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`;
      return route.fulfill({ contentType: "text/event-stream", body: event("tool_started", { tool: "read_file" }) + event("tool_completed", { tool: "read_file", detail: { path: file.path, text: file.content } }) + event("tool_completed", { tool: "view_images", detail: { images: ["actual.png", "sample.png"] } }) + event("answer_delta", { delta: answer }) + event("completed", { reply: { answer } }) });
    }
    if (path.includes("/editor/proposals/") && path.endsWith("/confirm")) {
      const body = route.request().postDataJSON(); const proposal = state.proposals[0];
      if (body.accepted) { const edit = (proposal.edits as { path: string; content: string }[])[0]; const file = resourcePackage.files.find(f => f.path === edit.path)!; file.content = edit.content; file.checksum = digest(edit.content); proposal.status = "accepted"; changed(); } else proposal.status = "rejected";
      return route.fulfill({ json: state });
    }
    if (path.endsWith("/editor/accept")) { draft.revision = Number(draft.revision) + 1; state.validation = { ready: true, issues: [] }; return route.fulfill({ json: state }); }
    if (path.endsWith("/publish")) { publications.push(route.request().postDataJSON()); if (options.publishFailOnce && publications.length === 1) return route.fulfill({ status: 503, json: { detail: { message: "发布暂时失败，可重试" } } }); published = true; return route.fulfill({ json: { ...row(), previous_version_retained: options.retained ?? false } }); }
    return route.fulfill({ status: 404, json: { detail: path } });
  });
  return { saves, turns, uploads, publications, state };
}
async function open(page: Page) { await page.goto("/agents/extraction"); await page.getByRole("button", { name: "查看规则", exact: true }).click(); await expect(page.getByRole("dialog")).toBeVisible(); }

test("双击编辑、保存草稿并发布替换新版", async ({ page }) => {
  const data = await fixture(page); await open(page);
  await page.getByRole("button", { name: "双击编辑本阶段规则", exact: true }).dblclick();
  const editor = page.getByRole("textbox", { name: "编辑本阶段规则", exact: true }); await editor.fill("按标题栏识别功能区，保留业务页号");
  await expect(page.getByRole("button", { name: "确认修改并发布新版" })).toBeDisabled();
  await page.getByRole("button", { name: "保存草稿修改" }).click();
  expect(data.publications).toHaveLength(0); expect(data.saves).toHaveLength(1);
  await page.getByRole("button", { name: "确认修改并发布新版" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0); await expect(page.getByRole("status")).toContainText("已发布 1.0.1");
  expect(data.publications).toHaveLength(1); await expect(page.getByText("版本 1.0.0", { exact: false })).toHaveCount(0);
});

test("图纸与实际结果分析、工具展开、同意后修改发布", async ({ page }) => {
  const data = await fixture(page, { retained: true }); await open(page); await page.getByRole("button", { name: "AI 辅助编辑" }).click();
  await page.getByRole("button", { name: "Stage 2 当前页扫描", exact: true }).click();
  await page.getByRole("textbox", { name: "规则修改要求" }).fill("端子多出了GTR，结合原图分析原因并给修改建议");
  await page.getByText("补充当前提取结果（可选）", { exact: true }).click(); await page.getByRole("textbox", { name: "当前提取结果" }).fill('{"start_terminal":"GTR-X3:1"}');
  await page.getByLabel("上传规则诊断图纸", { exact: true }).setInputFiles({ name: "actual.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "同意修改并发布", exact: true })).toBeEnabled();
  await page.getByText("已读取规则文件", { exact: true }).click(); await expect(page.locator(".profile-tool pre").first()).toContainText("resources/scan.md");
  await page.getByText("查看修改前后 · resources/scan.md", { exact: true }).click(); await expect(page.locator(".profile-proposal")).toContainText("不添加GTR前缀");
  expect(data.publications).toHaveLength(0); expect(data.turns[0].intent).toBe("discuss"); expect(data.turns[0].focus_stage).toBe("scan"); expect(data.turns[0].attachment_ids).toHaveLength(1); expect(JSON.stringify(data.turns[0].observations)).toContain("GTR-X3:1");
  await page.screenshot({ path: test.info().outputPath("profile-rule-chat-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "同意修改并发布", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("旧版仍被项目或任务引用"); expect(data.publications).toHaveLength(1);
});

test("手动保存冲突保留编辑内容，取消不写入", async ({ page }) => {
  await fixture(page, { conflict: true }); await open(page); await page.getByRole("button", { name: "双击编辑本阶段规则", exact: true }).dblclick();
  const editor = page.getByRole("textbox", { name: "编辑本阶段规则", exact: true }); await editor.fill("我的修改需要保留");
  await page.getByRole("button", { name: "保存草稿修改" }).click(); await expect(page.getByRole("alert")).toContainText("草稿已更新"); await expect(editor).toHaveValue("我的修改需要保留");
  await page.getByRole("button", { name: "取消编辑" }).click(); await expect(page.getByRole("button", { name: "双击编辑本阶段规则", exact: true })).toContainText("按标题栏");
});

test("分析失败复用同一回合和图片重试", async ({ page }) => {
  const data = await fixture(page, { failStreamOnce: true }); await open(page); await page.getByRole("button", { name: "AI 辅助编辑" }).click();
  await page.getByRole("textbox", { name: "规则修改要求" }).fill("请分析提取错误"); await page.getByLabel("上传规则诊断图纸", { exact: true }).setInputFiles({ name: "actual.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await page.getByRole("button", { name: "发送", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("分析暂时失败");
  await page.getByRole("button", { name: "重试本轮分析" }).click(); await expect(page.getByRole("button", { name: "同意修改并发布", exact: true })).toBeEnabled();
  expect(data.uploads).toHaveLength(1); expect(data.turns[0].turn_id).toBe(data.turns[1].turn_id);
});

test("发布失败后保留已确认草稿可重试", async ({ page }) => {
  const data = await fixture(page, { publishFailOnce: true }); await open(page); await page.getByRole("button", { name: "双击编辑本阶段规则", exact: true }).dblclick();
  await page.getByRole("textbox", { name: "编辑本阶段规则", exact: true }).fill("修改后的分页规则"); await page.getByRole("button", { name: "保存草稿修改" }).click();
  await page.getByRole("button", { name: "确认修改并发布新版" }).click(); await expect(page.getByRole("alert")).toContainText("发布暂时失败");
  await page.getByRole("button", { name: "确认修改并发布新版" }).click(); await expect(page.getByRole("status")).toContainText("已发布"); expect(data.publications).toHaveLength(2);
});

test("只读规则禁用编辑，越权创建明确报错", async ({ page }) => {
  await fixture(page, { readonly: true }); await open(page); await expect(page.getByRole("button", { name: "AI 辅助编辑" })).toBeDisabled(); await expect(page.getByRole("button", { name: "双击编辑本阶段规则", exact: true })).toHaveCount(0);
});

test("编辑权限失败不伪造草稿", async ({ page }) => {
  await fixture(page, { denied: true }); await open(page); await page.getByRole("button", { name: "AI 辅助编辑" }).click(); await expect(page.getByRole("alert")).toContainText("只能编辑自己的规则"); await expect(page.getByRole("textbox", { name: "规则修改要求" })).toHaveCount(0);
});

test("窄屏编辑与长文本不溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page); await open(page); await page.getByRole("button", { name: "AI 辅助编辑" }).click();
  await page.getByRole("textbox", { name: "规则修改要求" }).fill("很长的修改说明".repeat(200));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("profile-rule-chat-mobile.png"), fullPage: true });
});
