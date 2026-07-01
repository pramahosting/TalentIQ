import { } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart2, Play, RefreshCw, ExternalLink, Trash2, TrendingUp, Award } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { jobintelApi } from "../lib/api";
import { useLatestMutation } from "../hooks/useLatestMutation";
import HistoryDropdown from "../components/HistoryDropdown";

const PIE_COLORS = ["#00c7b7","#8b5cf6","#f59e0b","#f43f5e","#3b82f6","#10b981","#ec4899","#06b6d4","#84cc16","#f97316"];

const COUNTRIES = ["Australia","USA","UK","India","Canada","Singapore","New Zealand","UAE"];
const DOMAINS: Record<string, string[]> = {
  "Australia": ["Banking & Financial Services","Technology","Healthcare","Government","Accounting & Audit","Retail","Mining & Resources","Education"],
  "USA": ["Technology","Banking & Financial Services","Healthcare","Government","Retail","Manufacturing","Media & Entertainment","Education"],
  "UK": ["Banking & Financial Services","Technology","Healthcare","Government","Retail","Legal","Education","Creative Industries"],
  "India": ["Technology","Banking & Financial Services","Healthcare","Manufacturing","Retail","Education","Telecommunications","Government"],
  "Canada": ["Technology","Banking & Financial Services","Healthcare","Government","Natural Resources","Manufacturing","Retail","Education"],
  "default": ["Technology","Banking & Financial Services","Healthcare","Government","Manufacturing","Retail","Education","Accounting & Audit"],
};

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = { pending:"tiq-badge-amber", running:"tiq-badge-teal", completed:"tiq-badge-teal", failed:"tiq-badge-rose" };
  return <span className={`tiq-badge ${map[status] || "tiq-badge-slate"}`}>{status}</span>;
}

function StatCard({ label, value, color }: { label: string; value: any; color?: string }) {
  return (
    <div className="tiq-stat-card" style={{ padding: "14px 16px" }}>
      <div className="tiq-stat-label">{label}</div>
      <div className="tiq-stat-value" style={{ fontSize: 22, color: color || "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

export default function MarketIntelPage() {
    const qc = useQueryClient();
  const [country, setCountry] = useState("Australia");
  const [domain, setDomain] = useState("Banking & Financial Services");
  const [jobCount, setJobCount] = useState("100");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [tab, setTab] = useState<"overview" | "records">("overview");

  const domains = DOMAINS[country] || DOMAINS["default"];

  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: ["intel-runs"],
    queryFn: jobintelApi.listRuns,
    refetchInterval: 5000,
  });

  const { data: selectedRun } = useQuery({
    queryKey: ["intel-run", selectedRunId],
    queryFn: () => jobintelApi.getRun(selectedRunId!),
    enabled: !!selectedRunId,
    refetchInterval: (data: any) =>
      data?.status === "completed" || data?.status === "failed" ? false : 2000,
  });

  const { data: records = [] } = useQuery({
    queryKey: ["intel-records", selectedRunId],
    queryFn: () => jobintelApi.getRunRecords(selectedRunId!),
    enabled: !!selectedRunId && selectedRun?.status === "completed",
  });

  const runMutation = useMutation({
    mutationKey: ["jobintel-run"],
    mutationFn: () => jobintelApi.runAnalysis({
      role: domain,
      location: country,
      industry: domain,
      max_results: parseInt(jobCount),
    }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["intel-runs"] });
      setSelectedRunId(data.id);
    },
  });

  // Shared-cache view of the same mutation — lets the run survive the user
  // switching to another agent page while it's kicking off, and auto-selects
  // it here again whenever they come back, regardless of which mount
  // originally triggered it. (The run itself is already tracked server-side
  // and polled via refetchInterval above, so this only affects convenience
  // auto-selection, not data loss.)
  const runState = useLatestMutation<any>(["jobintel-run"]);
  const lastSeenRunId = useRef<number | null>(null);
  useEffect(() => {
    if (runState.status === "success" && runState.data?.id && runState.data.id !== lastSeenRunId.current) {
      lastSeenRunId.current = runState.data.id;
      qc.invalidateQueries({ queryKey: ["intel-runs"] });
      setSelectedRunId(runState.data.id);
    }
  }, [runState.status, runState.data?.id, qc]);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => jobintelApi.deleteRun(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["intel-runs"] });
      if (selectedRunId === id) setSelectedRunId(null);
    },
  });

  const deleteAllMutation = useMutation({
    mutationFn: () => jobintelApi.deleteAllRuns(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["intel-runs"] });
      setSelectedRunId(null);
    },
  });

  const insights = selectedRun?.insights;

  return (
    <div>
      {/* Header */}
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="tiq-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BarChart2 size={22} color="var(--violet-500)" /> MarketIntel
          </h1>
          <p className="tiq-page-sub">Simulate job market data — skill demand, salary trends, hiring patterns</p>
        </div>
      </div>

      {/* Run form + history box side by side (history now a dropdown, same spot as before) */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24, alignItems: "start" }}>
        <div className="tiq-card" style={{ margin: 0 }}>
          <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <BarChart2 size={16} /> New market simulation
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 16, alignItems: "flex-end" }}>
            <div className="tiq-form-group">
              <label className="tiq-label">Country *</label>
              <select className="tiq-input tiq-select" value={country}
                onChange={e => { setCountry(e.target.value); setDomain((DOMAINS[e.target.value] || DOMAINS["default"])[0]); }}>
                {COUNTRIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Business Domain *</label>
              <select className="tiq-input tiq-select" value={domain} onChange={e => setDomain(e.target.value)}>
                {domains.map(d => <option key={d}>{d}</option>)}
              </select>
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label">Number of Jobs</label>
              <select className="tiq-input tiq-select" value={jobCount} onChange={e => setJobCount(e.target.value)}>
                {["50","100","200","300","500","1000","2000","5000","10000"].map(n => <option key={n}>{n}</option>)}
              </select>
            </div>
            <button className="tiq-btn tiq-btn-primary" onClick={() => runMutation.mutate()}
              disabled={runState.status === "pending"} style={{ height: 38 }}>
              <Play size={14} />
              {runState.status === "pending" ? "Starting…" : "Run"}
            </button>
          </div>
        </div>

        {/* Analysis history — same spot as before, now a dropdown */}
        <div className="tiq-card" style={{ margin: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 700 }}>Analysis History ({runs.length})</span>
            {runs.length > 0 && (
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ fontSize: 10, color: "var(--rose-500)", padding: "2px 6px" }}
                onClick={() => { if (confirm("Delete all runs?")) deleteAllMutation.mutate(); }}>
                Clear all
              </button>
            )}
          </div>
          <div style={{ maxWidth: 420, width: "100%" }}>
            <HistoryDropdown
              value={selectedRunId}
              onChange={id => setSelectedRunId(id as number | null)}
              options={runs.map((run: any) => ({
                id: run.id,
                label: `${run.industry || run.role} · ${run.location} · ${run.total_jobs_scraped} jobs · ${run.status} · ${new Date(run.created_at).toLocaleDateString()}`,
              }))}
              onDelete={id => deleteMutation.mutate(id as number)}
              placeholder="Select a past run…"
              confirmDeleteMessage="Delete this run?"
            />
          </div>
        </div>
      </div>

      <div>
        {/* Results */}
          {!selectedRun ? (
            <div className="tiq-card">
              <div className="tiq-empty">
                <BarChart2 size={40} /><div className="tiq-empty-title">Select a run</div>
                <div>Run a new simulation or select one from history to view insights</div>
              </div>
            </div>
          ) : selectedRun.status !== "completed" ? (
            <div className="tiq-card">
              {selectedRun.status === "failed" ? (
                <div className="tiq-alert tiq-alert-error">
                  Simulation failed: {selectedRun.insights?.error || "Unknown error — check backend logs."}
                </div>
              ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "24px 0" }}>
                <RefreshCw size={20} color="var(--teal-500)" style={{ animation: "tiq-spin 1s linear infinite" }} />
                <div>
                  <div style={{ fontWeight: 600 }}>Simulating job market data…</div>
                  <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Generating {jobCount} job records and computing insights</div>
                </div>
              </div>
              )}
            </div>
          ) : (
            <div>
              <div className="tiq-tabs">
                {[["overview","Overview"],["records",`Jobs (${records.length})`]].map(([key, label]) => (
                  <button key={key} className={`tiq-tab${tab === key ? " active" : ""}`} onClick={() => setTab(key as any)}>{label}</button>
                ))}
              </div>

              {tab === "overview" && insights && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
                    <StatCard label="Total Jobs" value={insights.total_jobs} />
                    <StatCard label="Avg Salary" value={insights.salary_stats ? `$${Math.round(insights.salary_stats.avg/1000)}k` : "N/A"} color="var(--teal-500)" />
                    <StatCard label="Unique Skills" value={insights.top_skills?.length || 0} />
                  </div>

                  {/* Job type pie */}
                  {insights.job_type_breakdown && Object.keys(insights.job_type_breakdown).length > 0 && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Job type breakdown</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <PieChart>
                          <Pie data={Object.entries(insights.job_type_breakdown).map(([name,value]) => ({ name, value }))}
                            cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value">
                            {Object.keys(insights.job_type_breakdown).map((_,i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                          </Pie>
                          <Tooltip /><Legend iconSize={10} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Exp level breakdown */}
                  {insights.exp_level_breakdown && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Experience level demand</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={Object.entries(insights.exp_level_breakdown).map(([name,value]) => ({ name, value }))}>
                          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Bar dataKey="value" fill="var(--violet-500)" radius={[4,4,0,0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Company type */}
                  {insights.company_type_breakdown && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title">Company types</div>
                      {Object.entries(insights.company_type_breakdown).map(([type, count]: any, i) => (
                        <div key={type} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                          <div style={{ width: 110, fontSize: 12, color: "var(--text-secondary)", flexShrink: 0 }}>{type}</div>
                          <div style={{ flex: 1 }}>
                            <div className="tiq-score-bar">
                              <div className="tiq-score-bar-fill" style={{ width: `${Math.round((count/insights.total_jobs)*100)}%`, background: PIE_COLORS[i % PIE_COLORS.length] }} />
                            </div>
                          </div>
                          <div style={{ width: 28, fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{count}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Top skills */}
                  {insights.top_skills && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <TrendingUp size={15} color="var(--teal-500)" /> Top skills in demand
                      </div>
                      <ResponsiveContainer width="100%" height={320}>
                        <BarChart data={insights.top_skills.slice(0, 15)} layout="vertical"
                          margin={{ left: 120, right: 16, top: 4, bottom: 4 }}>
                          <XAxis type="number" tick={{ fontSize: 11 }} />
                          <YAxis type="category" dataKey="skill" tick={{ fontSize: 11 }} width={120} />
                          <Tooltip />
                          <Bar dataKey="count" fill="var(--teal-500)" radius={[0,4,4,0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Top tools */}
                  {insights.top_tools && (
                    <div className="tiq-card" style={{ padding: 20 }}>
                      <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Award size={15} color="var(--violet-500)" /> Top tools &amp; technologies
                      </div>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={insights.top_tools.slice(0, 12)} layout="vertical"
                          margin={{ left: 110, right: 16, top: 4, bottom: 4 }}>
                          <XAxis type="number" tick={{ fontSize: 11 }} />
                          <YAxis type="category" dataKey="tool" tick={{ fontSize: 11 }} width={110} />
                          <Tooltip />
                          <Bar dataKey="count" fill="var(--violet-500)" radius={[0,4,4,0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              )}

              {tab === "records" && (
                <div className="tiq-card" style={{ padding: 0, overflow: "hidden" }}>
                  <div className="tiq-card-title" style={{ padding: "14px 16px 0" }}>Market Intelligence Data</div>
                  <div className="tiq-table-wrap" style={{ border: "none", overflowX: "auto" }}>
                    <table className="tiq-table">
                      <thead>
                        <tr>
                          <th>Job Group</th>
                          <th>Standard Skills</th>
                          <th>Job Title</th>
                          <th>Company</th>
                          <th>Company Type</th>
                          <th>Location</th>
                          <th>Experience</th>
                          <th>Key Skills</th>
                          <th>Soft Skills</th>
                          <th>Tools &amp; Tech</th>
                          <th>Certifications</th>
                          <th>Job Type</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(() => {
                          // Build groups exactly like the reference CSV: Job Group + Standard Skills
                          // shown only on the first row of each consecutive group, blank thereafter.
                          let lastGroup = "";
                          return records.map((r: any) => {
                            const g = r.job_group || "General Roles";
                            const isNewGroup = g !== lastGroup;
                            lastGroup = g;

                            // Standard Skills = the set of unique key skills across the whole group
                            const groupItems = records.filter((x: any) => (x.job_group || "General Roles") === g);
                            const standardSkills = Array.from(new Set(groupItems.flatMap((it: any) => it.key_skills || []))).slice(0, 8);

                            return (
                              <tr key={r.id}>
                                <td style={{ fontWeight: 700, fontSize: 12, color: "var(--violet-500)", whiteSpace: "nowrap" }}>
                                  {isNewGroup ? g : ""}
                                </td>
                                <td style={{ minWidth: 180 }}>
                                  {isNewGroup && (
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                                      {standardSkills.map((s: any) => (
                                        <span key={s} className="tiq-badge tiq-badge-violet" style={{ fontSize: 9 }}>{s}</span>
                                      ))}
                                    </div>
                                  )}
                                </td>
                                <td style={{ fontWeight: 600, fontSize: 12, whiteSpace: "nowrap" }}>
                                  {r.title}
                                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{r.published_date}</div>
                                </td>
                                <td style={{ fontSize: 12 }}>{r.company}</td>
                                <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{r.company_type}</td>
                                <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>{r.location}</td>
                                <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                                  {r.experience_years} ({r.experience_level})
                                </td>
                                <td style={{ minWidth: 160 }}>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                                    {(r.key_skills || []).map((s: string) => (
                                      <span key={s} className="tiq-badge tiq-badge-teal" style={{ fontSize: 9 }}>{s}</span>
                                    ))}
                                  </div>
                                </td>
                                <td style={{ minWidth: 140 }}>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                                    {(r.soft_skills || []).map((s: string) => (
                                      <span key={s} className="tiq-badge tiq-badge-rose" style={{ fontSize: 9 }}>{s}</span>
                                    ))}
                                  </div>
                                </td>
                                <td style={{ minWidth: 140 }}>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                                    {(r.tools || []).map((s: string) => (
                                      <span key={s} className="tiq-badge tiq-badge-slate" style={{ fontSize: 9 }}>{s}</span>
                                    ))}
                                  </div>
                                </td>
                                <td style={{ fontSize: 10, color: "var(--text-muted)", minWidth: 120, whiteSpace: "nowrap" }}>
                                  {(r.certifications || []).join("; ")}
                                </td>
                                <td><span className="tiq-badge tiq-badge-violet" style={{ fontSize: 10 }}>{r.job_type || "—"}</span></td>
                                <td style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{r.source}</td>
                              </tr>
                            );
                          });
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
    </div>
  );
}