import { Bell, Cable, Check, ChevronDown, LogOut, Settings, UserRound, UsersRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { logout } from "@/apis/auth";
import type { ProjectDetail } from "@/apis/types";
import { useSessionStore } from "@/stores/session-store";

export function AppHeader({ project }: { project: ProjectDetail }) {
  const navigate = useNavigate();
  const clearSession = useSessionStore((state) => state.clearSession);
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
    await logout();
    clearSession();
    navigate("/login");
  }

  return (
    <header className="app-header">
      <Link to="/projects/peru-tpp-1-sts" className="app-brand" aria-label="线表智能提取系统首页">
        <span className="app-brand-mark"><Cable size={21} /></span>
        <span className="app-brand-copy"><strong>线表智能提取系统</strong><small>Drawing Intelligence</small></span>
      </Link>
      <div className="header-divider" />
      <div className="header-project"><span>当前项目</span><strong>{project.name}</strong></div>
      <div className="header-actions">
        <span className={`run-state run-state-${project.status}`}><Check size={14} />{project.status === "completed" ? "处理完成" : project.status === "review" ? "待复核" : "处理中"}</span>
        <button className="header-icon-button" type="button" aria-label="通知" title="通知"><Bell size={19} /><span className="notification-dot" /></button>
        <div className="account-menu" ref={menuRef}>
          <button className="account-trigger" type="button" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen}>
            <span className="avatar">顾</span>
            <span className="account-copy"><strong>顾工程师</strong><small>项目管理员</small></span>
            <ChevronDown size={16} />
          </button>
          {menuOpen ? (
            <div className="account-popover">
              <div className="account-summary"><span className="avatar avatar-large">顾</span><div><strong>顾工程师</strong><span>engineer@zpmc.com</span></div></div>
              <button type="button"><UserRound size={16} />个人资料</button>
              <button type="button"><UsersRound size={16} />切换账号</button>
              <button type="button"><Settings size={16} />账户设置</button>
              <button type="button" onClick={handleLogout}><LogOut size={16} />退出登录</button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
