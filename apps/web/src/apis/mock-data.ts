import type { AgentEvent, DrawingLibraryItem, ProjectDetail, ProjectSummary, RuleLibraryItem, StageEvent, WiringRow } from "./types";

export const mockDrawingLibrary: DrawingLibraryItem[] = [
  { id: "library-peru", projectId: "peru-tpp-1-sts", name: "PERU TPP 1 STS 图纸", folder: "项目图纸 / PERU TPP 1 STS", drawingCount: 10, updatedAt: "今天 10:42", status: "completed" },
  { id: "library-abb", projectId: "abb-main-drive", name: "大车主传动系统图纸", folder: "项目图纸 / 大车主传动系统", drawingCount: 24, updatedAt: "昨天 16:18", status: "review" },
  { id: "library-shore", projectId: "shore-power-upgrade", name: "岸电系统改造图纸", folder: "项目图纸 / 岸电系统改造", drawingCount: 0, updatedAt: "10 月 6 日", status: "queued" },
];

export const mockRuleLibrary: RuleLibraryItem[] = [
  { id: "rule-zh", key: "zh", name: "振华 ZH / EPLAN", version: "zh-2026.10", summary: "矩形端子、页码引用与跨页索引解析", status: "published", updatedAt: "今天 09:30" },
  { id: "rule-abb", key: "abb", name: "ABB / Circle Mark", version: "abb-2026.04", summary: "圆圈放线标志与 ABB 端子规则", status: "candidate", updatedAt: "昨天 16:00" },
];

export const mockProjects: ProjectSummary[] = [
  { id: "peru-tpp-1-sts", name: "PERU TPP 1 STS", company: "振华重工", profile: "ZH / EPLAN", status: "completed", progress: 100, workspaceCount: 2, drawingCount: 10, updatedAt: "今天 10:42" },
  { id: "abb-main-drive", name: "大车主传动系统", company: "ABB", profile: "ABB / Circle Mark", status: "review", progress: 86, workspaceCount: 3, drawingCount: 24, updatedAt: "昨天 16:18" },
  { id: "shore-power-upgrade", name: "岸电系统改造", company: "振华重工", profile: "待识别", status: "queued", progress: 0, workspaceCount: 0, drawingCount: 0, updatedAt: "10 月 6 日" },
];

const peruProject: ProjectDetail = {
  ...mockProjects[0],
  sourceFilename: "1002001641 PERU TPP 1 STS.pdf",
  projectNo: "1002001641",
  resultVersion: "结果版本 V3",
  workspaces: [
    {
      id: "ws-002c", code: "002.C", name: "主电源与岸电", status: "completed",
      drawings: [
        { id: "d-002c-03", name: "辅助变压器供电", drawingPage: "3", pdfPage: 48, status: "completed", recordCount: 15 },
        { id: "d-002c-06", name: "预留及接口", drawingPage: "6", pdfPage: 49, status: "completed", recordCount: 0 },
        { id: "d-002c-11", name: "主电源进线", drawingPage: "11", pdfPage: 50, status: "completed", recordCount: 10, imageUrl: "/demo/zh-002c-11.png" },
        { id: "d-002c-21", name: "跨区控制接口", drawingPage: "21", pdfPage: 54, status: "review", recordCount: 2 },
      ],
    },
    {
      id: "ws-003c", code: "003.C", name: "驱动控制", status: "processing",
      drawings: [
        { id: "d-003c-01", name: "驱动电源", drawingPage: "1", pdfPage: 55, status: "completed", recordCount: 8 },
        { id: "d-003c-02", name: "电机制动", drawingPage: "2", pdfPage: 56, status: "processing", recordCount: 4 },
        { id: "d-003c-03", name: "状态反馈", drawingPage: "3", pdfPage: 57, status: "queued", recordCount: 0 },
      ],
    },
  ],
};

const abbProject: ProjectDetail = {
  ...mockProjects[1],
  sourceFilename: "ABB main drive schematic.pdf",
  projectNo: "ABB-MD-2026-04",
  resultVersion: "待复核版本 V1",
  workspaces: [
    { id: "ws-abb-power", code: "POWER", name: "主回路", status: "review", drawings: [
      { id: "d-abb-01", name: "进线与保护", drawingPage: "1", pdfPage: 1, status: "completed", recordCount: 6 },
      { id: "d-abb-02", name: "变频器主回路", drawingPage: "2", pdfPage: 2, status: "review", recordCount: 9 },
    ] },
    { id: "ws-abb-control", code: "CTRL", name: "控制回路", status: "processing", drawings: [
      { id: "d-abb-03", name: "圆圈放线标志", drawingPage: "3", pdfPage: 3, status: "processing", recordCount: 4 },
    ] },
  ],
};

const queuedProject: ProjectDetail = {
  ...mockProjects[2], sourceFilename: "shore-power-upgrade.pdf", projectNo: "待识别", resultVersion: "等待处理", workspaces: [],
};

export const mockProjectDetails: Record<string, ProjectDetail> = {
  [peruProject.id]: peruProject,
  [abbProject.id]: abbProject,
  [queuedProject.id]: queuedProject,
};

export const mockWiringRows: WiringRow[] = [
  { id: "row-001", workspaceId: "ws-002c", drawingId: "d-002c-11", page: "002.C / 11", lineNumber: "002C2111", voltageLevel: "380VAC", startCode: "+00-TA2", startDescription: "辅助变压器进线 U2", startTerminal: "XA:1", endCode: "+00-FC1", endDescription: "主电源断路器 L1", endTerminal: "FC1:1", current: "400A", remark: "Ir=400A", status: "confirmed", confidence: 0.98 },
  { id: "row-002", workspaceId: "ws-002c", drawingId: "d-002c-11", page: "002.C / 11", lineNumber: "002C2112", voltageLevel: "380VAC", startCode: "+00-TA2", startDescription: "辅助变压器进线 V2", startTerminal: "XA:2", endCode: "+00-FC1", endDescription: "主电源断路器 L2", endTerminal: "FC1:3", current: "400A", remark: "Ir=400A", status: "confirmed", confidence: 0.97 },
  { id: "row-003", workspaceId: "ws-002c", drawingId: "d-002c-11", page: "002.C / 11", lineNumber: "002C2113", voltageLevel: "380VAC", startCode: "+00-TA2", startDescription: "辅助变压器进线 W2", startTerminal: "XA:3", endCode: "+00-FC1", endDescription: "主电源断路器 L3", endTerminal: "FC1:5", current: "400A", remark: "Ir=400A", status: "confirmed", confidence: 0.97 },
  { id: "row-004", workspaceId: "ws-002c", drawingId: "d-002c-11", page: "002.C / 11", lineNumber: "002C2104", voltageLevel: "380VAC", startCode: "+00-TA2", startDescription: "岸电进线 U", startTerminal: "XA:5", endCode: "+00-FC2", endDescription: "岸电断路器 L1", endTerminal: "FC2:1", current: "125A", remark: "Ir=125A", status: "confirmed", confidence: 0.96 },
  { id: "row-005", workspaceId: "ws-002c", drawingId: "d-002c-21", page: "002.C / 21", lineNumber: "021M0115", voltageLevel: "24VDC", startCode: "+01F12", startDescription: "控制柜接口", startTerminal: "XD21:15", endCode: "+03F08", endDescription: "风机接触器", endTerminal: "FC103:2", current: "", remark: "跨页索引 003.C / 20.2", status: "review", confidence: 0.82, endReference: { targetDrawingId: "d-003c-02", targetPage: "003.C / 2", targetTerminal: "FC103:2", kind: "cross-page" } },
  { id: "row-006", workspaceId: "ws-003c", drawingId: "d-003c-01", page: "003.C / 1", lineNumber: "003G0121", voltageLevel: "24VDC", startCode: "+01F11.3", startDescription: "PLC 输入公共端", startTerminal: "XD3:3", endCode: "+01F26", endDescription: "模拟量输入模块", endTerminal: "X3:3", current: "", remark: "24VDC+", status: "confirmed", confidence: 0.94 },
];

export const mockStageEvents: StageEvent[] = [
  { id: "stage-1", stage: "Stage 1", title: "页面分类", detail: "识别 2 个工作区、10 张图纸", status: "done", timestamp: "10:16" },
  { id: "stage-2", stage: "Stage 2", title: "当前页扫描", detail: "完成 10 / 10 页，提取 39 条候选连接", status: "done", timestamp: "10:31" },
  { id: "stage-3", stage: "Stage 3", title: "跨页补全", detail: "完成 6 个跨页任务，2 条进入人工复核", status: "done", timestamp: "10:39" },
];

export const mockAgentEvents: AgentEvent[] = [
  { id: "agent-1", kind: "thought", timestamp: "10:16:02", title: "主 Agent", detail: "检测到 PDF 已上传，准备调用三阶段提取子 Agent。", stage: "导入", status: "done" },
  { id: "agent-2", kind: "stage", timestamp: "10:16:08", title: "Stage 1 页面分类", detail: "已识别 2 个工作区和 10 张图纸，正在建立图纸索引。", stage: "Stage 1", status: "done" },
  { id: "agent-3", kind: "stage", timestamp: "10:31:14", title: "Stage 2 当前页扫描", detail: "10 / 10 页完成，发现 1 条跨页索引待补全。", stage: "Stage 2", status: "done" },
  { id: "agent-4", kind: "thought", timestamp: "10:38:21", title: "主 Agent", detail: "根据跨页引用证据，交给 Stage 3 处理目标页端子。", stage: "Stage 3", status: "done" },
  { id: "agent-5", kind: "result", timestamp: "10:42:07", title: "主 Agent", detail: "结果已落库，1 条连接需要人工复核。", stage: "结果", status: "done" },
];
