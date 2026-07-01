import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings, Key, User, Shield, Trash2 , Home} from "lucide-react";
import { authApi } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

export default function SettingsPage() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"profile" | "apikeys" | "admin">("profile");

  // ── PROFILE ──────────────────────────────────────────────────────
  const [profile, setProfile] = useState({
    name: user?.name || "",
    company: user?.company || "",
    phone: user?.phone || "",
    address: user?.address || "",
  });
  const profileMut = useMutation({
    mutationFn: () => authApi.updateProfile(profile),
    onSuccess: () => refreshUser(),
  });

  // ── PASSWORD ─────────────────────────────────────────────────────
  const [pw, setPw] = useState({ old: "", next: "", confirm: "" });
  const [pwErr, setPwErr] = useState("");
  const [pwOk, setPwOk] = useState(false);
  const pwMut = useMutation({
    mutationFn: () => authApi.changePassword(pw.old, pw.next),
    onSuccess: () => { setPwOk(true); setPw({ old: "", next: "", confirm: "" }); },
    onError: (e: any) => setPwErr(e.response?.data?.detail || "Failed"),
  });

  // ── API KEYS ─────────────────────────────────────────────────────
  const { data: savedKeys = [] } = useQuery({ queryKey: ["api-keys"], queryFn: authApi.listApiKeys });

  // Each service stores its fields independently
  const [adzuna, setAdzuna] = useState({ app_id: "", app_key: "" });
  const [groq, setGroq] = useState({ api_key: "" });
  const [linkedin, setLinkedin] = useState({ email: "", password: "" });
  const [smtp, setSmtp] = useState({ host: "", port: "587", username: "", password: "", from_email: "" });
  const [ollama, setOllama] = useState({ base_url: "http://localhost:11434", model: "llama3" });
  const [keyMsg, setKeyMsg] = useState("");

  const flashMsg = (m: string) => { setKeyMsg(m); setTimeout(() => setKeyMsg(""), 3000); };

  const [savingService, setSavingService] = useState("");
  const saveKey = async (service: string, fields: Record<string, string>) => {
    const entries = Object.entries(fields).filter(([, v]) => v.trim() !== "");
    if (entries.length === 0) { flashMsg("Enter at least one value to save."); return; }
    setSavingService(service);
    try {
      for (const [key_name, key_value] of entries) {
        await authApi.saveApiKey({ service, key_name, key_value });
      }
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      flashMsg("✅ " + service + " credentials saved successfully!");
    } catch (e: any) {
      flashMsg("❌ Failed to save " + service + ": " + (e.response?.data?.detail || e.message));
    } finally {
      setSavingService("");
    }
  };

  const deleteKeyMut = useMutation({
    mutationFn: (id: number) => authApi.deleteApiKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  // ── ADMIN USERS ──────────────────────────────────────────────────
  const { data: users = [] } = useQuery({
    queryKey: ["admin-users-settings"],
    queryFn: authApi.listUsers,
    enabled: user?.role === "admin",
  });
  const deactivateMut = useMutation({
    mutationFn: (id: number) => authApi.deactivateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users-settings"] }),
  });

  const inp = (label: string, val: string, set: (v: string) => void, type = "text", ph = "") => (
    <div className="tiq-form-group">
      <label className="tiq-label">{label}</label>
      <input type={type} className="tiq-input" value={val}
        onChange={e => set(e.target.value)} placeholder={ph} />
    </div>
  );

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title">Settings</h1>
        <p className="tiq-page-sub">Manage your account, credentials and API keys</p>
      </div>
      <button onClick={() => navigate("/")} className="tiq-btn tiq-btn-ghost tiq-btn-sm"
        style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, alignSelf: "flex-start" }}>
        <Home size={14} /> Home
      </button>

      <div className="tiq-tabs">
        <button className={`tiq-tab${tab === "profile" ? " active" : ""}`} onClick={() => setTab("profile")}>
          <User size={13} style={{ display: "inline", marginRight: 6 }} />Profile
        </button>
        <button className={`tiq-tab${tab === "apikeys" ? " active" : ""}`} onClick={() => setTab("apikeys")}>
          <Key size={13} style={{ display: "inline", marginRight: 6 }} />API Keys
        </button>
        {user?.role === "admin" && (
          <button className={`tiq-tab${tab === "admin" ? " active" : ""}`} onClick={() => setTab("admin")}>
            <Shield size={13} style={{ display: "inline", marginRight: 6 }} />Users
          </button>
        )}
      </div>

      {/* ── PROFILE TAB ── */}
      {tab === "profile" && (
        <div style={{ maxWidth: 560 }}>
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">Personal information</div>
            <div className="tiq-grid-2">
              {inp("Full name", profile.name, v => setProfile(p => ({ ...p, name: v })))}
              {inp("Company", profile.company, v => setProfile(p => ({ ...p, company: v })))}
              {inp("Phone", profile.phone, v => setProfile(p => ({ ...p, phone: v })))}
              <div className="tiq-form-group">
                <label className="tiq-label">Email (User ID — read only)</label>
                <input className="tiq-input" value={user?.email || ""} disabled style={{ opacity: .6 }} />
              </div>
            </div>
            {inp("Address", profile.address, v => setProfile(p => ({ ...p, address: v })))}
            {profileMut.isSuccess && <div className="tiq-alert tiq-alert-success">Profile updated.</div>}
            <button className="tiq-btn tiq-btn-primary" onClick={() => profileMut.mutate()} disabled={profileMut.isPending}>
              {profileMut.isPending ? "Saving…" : "Save changes"}
            </button>
          </div>

          <div className="tiq-card">
            <div className="tiq-card-title">Change password</div>
            {pwErr && <div className="tiq-alert tiq-alert-error">{pwErr}</div>}
            {pwOk && <div className="tiq-alert tiq-alert-success">Password changed.</div>}
            {inp("Current password", pw.old, v => setPw(p => ({ ...p, old: v })), "password")}
            {inp("New password", pw.next, v => setPw(p => ({ ...p, next: v })), "password")}
            {inp("Confirm new password", pw.confirm, v => setPw(p => ({ ...p, confirm: v })), "password")}
            <button className="tiq-btn tiq-btn-outline"
              onClick={() => {
                setPwErr(""); setPwOk(false);
                if (pw.next !== pw.confirm) { setPwErr("Passwords don't match"); return; }
                pwMut.mutate();
              }}
              disabled={!pw.old || !pw.next || pwMut.isPending}>
              {pwMut.isPending ? "Changing…" : "Change password"}
            </button>
          </div>
        </div>
      )}

      {/* ── API KEYS TAB ── */}
      {tab === "apikeys" && (
        <div style={{ maxWidth: 680 }}>
          {keyMsg && <div className="tiq-alert tiq-alert-success tiq-mb-4">{keyMsg}</div>}

          {/* ADZUNA */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">Adzuna — Job Search API</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Free at <a href="https://developer.adzuna.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>developer.adzuna.com</a>. Needed for JobHunt and JobIntel agents.
            </p>
            <div className="tiq-grid-2">
              {inp("App ID", adzuna.app_id, v => setAdzuna(a => ({ ...a, app_id: v })), "text", "e.g. 638c0962")}
              {inp("App Key", adzuna.app_key, v => setAdzuna(a => ({ ...a, app_key: v })), "password", "e.g. 04681adc…")}
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("adzuna", adzuna)} disabled={savingService === "adzuna"}>
              {savingService === "adzuna" ? "Saving…" : "Save Adzuna Keys"}
            </button>
          </div>

          {/* GROQ */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">Groq — AI / LLM API</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Free at <a href="https://console.groq.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>console.groq.com</a>. Enables AI resume matching and cover letter generation.
            </p>
            {inp("API Key", groq.api_key, v => setGroq({ api_key: v }), "password", "gsk_…")}
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("groq", groq)} disabled={savingService === "groq"}>
              {savingService === "groq" ? "Saving…" : "Save Groq Key"}
            </button>
          </div>

          {/* LINKEDIN */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">LinkedIn — Candidate Search</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Your LinkedIn login credentials. Used by LinkLens agent to search candidate profiles via Playwright browser automation.
            </p>
            <div className="tiq-grid-2">
              {inp("LinkedIn Email", linkedin.email, v => setLinkedin(l => ({ ...l, email: v })), "email", "you@email.com")}
              {inp("LinkedIn Password", linkedin.password, v => setLinkedin(l => ({ ...l, password: v })), "password", "••••••••")}
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("linkedin", linkedin)} disabled={savingService === "linkedin"}>
              {savingService === "linkedin" ? "Saving…" : "Save LinkedIn Credentials"}
            </button>
          </div>

          {/* OLLAMA */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">Ollama — Local/Self-Hosted LLM</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Used as a fallback for JD Creator when no Groq key is set. Requires{" "}
              <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>Ollama</a>{" "}
              running locally (or reachable at the URL below) with a model pulled, e.g. <code>ollama pull llama3</code>.
            </p>
            <div className="tiq-grid-2">
              {inp("Base URL", ollama.base_url, v => setOllama(o => ({ ...o, base_url: v })), "text", "http://localhost:11434")}
              {inp("Model", ollama.model, v => setOllama(o => ({ ...o, model: v })), "text", "llama3")}
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("ollama", ollama)} disabled={savingService === "ollama"}>
              {savingService === "ollama" ? "Saving…" : "Save Ollama Settings"}
            </button>
          </div>

          {/* SMTP */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">SMTP — Candidate Email Invites</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Used by CandidateLens to send video-interview invite emails to candidates.
              For Gmail, use an <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>app password</a>, not your regular password.
            </p>
            <div className="tiq-grid-2">
              {inp("SMTP Host", smtp.host, v => setSmtp(s => ({ ...s, host: v })), "text", "e.g. smtp.gmail.com")}
              {inp("SMTP Port", smtp.port, v => setSmtp(s => ({ ...s, port: v })), "text", "587")}
              {inp("Username", smtp.username, v => setSmtp(s => ({ ...s, username: v })), "text", "you@company.com")}
              {inp("Password", smtp.password, v => setSmtp(s => ({ ...s, password: v })), "password", "••••••••")}
              {inp("From Email", smtp.from_email, v => setSmtp(s => ({ ...s, from_email: v })), "email", "recruiting@company.com")}
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("smtp", smtp)} disabled={savingService === "smtp"}>
              {savingService === "smtp" ? "Saving…" : "Save SMTP Settings"}
            </button>
          </div>

          {/* SAVED KEYS LIST */}
          <div className="tiq-card">
            <div className="tiq-card-title">Saved keys</div>
            {savedKeys.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No keys saved yet.</div>
            ) : (
              <div className="tiq-table-wrap">
                <table className="tiq-table">
                  <thead><tr><th>Service</th><th>Key</th><th>Saved</th><th></th></tr></thead>
                  <tbody>
                    {savedKeys.map((k: any) => (
                      <tr key={k.id}>
                        <td><span className="tiq-badge tiq-badge-slate">{k.service}</span></td>
                        <td style={{ fontFamily: "monospace", fontSize: 12 }}>{k.key_name}</td>
                        <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{new Date(k.created_at).toLocaleDateString()}</td>
                        <td>
                          <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                            onClick={() => deleteKeyMut.mutate(k.id)}>
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ADMIN TAB ── */}
      {tab === "admin" && user?.role === "admin" && (
        <div>
          <div className="tiq-card">
            <div className="tiq-card-title">All users ({users.length})</div>
            <div className="tiq-table-wrap">
              <table className="tiq-table">
                <thead>
                  <tr><th>Name</th><th>Email (User ID)</th><th>Role</th><th>Company</th><th>Status</th><th>Last login</th><th></th></tr>
                </thead>
                <tbody>
                  {users.map((u: any) => (
                    <tr key={u.id}>
                      <td style={{ fontWeight: 600 }}>{u.name}</td>
                      <td style={{ fontSize: 13 }}>{u.email}</td>
                      <td><span className={`tiq-badge ${u.role === "admin" ? "tiq-badge-violet" : "tiq-badge-slate"}`}>{u.role}</span></td>
                      <td style={{ fontSize: 13, color: "var(--text-muted)" }}>{u.company || "—"}</td>
                      <td><span className={`tiq-badge ${u.is_active ? "tiq-badge-teal" : "tiq-badge-rose"}`}>{u.is_active ? "Active" : "Inactive"}</span></td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{u.last_login ? new Date(u.last_login).toLocaleDateString() : "Never"}</td>
                      <td>
                        {u.id !== user.id && u.is_active && (
                          <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)", fontSize: 11 }}
                            onClick={() => deactivateMut.mutate(u.id)}>Deactivate</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}