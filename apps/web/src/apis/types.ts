export type EntityStatus = "completed" | "processing" | "review" | "queued" | "failed";

export interface Drawing {
  id: string;
  name: string;
  drawingPage: string;
  pdfPage: number;
  status: EntityStatus;
  recordCount: number;
  imageUrl?: string;
}

export interface Workspace {
  id: string;
  code: string;
  name: string;
  status: EntityStatus;
  drawings: Drawing[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  company: string;
  profile: string;
  status: EntityStatus;
  progress: number;
  workspaceCount: number;
  drawingCount: number;
  updatedAt: string;
}

export interface ProjectDetail extends ProjectSummary {
  sourceFilename: string;
  projectNo: string;
  resultVersion: string;
  workspaces: Workspace[];
}

export interface WiringRow {
  id: string;
  workspaceId: string;
  drawingId: string;
  page: string;
  lineNumber: string;
  voltageLevel: string;
  startCode: string;
  startDescription: string;
  startTerminal: string;
  endCode: string;
  endDescription: string;
  endTerminal: string;
  current: string;
  remark: string;
  status: "confirmed" | "review";
  confidence: number;
  endReference?: {
    targetDrawingId: string;
    targetPage: string;
    targetTerminal: string;
    kind: "cross-page" | "same-page";
  };
}

export interface StageEvent {
  id: string;
  stage: string;
  title: string;
  detail: string;
  status: "done" | "active" | "pending" | "failed";
  timestamp: string;
}

export type AgentEventKind = "thought" | "stage" | "tool" | "result" | "error";

export interface AgentEvent {
  id: string;
  kind: AgentEventKind;
  timestamp: string;
  title: string;
  detail: string;
  stage?: string;
  status?: "running" | "done" | "pending" | "failed";
}

export interface DrawingLibraryItem {
  id: string;
  projectId: string;
  name: string;
  folder: string;
  drawingCount: number;
  updatedAt: string;
  status: EntityStatus;
}

export interface RuleLibraryItem {
  id: string;
  key: "zh" | "abb";
  name: string;
  version: string;
  summary: string;
  status: "published" | "candidate";
  updatedAt: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface LoginResult {
  user: { id: string; name: string; email: string; role: string };
  accessToken: string;
}
