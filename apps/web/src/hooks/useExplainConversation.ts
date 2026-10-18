import { useCallback, useEffect, useRef, useState } from "react";
import { evidenceDrawings, streamExplanation, type EvidenceDrawing, type ExplainSelection, type ToolActivity } from "@/apis/explain";
import { explainEdits, type EditProposal, type EditReceipt } from "@/apis/explain-edits";

export interface ExplainTool { activity: ToolActivity; status: "running" | "done" | "failed" }
export interface ExplainMessage {
  id: string; question: string; answer: string; tools: ExplainTool[];
  status: "running" | "done" | "failed" | "cancelled";
  error?: string; historyReset?: boolean;
}

export function useExplainConversation(projectId: string, selection: ExplainSelection) {
  const [conversationId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState<ExplainMessage[]>([]);
  const [drawings, setDrawings] = useState<EvidenceDrawing[]>([]);
  const [busy, setBusy] = useState(false);
  const [proposals, setProposals] = useState<EditProposal[]>([]);
  const [proposalError, setProposalError] = useState("");
  const versions = useRef<Record<string, number>>({});
  const controller = useRef<AbortController | null>(null);

  const send = useCallback(async (question: string, retryId?: string) => {
    if (!question.trim() || controller.current) return;
    const id = retryId ?? crypto.randomUUID();
    const abort = new AbortController(); controller.current = abort; setBusy(true);
    const message: ExplainMessage = { id, question, answer: "", tools: [], status: "running" };
    setMessages(previous => retryId ? previous.map(item => item.id === retryId ? message : item) : [...previous, message]);
    const update = (change: (item: ExplainMessage) => ExplainMessage) => {
      if (!abort.signal.aborted) setMessages(previous => previous.map(item => item.id === id ? change(item) : item));
    };
    try {
      const currentSelection = { ...selection, recordVersion: selection.connectionId ? versions.current[selection.connectionId] ?? selection.recordVersion : undefined };
      for await (const event of streamExplanation(currentSelection, projectId, conversationId, id, question, abort.signal)) {
        if (abort.signal.aborted) break;
        if (event.type === "answer_delta") update(item => ({ ...item, answer: item.answer + (event.delta ?? "") }));
        if (event.type === "answer_reset") update(item => ({ ...item, answer: "" }));
        if (event.proposal) setProposals(previous => [...previous.filter(p => p.proposal_id !== event.proposal!.proposal_id), event.proposal!]);
        if (event.context || event.retrieval) {
          const images = evidenceDrawings((event.context ?? event.retrieval)!);
          setDrawings(previous => [...new Map([...previous, ...images].map(image => [image.key, image])).values()]);
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
          if (result.proposals?.length) setProposals(previous => [...new Map([...previous, ...result.proposals!].map(p => [p.proposal_id, p])).values()]);
          setDrawings(evidenceDrawings(result));
          update(item => ({ ...item, answer: result.answer, status: "done", historyReset: result.history_reset }));
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
    const initial = selection.scope === "page" ? "请检索本页全部端子及相关跨页图纸，说明这些连接的信息来源与获取链路；需要时查看图纸。" : "请解释这条端子连接的获取链路，说明原页、跨页引用和已保存的提取依据；需要时查看图纸。";
    const timer = window.setTimeout(() => { void send(initial); }, 0);
    return () => { window.clearTimeout(timer); controller.current?.abort(); controller.current = null; };
  }, [selection.scope, send]);

  useEffect(() => { let active = true; explainEdits.list(projectId).then(items => { if (active) { setProposals(previous => [...new Map([...items, ...previous].map(p => [p.proposal_id, p])).values()]); setProposalError(""); } }).catch(reason => { if (active) setProposalError(String(reason)); }); return () => { active = false; }; }, [projectId]);
  const applyDecision = useCallback((receipt: EditReceipt) => {
    setProposals(previous => previous.map(p => p.proposal_id === receipt.proposal_id ? { ...p, status: receipt.status } : p));
    if (receipt.status === "applied") { versions.current = { ...versions.current, ...receipt.versions }; setDrawings([]); }
  }, []);

  return { messages, drawings, busy, send, stop, proposals, proposalError, applyDecision };
}
