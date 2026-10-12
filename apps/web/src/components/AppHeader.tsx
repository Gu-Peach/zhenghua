import { Bell, Cable, Check, ChevronDown, LogOut, Settings, UserRound, UsersRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { logout } from "@/apis/auth";
import type { ProjectDetail } from "@/apis/types";
import { useSessionStore } from "@/stores/session-store";

export function AppHeader({ project }: { project: ProjectDetail }) {
  const navigate = useNavigate();
  const clearSession = useSessionStore((state) => state.clearSession);
  const user = useSessionStore((state) => state.session?.user);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function closeMenu(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, []);

  async function handleLogout() {
    try { await logout(); }
    finally { clearSession(); navigate("/login"); }
  }

  return (
    <header className="app-header">
      <Link to="/projects" className="app-brand" aria-label="线表智能提取系统首页">
        <span className="app-brand-mark"><Cable size={21} /></span>
        <span className="app-brand-copy"><strong>线表智能提取系统</strong><small>Drawing Intelligence</small></span>
      </Link>
      <div className="header-divider" />
      <div className="header-project"><span>当前项目</span><strong>{project.name}</strong></div>
      <div className="header-actions">
        <span className={`run-state run-state-${project.status}`}><Check size={14} />{{ completed: "处理完成", review: "待复核", failed: "处理失败", processing: "处理中", queued: "等待处理" }[project.status]}</span>
        <button className="header-icon-button" type="button" aria-label="通知" title="通知"><Bell size={19} /><span className="notification-dot" /></button>
        <div className="account-menu" ref={menuRef}>
          <button className="account-trigger" type="button" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen}>
            <span className="avatar">{user?.name.slice(0, 1) ?? "用"}</span>
            <span className="account-copy"><strong>{user?.name}</strong><small>{user?.role}</small></span>
            <ChevronDown size={16} />
          </button>
          {menuOpen ? (
            <div className="account-popover">
              <div className="account-summary"><span className="avatar avatar-large">{user?.name.slice(0, 1)}</span><div><strong>{user?.name}</strong><span>{user?.email}</span></div></div>
              <button type="button"><UserRound size={16} />个人资料</button>
              <button type="button" onClick={handleLogout}><UsersRound size={16} />切换账号</button>
              <button type="button"><Settings size={16} />账户设置</button>
              <button type="button" onClick={handleLogout}><LogOut size={16} />退出登录</button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
