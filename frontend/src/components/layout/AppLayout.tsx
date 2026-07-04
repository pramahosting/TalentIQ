import { useState } from "react";
import { Outlet, NavLink, Link } from "react-router-dom";
import {
  LayoutDashboard, Search, BarChart2, Users,
  Settings, LogOut, Shield, Database, BrainCircuit, Briefcase, Home, FileEdit,
  ChevronDown, ChevronRight,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

const INDIVIDUAL_ITEMS = [
  { to: "/app/cvintel",  label: "CVAnalysis",   icon: BrainCircuit },
  { to: "/app/jobhunt",  label: "JobHunter",    icon: Search       },
];

const BUSINESS_ITEMS = [
  { to: "/app/jobintel", label: "MarketIntel",  icon: BarChart2    },
  { to: "/app/linklens", label: "LinkExplore",  icon: Users        },
  { to: "/app/jdcreator",label: "JD Creator",   icon: FileEdit     },
  { to: "/app/joblens",  label: "CandidateLens",icon: Briefcase    },
];

function NavGroup({ title, items, defaultOpen = true }: { title: string; items: typeof INDIVIDUAL_ITEMS; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%",
          background: "none", border: "none", cursor: "pointer", padding: "8px 16px",
          fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
          color: "rgba(255,255,255,.35)",
        }}
      >
        {title}
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </button>
      {open && items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to}
          className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
          <Icon size={16} />{label}
        </NavLink>
      ))}
    </div>
  );
}

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
          <div className="tiq-nav-section">Agents</div>
          <NavLink to="/app" end
            className={({ isActive }) => `tiq-nav-item${isActive ? " active" : ""}`}>
            <LayoutDashboard size={16} />Dashboard
          </NavLink>

          <NavGroup title="Individual" items={INDIVIDUAL_ITEMS} />
          <NavGroup title="Business" items={BUSINESS_ITEMS} />

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