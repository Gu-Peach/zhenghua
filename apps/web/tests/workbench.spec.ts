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
  await expect(page.getByText("没有可用的规则模板，请先发布一个完整的规则包。")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建并注册", exact: true })).toHaveCount(0);
});

test("真实接口适配：页/线号组首、跨页下方预览、编辑和三阶段资源", async ({ page }) => {
  await page.goto(`/projects/${project}`);
  await expect(page.getByRole("heading", { name: "验收工程" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "线号", exact: true })).toBeVisible();
  const bodyRows = page.locator(".result-table tbody tr");
  await expect(bodyRows).toHaveCount(2);
  await expect(bodyRows.nth(0).getByRole("button", { name: "002.C / 1" })).toBeVisible();
  await expect(bodyRows.nth(1).getByRole("button", { name: "002.C / 1" })).toHaveCount(0);
  await page.getByRole("button", { name: "X3:1", exact: true }).click();
  await expect(page.locator(".below-previews .drawing-preview")).toHaveCount(2);
  await expect(page.locator(".below-previews")).toContainText("终点 X3:1");
  await expect(page.locator(".result-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑 XD3:1" }).click();
  await page.getByLabel("终点端子", { exact: true }).fill("X3:99");
  const saving = page.waitForRequest(r => r.method() === "PATCH" && r.url().includes("/connections/"));
  await page.getByRole("button", { name: "确认保存" }).click();
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
  await page.getByRole("separator", { name: "调整 Agent 面板宽度" }).focus();
  const before = await page.locator(".ai-panel").boundingBox();
  await page.keyboard.press("ArrowLeft");
  const after = await page.locator(".ai-panel").boundingBox();
  expect(after!.width).toBeGreaterThan(before!.width);
});

test("断线续传使用已收到序号，不重复发起任务", async ({ page }) => {
  const runId = "10000000-0000-4000-8000-000000000098";
  let turns = 0; const cursors: string[] = [];
  await page.route("**/api/v1/supervisor/turns/stream", async route => {
    turns++;
    await route.fulfill({ contentType: "text/event-stream", body: `event: response\ndata: ${JSON.stringify({ receipt: { agent_run_id: runId }, user_event: { user_message: "已开始当前页重识别。" } })}\n\n` });
  });
  await page.route(`**/api/v1/runs/${runId}/events/stream?**`, async route => {
    const cursor = new URL(route.request().url()).searchParams.get("after_seq")!;
    cursors.push(cursor);
    const e = cursor === "-1" ? { seq: 0, event_type: "STAGE_STARTED", stage: "PAGE_SCAN", message: "扫描开始" } : { seq: 1, event_type: "STAGE_COMPLETED", stage: "PAGE_SCAN", message: "扫描已完成" };
    await route.fulfill({ contentType: "text/event-stream", body: `event: ${e.event_type}\ndata: ${JSON.stringify({ ...e, agent_run_id: runId, occurred_at: "2026-10-12" })}\n\n` });
  });
  await page.route(`**/api/v1/runs/${runId}`, route => route.fulfill({ json: { run: { status: cursors.length > 1 ? "SUCCEEDED" : "RUNNING" } } }));
  await page.route(`**/api/v1/runs/${runId}/artifacts`, route => route.fulfill({ json: { items: [] } }));
  await page.goto(`/projects/${project}`);
  await page.getByRole("textbox", { name: "向主 Agent 提出自然语言需求" }).fill("重新识别当前连接");
  await page.getByRole("button", { name: "发送给主 Agent" }).click();
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
