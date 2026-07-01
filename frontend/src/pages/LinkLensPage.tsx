import { useNavigate } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Search, Download, RefreshCw, Linkedin, MapPin, Briefcase, CheckCircle, XCircle, Clock, Terminal , Home, Trash2 } from "lucide-react";
import { linklensApi, downloadBlob } from "../lib/api";
import { api } from "../lib/api";
import { useSearchHistory } from "../hooks/useSearchHistory";
import { useLatestMutation } from "../hooks/useLatestMutation";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; icon: any }> = {
    pending:   { cls: "tiq-badge-slate",  icon: Clock },
    running:   { cls: "tiq-badge-amber",  icon: RefreshCw },
    completed: { cls: "tiq-badge-teal",   icon: CheckCircle },
    failed:    { cls: "tiq-badge-rose",   icon: XCircle },
  };
  const { cls, icon: Icon } = map[status] || map.pending;
  return (
    <span className={`tiq-badge ${cls}`} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <Icon size={11} /> {status}
    </span>
  );
}

function AcceptedBadge({ val }: { val: string }) {
  return val === "Y"
    ? <span className="tiq-badge tiq-badge-teal">✓ Accepted</span>
    : <span className="tiq-badge tiq-badge-slate">N</span>;
}

export default function LinkLensPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState({
    job_title: "", country: "Australia", city: "All",
    skills: "", max_results: "25", headless: true,
  });
  const titleHistory  = useSearchHistory("ll_title");
  const skillsHistory = useSearchHistory("ll_skills");
  const [activeSearchId, setActiveSearchId] = useState<number | null>(null);

  const deleteMut = useMutation({
    mutationFn: (id: number) => linklensApi.deleteSearch(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["ll-searches"] });
      if (activeSearchId === id) { setActiveSearchId(null); setStatusLog([]); }
    },
  });
  const [statusLog, setStatusLog] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const { data: searches = [], isLoading: searchesLoading } = useQuery({
    queryKey: ["ll-searches"],
    queryFn: linklensApi.listSearches,
    refetchInterval: 5000,
  });

  const { data: activeSearch, refetch: refetchActive } = useQuery({
    queryKey: ["ll-search", activeSearchId],
    queryFn: () => linklensApi.getSearch(activeSearchId!),
    enabled: !!activeSearchId,
    refetchInterval: (data: any) =>
      data?.status === "running" ? 4000 : false,
  });

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [statusLog]);

  const startMut = useMutation({
    mutationKey: ["linklens-start"],
    mutationFn: () => api.post("/api/linklens/search", {
      ...form,
      max_results: parseInt(form.max_results),
      headless: form.headless,
    }).then(r => r.data),
    onSuccess: (data) => {
      titleHistory.addEntry(form.job_title);
      if (form.skills) skillsHistory.addEntry(form.skills);
      setActiveSearchId(data.id);
      setStatusLog([`[${new Date().toLocaleTimeString()}] 🚀 Search started (ID: ${data.id})`]);
      qc.invalidateQueries({ queryKey: ["ll-searches"] });
      // Start SSE stream
      startStatusStream(data.id);
    },
    onError: (e: any) => {
      setStatusLog(l => [...l, `❌ Error: ${e.response?.data?.detail || e.message}`]);
    },
  });

  // Shared-cache view of the same mutation — lets a started search survive
  // the user switching to another agent page. The actual scrape runs as a
  // backend job regardless (tracked by activeSearch's own polling below),
  // so nothing is lost; this just re-selects it here on return. Note: the
  // live SSE status log is inherently a live-tailing feature and doesn't
  // replay past messages — the search's persisted status/progress is what
  // matters and that's always safe.
  const startState = useLatestMutation<any>(["linklens-start"]);
  const lastSeenStartId = useRef<number | null>(null);
  useEffect(() => {
    if (startState.status === "success" && startState.data?.id && startState.data.id !== lastSeenStartId.current) {
      lastSeenStartId.current = startState.data.id;
      qc.invalidateQueries({ queryKey: ["ll-searches"] });
      setActiveSearchId(prev => prev ?? startState.data.id);
    }
  }, [startState.status, startState.data?.id, qc]);

  const startStatusStream = (searchId: number) => {
    setStreaming(true);
    const token = localStorage.getItem("talentiq_token") || "";
    const evtSource = new EventSource(
      `/api/linklens/searches/${searchId}/status?token=${token}`
    );

    evtSource.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.done) {
        evtSource.close();
        setStreaming(false);
        refetchActive();
        qc.invalidateQueries({ queryKey: ["ll-searches"] });
        return;
      }
      if (data.message) {
        setStatusLog(prev => [...prev, data.message]);
      }
    };

    evtSource.onerror = () => {
      evtSource.close();
      setStreaming(false);
      refetchActive();
    };
  };

  const exportMut = useMutation({
    mutationFn: (id: number) => linklensApi.exportProfiles(id),
    onSuccess: (blob, id) => downloadBlob(blob, `linklens_${id}.xlsx`),
  });

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const profiles = activeSearch?.profiles || [];
  const accepted = profiles.filter((p: any) => p.accepted === "Y").length;

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Linkedin size={22} color="#0A66C2" /> LinkExplore
        </h1>
        <p className="tiq-page-sub">Search LinkedIn at scale — extract candidates, skills and contacts</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 24, alignItems: "flex-start" }}>

        {/* ── SEARCH FORM ── */}
        <div>
          <div className="tiq-card tiq-mb-4">
            <div className="tiq-card-title">New Search</div>

            <div className="tiq-form-group">
              <label className="tiq-label">Job Title *</label>
              <input className="tiq-input" value={form.job_title} onChange={set("job_title")}
                placeholder="e.g. Senior Accountant" list="ll-title-list" />
              <datalist id="ll-title-list">
                {titleHistory.history.map(h => <option key={h} value={h} />)}
              </datalist>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Country</label>
              <input className="tiq-input" value={form.country} onChange={set("country")} />
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">City (or "All")</label>
              <input className="tiq-input" value={form.city} onChange={set("city")} />
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Skills (comma separated)</label>
              <input className="tiq-input" value={form.skills} onChange={set("skills")}
                placeholder="Xero, MYOB, CPA" list="ll-skills-list" />
              <datalist id="ll-skills-list">
                {skillsHistory.history.map(h => <option key={h} value={h} />)}
              </datalist>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Max Profiles</label>
              <select className="tiq-input tiq-select" value={form.max_results}
                onChange={e => setForm(f => ({ ...f, max_results: e.target.value }))}>
                {[10, 25, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Browser Mode</label>
              <select className="tiq-input tiq-select" value={form.headless ? "true" : "false"}
                onChange={e => setForm(f => ({ ...f, headless: e.target.value === "true" }))}>
                <option value="true">Headless (background, faster)</option>
                <option value="false">Visible (shows browser window)</option>
              </select>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                Use Visible mode if LinkedIn shows CAPTCHA or blocks headless.
              </div>
            </div>

            <button className="tiq-btn tiq-btn-primary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={() => startMut.mutate()}
              disabled={!form.job_title || startState.status === "pending" || streaming}>
              <Search size={14} />
              {streaming ? "Running…" : startState.status === "pending" ? "Starting…" : "Start Search"}
            </button>
          </div>

          {/* PAST SEARCHES */}
          <div className="tiq-card" style={{ padding: 0 }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Past Searches
            </div>
            {searches.length === 0 ? (
              <div style={{ padding: 16, fontSize: 13, color: "var(--text-muted)" }}>No searches yet.</div>
            ) : searches.map((s: any) => (
              <div key={s.id}
                onClick={() => { setActiveSearchId(s.id); setStatusLog([]); }}
                style={{
                  padding: "10px 16px", cursor: "pointer", fontSize: 13,
                  background: activeSearchId === s.id ? "rgba(0,199,183,.06)" : undefined,
                  borderLeft: activeSearchId === s.id ? "3px solid var(--teal-500)" : "3px solid transparent",
                }}>
                <div style={{ fontWeight: 600 }}>{s.job_title}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, display: "flex", gap: 8, alignItems: "center" }}>
                  <StatusBadge status={s.status} />
                  <span>{s.profiles_found} profiles</span>
                  <span>{s.city}, {s.country}</span>
                  <button
                    onClick={e => { e.stopPropagation(); if(confirm("Delete this search?")) deleteMut.mutate(s.id); }}
                    style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex", padding: 2 }}
                  ><Trash2 size={11} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── MAIN PANEL ── */}
        <div>
          {/* LIVE STATUS LOG */}
          {(statusLog.length > 0 || streaming) && (
            <div className="tiq-card tiq-mb-4" style={{ background: "#0d1117", border: "1px solid #30363d" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Terminal size={14} color="#58a6ff" />
                <span style={{ fontSize: 12, fontWeight: 700, color: "#58a6ff", letterSpacing: ".5px" }}>
                  LIVE STATUS {streaming && <span style={{ color: "#f0883e" }}>● RUNNING</span>}
                </span>
              </div>
              <div ref={logRef} style={{
                maxHeight: 240, overflowY: "auto", fontFamily: "monospace",
                fontSize: 12, lineHeight: 1.7,
              }}>
                {statusLog.map((msg, i) => {
                  const color = msg.includes("❌") ? "#f85149"
                    : msg.includes("✅") ? "#3fb950"
                    : msg.includes("⚠️") ? "#f0883e"
                    : msg.includes("🔐") || msg.includes("💾") ? "#d2a8ff"
                    : msg.includes("🔍") || msg.includes("📄") ? "#58a6ff"
                    : msg.includes("📥") || msg.includes("🧠") ? "#79c0ff"
                    : "#c9d1d9";
                  return (
                    <div key={i} style={{ color, padding: "1px 0" }}>{msg}</div>
                  );
                })}
                {streaming && (
                  <div style={{ color: "#58a6ff" }}>
                    <span className="tiq-spinner" style={{ width: 10, height: 10, borderWidth: 2, marginRight: 6, verticalAlign: "middle" }} />
                    Processing...
                  </div>
                )}
              </div>
            </div>
          )}

          {/* RESULTS */}
          {activeSearch ? (
            <div className="tiq-card" style={{ padding: 0 }}>
              <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>
                    {activeSearch.job_title} — {activeSearch.city}, {activeSearch.country}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
                    <StatusBadge status={activeSearch.status} />
                    &nbsp; {profiles.length} total · {accepted} accepted
                    {activeSearch.skills && <> · Skills: {activeSearch.skills}</>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" onClick={() => refetchActive()}>
                    <RefreshCw size={13} />
                  </button>
                  {profiles.length > 0 && (
                    <button className="tiq-btn tiq-btn-outline tiq-btn-sm"
                      onClick={() => exportMut.mutate(activeSearch.id)}
                      disabled={exportMut.isPending}>
                      <Download size={13} /> Export Excel
                    </button>
                  )}
                </div>
              </div>

              {profiles.length === 0 ? (
                <div className="tiq-empty" style={{ padding: 48 }}>
                  <Users size={36} />
                  <div className="tiq-empty-title">
                    {activeSearch.status === "running" ? "Search in progress…" : "No profiles found"}
                  </div>
                  <div style={{ fontSize: 13 }}>
                    {activeSearch.status === "running"
                      ? "Watch the live status above. Results appear when complete."
                      : "Try a different job title or location."}
                  </div>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="tiq-table">
                    <thead>
                      <tr>
                        <th style={{ width: 40 }}>✓</th>
                        <th>Name</th>
                        <th>Title</th>
                        <th>Company</th>
                        <th>Location</th>
                        <th>Skills</th>
                        <th>Contact</th>
                        <th>Profile</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profiles.map((p: any) => (
                        <tr key={p.id}>
                          <td><AcceptedBadge val={p.accepted} /></td>
                          <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{p.name}</td>
                          <td style={{ fontSize: 12, maxWidth: 200 }}>{p.title}</td>
                          <td style={{ fontSize: 12 }}>{p.company}</td>
                          <td style={{ fontSize: 12 }}>
                            {p.location && p.location !== "Not found" && (
                              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                <MapPin size={11} color="var(--text-muted)" />{p.location}
                              </span>
                            )}
                          </td>
                          <td style={{ fontSize: 11, maxWidth: 160, color: "var(--text-secondary)" }}>
                            {Array.isArray(p.skills) ? p.skills.slice(0, 3).join(", ") : (p.skills || "")}
                          </td>
                          <td style={{ fontSize: 11 }}>
                            {p.email && <div>{p.email}</div>}
                            {p.phone && <div style={{ color: "var(--text-muted)" }}>{p.phone}</div>}
                          </td>
                          <td>
                            {p.profile_url && (
                              <a href={p.profile_url} target="_blank" rel="noopener noreferrer"
                                className="tiq-btn tiq-btn-ghost tiq-btn-sm"
                                style={{ color: "#0A66C2", fontSize: 11 }}>
                                <Linkedin size={11} /> View
                              </a>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="tiq-card">
              <div className="tiq-empty">
                <Linkedin size={48} color="#0A66C2" style={{ opacity: .4 }} />
                <div className="tiq-empty-title">Start a Search</div>
                <div style={{ fontSize: 13, maxWidth: 380, textAlign: "center" }}>
                  Enter a job title and location, then click Start Search.
                  LinkLens will log in to LinkedIn, collect profile links, download each profile,
                  and extract structured candidate data.
                </div>
                <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-muted)" }}>
                  Make sure your LinkedIn credentials are saved in <strong>Settings → API Keys</strong>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
