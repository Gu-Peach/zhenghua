import { create } from "zustand";
import { useSessionStore } from "./session-store";

interface Disclosure { opened: boolean; selection: string }
interface TreeState {
  branches: Record<string, Disclosure>;
  positions: Record<string, number>;
  disclose: (branch: string, opened: boolean, selection: string) => void;
  savePosition: (project: string, position: number) => void;
}

// UI state survives workspace remounts, but is never persisted across browser sessions.
export const useProjectTreeStore = create<TreeState>(set => ({
  branches: {}, positions: {},
  disclose: (branch, opened, selection) => set(state => ({ branches: { ...state.branches, [branch]: { opened, selection } } })),
  savePosition: (project, position) => set(state => state.positions[project] === position ? state : { positions: { ...state.positions, [project]: position } }),
}));

useSessionStore.subscribe((state, previous) => {
  if (state.session?.user.id !== previous.session?.user.id) useProjectTreeStore.setState({ branches: {}, positions: {} });
});
