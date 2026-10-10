import { CheckCircle2, Eye, EyeOff, Loader2, LockKeyhole, Mail, ScanLine, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "@/apis/auth";
import { useSessionStore } from "@/stores/session-store";

export function LoginView() {
  const navigate = useNavigate();
  const setSession = useSessionStore((state) => state.setSession);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const session = await login({ email: String(data.get("email")), password: String(data.get("password")) });
      setSession(session);
      navigate("/projects/peru-tpp-1-sts");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-visual" aria-label="电气图纸预览">
        <img src="/demo/zh-002c-11.png" alt="电气原理图" className="login-drawing" />
        <div className="login-visual-shade" />
        <div className="login-brand"><span className="brand-symbol">线</span><div><strong>线表智能提取系统</strong><span>Electrical Drawing Intelligence</span></div></div>
        <div className="login-visual-copy">
          <span className="eyebrow">ENGINEERING WORKSPACE</span><h1>让每一条连接都可追溯</h1><p>从原始图纸到结构化线表，保留工作区、图纸页与提取证据。</p>
          <ul><li><ScanLine size={18} />阶段化识别与跨页补全</li><li><ShieldCheck size={18} />项目级权限与结果版本</li><li><CheckCircle2 size={18} />结构化校验与人工复核</li></ul>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-form-shell">
          <div className="mobile-login-brand"><span className="brand-symbol">线</span><strong>线表智能提取系统</strong></div>
          <div className="login-heading"><span className="eyebrow">WELCOME BACK</span><h2>登录工程工作台</h2><p>使用企业账号继续访问项目与提取结果。</p></div>
          <form onSubmit={handleSubmit} className="login-form">
            <label htmlFor="email">邮箱</label>
            <div className="input-shell"><Mail size={18} /><input id="email" name="email" type="email" defaultValue="engineer@zpmc.com" autoComplete="email" required /></div>
            <div className="password-label"><label htmlFor="password">密码</label><button type="button" className="text-button">忘记密码</button></div>
            <div className="input-shell"><LockKeyhole size={18} /><input id="password" name="password" type={showPassword ? "text" : "password"} defaultValue="prototype" autoComplete="current-password" required /><button type="button" className="field-icon-button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
            <label className="check-row"><input type="checkbox" defaultChecked /><span>保持登录状态</span></label>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button type="submit" className="login-submit" disabled={submitting}>{submitting ? <Loader2 size={18} className="spin" /> : null}{submitting ? "正在登录" : "登录"}</button>
          </form>
          <p className="login-support">访问受限？<Link to="/login">联系系统管理员</Link></p><p className="prototype-note">静态原型 · 当前使用 Mock 登录</p>
        </div>
      </section>
    </main>
  );
}
