import { create } from "zustand";
import type { AssistantScope } from "@/apis/assistant";

interface AssistantState {
  scope: AssistantScope;
  hidden: boolean;
  refresh: number;
  setScope: (scope: AssistantScope, hidden?: boolean) => void;
  refreshResults: () => void;
}
export const useAssistantStore = create<AssistantState>(set => ({
  scope: {}, hidden: false, refresh: 0,
  setScope: (scope, hidden = false) => set({ scope, hidden }),
  refreshResults: () => set(state => ({ refresh: state.refresh + 1 })),
}));
