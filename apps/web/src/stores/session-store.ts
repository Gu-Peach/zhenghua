import { create } from "zustand";
import type { LoginResult } from "@/apis/types";

interface SessionState {
  session: LoginResult | null;
  initialized: boolean;
  setInitialized: () => void;
  setSession: (session: LoginResult) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  session: null,
  initialized: false,
  setInitialized: () => set({ initialized: true }),
  setSession: (session) => set({ session, initialized: true }),
  clearSession: () => set({ session: null, initialized: true }),
}));
