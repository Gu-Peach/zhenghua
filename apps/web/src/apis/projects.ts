import { request } from "./client";
import { mockDrawingLibrary, mockProjectDetails, mockProjects, mockRuleLibrary, mockStageEvents, mockWiringRows } from "./mock-data";
import type { AgentEvent, DrawingLibraryItem, ProjectDetail, ProjectSummary, RuleLibraryItem, StageEvent, WiringRow } from "./types";

const useMocks = import.meta.env.VITE_USE_MOCKS !== "false";

export const projectApi = {
  async list(): Promise<ProjectSummary[]> {
    if (useMocks) return mockProjects;
    return request<ProjectSummary[]>("/api/v1/projects");
  },
  async get(projectId: string): Promise<ProjectDetail> {
    if (useMocks) return mockProjectDetails[projectId] ?? mockProjectDetails["peru-tpp-1-sts"];
    return request<ProjectDetail>(`/api/v1/projects/${projectId}`);
  },
  async listConnections(projectId: string): Promise<WiringRow[]> {
    if (useMocks) return mockWiringRows;
    return request<WiringRow[]>(`/api/v1/projects/${projectId}/connections`);
  },
  async listRunEvents(projectId: string): Promise<StageEvent[]> {
    if (useMocks) return mockProjectDetails[projectId]?.status === "queued" ? [] : mockStageEvents;
    return request<StageEvent[]>(`/api/v1/projects/${projectId}/runs/latest/events`);
  },
  async listAgentEvents(projectId: string): Promise<AgentEvent[]> {
    if (useMocks) return [];
    return request<AgentEvent[]>(`/api/v1/projects/${projectId}/runs/latest/agent-events`);
  },
  async listDrawingLibrary(): Promise<DrawingLibraryItem[]> {
    if (useMocks) return mockDrawingLibrary;
    return request<DrawingLibraryItem[]>("/api/v1/drawing-library");
  },
  async listRuleLibrary(): Promise<RuleLibraryItem[]> {
    if (useMocks) return mockRuleLibrary;
    return request<RuleLibraryItem[]>("/api/v1/rule-library");
  },
};
