import { Navigate, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { restoreSession } from "@/apis/client";
import { useSessionStore } from "@/stores/session-store";
import { MainAssistantPanel } from "@/components/MainAssistantPanel";

export function AppLayout() {
  const { initialized, session } = useSessionStore();
  useEffect(() => { if (!initialized) void restoreSession().catch(() => useSessionStore.getState().clearSession()); }, [initialized]);
  if (!initialized) return <main className="state-page">正在恢复登录…</main>;
  if (!session) return <Navigate to="/login" replace />;
  return <><Outlet /><MainAssistantPanel key={session.user.id} /></>;
}
