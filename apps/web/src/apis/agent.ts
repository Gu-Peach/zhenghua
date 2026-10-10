import { API_BASE_URL } from "./client";
import { mockProjectDetails, mockWiringRows } from "./mock-data";
import type { AgentEvent, RuleLibraryItem, WiringRow } from "./types";

export type SupervisorCommand =
  | { kind: "extract"; filename: string }
  | { kind: "repair"; message: string };

export type SupervisorRequest = SupervisorCommand & { projectId: string };
export type AgentStageStatus = "pending" | "processing" | "done" | "failed";

export interface AgentStageProgress {
  stage: string;
  status: AgentStageStatus;
  agentName?: string;
}

export interface AgentStreamUpdate {
  stageUpdate?: AgentStageProgress;
  event?: AgentEvent;
  rowPatch?: WiringRow;
  ruleCandidate?: RuleLibraryItem;
}

const useMocks = import.meta.env.VITE_USE_MOCKS !== "false";

export async function* streamSupervisorRun(input: SupervisorRequest, signal?: AbortSignal, mockRows?: WiringRow[]): AsyncGenerator<AgentStreamUpdate> {
  if (useMocks) {
    yield* streamMockRun(input, signal, mockRows ?? mockWiringRows);
    return;
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/supervisor/runs`, {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) throw new Error(`Supervisor 请求失败 (${response.status})`);
  if (!response.body) throw new Error("Supervisor 未返回事件流");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame.split(/\r?\n/).find((line) => line.startsWith("data:"))?.slice(5).trim();
      if (data) yield JSON.parse(data) as AgentStreamUpdate;
    }
    if (done) break;
  }
  if (buffer.trim()) {
    const data = buffer.split(/\r?\n/).find((line) => line.startsWith("data:"))?.slice(5).trim();
    if (data) yield JSON.parse(data) as AgentStreamUpdate;
  }
}

async function* streamMockRun(input: SupervisorRequest, signal: AbortSignal | undefined, rows: WiringRow[]): AsyncGenerator<AgentStreamUpdate> {
  const emit = async function* (updates: AgentStreamUpdate[]) {
    for (const update of updates) {
      await wait(680, signal);
      yield update;
    }
  };

  if (input.kind === "extract") {
    const drawingCount = mockProjectDetails[input.projectId]?.drawingCount ?? 0;
    yield* emit([
      stageProgress("Stage 1", "pending"),
      eventUpdate("thought", "主 Agent", `收到 ${input.filename}。正在分析文件类型和项目归属，准备选择提取 Agent。`, "PDF 导入", "done"),
      eventUpdate("thought", "主 Agent", "判断这是原理图 PDF，先调用页面分类 Agent 建立工作区和图纸索引。", "Agent 路由", "done"),
      stageProgress("Stage 1", "processing", "Stage 1 页面分类 Agent"),
      eventUpdate("stage", "Stage 1 页面分类 Agent", `正在扫描 PDF 页面并建立索引，预计处理 ${drawingCount || "待识别"} 张图纸。`, "Stage 1", "running"),
      stageProgress("Stage 1", "done"),
      eventUpdate("thought", "主 Agent", "Stage 1 已返回工作区和图纸索引，继续调用当前页扫描 Agent。", "Agent 路由", "done"),
      stageProgress("Stage 2", "processing", "Stage 2 当前页扫描 Agent"),
      eventUpdate("stage", "Stage 2 当前页扫描 Agent", "正在逐页提取起点、终点与端子候选，保留来源证据。", "Stage 2", "running"),
      stageProgress("Stage 2", "done"),
      eventUpdate("thought", "主 Agent", "发现跨页引用任务，调用跨页补全 Agent 读取目标页。", "Agent 路由", "done"),
      stageProgress("Stage 3", "processing", "Stage 3 跨页补全 Agent"),
      eventUpdate("stage", "Stage 3 跨页补全 Agent", "正在根据跨页索引加载目标页，补全可确认的终点信息。", "Stage 3", "running"),
      stageProgress("Stage 3", "done"),
      eventUpdate("result", "主 Agent", "三阶段提取完成；待复核项已保留，结果可在左侧图纸树和线表中检查。", "结果落库", "done"),
    ]);
    return;
  }

  const intent = resolveRepairIntent(input.message, rows);
  const row = intent.row;
  if (!row) {
    yield { event: makeEvent("error", "主 Agent", `未能从自然语言请求中定位线号${intent.lineNumber ? ` ${intent.lineNumber}` : ""}，请补充线号或图纸范围。`, "请求理解", "failed") };
    return;
  }
  const crossPage = row.endReference?.kind === "cross-page";
  const stage = crossPage ? "Stage 3" : "Stage 2";
  const patch: WiringRow = {
    ...row,
    endTerminal: intent.answer || row.endTerminal,
    status: "confirmed",
    remark: intent.answer ? "用户自然语言修订" : crossPage ? "跨页索引已重新解析" : "当前页已重新提取",
  };
  const candidate: RuleLibraryItem | undefined = intent.diagnosis === "rule" ? {
    id: `rule-candidate-${Date.now()}`,
    key: input.projectId === "abb-main-drive" ? "abb" : "zh",
    name: input.projectId === "abb-main-drive" ? "ABB / Circle Mark" : "振华 ZH / EPLAN",
    version: input.projectId === "abb-main-drive" ? "abb-2026.05-candidate" : "zh-2026.11-candidate",
    summary: `候选修正规则：${crossPage ? "跨页目标端子索引优先采用目标页证据" : "同页端子邻接关系增加确定性校验"}`,
    status: "candidate",
    updatedAt: "刚刚",
  } : undefined;

  yield* emit([
    eventUpdate("thought", "主 Agent", `已理解用户请求：“${input.message}”。识别线号 ${row.lineNumber}，${intent.answer ? `提取到用户答案 ${intent.answer}` : "未发现明确答案"}。`, "请求理解", "done"),
    ...(intent.answer ? [] : [
      stageProgress("数据库查询", "processing", "结果查询子 Agent"),
      eventUpdate("tool", "结果查询子 Agent", `已从结果库读取线号 ${row.lineNumber} 的来源、终点和跨页引用证据。`, "数据库查询", "running"),
      stageProgress("数据库查询", "done"),
    ]),
    ...(intent.answer ? [] : [
      eventUpdate("thought", "主 Agent", `判断为${crossPage ? "跨页索引" : "同页连接"}，主动调用 ${stage} 子 Agent。`, "纠错路由", "done"),
      stageProgress(stage, "processing", stage === "Stage 3" ? "Stage 3 跨页补全 Agent" : "Stage 2 当前页扫描 Agent"),
      eventUpdate("stage", `${stage} ${crossPage ? "跨页补全" : "当前页扫描"}`, crossPage ? "重新读取目标页索引并复核指定终点，不修改已确认起点。" : "在来源页重新扫描指定连接并执行确定性端子校验。", stage, "running"),
      stageProgress(stage, "done"),
    ]),
    { event: makeEvent("tool", "修复工具", intent.answer ? "已将用户自然语言中的答案直接写入线表 Mock 状态。" : `${stage} 子 Agent 返回修订结果，正在同步线表。`, "结果修订", "done"), rowPatch: patch },
    eventUpdate("thought", "判断 Agent", `本次失败归因为${intent.diagnosis === "rule" ? "提取规则问题" : "大模型幻觉问题"}。`, "问题归因", "done"),
    ...(candidate ? [{ event: makeEvent("result", "规则候选", "已生成待审核规则版本；通过固定案例回归和人工审核前不会影响生产 Profile。", "规则改进", "pending"), ruleCandidate: candidate }] : []),
    eventUpdate("result", "主 Agent", `线号 ${row.lineNumber} 修复链路完成，线表已实时更新。`, "结果回写", "done"),
  ]);
}

interface RepairIntent {
  row?: WiringRow;
  lineNumber?: string;
  answer: string;
  diagnosis: "hallucination" | "rule";
}

function resolveRepairIntent(message: string, rows: WiringRow[]): RepairIntent {
  const normalized = message.trim();
  const lineNumber = rows.map((row) => row.lineNumber).find((candidate) => normalized.toLowerCase().includes(candidate.toLowerCase()));
  const row = rows.find((candidate) => candidate.lineNumber === lineNumber);
  const answerMatch = normalized.match(/(?:答案|改为|改成|应为|终点(?:端子)?是)\s*[:：]?\s*([A-Za-z0-9+_.:-]+)/i);
  const diagnosis = /规则|解析|引用|profile|标准/i.test(normalized) ? "rule" : "hallucination";
  return { row, lineNumber, answer: answerMatch?.[1] ?? "", diagnosis };
}

function eventUpdate(kind: AgentEvent["kind"], title: string, detail: string, stage: string, status: NonNullable<AgentEvent["status"]>): AgentStreamUpdate {
  return { event: makeEvent(kind, title, detail, stage, status) };
}

function stageProgress(stage: string, status: AgentStageStatus, agentName?: string): AgentStreamUpdate {
  return { stageUpdate: { stage, status, agentName } };
}

function makeEvent(kind: AgentEvent["kind"], title: string, detail: string, stage: string, status: NonNullable<AgentEvent["status"]>): AgentEvent {
  return { id: `agent-${Date.now()}-${Math.random().toString(16).slice(2)}`, kind, title, detail, stage, status, timestamp: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) };
}

function wait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("操作已取消", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("操作已取消", "AbortError"));
    }, { once: true });
  });
}
