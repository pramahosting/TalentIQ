import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, BarChart2, Users, Star, Briefcase, Target, Activity , Home} from "lucide-react";
import { dashboardApi } from "../lib/api";
import { Link } from "react-router-dom";

const STAT_CARDS = [
  { key: "total_job_searches", label: "Job Searches", icon: Search, color: "#00c7b7", bg: "rgba(0,199,183,.1)" },
  { key: "total_jobs_found", label: "Jobs Found", icon: Briefcase, color: "#3b82f6", bg: "rgba(59,130,246,.1)" },
  { key: "total_matches", label: "Resume Matches", icon: Target, color: "#8b5cf6", bg: "rgba(139,92,246,.1)" },
  { key: "avg_ats_score", label: "Avg ATS Score", icon: Star, color: "#f59e0b", bg: "rgba(245,158,11,.1)", suffix: "%" },
  { key: "total_intel_runs", label: "Intel Runs", icon: BarChart2, color: "#ec4899", bg: "rgba(236,72,153,.1)" },
  { key: "total_profiles_found", label: "Profiles Found", icon: Users, color: "#10b981", bg: "rgba(16,185,129,.1)" },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: dashboardApi.getStats,
    refetchInterval: 30_000,
  });

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title">Dashboard</h1>
        <p className="tiq-page-sub">Your TalentIQ activity at a glance</p>
      </div>

      {/* STATS */}
      <div className="tiq-stats-grid">
        {STAT_CARDS.map(({ key, label, icon: Icon, color, bg, suffix }) => (
          <div key={key} className="tiq-stat-card">
            <div className="tiq-stat-icon" style={{ background: bg }}>
              <Icon size={18} color={color} />
            </div>
            <div className="tiq-stat-label">{label}</div>
            <div className="tiq-stat-value">
              {isLoading ? "—" : (
                (stats?.[key as keyof typeof stats] ?? 0) + (suffix || "")
              )}
            </div>
          </div>
        ))}
      </div>

      {/* QUICK ACTIONS */}
      <div className="tiq-grid-3 tiq-mb-6">
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
            icon: <BarChart2 size={20} color="#8b5cf6" />,
            title: "Run market analysis",
            desc: "Analyse skill demand, salary trends, and hiring patterns across industries.",
            color: "#8b5cf6",
            bg: "rgba(139,92,246,.08)",
          },
          {
            to: "/app/linklens",
            icon: <Users size={20} color="#f59e0b" />,
            title: "Find candidates",
            desc: "Search LinkedIn at scale, extract profiles, and export to spreadsheet.",
            color: "#f59e0b",
            bg: "rgba(245,158,11,.08)",
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

      {/* RECENT ACTIVITY */}
      
  );
}
