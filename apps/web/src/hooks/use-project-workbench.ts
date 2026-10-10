import { useMemo, useState } from "react";
import type { ProjectDetail, WiringRow } from "@/apis/types";

export type CenterTab = "results" | "drawing" | "events";

export function useProjectWorkbench(project: ProjectDetail | null, rows: WiringRow[]) {
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<CenterTab>("results");
  const [query, setQuery] = useState("");
  const [highlightedRowId, setHighlightedRowId] = useState<string | null>(null);

  const effectiveWorkspaceId = selectedWorkspaceId ?? project?.workspaces[0]?.id ?? null;
  const selectedWorkspace = project?.workspaces.find((workspace) => workspace.id === effectiveWorkspaceId) ?? null;
  const selectedDrawing = selectedWorkspace?.drawings.find((drawing) => drawing.id === selectedDrawingId) ?? null;
  const visibleRows = useMemo(() => rows.filter((row) => {
    if (row.workspaceId !== effectiveWorkspaceId) return false;
    if (selectedDrawingId && row.drawingId !== selectedDrawingId) return false;
    return Object.values(row).join(" ").toLowerCase().includes(query.toLowerCase());
  }), [effectiveWorkspaceId, query, rows, selectedDrawingId]);

  function selectWorkspace(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId);
    setSelectedDrawingId(null);
    setActiveTab("results");
  }

  function selectDrawing(workspaceId: string, drawingId: string) {
    setSelectedWorkspaceId(workspaceId);
    setSelectedDrawingId(drawingId);
    setActiveTab("results");
  }

  function openDrawing(drawingId: string) {
    const workspace = project?.workspaces.find((item) => item.drawings.some((drawing) => drawing.id === drawingId));
    if (!workspace) return;
    setSelectedWorkspaceId(workspace.id);
    setSelectedDrawingId(drawingId);
    setActiveTab("drawing");
  }

  function openRowTarget(row: WiringRow) {
    if (!row.endReference || row.endReference.kind !== "cross-page") return;
    setSelectedWorkspaceId(project?.workspaces.find((workspace) => workspace.drawings.some((drawing) => drawing.id === row.endReference?.targetDrawingId))?.id ?? null);
    setSelectedDrawingId(row.endReference.targetDrawingId);
    setHighlightedRowId(row.id);
    setActiveTab("drawing");
  }

  function hoverRowTarget(rowId: string | null) {
    setHighlightedRowId(rowId);
  }

  return { activeTab, effectiveWorkspaceId, highlightedRowId, query, selectedDrawing, selectedDrawingId, selectedWorkspace, visibleRows, setActiveTab, setQuery, selectDrawing, selectWorkspace, openDrawing, openRowTarget, hoverRowTarget };
}
