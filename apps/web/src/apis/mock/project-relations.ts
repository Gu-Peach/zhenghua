import type { Drawing, ProjectDetail, ProjectSummary } from "../types";

export const POWER_MOCK_ID = "mock-gcr-low-voltage";
export const LIGHTING_MOCK_ID = "mock-gcr-lighting";

export interface TerminalRelation {
  id: string;
  wire: string;
  purpose: string;
  terminal: string;
  projectId: string;
  workspaceId: string;
  drawingId: string;
  drawingPage: string;
  remoteDevice: string;
  remoteTerminal: string;
}

function drawing(id: string, drawingPage: string, pdfPage: number, recordCount: number): Drawing {
  return { id, drawingPage, pdfPage, recordCount, name: `模拟图纸 · ${drawingPage}`, status: "completed" };
}

// Deliberately separate from server projects. These identifiers must never reach business APIs.
export const relationMockProjects: ProjectDetail[] = [
  {
    id: POWER_MOCK_ID, name: "低压配电系统（Mock）", company: "前端模拟", profile: "Mock",
    status: "completed", progress: 100, workspaceCount: 1, drawingCount: 2,
    updatedAt: "2026-10-20", sourceFilename: "", projectNo: "MOCK-LV", resultVersion: "模拟数据", sourceAvailable: false,
    workspaces: [{ id: "mock-lv-workspace", code: "003.C", name: "低压动力与控制电源", status: "completed",
      drawings: [drawing("mock-lv-main", "003C01", 1, 4), drawing("mock-lv-control", "003C03", 2, 3)] }],
  },
  {
    id: LIGHTING_MOCK_ID, name: "照明配电系统（Mock）", company: "前端模拟", profile: "Mock",
    status: "completed", progress: 100, workspaceCount: 1, drawingCount: 1,
    updatedAt: "2026-10-20", sourceFilename: "", projectNo: "MOCK-LIGHT", resultVersion: "模拟数据", sourceAvailable: false,
    workspaces: [{ id: "mock-light-workspace", code: "080.C", name: "辅助电源配电", status: "completed",
      drawings: [drawing("mock-light-aux", "080C02", 1, 3)] }],
  },
];

const groups = [
  { wire: "0261", purpose: "主电源", projectId: POWER_MOCK_ID, workspaceId: "mock-lv-workspace", drawingId: "mock-lv-main", drawingPage: "003C01", remoteDevice: "+01F11.1", pairs: [["X1:1", "XD10:13"], ["X1:2", "XD10:14"], ["X1:3", "XD10:15"], ["PE", "PE"]] },
  { wire: "0262", purpose: "控制电源", projectId: POWER_MOCK_ID, workspaceId: "mock-lv-workspace", drawingId: "mock-lv-control", drawingPage: "003C03", remoteDevice: "+01F11.3", pairs: [["X21:1", "XD21:7"], ["X21:2", "XD21:20"], ["PE", "PE"]] },
  { wire: "0263", purpose: "辅助电源", projectId: LIGHTING_MOCK_ID, workspaceId: "mock-light-workspace", drawingId: "mock-light-aux", drawingPage: "080C02", remoteDevice: "+01F12.2", pairs: [["X22:1", "XD22:90"], ["X22:2", "N-BAR"], ["PE", "PE"]] },
];

export const terminalRelations: TerminalRelation[] = groups.flatMap(({ pairs, ...group }) => pairs.map(([terminal, remoteTerminal], index) => ({
  ...group, id: `${group.wire}-${index}`, terminal, remoteTerminal,
})));

export function isRelationMockProject(id: string): boolean {
  return relationMockProjects.some(project => project.id === id);
}

export function isGcrRelationSource(project: ProjectSummary): boolean {
  return project.name.includes("1002001693") || /大车.*卷盘/.test(project.name);
}

export function isGcr101(project: ProjectDetail, drawingId: string | null): boolean {
  return isGcrRelationSource(project) && project.workspaces.some(workspace => workspace.drawings.some(page =>
    page.id === drawingId && ["GCR101", "GCR11", "1A"].includes(page.drawingPage.replace(/[^A-Z0-9]/gi, "").toUpperCase())));
}

export function relationProjectHref(relation: TerminalRelation, origin: string, originWorkspace: string, originDrawing: string): string {
  const params = new URLSearchParams({ workspace: relation.workspaceId, drawing: relation.drawingId, view: "relations", origin, originWorkspace, originDrawing });
  return `/projects/${relation.projectId}?${params}`;
}

export function originProjectHref(origin: string, workspace: string, drawingId: string): string {
  const params = new URLSearchParams({ view: "relations" });
  if (workspace) params.set("workspace", workspace);
  if (drawingId) params.set("drawing", drawingId);
  return `/projects/${origin}?${params}`;
}
