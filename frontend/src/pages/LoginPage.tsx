import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Mail, Lock, ArrowRight } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { api } from "../lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Forgot password state
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMsg, setForgotMsg] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/app");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotLoading(true);
    setForgotMsg("");
    try {
      await api.post("/api/auth/reset-request", { email: forgotEmail });
      setForgotMsg("If that email exists, a reset link has been sent. Check your inbox.");
    } catch {
      setForgotMsg("If that email exists, a reset link has been sent. Check your inbox.");
    } finally {
      setForgotLoading(false);
    }
  };

  if (forgotMode) {
    return (
      <div className="tiq-auth-wrap">
        <div className="tiq-auth-card">
          <div className="tiq-logo-wordmark" style={{ fontSize: 20, marginBottom: 24 }}>TalentIQ</div>
          <h1 className="tiq-auth-title">Reset password</h1>
          <p className="tiq-auth-sub">Enter your email and we'll send a reset link</p>

          {forgotMsg ? (
            <div className="tiq-alert tiq-alert-success" style={{ marginBottom: 20 }}>
              {forgotMsg}
            </div>
          ) : (
            <form onSubmit={handleForgot}>
              <div className="tiq-form-group">
                <label className="tiq-label">Email address</label>
                <div style={{ position: "relative" }}>
                  <Mail size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                  <input type="email" className="tiq-input" style={{ paddingLeft: 36 }}
                    value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                    placeholder="you@company.com" required />
                </div>
              </div>
              <button type="submit" className="tiq-btn tiq-btn-primary"
                style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
                disabled={forgotLoading}>
                {forgotLoading ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}

          <div className="tiq-auth-footer">
            <button onClick={() => { setForgotMode(false); setForgotMsg(""); }}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--teal-500)", fontSize: 13 }}>
              ← Back to sign in
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="tiq-auth-wrap">
      <div className="tiq-auth-card">
        <div className="tiq-logo-wordmark" style={{ fontSize: 20, marginBottom: 24 }}>TalentIQ</div>
        <h1 className="tiq-auth-title">Welcome back</h1>
        <p className="tiq-auth-sub">Sign in with your email address</p>

        <div style={{ marginBottom: 16, padding: "10px 14px", background: "rgba(0,199,183,.06)",
          border: "1px solid rgba(0,199,183,.2)", borderRadius: 8, fontSize: 12 }}>
          <strong>Admin:</strong> admin@talentiq.ai &nbsp;/&nbsp; Talent@1
        </div>

        {error && <div className="tiq-alert tiq-alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="tiq-form-group">
            <label className="tiq-label">Email (User ID)</label>
            <div style={{ position: "relative" }}>
              <Mail size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", pointerEvents: "none" }} />
              <input type="email" className="tiq-input" style={{ paddingLeft: 36 }}
                value={email} onChange={e => setEmail(e.target.value)}
                placeholder="admin@talentiq.ai" required autoComplete="email" />
            </div>
          </div>

          <div className="tiq-form-group">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <label className="tiq-label" style={{ margin: 0 }}>Password</label>
              <button type="button" onClick={() => setForgotMode(true)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: "var(--teal-500)" }}>
                Forgot password?
              </button>
            </div>
            <div style={{ position: "relative" }}>
              <Lock size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", pointerEvents: "none" }} />
              <input type={showPw ? "text" : "password"} className="tiq-input"
                style={{ paddingLeft: 36, paddingRight: 40 }}
                value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" required autoComplete="current-password" />
              <button type="button" onClick={() => setShowPw(s => !s)}
                style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex", alignItems: "center" }}>
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button type="submit" className="tiq-btn tiq-btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: 8, gap: 8 }}
            disabled={loading}>
            {loading ? "Signing in…" : <><span>Sign in</span><ArrowRight size={15} /></>}
          </button>
        </form>

        <div className="tiq-auth-footer">
          Don't have an account? <Link to="/register" className="tiq-auth-link">Register</Link>
        </div>
      </div>
    </div>
  );
}
