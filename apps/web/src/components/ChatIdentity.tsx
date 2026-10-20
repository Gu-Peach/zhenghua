import { Bot } from "lucide-react";

export function ChatIdentity({ user = false, name = "图纸助手" }: { user?: boolean; name?: string }) {
  return <div className={`chat-identity${user ? " is-user" : ""}`}>{!user && <span className="chat-avatar"><Bot size={16} aria-hidden="true" /></span>}<strong>{user ? "你" : name}</strong></div>;
}
