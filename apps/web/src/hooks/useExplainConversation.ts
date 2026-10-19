import { useCallback, useEffect, useRef, useState } from "react";
import { evidenceDrawings, streamExplanation, type EvidenceDrawing, type ExplainSelection, type ToolActivity } from "@/apis/explain";
import { explainEdits, type EditProposal, type EditReceipt } from "@/apis/explain-edits";
import { rescans as rescanApi, type RescanRun } from "@/apis/rescan";

export interface ExplainTool { activity: ToolActivity; status: "running" | "done" | "failed" }
export interface ExplainMessage {
  id: string; question: string; answer: string; tools: ExplainTool[];
  status: "running" | "done" | "failed" | "cancelled";
  error?: string; historyReset?: boolean;
  drawings: EvidenceDrawing[];
}

export function useExplainConversation(projectId: string, selection: ExplainSelection) {
  const [conversationId, setConversationId] = useState(() => crypto.randomUUID());
  const selectionOverride = useRef<ExplainSelection | null>(null);
  const initialSent = useRef(false);
  const [selectionNotice, setSelectionNotice] = useState("");
  const [currentTitle, setCurrentTitle] = useState(selection.title);
  const [messages, setMessages] = useState<ExplainMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [proposals, setProposals] = useState<EditProposal[]>([]);
  const [proposalError, setProposalError] = useState("");
  const [rescans, setRescans] = useState<RescanRun[]>([]);
  const [rescanHistoryError, setRescanHistoryError] = useState("");
  const [loadingRescans, setLoadingRescans] = useState(false);
  const attachmentIds = useRef<string[]>([]); const turnAttachments = useRef<Record<string, string[]>>({});
  const turnRescans = useRef<Record<string, string | undefined>>({});
  const turnPermissions = useRef<Record<string, boolean>>({});
  const versions = useRef<Record<string, number>>({});
  const controller = useRef<AbortController | null>(null);

  const send = useCallback(async (question: string, retryId?: string, rescanId?: string, allowRescan = true) => {
    if (!question.trim() || controller.current) return;
    const id = retryId ?? crypto.randomUUID();
    turnAttachments.current[id] ??= [...attachmentIds.current];
    turnPermissions.current[id] ??= allowRescan;
    if (!retryId) turnRescans.current[id] = rescanId;
    const abort = new AbortController(); controller.current = abort; setBusy(true);
    const message: ExplainMessage = { id, question, answer: "", tools: [], drawings: [], status: "running" };
    setMessages(previous => retryId ? previous.map(item => item.id === retryId ? message : item) : [...previous, message]);
    const update = (change: (item: ExplainMessage) => ExplainMessage) => {
      if (!abort.signal.aborted) setMessages(previous => previous.map(item => item.id === id ? change(item) : item));
    };
    try {
      const current = selectionOverride.current ?? selection;
      const currentSelection = { ...current, recordVersion: current.connectionId ? versions.current[current.connectionId] ?? current.recordVersion : undefined };
      for await (const event of streamExplanation(currentSelection, projectId, conversationId, id, question, abort.signal, turnAttachments.current[id], turnRescans.current[id], turnPermissions.current[id])) {
        if (abort.signal.aborted) break;
        if (event.type === "answer_delta") update(item => ({ ...item, answer: item.answer + (event.delta ?? "") }));
        if (event.type === "answer_reset") update(item => ({ ...item, answer: "" }));
        if (event.proposal) setProposals(previous => [...previous.filter(p => p.proposal_id !== event.proposal!.proposal_id), event.proposal!]);
        if (event.rescan) setRescans(previous => [...previous.filter(r => r.id !== event.rescan!.id), event.rescan!]);
        if (event.context || event.retrieval) {
          const images = evidenceDrawings((event.context ?? event.retrieval)!);
          update(item => ({ ...item, drawings: [...new Map([...item.drawings, ...images].map(image => [image.key, image])).values()] }));
        }
        if (event.tool) {
          const activity = event.tool;
          update(item => {
            const tool: ExplainTool = { activity, status: event.type === "tool_started" ? "running" : event.type === "tool_failed" ? "failed" : "done" };
            return { ...item, tools: item.tools.some(t => t.activity.id === activity.id) ? item.tools.map(t => t.activity.id === activity.id ? tool : t) : [...item.tools, tool] };
          });
        }
        if (event.type === "completed" && event.result) {
          const result = event.result;
          if (result.rescans?.length) setRescans(previous => [...new Map([...previous, ...result.rescans!].map(r => [r.id, r])).values()]);
          if (result.proposals?.length) setProposals(previous => [...new Map([...previous, ...result.proposals!].map(p => [p.proposal_id, p])).values()]);
          update(item => ({ ...item, drawings: evidenceDrawings(result), answer: result.answer, status: "done", historyReset: result.history_reset }));
        }
      }
    } catch (reason) {
      if (!abort.signal.aborted) update(item => ({ ...item, status: "failed", error: reason instanceof Error ? reason.message : "解释失败，请重试。", tools: item.tools.map(tool => tool.status === "running" ? { ...tool, status: "failed" } : tool) }));
    } finally {
      if (controller.current === abort) { controller.current = null; setBusy(false); }
    }
  }, [projectId, selection, conversationId]);

  const stop = useCallback(() => {
    controller.current?.abort(); controller.current = null; setBusy(false);
    setMessages(previous => previous.map(item => item.status === "running" ? { ...item, status: "cancelled", tools: item.tools.map(tool => tool.status === "running" ? { ...tool, status: "failed" } : tool) } : item));
  }, []);

  useEffect(() => {
    if (selection.skipInitial || initialSent.current) return () => { controller.current?.abort(); controller.current = null; };
    const initial = selection.initialMessage ?? (selection.scope === "page" ? "请检索本页全部端子及相关跨页图纸，说明这些连接的信息来源与获取链路；需要时查看图纸。" : "请解释这条端子连接的获取链路，说明原页、跨页引用和已保存的提取依据；需要时查看图纸。");
    const timer = window.setTimeout(() => { initialSent.current = true; void send(initial, undefined, undefined, !!selection.initialMessage); }, 0);
    return () => { window.clearTimeout(timer); controller.current?.abort(); controller.current = null; };
  }, [selection.scope, selection.skipInitial, selection.initialMessage, send]);

  useEffect(() => { let active = true; explainEdits.list(projectId).then(items => { if (active) { setProposals(previous => [...new Map([...items, ...previous].map(p => [p.proposal_id, p])).values()]); setProposalError(""); } }).catch(reason => { if (active) setProposalError(String(reason)); }); return () => { active = false; }; }, [projectId]);
  const loadRescans = useCallback(async () => {
    setLoadingRescans(true); setRescanHistoryError("");
    try { const items = await rescanApi.list(projectId); setRescans(previous => [...new Map([...items, ...previous].map(r => [r.id, r])).values()]); if (!items.length) setRescanHistoryError("当前项目暂无重扫记录。"); }
    catch (reason) { setRescanHistoryError(`重扫记录读取失败：${String(reason)}`); }
    finally { setLoadingRescans(false); }
  }, [projectId]);
  const setAttachmentIds = useCallback((ids: string[]) => { attachmentIds.current = ids; }, []);
  const applyRescan = useCallback((run: RescanRun) => {
    setRescans(previous => [...previous.filter(r => r.id !== run.id), run]);
    if (run.status === "applied") {
      versions.current = { ...versions.current, ...run.versions };
      const removedRows = run.candidate?.replacement?.removed ?? [];
      const deletedIds = new Set(removedRows.map(row => row.connection_id));
      if (deletedIds.size) setProposals(previous => previous.filter(proposal => !proposal.changes.some(change => deletedIds.has(change.connection_id))));
      const current = selectionOverride.current ?? selection;
      const removed = removedRows.find(row => row.connection_id === current.connectionId);
      if (removed) {
        selectionOverride.current = { scope: "page", title: `${removed.source_drawing_page ?? `PDF ${removed.source_pdf_page_number}`} · 替换后结果`, query: { pdf_page_number: removed.source_pdf_page_number, offset: 0, limit: 50 }, batchId: run.batch_id, sourcePdf: removed.source_pdf_page_number };
        setCurrentTitle(selectionOverride.current.title);
        setSelectionNotice("原记录已按范围替换。后续提问查询该页的新结果；下方历史对话保留作本次操作说明。");
        attachmentIds.current = []; turnAttachments.current = {}; turnRescans.current = {}; turnPermissions.current = {};
        setConversationId(crypto.randomUUID());
      }
    }
  }, [selection]);
  const applyDecision = useCallback((receipt: EditReceipt) => {
    setProposals(previous => previous.map(p => p.proposal_id === receipt.proposal_id ? { ...p, status: receipt.status } : p));
    if (receipt.status === "applied") { versions.current = { ...versions.current, ...receipt.versions }; }
  }, []);

  return { messages, busy, send, stop, proposals, proposalError, applyDecision, conversationId, rescans, setAttachmentIds, applyRescan, loadRescans, loadingRescans, rescanHistoryError, selectionNotice, currentTitle };
}
