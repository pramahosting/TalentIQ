import { useNavigate } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings, Key, User, Shield, Trash2 , Home} from "lucide-react";
import { authApi, groqPoolApi } from "../lib/api";
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
  const [groq, setGroq] = useState({ api_key: "", model: "" });
  const [linkedin, setLinkedin] = useState({ email: "", password: "" });
  const [smtp, setSmtp] = useState({ host: "", port: "587", username: "", password: "", from_email: "" });
  const [ollama, setOllama] = useState({ base_url: "http://localhost:11434", model: "llama3" });
  const [morphcast, setMorphcast] = useState({ license_key: "" });
  const [keyMsg, setKeyMsg] = useState("");

  const flashMsg = (m: string) => { setKeyMsg(m); setTimeout(() => setKeyMsg(""), 3000); };

  const [savingService, setSavingService] = useState("");
  const isAdmin = user?.role === "admin";
  const { data: globalKeys = [] } = useQuery({ queryKey: ["global-keys"], queryFn: authApi.listGlobalKeys });
  const globalServiceSet = new Set(globalKeys.map((k: any) => k.service));
  const SHAREABLE = ["groq", "ollama", "adzuna"];
  const [globalToggle, setGlobalToggle] = useState<Record<string, boolean>>({});

  // ── GROQ KEY POOL (admin only) ───────────────────────────────────
  const { data: poolKeys = [], refetch: refetchPool } = useQuery({
    queryKey: ["groq-pool"], queryFn: groqPoolApi.list, enabled: isAdmin,
  });
  const [newPoolKey, setNewPoolKey] = useState({ key_value: "", model: "" });
  // Pulled live from Groq's own API using the key just typed in, rather
  // than a hardcoded list — a fixed list is exactly the kind of thing
  // that goes stale the moment Groq adds or retires a model (hit this
  // directly, twice, earlier this session).
  const [fetchedModels, setFetchedModels] = useState<string[] | null>(null);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [modelsFetchError, setModelsFetchError] = useState("");
  const fetchModelsForKey = async (keyOverride?: string) => {
    const key = (keyOverride ?? newPoolKey.key_value).trim();
    if (!key) { setModelsFetchError("Enter the API key above first."); return; }
    setFetchingModels(true); setModelsFetchError(""); setFetchedModels(null);
    try {
      const res = await groqPoolApi.listModels(key);
      setFetchedModels(res.models || []);
    } catch (e: any) {
      setModelsFetchError(e.response?.data?.detail || "Could not fetch models for this key.");
    } finally {
      setFetchingModels(false);
    }
  };
  // Auto-fetches shortly after the user stops typing/pasting a
  // plausible-looking key — no extra click needed, models just show up
  // the way they would if you were looking at Groq's own console. The
  // manual button stays as a fallback (e.g. to retry after a transient
  // network error) but isn't the primary path anymore.
  const autoFetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (autoFetchTimer.current) clearTimeout(autoFetchTimer.current);
    const key = newPoolKey.key_value.trim();
    if (key.length < 20) return; // too short to plausibly be a real key yet
    autoFetchTimer.current = setTimeout(() => { fetchModelsForKey(key); }, 600);
    return () => { if (autoFetchTimer.current) clearTimeout(autoFetchTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newPoolKey.key_value]);
  const [poolMsg, setPoolMsg] = useState("");
  const flashPool = (m: string) => { setPoolMsg(m); setTimeout(() => setPoolMsg(""), 3000); };

  const addPoolMut = useMutation({
    mutationFn: () => groqPoolApi.add({ key_value: newPoolKey.key_value.trim(), model: newPoolKey.model.trim() || undefined }),
    onSuccess: () => { refetchPool(); setNewPoolKey({ key_value: "", model: "" }); setFetchedModels(null); setModelsFetchError(""); flashPool("Key added to pool."); },
    onError: (e: any) => flashPool(`❌ ${e.response?.data?.detail || "Failed to add key"}`),
  });
  const togglePoolMut = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => groqPoolApi.update(id, { is_active }),
    onSuccess: () => refetchPool(),
    onError: (e: any) => flashPool(`❌ ${e.response?.data?.detail || "Failed to update key"}`),
  });
  const removePoolMut = useMutation({
    mutationFn: (id: number) => groqPoolApi.remove(id),
    onSuccess: () => { refetchPool(); flashPool("Key removed from pool."); },
    onError: (e: any) => flashPool(`❌ ${e.response?.data?.detail || "Failed to remove key"}`),
  });

  const saveKey = async (service: string, fields: Record<string, string>) => {
    const entries = Object.entries(fields).filter(([, v]) => v.trim() !== "");
    if (entries.length === 0) { flashMsg("Enter at least one value to save."); return; }
    setSavingService(service);
    const isGlobal = isAdmin && SHAREABLE.includes(service) && !!globalToggle[service];
    try {
      for (const [key_name, key_value] of entries) {
        await authApi.saveApiKey({ service, key_name, key_value, is_global: isGlobal });
      }
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      flashMsg("✅ " + service + " credentials saved successfully!" + (isGlobal ? " (shared with all users)" : ""));
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

  const globalCheckbox = (service: string) => isAdmin && (
    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted)", margin: "8px 0" }}>
      <input type="checkbox" checked={!!globalToggle[service]}
        onChange={e => setGlobalToggle(g => ({ ...g, [service]: e.target.checked }))} />
      Make this available to all users (admin only — Groq/Ollama/Adzuna can be shared platform-wide)
    </label>
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

          {/* ADZUNA / GROQ / OLLAMA — admin-managed only. These three are
              platform-shared credentials (see utils/credentials.py
              SHAREABLE_SERVICES); every user already inherits whatever the
              admin configures here, so only admins get the editable form —
              everyone else sees a simple status readout instead. */}
          {isAdmin ? (
            <div className="tiq-card tiq-mb-6">
              <div className="tiq-card-title">Adzuna — Job Search API</div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
                Free at <a href="https://developer.adzuna.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>developer.adzuna.com</a>. Needed for JobHunt and JobIntel agents.
              </p>
              <div className="tiq-grid-2">
                {inp("App ID", adzuna.app_id, v => setAdzuna(a => ({ ...a, app_id: v })), "text", "e.g. 638c0962")}
                {inp("App Key", adzuna.app_key, v => setAdzuna(a => ({ ...a, app_key: v })), "password", "e.g. 04681adc…")}
              </div>
              {globalCheckbox("adzuna")}
              <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("adzuna", adzuna)} disabled={savingService === "adzuna"}>
                {savingService === "adzuna" ? "Saving…" : "Save Adzuna Keys"}
              </button>
            </div>
          ) : null}

          {isAdmin ? (
            <div className="tiq-card tiq-mb-6">
              <div className="tiq-card-title">Groq Key Pool — scale capacity automatically</div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
                Add multiple Groq keys here (from separate Groq accounts if you want real added
                throughput — Groq's rate limits apply per account, not per key). The platform
                automatically spreads load across whichever keys are healthy, and routes around
                any that are temporarily rate-limited, recovering them automatically once they
                cool down.
              </p>

              {poolMsg && (
                <div style={{ fontSize: 12, marginBottom: 12, padding: "8px 12px", borderRadius: 6,
                  background: poolMsg.startsWith("❌") ? "rgba(239,68,68,.08)" : "rgba(20,184,166,.08)",
                  color: poolMsg.startsWith("❌") ? "#ef4444" : "var(--teal-500)" }}>
                  {poolMsg}
                </div>
              )}

              {poolKeys.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>
                    Keys in pool ({poolKeys.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {(() => {
                      // Numbered by chronological addition order (oldest = #1),
                      // not by current display position — the list itself
                      // shows newest-first, but "key #1" should always mean
                      // "the first one I added", not shift around based on
                      // display order.
                      const byAddedAsc = [...poolKeys].sort((a: any, b: any) =>
                        new Date(a.added_at || 0).getTime() - new Date(b.added_at || 0).getTime()
                      );
                      const numberOf = new Map(byAddedAsc.map((k: any, i: number) => [k.id, i + 1]));
                      return poolKeys.map((k: any) => (
                      <div key={k.id} style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                        border: "1px solid var(--border)", borderRadius: 8,
                        opacity: k.is_active ? 1 : 0.5,
                      }}>
                        <span style={{
                          display: "flex", alignItems: "center", justifyContent: "center",
                          width: 24, height: 24, borderRadius: 6, flexShrink: 0,
                          background: "var(--surface-2, rgba(0,0,0,.06))", fontSize: 11, fontWeight: 700,
                          color: "var(--text-muted)",
                        }}>
                          {numberOf.get(k.id)}
                        </span>
                        <span style={{ fontFamily: "monospace", fontSize: 13 }}>{k.key_preview}</span>
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{k.model || "platform default"}</span>
                        {k.cooldown_until && new Date(k.cooldown_until) > new Date() && (
                          <span style={{ fontSize: 11, color: "#f59e0b" }}>⏳ cooling down</span>
                        )}
                        {!k.is_active && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>disabled</span>}
                        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                          <button
                            className="tiq-btn tiq-btn-sm"
                            onClick={() => togglePoolMut.mutate({ id: k.id, is_active: !k.is_active })}
                          >
                            {k.is_active ? "Disable" : "Enable"}
                          </button>
                          <button
                            className="tiq-btn tiq-btn-sm"
                            style={{ color: "#ef4444" }}
                            onClick={() => { if (confirm("Remove this key from the pool?")) removePoolMut.mutate(k.id); }}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                      ));
                    })()}
                  </div>
                </div>
              )}

              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.4 }}>
                  Add a new key — will become Key #{poolKeys.length + 1}
                </div>

                {inp("API Key", newPoolKey.key_value, v => { setNewPoolKey(k => ({ ...k, key_value: v })); setFetchedModels(null); setModelsFetchError(""); }, "password", "gsk_…")}

                <div style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 10 }}>
                  {fetchingModels && (
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Checking with Groq…</span>
                  )}
                  {!fetchingModels && fetchedModels && (
                    <span style={{ fontSize: 12, color: "var(--teal-500)" }}>✓ {fetchedModels.length} models available for this key</span>
                  )}
                  {!fetchingModels && !fetchedModels && !modelsFetchError && newPoolKey.key_value.trim().length > 0 && (
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Models will load automatically once the key looks complete…</span>
                  )}
                  <button
                    type="button"
                    className="tiq-btn tiq-btn-sm"
                    onClick={() => fetchModelsForKey()}
                    disabled={fetchingModels || !newPoolKey.key_value.trim()}
                  >
                    {fetchedModels ? "Refetch" : "Fetch now"}
                  </button>
                  {modelsFetchError && <span style={{ fontSize: 12, color: "#ef4444" }}>{modelsFetchError}</span>}
                </div>

                <div style={{ marginTop: 12, marginBottom: 14 }}>
                  <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Model</label>
                  {fetchedModels ? (
                    <select
                      value={newPoolKey.model}
                      onChange={e => setNewPoolKey(k => ({ ...k, model: e.target.value }))}
                      className="tiq-input"
                      style={{ width: "100%" }}
                    >
                      <option value="">Platform default</option>
                      {fetchedModels.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <>
                      {inp("", newPoolKey.model, v => setNewPoolKey(k => ({ ...k, model: v })), "text", "leave blank for platform default, or fetch models above to pick from a live list")}
                    </>
                  )}
                </div>

                <button
                  className="tiq-btn tiq-btn-primary"
                  onClick={() => addPoolMut.mutate()}
                  disabled={addPoolMut.isPending || !newPoolKey.key_value.trim()}
                >
                  {addPoolMut.isPending ? "Adding…" : `Add as Key #${poolKeys.length + 1}`}
                </button>
              </div>
            </div>
          ) : null}

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

          {isAdmin ? (
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
              {globalCheckbox("ollama")}
              <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("ollama", ollama)} disabled={savingService === "ollama"}>
                {savingService === "ollama" ? "Saving…" : "Save Ollama Settings"}
              </button>
            </div>
          ) : (
            <div className="tiq-card tiq-mb-6">
              <div className="tiq-card-title">Platform AI & Search Services</div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
                Adzuna, Groq, and Ollama are configured platform-wide by your administrator — every feature that
                uses them (resume summaries, JD skill extraction, interview questions, CVAnalysis scoring, job
                search, and more) automatically uses whatever is set up here, no action needed from you.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { key: "adzuna", label: "Adzuna (job search)" },
                  { key: "groq", label: "Groq (AI / LLM)" },
                  { key: "ollama", label: "Ollama (local LLM fallback)" },
                ].map(({ key, label }) => (
                  <div key={key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: globalServiceSet.has(key) ? "#10b981" : "#d1d5db",
                      flexShrink: 0,
                    }} />
                    <span>{label}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {globalServiceSet.has(key) ? "Configured" : "Not yet configured"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MORPHCAST */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title">MorphCast — Video Interview Emotion AI</div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Powers the facial emotion analysis during CandidateLens video interviews (Video Review column).
              Get a free license key at{" "}
              <a href="https://www.morphcast.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--teal-500)" }}>morphcast.com</a>{" "}
              — a key is required on every load; without one, interviews still run but skip emotion analysis.
            </p>
            <div className="tiq-grid-2">
              {inp("License Key", morphcast.license_key, v => setMorphcast({ license_key: v }), "text", "paste your MorphCast license key")}
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => saveKey("morphcast", morphcast)} disabled={savingService === "morphcast"}>
              {savingService === "morphcast" ? "Saving…" : "Save MorphCast Key"}
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