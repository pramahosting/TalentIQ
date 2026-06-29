import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart2, Play, RefreshCw, ExternalLink , Home} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { jobintelApi } from "../lib/api";

const PIE_COLORS = ["#00c7b7", "#8b5cf6", "#f59e0b", "#f43f5e", "#3b82f6", "#10b981", "#ec4899"];

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "tiq-badge-amber",
    running: "tiq-badge-teal",
    completed: "tiq-badge-teal",
    failed: "tiq-badge-rose",
  };
  return <span className={`tiq-badge ${map[status] || "tiq-badge-slate"}`}>{status}</span>;
}

export default function MarketIntelPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState({ role: "", location: "", industry: "", max_results: "20" });
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [tab, setTab] = useState<"overview" | "records">("overview");

  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: ["intel-runs"],
    queryFn: jobintelApi.listRuns,
    refetchInterval: 5000,
  });

  const { data: selectedRun } = useQuery({
    queryKey: ["intel-run", selectedRunId],
    queryFn: () => jobintelApi.getRun(selectedRunId!),
    enabled: !!selectedRunId,
    refetchInterval: (data: any) => (data?.status === "completed" || data?.status === "failed") ? false : 3000,
  });

  const { data: records = [] } = useQuery({
    queryKey: ["intel-records", selectedRunId],
    queryFn: () => jobintelApi.getRunRecords(selectedRunId!),
    enabled: !!selectedRunId && selectedRun?.status === "completed",
  });

  const runMutation = useMutation({
    mutationFn: () => jobintelApi.runAnalysis({
      ...form, max_results: parseInt(form.max_results),
    }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["intel-runs"] });
      setSelectedRunId(data.id);
    },
  });

  const setF = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const insights = selectedRun?.insights;

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title">MarketIntel Agent</h1>
        <p className="tiq-page-sub">Market intelligence: skill demand, salary trends, hiring patterns</p>
      </div>

      {/* RUN FORM */}
      <div className="tiq-card tiq-mb-6">
        <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <BarChart2 size={16} /> New analysis
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
          <div className="tiq-form-group">
            <label className="tiq-label">Role / Domain *</label>
            <input className="tiq-input" value={form.role} onChange={setF("role")} placeholder="e.g. Data Engineer" />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Location</label>
            <input className="tiq-input" value={form.location} onChange={setF("location")} placeholder="e.g. Melbourne" />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Industry</label>
            <input className="tiq-input" value={form.industry} onChange={setF("industry")} placeholder="e.g. Finance" />
          </div>
          <div className="tiq-form-group">
            <label className="tiq-label">Max jobs</label>
            <select className="tiq-input tiq-select" value={form.max_results} onChange={setF("max_results")}>
              {["10", "20", "30", "50"].map((n) => <option key={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <button
          className="tiq-btn tiq-btn-primary"
          onClick={() => runMutation.mutate()}
          disabled={!form.role || runMutation.isPending}
        >
          <Play size={14} />
          {runMutation.isPending ? "Starting…" : "Run analysis"}
        </button>
      </div>

      <div className="tiq-grid-2" style={{ gap: 20, alignItems: "flex-start" }}>
        {/* RUN HISTORY */}
        <div className="tiq-card" style={{ maxHeight: 480, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div className="tiq-card-title">Analysis history</div>
          {runsLoading ? (
            <div className="tiq-spinner-wrap"><div className="tiq-spinner" /></div>
          ) : runs.length === 0 ? (
            <div className="tiq-empty"><BarChart2 size={32} /><div className="tiq-empty-title">No runs yet</div></div>
          ) : (
            <div style={{ overflowY: "auto", flex: 1 }}>
              {runs.map((run: any) => (
                <div
                  key={run.id}
                  onClick={() => setSelectedRunId(run.id)}
                  style={{
                    padding: "12px 14px",
                    borderRadius: 8,
                    cursor: "pointer",
                    background: selectedRunId === run.id ? "rgba(0,199,183,.06)" : "transparent",
                    border: selectedRunId === run.id ? "1px solid rgba(0,199,183,.2)" : "1px solid transparent",
                    marginBottom: 6,
                    transition: "all .15s",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{run.role}</div>
                    <StatusBadge status={run.status} />
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                    {run.location || "All locations"} · {run.total_jobs_scraped} jobs · {new Date(run.created_at).toLocaleDateString()}
                  </div>
                  {run.status === "running" && (
                    <div style={{ marginTop: 8 }}>
                      <div className="tiq-score-bar">
                        <div className="tiq-score-bar-fill" style={{ width: "60%", background: "linear-gradient(90deg, #8b5cf6, #c4b5fd)", animation: "none" }} />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ANALYSIS RESULTS */}
        <div>
          {!selectedRun ? (
            <div className="tiq-card">
              <div className="tiq-empty">
                <BarChart2 size={40} />
                <div className="tiq-empty-title">Select an analysis</div>
                <div>Run a new analysis or select one from history to view insights</div>
              </div>
            </div>
          ) : selectedRun.status !== "completed" ? (
            <div className="tiq-card">
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "24px 0" }}>
                <RefreshCw size={20} color="var(--teal-500)" style={{ animation: "tiq-spin 1s linear infinite" }} />
                <div>
                  <div style={{ fontWeight: 600 }}>Analysis {selectedRun.status}…</div>
                  <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Scraping job data and computing insights</div>
                </div>
              </div>
            </div>
          ) : (
            <div>
              <div className="tiq-tabs">
                <button className={`tiq-tab${tab === "overview" ? " active" : ""}`} onClick={() => setTab("overview")}>Analytics</button>
                <button className={`tiq-tab${tab === "records" ? " active" : ""}`} onClick={() => setTab("records")}>
                  Job records ({records.length})
                </button>
              </div>

              {tab === "overview" && insights && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  {/* SUMMARY STATS */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                    {[
                      { label: "Total Jobs", value: insights.total_jobs },
                      { label: "Avg Min Salary", value: insights.salary_stats ? `$${(insights.salary_stats.avg / 1000).toFixed(0)}k` : "N/A" },
                      { label: "Unique Skills", value: insights.top_skills?.length || 0 },
                    ].map((s) => (
                      <div key={s.label} className="tiq-stat-card" style={{ padding: "14px 16px" }}>
                        <div className="tiq-stat-label">{s.label}</div>
                        <div className="tiq-stat-value" style={{ fontSize: 22 }}>{s.value}</div>
                      </div>
                    ))}
                  </div>

                  {/* TOP SKILLS CHART */}
                  {insights.top_skills?.length > 0 && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Top skills in demand</div>
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={insights.top_skills.slice(0, 10)} layout="vertical"
                          margin={{ left: 60, right: 16, top: 4, bottom: 4 }}>
                          <XAxis type="number" tick={{ fontSize: 11 }} />
                          <YAxis type="category" dataKey="skill" tick={{ fontSize: 11 }} width={60} />
                          <Tooltip />
                          <Bar dataKey="count" fill="var(--teal-500)" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* JOB TYPE PIE */}
                  {insights.job_type_breakdown && Object.keys(insights.job_type_breakdown).length > 0 && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Job type breakdown</div>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie
                            data={Object.entries(insights.job_type_breakdown).map(([name, value]) => ({ name, value }))}
                            cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                            dataKey="value"
                          >
                            {Object.keys(insights.job_type_breakdown).map((_, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend iconSize={10} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* COMPANY TYPE */}
                  {insights.company_type_breakdown && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Company type</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {Object.entries(insights.company_type_breakdown).map(([type, count]: any, i) => (
                          <div key={type} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                            <div style={{ width: 90, fontSize: 12, color: "var(--text-secondary)", flexShrink: 0 }}>{type}</div>
                            <div style={{ flex: 1 }}>
                              <div className="tiq-score-bar">
                                <div className="tiq-score-bar-fill"
                                  style={{
                                    width: `${Math.round((count / insights.total_jobs) * 100)}%`,
                                    background: PIE_COLORS[i % PIE_COLORS.length],
                                  }}
                                />
                              </div>
                            </div>
                            <div style={{ width: 24, fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{count}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {tab === "records" && (
                <div className="tiq-card" style={{ padding: 0, overflow: "hidden" }}>
                  <div className="tiq-table-wrap" style={{ border: "none" }}>
                    <table className="tiq-table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Company</th>
                          <th>Domain</th>
                          <th>Level</th>
                          <th>Top Skills</th>
                          <th>Link</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((r: any) => (
                          <tr key={r.id}>
                            <td style={{ fontWeight: 600 }}>{r.title}</td>
                            <td style={{ color: "var(--text-secondary)" }}>{r.company}</td>
                            <td><span className="tiq-badge tiq-badge-violet">{r.domain || "—"}</span></td>
                            <td><span className="tiq-badge tiq-badge-slate">{r.experience_level || "—"}</span></td>
                            <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                              {r.key_skills?.slice(0, 3).join(", ") || "—"}
                            </td>
                            <td>
                              {r.source_url && (
                                <a href={r.source_url} target="_blank" rel="noopener noreferrer"
                                  className="tiq-btn tiq-btn-ghost tiq-btn-sm">
                                  <ExternalLink size={12} />
                                </a>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
