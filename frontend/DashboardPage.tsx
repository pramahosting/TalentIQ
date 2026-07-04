import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Search, BarChart2, Users, Star, Briefcase, Target, Activity, Home, FileText, FolderOpen, Loader2, CheckCircle2 } from "lucide-react";
import { dashboardApi, candidateTrackApi } from "../lib/api";
import { Link } from "react-router-dom";

// A colored pill used across every dashboard table for status-style counts.
function Pill({ value, color }: { value: number | string; color: string }) {
  return (
    <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: `${color}20`, color }}>
      {value}
    </span>
  );
}

// Shared card shell (colored header band + icon + title) used by every
// module's dashboard table, so all four modules look consistent.
function TableCard({ icon: Icon, color, title, children }: { icon: any; color: string; title: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", background: `linear-gradient(135deg, ${color}14, ${color}03)`, borderBottom: "1px solid var(--border)" }}>
        <Icon size={14} color={color} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: ".03em" }}>{title}</span>
      </div>
      <div style={{ overflowX: "auto" }}>{children}</div>
    </div>
  );
}

function EmptyRow({ colSpan, icon: Icon, text }: { colSpan: number; icon: any; text: string }) {
  return (
    <tr><td colSpan={colSpan} style={{ textAlign: "center", padding: "28px 16px" }}>
      <Icon size={22} color="var(--text-muted)" style={{ opacity: .5, marginBottom: 6 }} />
      <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{text}</div>
    </td></tr>
  );
}

function LoadingRow({ colSpan }: { colSpan: number }) {
  return <tr><td colSpan={colSpan} style={{ textAlign: "center", padding: 28, color: "var(--text-muted)" }}>Loading…</td></tr>;
}

function ErrorRow({ colSpan, error }: { colSpan: number; error: any }) {
  const detail = error?.response?.data?.detail || error?.message || "Unknown error";
  const status = error?.response?.status;
  return (
    <tr><td colSpan={colSpan} style={{ textAlign: "center", padding: "20px 16px" }}>
      <div style={{ color: "var(--rose-500)", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
        Failed to load{status ? ` (${status})` : ""}
      </div>
      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>{String(detail)}</div>
    </td></tr>
  );
}

function dateOnly(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString() : "—";
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: jdSummary = [], isLoading: jdLoading, error: jdError } = useQuery({
    queryKey: ["dashboard-jd-summary"],
    queryFn: candidateTrackApi.jdDashboardSummary,
    refetchInterval: 30_000,
  });
  const { data: vendorSummary = [], isLoading: vendorLoading, error: vendorError } = useQuery({
    queryKey: ["dashboard-vendor-summary"],
    queryFn: candidateTrackApi.vendorDashboardSummary,
    refetchInterval: 30_000,
  });
  const { data: jobHunterSummary = [], isLoading: jobHunterLoading, error: jobHunterError } = useQuery({
    queryKey: ["dashboard-jobhunter-summary"],
    queryFn: dashboardApi.jobHunterSummary,
    refetchInterval: 30_000,
  });
  const { data: marketIntelSummary = [], isLoading: marketIntelLoading, error: marketIntelError } = useQuery({
    queryKey: ["dashboard-marketintel-summary"],
    queryFn: dashboardApi.marketIntelSummary,
    refetchInterval: 30_000,
  });
  const { data: linkExploreSummary = [], isLoading: linkExploreLoading, error: linkExploreError } = useQuery({
    queryKey: ["dashboard-linkexplore-summary"],
    queryFn: dashboardApi.linkExploreSummary,
    refetchInterval: 30_000,
  });

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h1 className="tiq-page-title">Management Dashboard</h1>
          <p className="tiq-page-sub">Your TalentIQ activity at a glance</p>
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 600, alignSelf: "flex-end" }}>
          {today}
        </div>
      </div>

      {/* CandidateLens — real-time tables from the management tables, side by side */}
      <div className="tiq-card tiq-mb-6" style={{ borderLeft: "4px solid #f43f5e" }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)", marginBottom: 16 }}>
          CandidateLens
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", background: "linear-gradient(135deg, rgba(99,102,241,.08), rgba(99,102,241,.02))", borderBottom: "1px solid var(--border)" }}>
              <FileText size={14} color="#6366f1" />
              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: ".03em" }}>
                JDs by Client
              </span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="tiq-table" style={{ fontSize: 12, width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ width: 36 }}>#</th>
                    <th>Client</th>
                    <th style={{ textAlign: "center" }}>Total</th>
                    <th style={{ textAlign: "center" }}>Open</th>
                    <th style={{ textAlign: "center" }}>In Progress</th>
                    <th style={{ textAlign: "center" }}>Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {jdLoading ? (
                    <tr><td colSpan={6} style={{ textAlign: "center", padding: 28, color: "var(--text-muted)" }}>Loading…</td></tr>
                  ) : jdError ? (
                    <ErrorRow colSpan={6} error={jdError} />
                  ) : jdSummary.length === 0 ? (
                    <tr><td colSpan={6} style={{ textAlign: "center", padding: "28px 16px" }}>
                      <FolderOpen size={22} color="var(--text-muted)" style={{ opacity: .5, marginBottom: 6 }} />
                      <div style={{ color: "var(--text-muted)", fontSize: 12 }}>No JDs yet — create one in Management → Job Descriptions</div>
                    </td></tr>
                  ) : (
                    jdSummary.map((r: any, i: number) => (
                      <tr key={r.client_id ?? `none-${i}`}>
                        <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                        <td style={{ fontWeight: 600 }}>{r.client_name}</td>
                        <td style={{ textAlign: "center", fontWeight: 700 }}>{r.total_jds}</td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(16,185,129,.12)", color: "#10b981" }}>
                            {r.open_jds}
                          </span>
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(245,158,11,.12)", color: "#f59e0b" }}>
                            {r.in_progress_jds}
                          </span>
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(107,114,128,.12)", color: "#6b7280" }}>
                            {r.closed_jds}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", background: "linear-gradient(135deg, rgba(244,63,94,.08), rgba(244,63,94,.02))", borderBottom: "1px solid var(--border)" }}>
              <Users size={14} color="#f43f5e" />
              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: ".03em" }}>
                Candidates by Vendor
              </span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="tiq-table" style={{ fontSize: 12, width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ width: 36 }}>#</th>
                    <th>Vendor</th>
                    <th style={{ textAlign: "center" }}>Total</th>
                    <th style={{ textAlign: "center" }}>Consideration</th>
                    <th style={{ textAlign: "center" }}>Successful</th>
                    <th style={{ textAlign: "center" }}>Rejected</th>
                    <th style={{ textAlign: "center" }}>Avg Score</th>
                  </tr>
                </thead>
                <tbody>
                  {vendorLoading ? (
                    <tr><td colSpan={7} style={{ textAlign: "center", padding: 28, color: "var(--text-muted)" }}>Loading…</td></tr>
                  ) : vendorError ? (
                    <ErrorRow colSpan={7} error={vendorError} />
                  ) : vendorSummary.length === 0 ? (
                    <tr><td colSpan={7} style={{ textAlign: "center", padding: "28px 16px" }}>
                      <Users size={22} color="var(--text-muted)" style={{ opacity: .5, marginBottom: 6 }} />
                      <div style={{ color: "var(--text-muted)", fontSize: 12 }}>No vendors yet — add one in Management → Vendors</div>
                    </td></tr>
                  ) : (
                    vendorSummary.map((r: any, i: number) => (
                      <tr key={r.vendor_id}>
                        <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                        <td style={{ fontWeight: 600 }}>{r.vendor_name}</td>
                        <td style={{ textAlign: "center", fontWeight: 700 }}>{r.total_candidates}</td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(245,158,11,.12)", color: "#f59e0b" }}>
                            {r.in_consideration}
                          </span>
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(16,185,129,.12)", color: "#10b981" }}>
                            {r.successful}
                          </span>
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span style={{ display: "inline-block", minWidth: 24, padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: "rgba(239,68,68,.12)", color: "#ef4444" }}>
                            {r.rejected}
                          </span>
                        </td>
                        <td style={{ textAlign: "center", fontWeight: 700, color: r.avg_score != null ? "var(--text-primary)" : "var(--text-muted)" }}>
                          {r.avg_score != null ? `${r.avg_score}%` : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* MarketIntel — real-time, by role */}
      <div className="tiq-card tiq-mb-6" style={{ borderLeft: "4px solid #ec4899" }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)", marginBottom: 16 }}>
          MarketIntel
        </div>
        <TableCard icon={BarChart2} color="#ec4899" title="Analysis Runs by Role">
          <table className="tiq-table" style={{ fontSize: 12, width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 36 }}>#</th>
                <th>Role</th>
                <th style={{ textAlign: "center" }}>Total Runs</th>
                <th style={{ textAlign: "center" }}>Jobs Analysed</th>
                <th style={{ textAlign: "center" }}>Avg Jobs / Run</th>
                <th style={{ textAlign: "center" }}>Last Run</th>
              </tr>
            </thead>
            <tbody>
              {marketIntelLoading ? <LoadingRow colSpan={6} /> :
                marketIntelError ? <ErrorRow colSpan={6} error={marketIntelError} /> :
                marketIntelSummary.length === 0 ? <EmptyRow colSpan={6} icon={BarChart2} text="No MarketIntel runs yet — start one from MarketIntel" /> :
                marketIntelSummary.map((r: any, i: number) => (
                  <tr key={r.role}>
                    <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                    <td style={{ fontWeight: 600 }}>{r.role}</td>
                    <td style={{ textAlign: "center", fontWeight: 700 }}>{r.total_runs}</td>
                    <td style={{ textAlign: "center" }}><Pill value={r.total_jobs_analyzed} color="#ec4899" /></td>
                    <td style={{ textAlign: "center" }}>{r.avg_jobs_per_run}</td>
                    <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{dateOnly(r.last_run)}</td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </TableCard>
      </div>

      {/* LinkExplore — real-time, by job title searched */}
      <div className="tiq-card tiq-mb-6" style={{ borderLeft: "4px solid #10b981" }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)", marginBottom: 16 }}>
          LinkExplore
        </div>
        <TableCard icon={Users} color="#10b981" title="Searches by Job Title">
          <table className="tiq-table" style={{ fontSize: 12, width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 36 }}>#</th>
                <th>Job Title</th>
                <th style={{ textAlign: "center" }}>Total Searches</th>
                <th style={{ textAlign: "center" }}>Profiles Found</th>
                <th style={{ textAlign: "center" }}>Countries</th>
                <th style={{ textAlign: "center" }}>Last Search</th>
              </tr>
            </thead>
            <tbody>
              {linkExploreLoading ? <LoadingRow colSpan={6} /> :
                linkExploreError ? <ErrorRow colSpan={6} error={linkExploreError} /> :
                linkExploreSummary.length === 0 ? <EmptyRow colSpan={6} icon={Users} text="No LinkExplore searches yet — start one from LinkExplore" /> :
                linkExploreSummary.map((r: any, i: number) => (
                  <tr key={r.job_title}>
                    <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                    <td style={{ fontWeight: 600 }}>{r.job_title}</td>
                    <td style={{ textAlign: "center", fontWeight: 700 }}>{r.total_searches}</td>
                    <td style={{ textAlign: "center" }}><Pill value={r.total_profiles} color="#10b981" /></td>
                    <td style={{ textAlign: "center" }}>{r.countries}</td>
                    <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{dateOnly(r.last_search)}</td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </TableCard>
      </div>

      {/* JobHunter — real-time, by role searched */}
      <div className="tiq-card tiq-mb-6" style={{ borderLeft: "4px solid #00c7b7" }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)", marginBottom: 16 }}>
          JobHunter
        </div>
        <TableCard icon={Search} color="#00c7b7" title="Searches &amp; Matches by Role">
          <table className="tiq-table" style={{ fontSize: 12, width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 36 }}>#</th>
                <th>Role</th>
                <th style={{ textAlign: "center" }}>Searches</th>
                <th style={{ textAlign: "center" }}>Jobs Found</th>
                <th style={{ textAlign: "center" }}>Matches Run</th>
                <th style={{ textAlign: "center" }}>Avg ATS Score</th>
                <th style={{ textAlign: "center" }}>Last Search</th>
              </tr>
            </thead>
            <tbody>
              {jobHunterLoading ? <LoadingRow colSpan={7} /> :
                jobHunterError ? <ErrorRow colSpan={7} error={jobHunterError} /> :
                jobHunterSummary.length === 0 ? <EmptyRow colSpan={7} icon={Search} text="No JobHunter searches yet — start one from JobHunter" /> :
                jobHunterSummary.map((r: any, i: number) => (
                  <tr key={r.role}>
                    <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                    <td style={{ fontWeight: 600 }}>{r.role}</td>
                    <td style={{ textAlign: "center", fontWeight: 700 }}>{r.total_searches}</td>
                    <td style={{ textAlign: "center" }}><Pill value={r.total_jobs_found} color="#3b82f6" /></td>
                    <td style={{ textAlign: "center" }}><Pill value={r.total_matches} color="#8b5cf6" /></td>
                    <td style={{ textAlign: "center", fontWeight: 700, color: r.avg_ats_score != null ? "var(--text-primary)" : "var(--text-muted)" }}>
                      {r.avg_ats_score != null ? `${r.avg_ats_score}%` : "—"}
                    </td>
                    <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{dateOnly(r.last_search)}</td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </TableCard>
      </div>

      {/* QUICK ACTIONS */}
      <div className="tiq-grid-3 tiq-mb-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {[
          {
            to: "/app/jobhunt",
            icon: <Search size={20} color="#00c7b7" />,
            title: "Search & match jobs",
            desc: "Upload your resume, search live jobs, get ATS scores and cover letters.",
            color: "var(--teal-500)",
            bg: "rgba(0,199,183,.08)",
          },
          {
            to: "/app/jobintel",
            icon: <BarChart2 size={20} color="#ec4899" />,
            title: "Run market analysis",
            desc: "Analyse skill demand, salary trends, and hiring patterns across industries.",
            color: "#ec4899",
            bg: "rgba(236,72,153,.08)",
          },
          {
            to: "/app/linklens",
            icon: <Users size={20} color="#10b981" />,
            title: "Find candidates",
            desc: "Search LinkedIn at scale, extract profiles, and export to spreadsheet.",
            color: "#10b981",
            bg: "rgba(16,185,129,.08)",
          },
          {
            to: "/app/joblens",
            icon: <Users size={20} color="#f43f5e" />,
            title: "Rank candidates",
            desc: "Upload a JD and multiple CVs, get AI-ranked candidates and interview questions.",
            color: "#f43f5e",
            bg: "rgba(244,63,94,.08)",
          },
        ].map((item) => (
          <Link to={item.to} key={item.to} style={{ textDecoration: "none" }}>
            <div className="tiq-card" style={{ cursor: "pointer", transition: "transform .15s, box-shadow .15s" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)"; (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 24px rgba(0,0,0,.08)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.transform = ""; (e.currentTarget as HTMLElement).style.boxShadow = ""; }}
            >
              <div style={{ width: 40, height: 40, borderRadius: 10, background: item.bg, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}>
                {item.icon}
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)", marginBottom: 6 }}>
                {item.title}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6 }}>{item.desc}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}