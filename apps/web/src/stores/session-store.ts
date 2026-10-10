import { create } from "zustand";
import type { LoginResult } from "@/apis/types";

interface SessionState {
  session: LoginResult | null;
  setSession: (session: LoginResult) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  session: null,
  setSession: (session) => set({ session }),
  clearSession: () => set({ session: null }),
}));
