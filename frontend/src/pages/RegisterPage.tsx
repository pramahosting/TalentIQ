import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../hooks/useAuth";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", company: "", phone: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate("/app");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      const msg = err?.message;
      if (detail) setError(`Error ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
      else if (status) setError(`HTTP ${status}: ${JSON.stringify(err?.response?.data)}`);
      else setError(`Network error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tiq-auth-wrap">
      <div className="tiq-auth-card" style={{ maxWidth: 480 }}>
        <div className="tiq-logo-wordmark" style={{ fontSize: 20, marginBottom: 24 }}>TalentIQ</div>
        <h1 className="tiq-auth-title">Create your account</h1>
        <p className="tiq-auth-sub">Get started with all three AI agents</p>

        {error && (
          <div className="tiq-alert tiq-alert-error" style={{ fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="tiq-grid-2">
            <div className="tiq-form-group">
              <label className="tiq-label">Full name</label>
              <input className="tiq-input" value={form.name} onChange={set("name")} placeholder="Jane Smith" required />
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Company</label>
              <input className="tiq-input" value={form.company} onChange={set("company")} placeholder="Acme Corp" />
            </div>
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Email address</label>
            <input type="email" className="tiq-input" value={form.email} onChange={set("email")} placeholder="you@company.com" required />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Phone (optional)</label>
            <input className="tiq-input" value={form.phone} onChange={set("phone")} placeholder="+61 400 000 000" />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Password</label>
            <input type="password" className="tiq-input" value={form.password} onChange={set("password")} placeholder="min. 8 characters" required minLength={8} />
          </div>
          <button type="submit" className="tiq-btn tiq-btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: 8 }} disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <div className="tiq-auth-footer">
          Already have an account? <Link to="/login" className="tiq-auth-link">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
