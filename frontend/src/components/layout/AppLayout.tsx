import { Outlet, NavLink, Link } from "react-router-dom";
import {
  LayoutDashboard, Search, BarChart2, Users,
  Settings, LogOut, Shield, Database, BrainCircuit, Briefcase, Home
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

const NAV_ITEMS = [
  { to: "/app",          label: "Dashboard",    icon: LayoutDashboard, end: true  },
  { to: "/app/jobhunt",  label: "JobHunter",    icon: Search           },
  { to: "/app/jobintel", label: "MarketIntel",  icon: BarChart2        },
  { to: "/app/linklens", label: "LinkExplore",  icon: Users            },
  { to: "/app/cvintel",  label: "CVAnalysis",   icon: BrainCircuit     },
  { to: "/app/joblens",  label: "CandidateLens",icon: Briefcase        },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";

  return (
    <div className="tiq-app-shell">
      <aside className="tiq-sidebar">
        <div className="tiq-logo">
          <div className="tiq-logo-wordmark">TalentIQ</div>
          <div className="tiq-logo-sub">Platform</div>
        </div>

        <nav className="tiq-nav">
          <div className="tiq-nav-section">Workspace</div>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
              <Icon size={16} />{label}
            </NavLink>
          ))}

          <div className="tiq-nav-section">Account</div>
          <NavLink to="/app/settings"
            className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
            <Settings size={16} />Settings
          </NavLink>

          {isAdmin && (
            <>
              <div className="tiq-nav-section">Admin</div>
              <NavLink to="/app/admin-setup"
                className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
                <Shield size={16} />User Management
              </NavLink>
              <NavLink to="/app/file-manager"
                className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
                <Database size={16} />File Manager
              </NavLink>
            </>
          )}
        </nav>

        <div className="tiq-sidebar-footer">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: "50%",
              background: "rgba(0,199,183,.2)", flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13, fontWeight: 700, color: "#00c7b7",
            }}>
              {user?.name?.[0]?.toUpperCase()}
            </div>
            <div style={{ overflow: "hidden" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "white", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user?.name}
              </div>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,.35)" }}>{user?.role}</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="tiq-main">
        <div className="tiq-topbar">
          <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
            Welcome back, <strong style={{ color: "var(--text-primary)" }}>{user?.name?.split(" ")[0]}</strong>
          </div>
          {isAdmin && <span className="tiq-badge tiq-badge-violet">Admin</span>}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
            <Link to="/" style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textDecoration: "none", padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)" }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--text-primary)"; e.currentTarget.style.background = "var(--bg-secondary)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.background = "transparent"; }}>
              <Home size={12} /> Home
            </Link>
            <button onClick={logout} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: "#ef4444", padding: "5px 10px", borderRadius: 6, border: "1px solid #fecaca", background: "transparent", cursor: "pointer" }}
              onMouseEnter={e => { e.currentTarget.style.background = "#fef2f2"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
              <LogOut size={12} /> Sign out
            </button>
          </div>
        </div>
        <div className="tiq-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}