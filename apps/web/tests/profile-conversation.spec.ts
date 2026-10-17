import { test, expect, type Page } from "@playwright/test";

const draftId = "00000000-0000-0000-0000-000000000090";
const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG8sAAAAASUVORK5CYII=";
const stages = ["classification", "scan", "completion"];
async function fixture(page: Page, options: { conflict?: boolean; confirmConflict?: boolean; denied?: boolean; failStream?: boolean; publishFail?: boolean; delayed?: Promise<void>; pdfFailOnce?: boolean; singlePdf?: boolean; samePageCorrection?: boolean } = {}) {
  let exists = false;
  let draft: Record<string, unknown> = { draft_id: draftId, revision: 1, key: "sample", version: "1.0.0", checksum: "sha256:" + "0".repeat(64), attachments: [], files: [], template: { display_name: "聊天规则" } };
  const candidates: Record<string, Record<string, unknown>> = {}; const confirmed: Record<string, string> = {};
  const messages: Record<string, unknown>[] = []; const requests: Record<string, unknown>[] = []; const uploads: unknown[] = []; const publications: unknown[] = [];
  let pdfSample: { request_id: string; filename: string; checksum: string; page_count: number; pages: { attachment_id: string; pdf_page_number: number }[]; notice: string | null } | null = null;
  const pdfRequests: Record<string, unknown>[] = [];
  const state = () => ({ wizard: { draft, candidates, confirmed }, stage: stages.find(s => !confirmed[s]) ?? "completion", messages, publish_ready: Object.keys(confirmed).length === 3, issues: [], pdf_sample: pdfSample });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname; const method = route.request().method();
    if (path.includes("/auth/")) return route.fulfill({ json: { accessToken: "fixture", expiresIn: 3600, user: { id: "owner", name: "测试工程师", role: "工程师" } } });
    if (path === "/api/v1/capabilities") return route.fulfill({ json: { extraction: true, explain: true, profile: true } });
    if (path === "/api/v1/profile/drafts") {
      if (options.denied) return route.fulfill({ status: 403, json: { detail: { message: "无权访问规则草稿" } } });
      if (method === "POST") { const body = route.request().postDataJSON(); exists = true; draft = { ...draft, ...body, draft_id: draftId, template: { display_name: body.display_name } }; }
      return route.fulfill({ json: method === "POST" ? draft : exists ? [draft] : [] });
    }
    if (path.endsWith("/conversation")) return route.fulfill({ json: state() });
    if (path.endsWith("/pdf-samples")) {
      const body = route.request().postDataJSON(); pdfRequests.push(body);
      if (options.pdfFailOnce && pdfRequests.length === 1) return route.fulfill({ status: 503, json: { detail: { message: "PDF抽样暂时不可用" } } });
      if (!pdfSample || pdfSample.request_id !== body.request_id) {
        const pages = (options.singlePdf ? [1] : [2, 5]).map(pdf_page_number => ({ attachment_id: crypto.randomUUID(), pdf_page_number }));
        pdfSample = { request_id: body.request_id, filename: body.filename, checksum: "sha256:" + "1".repeat(64), page_count: options.singlePdf ? 1 : 8, pages, notice: options.singlePdf ? "PDF只有1页，仅使用这一页，不重复抽取。" : null };
        draft = { ...draft, revision: Number(draft.revision) + 1, attachments: [...draft.attachments as unknown[], ...pages.map(page => ({ id: page.attachment_id, filename: `pdf_${page.pdf_page_number}.png` }))] };
        Object.keys(candidates).forEach(key => delete candidates[key]); Object.keys(confirmed).forEach(key => delete confirmed[key]);
      }
      return route.fulfill({ json: { draft, sample: pdfSample } });
    }
    if (path.endsWith("/images") && method === "POST") { const body = route.request().postDataJSON(); uploads.push(body); draft = { ...draft, revision: Number(draft.revision) + 1, attachments: [...draft.attachments as unknown[], { id: body.image_id, filename: body.filename }] }; return route.fulfill({ json: draft }); }
    if (path.includes("/images/")) return route.fulfill({ json: { data_url: "data:image/png;base64," + png } });
    if (path.endsWith("/conversation/turns/stream")) {
      const body = route.request().postDataJSON(); requests.push(body);
      if (options.delayed) await options.delayed;
      const event = (type: string, data: Record<string, unknown>) => `event: ${type}\ndata: ${JSON.stringify({ type, turn_id: body.turn_id, ...data })}\n\n`;
      if (options.failStream || options.conflict || (options.confirmConflict && body.confirmation)) return route.fulfill({ contentType: "text/event-stream", body: `event: error\ndata: ${JSON.stringify({ message: options.conflict || options.confirmConflict ? "草稿已更新，请恢复对话" : "模型暂时不可用" })}\n\n` });
      let stage = body.stage ?? state().stage; let answer = "请上传带标题栏的样图，我还需要确认工作区和页号的位置。";
      if (body.confirmation) {
        const candidate = candidates[stage]; candidate.rule_text = body.confirmation.rule_text;
        const cases = candidate.cases as Record<string, unknown>[]; cases.forEach((c, i) => { c.expected = body.confirmation.expected[i]; });
        confirmed[stage] = String(candidate.id); answer = "已保存本阶段规则与Expected JSON。" + (stage === "scan" ? "请上传第二阶段原图对应的跨页图纸。" : stage === "classification" ? "请上传包含放线标记的原图。" : "三个阶段已确认，请手动发布。");
        const scanExpected = cases[0]?.expected as { units?: { connections?: { references?: unknown[] }[] }[] };
        if (stage === "scan" && !scanExpected.units?.some(unit => unit.connections?.some(c => c.references?.length))) answer = "已保存修正后的初扫。同页连接无需再提供目标图；建立第三阶段请另提供真实跨页样例。";
      } else if (options.samePageCorrection && stage === "completion" && String(body.message).includes("就在本页")) {
        const scan = candidates.scan; const previous = (scan.cases as { images: unknown[] }[])[0];
        candidates.scan = { ...scan, id: body.turn_id, rule_text: "同页可见终点沿线直接读取，不因元件不同当成跨页", cases: [{ id: "corrected", title: "同页修正候选", images: previous.images, expected: { units: [{ unit_id: "u1", connections: [{ start: { terminal: "X3:51" }, end: { terminal: "XD3:11" }, references: [], is_cross_page: "same_page" }] }] } }] };
        delete confirmed.scan; delete confirmed.completion; delete candidates.completion;
        stage = "scan"; answer = "已按你的纠正返回第二阶段，使用已有原图生成修正候选，请核对。";
      } else if (body.attachment_ids?.length || candidates[stage]) {
        const expected = stage === "classification" ? { plant_function: "002.C", drawing_page_number: 3 } : stage === "scan" ? { drawing_function: "002.C", drawing_page_number: 3, units: [{ unit_id: "u1", connections: [{ line_number: "002C0311", start: { terminal: String(body.message).includes("75") ? "X3:75" : "X3:51" }, end: null, references: [{ raw: "=080.C/42", target_function: "080.C", target_drawing_page: 42 }] }] }] } : { task_id: "wizard-0-0-0", end: { terminal: "XD21:60" } };
        candidates[stage] = { id: body.turn_id, stage, description: body.message, rule_text: "根据标题栏、放线标记和实际连接读取", cases: [{ id: "case", title: "对话读图样例", kind: "positive", images: [{ attachment_id: body.attachment_ids?.[0] ?? "image", role: "source_page" }], expected, ...(stage === "completion" ? { input: { source_connection: { start: { terminal: "X3:75" } }, reference: { raw: "=080.C/42" } } } : {}) }], model_calls: [], readings: [{ case_id: "case", summary: stage === "completion" ? "来源引用080.C/42，与目标回指匹配后读取XD21:60" : "右下标题栏工作区002.C，业务页3", wire_marker: stage === "scan" ? "导线上方的一道斜线" : null, evidence_steps: stage === "completion" ? ["已确认来源X3:75", "目标回指原页", "沿线到XD21:60"] : ["读取图中标注并沿线核对"] }] };
        if (stage === "classification" && pdfSample) {
          candidates[stage].cases = pdfSample.pages.map((page, index) => ({ id: `sample_${index}`, title: `PDF物理页 ${page.pdf_page_number}`, images: [{ attachment_id: page.attachment_id, role: "source_page" }], expected: { plant_function: "002.C", drawing_page_number: index + 3 } }));
          candidates[stage].readings = pdfSample.pages.map((page, index) => ({ case_id: `sample_${index}`, summary: `PDF物理页${page.pdf_page_number}与另一页使用相同标题栏布局`, wire_marker: null, evidence_steps: ["对照两页标题栏读取功能区与业务页"] }));
        }
        delete confirmed[stage]; answer = "我已读取图片并形成当前理解，请核对下方候选。你可以在聊天里纠正，再确认保存。";
      }
      draft = { ...draft, revision: Number(draft.revision) + 1 };
      messages.push({ id: body.turn_id, role: "user", text: body.message || "请读取这些图片", stage, attachment_ids: body.attachment_ids ?? [], created_at: "" }, { id: crypto.randomUUID(), role: "assistant", text: answer, stage, attachment_ids: [], created_at: "" });
      return route.fulfill({ contentType: "text/event-stream", body: event("progress", { message: "正在核对图纸与用户说明…" }) + event("answer_delta", { delta: answer }) + event("completed", { state: state() }) });
    }
    if (path.endsWith("/publish")) { publications.push(route.request().postDataJSON()); return options.publishFail ? route.fulfill({ status: 503, json: { detail: { message: "规则存储暂不可用" } } }) : route.fulfill({ json: { display_name: "聊天规则", profile_version: "1.0.0" } }); }
    return route.fulfill({ status: 404, json: { detail: "未定义夹具" } });
  });
  return { requests, uploads, publications, candidates, confirmed, pdfRequests };
}
async function send(page: Page, message: string) { await page.getByRole("textbox", { name: "给规则助手的消息" }).fill(message); await page.getByRole("button", { name: "发送", exact: true }).click(); }
async function start(page: Page) { await page.goto("/agents/profile"); await send(page, "聊天规则"); await expect(page.getByText("聊天规则 · custom_", { exact: false })).toBeVisible(); }
async function upload(page: Page, name = "sample.png") { await page.getByLabel("上传对话图片", { exact: true }).setInputFiles({ name, mimeType: "image/png", buffer: Buffer.from(png, "base64") }); }
async function confirm(page: Page) { await page.getByRole("button", { name: "确认本阶段并保存", exact: true }).click(); }

test("对话追问、图片读图、文字纠正、三阶段确认与手动发布", async ({ page }) => {
  const data = await fixture(page); await start(page);
  await send(page, "我想按标题栏分页");
  await expect(page.getByRole("log")).toContainText("请上传带标题栏的样图");
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toHaveCount(0);
  await upload(page); await send(page, "请先给出你对分页方式的理解");
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  expect(data.confirmed.classification).toBeUndefined(); await confirm(page);
  await expect(page.getByRole("button", { name: "2. 本页提取" })).toHaveAttribute("aria-current", "step");
  await upload(page, "scan.png"); await send(page, "斜线是放线标记，按图判断方向");
  await expect(page.getByText("导线上方的一道斜线", { exact: false })).toBeVisible();
  await send(page, "起点改成X3:75，其他保持"); await expect(page.getByLabel("0-0 start terminal", { exact: true })).toHaveValue("X3:75");
  await page.screenshot({ path: test.info().outputPath("profile-chat-scan-desktop.png") });
  await confirm(page); await expect(page.getByRole("button", { name: "3. 跨页补全" })).toHaveAttribute("aria-current", "step");
  await page.reload(); await page.getByLabel("继续已有草稿").selectOption(draftId);
  await expect(page.getByRole("log")).toContainText("起点改成X3:75");
  await upload(page, "080C42.png"); await send(page, "这是080.C/42对应的目标页");
  await expect(page.getByText("来源引用080.C/42，与目标回指匹配后读取XD21:60")).toBeVisible();
  await page.getByText("查看和修改识别结果", { exact: true }).click();
  await page.getByLabel("completion end terminal").fill("XD21:61"); await confirm(page);
  await expect(page.getByRole("button", { name: "发布规则", exact: true })).toBeEnabled();
  await expect(page.getByText("需提供至少一个不应提取或无法唯一补全的负例", { exact: true })).toHaveCount(0);
  expect(Object.values(data.candidates).flatMap(c => c.cases as { kind: string }[]).every(c => c.kind === "positive")).toBe(true);
  expect(data.publications).toHaveLength(0);
  const last = data.requests.at(-1)!.confirmation as { expected: { end: { terminal: string } }[] }; expect(last.expected[0].end.terminal).toBe("XD21:61");
  await page.getByRole("button", { name: "发布规则", exact: true }).click(); await expect(page.getByText("已发布：聊天规则", { exact: false })).toBeVisible();
});

test("对话版本冲突保留输入与图片，重试沿用消息不重复上传", async ({ page }) => {
  const data = await fixture(page, { conflict: true }); await start(page); await upload(page); await send(page, "请读取标题栏");
  await expect(page.getByRole("alert")).toContainText("草稿已更新"); await expect(page.getByRole("textbox", { name: "给规则助手的消息" })).toHaveValue("请读取标题栏");
  await page.getByRole("button", { name: "重试本轮" }).click(); await expect(page.getByRole("alert")).toContainText("草稿已更新");
  expect(data.requests[0].turn_id).toBe(data.requests[1].turn_id); expect(data.uploads).toHaveLength(1);
});

test("聊天等待可停止，恢复读取持久对话且不自动确认", async ({ page }) => {
  let release!: () => void; const delayed = new Promise<void>(resolve => { release = resolve; });
  const data = await fixture(page, { delayed }); await start(page); await send(page, "先说一下分类需要什么");
  await expect(page.getByRole("button", { name: "停止", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "停止", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("已停止"); release();
  await page.getByRole("button", { name: "恢复对话", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "给规则助手的消息" })).toBeEnabled(); expect(data.confirmed).toEqual({});
});

test("窄屏聊天和读图结果不溢出，支持移除待上传图片", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page); await start(page);
  await upload(page); await expect(page.getByRole("img", { name: "sample.png", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "移除 sample.png", exact: true }).click(); await expect(page.getByRole("img", { name: "sample.png", exact: true })).toHaveCount(0);
  await upload(page); await send(page, "标题栏识别工作区和业务页号");
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("profile-chat-mobile.png"), fullPage: true });
  const overflow = await page.evaluate(() => [...document.querySelectorAll(".profile-chat *")].filter(node => node.getBoundingClientRect().right > innerWidth + 1).map(node => ({ tag: node.tagName, cls: node.className, width: node.getBoundingClientRect().width })).slice(0, 12));
  expect(overflow).toEqual([]);
});

test("草稿无权限时清楚展示错误", async ({ page }) => {
  await fixture(page, { denied: true }); await page.goto("/agents/profile"); await expect(page.getByRole("alert")).toContainText("无权访问");
});

test("确认失败保留表格修正，未保存编辑阻止跳阶段", async ({ page }) => {
  await fixture(page, { confirmConflict: true }); await start(page); await upload(page); await send(page, "读取分类规则");
  await page.getByText("查看和修改识别结果", { exact: true }).click();
  await page.getByLabel("plant_function", { exact: true }).fill("002.X");
  await expect(page.getByRole("textbox", { name: "给规则助手的消息" })).toBeDisabled();
  await confirm(page); await expect(page.getByRole("alert")).toContainText("草稿已更新");
  await expect(page.getByLabel("plant_function", { exact: true })).toHaveValue("002.X");
});

test("PDF自动抽两页并生成独立分类答案，后续只采用用户上传原图", async ({ page }) => {
  const data = await fixture(page); await start(page);
  await page.getByLabel("上传分类PDF", { exact: true }).setInputFiles({ name: "drawings.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 fixture") });
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  await expect(page.getByText("已从《drawings.pdf》", { exact: false })).toContainText("PDF 物理页 2、5");
  expect(data.requests[0].attachment_ids).toHaveLength(2); expect(data.pdfRequests).toHaveLength(1);
  expect(data.requests[0]).not.toHaveProperty("content_base64");
  await page.getByText("查看和修改识别结果", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "PDF物理页 2", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PDF物理页 5", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("profile-pdf-two-pages-desktop.png"), fullPage: true });
  await confirm(page); await expect(page.getByRole("button", { name: "2. 本页提取" })).toHaveAttribute("aria-current", "step");
  await expect(page.getByLabel("上传分类PDF", { exact: true })).toHaveCount(0);
  await upload(page, "manual-source.png"); await send(page, "请按我上传的这张原图初扫");
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  const scan = data.requests.at(-1)!;
  expect(scan.stage).toBe("scan"); expect(scan.attachment_ids).toHaveLength(1);
  expect((data.requests[0].attachment_ids as string[])).not.toContain((scan.attachment_ids as string[])[0]);
});

test("PDF抽样失败可以用同一请求重试，不重复创建草稿", async ({ page }) => {
  const data = await fixture(page, { pdfFailOnce: true }); await start(page);
  await page.getByLabel("上传分类PDF", { exact: true }).setInputFiles({ name: "drawings.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 fixture") });
  await expect(page.getByRole("alert")).toContainText("PDF抽样暂时不可用"); expect(data.requests).toHaveLength(0);
  await page.getByRole("button", { name: "重试PDF抽样", exact: true }).click();
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  expect(data.pdfRequests[0].request_id).toBe(data.pdfRequests[1].request_id); expect(data.requests).toHaveLength(1);
});

test("单页PDF明确只取一页，窄屏可查看缓存说明", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await fixture(page, { singlePdf: true }); await start(page);
  await page.getByLabel("上传分类PDF", { exact: true }).setInputFiles({ name: "one.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 fixture") });
  await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible();
  await expect(page.getByText("PDF只有1页", { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("profile-pdf-mobile.png"), fullPage: true });
});

test("模型失败显示具体错误码和诊断编号，不再只有通用提示", async ({ page }) => {
  await fixture(page); await start(page);
  const reference = "00000000-0000-0000-0000-000000000099";
  await page.route("**/conversation/turns/stream", route => route.fulfill({ contentType: "text/event-stream", body: `event: error\ndata: ${JSON.stringify({ code: "MODEL_SCHEMA_INVALID", diagnostic_id: reference, message: "模型返回的JSON不符合GeneratedAnswer格式，请核对字段：expected。" })}\n\n` }));
  await send(page, "请读取本页");
  await expect(page.getByRole("alert")).toContainText("MODEL_SCHEMA_INVALID");
  await expect(page.getByRole("alert")).toContainText(reference);
  await expect(page.getByRole("button", { name: "重试本轮", exact: true })).toBeEnabled();
  await page.screenshot({ path: test.info().outputPath("profile-model-error-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("profile-model-error-mobile.png"), fullPage: true });
});

test("补全时纠正同页误判返回初扫候选，确认后不再索要同页目标图", async ({ page }) => {
  const data = await fixture(page, { samePageCorrection: true }); await start(page);
  await upload(page); await send(page, "读取分类"); await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible(); await confirm(page);
  await expect(page.getByRole("button", { name: "2. 本页提取" })).toHaveAttribute("aria-current", "step");
  await upload(page, "source.png"); await send(page, "读取原图"); await expect(page.getByRole("region", { name: "本阶段读图结果" })).toBeVisible(); await confirm(page);
  await expect(page.getByRole("button", { name: "3. 跨页补全" })).toHaveAttribute("aria-current", "step");
  const uploads = data.uploads.length;
  await send(page, "终点XD3:11就在本页，请按同页连接修正初扫");
  await expect(page.getByRole("button", { name: "2. 本页提取" })).toHaveAttribute("aria-current", "step");
  await expect(page.getByText("未标注原理号：X3:51 → XD3:11", { exact: true })).toBeVisible();
  expect(data.uploads).toHaveLength(uploads); expect(data.confirmed.scan).toBeUndefined();
  await confirm(page); await expect(page.getByRole("log")).toContainText("同页连接无需再提供目标图");
  expect(data.confirmed.scan).toBeTruthy(); expect(data.confirmed.completion).toBeUndefined();
  await page.screenshot({ path: test.info().outputPath("profile-correction-back-to-scan.png"), fullPage: true });
});
