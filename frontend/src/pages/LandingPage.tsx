import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import {
  Search, BarChart2, Users, Zap, Shield, Download,
  BrainCircuit, Briefcase, ArrowRight, CheckCircle,
  Globe, Database, Star, TrendingUp, Mail, Twitter, Linkedin, FileEdit,
} from "lucide-react";

const MODULES = [
  {
    icon: Search, color: "#0ea5e9", bg: "rgba(14,165,233,.12)",
    name: "JobHunter", route: "/app/jobhunt",
    tagline: "AI-powered job search & resume matching",
    desc: "Upload your resume, set your criteria, and let AI scrape live jobs, score your ATS fit, and draft personalised cover letters.",
    features: ["Live job scraping via Adzuna API", "ATS resume scoring 0–100%", "AI cover letter generation", "One-click Excel export"],
  },
  {
    icon: BarChart2, color: "#a78bfa", bg: "rgba(167,139,250,.12)",
    name: "MarketIntel", route: "/app/jobintel",
    tagline: "Job market intelligence & salary analytics",
    desc: "Turn hundreds of job postings into market signals. Track skill demand, salary trends, and hiring patterns.",
    features: ["Skill & tool demand ranking", "Salary range extraction", "Experience level breakdown", "Domain & company-type split"],
  },
  {
    icon: Users, color: "#34d399", bg: "rgba(52,211,153,.10)",
    name: "LinkExplore", route: "/app/linklens",
    tagline: "LinkedIn candidate search at scale",
    desc: "Search LinkedIn at scale. Find candidates by title, location, and skills, extract structured profiles and contact details.",
    features: ["Playwright-powered LinkedIn scraping", "Structured profile extraction", "Email pattern guessing", "Bulk candidate export"],
  },
  {
    icon: BrainCircuit, color: "#f472b6", bg: "rgba(244,114,182,.10)",
    name: "CVAnalysis", route: "/app/cvintel",
    tagline: "ATS resume analyser & gap finder",
    desc: "Score any resume against a job description instantly. Get matched skills, missing skills, and AI-powered improvement suggestions.",
    features: ["Instant ATS keyword scoring", "Matched vs missing skills", "AI improvement suggestions", "ATS formatting checker"],
  },
  {
    icon: FileEdit, color: "#0d9488", bg: "rgba(13,148,136,.10)",
    name: "JD Creator", route: "/app/jdcreator",
    tagline: "AI-generated job descriptions in seconds",
    desc: "Enter a role title, required skills, experience, and education — get a formal, professionally-written Position Description, ready to download as Word.",
    features: ["AI-written purpose & responsibilities", "Company branding from your profile", "One-click Word (.docx) download", "Saved JD history"],
  },
  {
    icon: Briefcase, color: "#fb923c", bg: "rgba(251,146,60,.10)",
    name: "CandidateLens", route: "/app/joblens",
    tagline: "AI recruitment engine & video interviews",
    desc: "Upload a JD and multiple CVs. AI ranks candidates by ATS score, generates interview questions, and runs video interviews.",
    features: ["Multi-CV batch scoring", "AI interview question generation", "Webcam video interviews", "Emotion analysis & Excel export"],
  },
];

const INDIVIDUAL_NAMES = ["CVAnalysis", "JobHunter"];
const BUSINESS_NAMES = ["MarketIntel", "LinkExplore", "JD Creator", "CandidateLens"];

const STATS = [
  { value: "6", label: "AI Modules" },
  { value: "100%", label: "Data Ownership" },
  { value: "∞", label: "Searches Saved" },
  { value: "AI", label: "LLM Powered" },
];

function NavDropdown({ label, names }: { label: string; names: string[] }) {
  const [open, setOpen] = useState(false);
  const items = MODULES.filter(m => names.includes(m.name));
  return (
    <div style={{ position: "relative" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}>
      <button style={{
        fontSize: 13, color: "#64748b", padding: "6px 10px", borderRadius: 6,
        fontWeight: 700, background: open ? "#f8fafc" : "transparent",
        border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
      }}>
        {label}
        <span style={{ fontSize: 9, transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }}>▾</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          background: "#ffffff", borderRadius: 10, border: "1px solid #f1f5f9",
          boxShadow: "0 12px 32px rgba(0,0,0,.12)", padding: 6, minWidth: 180, zIndex: 200,
        }}>
          {items.map(m => (
            <Link key={m.name} to={m.route}
              style={{ display: "block", fontSize: 13, color: "#374151", padding: "8px 10px", borderRadius: 6, textDecoration: "none", fontWeight: 500 }}
              onMouseEnter={e => { e.currentTarget.style.background = "#f8fafc"; e.currentTarget.style.color = "#0f172a"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#374151"; }}>
              {m.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function ModuleCard({ m, isEven }: { m: typeof MODULES[0]; isEven: boolean }) {
  const Icon = m.icon;
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "1fr 1fr", gap: 64,
      marginBottom: 80, alignItems: "center",
      direction: isEven ? "ltr" : "rtl",
    }}>
      <div style={{ direction: "ltr" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 16, padding: "6px 14px", borderRadius: 20, background: m.bg, border: `1px solid ${m.color}30` }}>
          <Icon size={14} color={m.color} />
          <span style={{ fontSize: 12, fontWeight: 700, color: m.color, textTransform: "uppercase", letterSpacing: ".5px" }}>{m.name}</span>
        </div>
        <h3 style={{ fontSize: "clamp(22px,3vw,32px)", fontWeight: 800, letterSpacing: "-.5px", marginBottom: 14, color: "#0f172a", lineHeight: 1.2 }}>{m.tagline}</h3>
        <p style={{ fontSize: 16, color: "#64748b", lineHeight: 1.8, marginBottom: 28 }}>{m.desc}</p>
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 32px" }}>
          {m.features.map(f => (
            <li key={f} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, fontSize: 14, color: "#374151" }}>
              <CheckCircle size={15} color={m.color} style={{ flexShrink: 0 }} /> {f}
            </li>
          ))}
        </ul>
        <Link to="/register" style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "10px 22px", borderRadius: 10, fontSize: 13, fontWeight: 600,
          background: m.bg, border: `1.5px solid ${m.color}50`,
          color: m.color, textDecoration: "none",
        }}>
          Try {m.name} <ArrowRight size={13} />
        </Link>
      </div>

      {/* Visual card */}
      <div style={{ direction: "ltr" }}>
        <div style={{
          background: "white", borderRadius: 20, padding: 28,
          border: "1.5px solid #f1f5f9",
          boxShadow: "0 8px 40px rgba(0,0,0,.08)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24, paddingBottom: 20, borderBottom: "1px solid #f1f5f9" }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: m.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon size={22} color={m.color} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a" }}>{m.name}</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>AI Module</div>
            </div>
            <div style={{ marginLeft: "auto", padding: "4px 12px", borderRadius: 20, background: "#f0fdf4", border: "1px solid #bbf7d0", fontSize: 11, color: "#16a34a", fontWeight: 700 }}>● Active</div>
          </div>
          {m.features.map((f, fi) => (
            <div key={f} style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
              background: fi % 2 === 0 ? "#f8fafc" : "transparent",
              borderRadius: 8, marginBottom: 4, fontSize: 13, color: "#475569",
            }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: m.color, flexShrink: 0 }} />
              {f}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModuleGroupHeading({ label, sub, color }: { label: string; sub: string; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "0 0 40px" }}>
      <div style={{ fontSize: "clamp(20px,2.6vw,28px)", fontWeight: 800, letterSpacing: "-.5px", color: "#0f172a" }}>{label}</div>
      <div style={{ fontSize: 12, fontWeight: 700, color, background: `${color}15`, border: `1px solid ${color}30`, padding: "4px 12px", borderRadius: 20, textTransform: "uppercase", letterSpacing: ".05em" }}>
        {sub}
      </div>
      <div style={{ flex: 1, height: 1, background: "#f1f5f9" }} />
    </div>
  );
}

export default function LandingPage() {
  const { user } = useAuth();
  const isLoggedIn = !!user;
  return (
    <div style={{ background: "#ffffff", color: "#0f172a", fontFamily: "'Inter',system-ui,sans-serif", overflowX: "hidden" }}>

      {/* ── NAV ── */}
      <nav style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "0 5%", height: 68,
        background: "rgba(255,255,255,0.92)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid #f1f5f9",
        position: "sticky", top: 0, zIndex: 100,
        boxShadow: "0 1px 3px rgba(0,0,0,.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg,#0ea5e9,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Zap size={18} color="white" fill="white" />
          </div>
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.5px", color: "#0f172a" }}>
            TalentIQ
          </span>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <NavDropdown label="Agents for Individual" names={INDIVIDUAL_NAMES} />
          <NavDropdown label="Agents for Business" names={BUSINESS_NAMES} />
          <div style={{ width: 1, height: 20, background: "#e2e8f0", margin: "0 6px" }} />
          {isLoggedIn ? (
            <Link to="/app"
              style={{ fontSize: 13, fontWeight: 600, padding: "8px 18px", borderRadius: 8, background: "linear-gradient(135deg,#0ea5e9,#6366f1)", color: "white", textDecoration: "none", boxShadow: "0 2px 8px rgba(14,165,233,.35)" }}>
              Go to Dashboard →
            </Link>
          ) : (
            <>
              <Link to="/login"
                style={{ fontSize: 13, color: "#374151", padding: "7px 16px", borderRadius: 8, textDecoration: "none", fontWeight: 500, border: "1px solid #e2e8f0" }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f8fafc")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                Sign in
              </Link>
              <Link to="/register"
                style={{ fontSize: 13, fontWeight: 600, padding: "8px 18px", borderRadius: 8, background: "linear-gradient(135deg,#0ea5e9,#6366f1)", color: "white", textDecoration: "none", boxShadow: "0 2px 8px rgba(14,165,233,.35)" }}>
                Get started
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* ── HERO ── */}
      <section style={{
        background: "linear-gradient(160deg, #f0f9ff 0%, #f5f3ff 50%, #fff7ed 100%)",
        padding: "96px 5% 80px", textAlign: "center",
        borderBottom: "1px solid #f1f5f9",
      }}>
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 24,
          padding: "6px 16px", borderRadius: 20,
          background: "white", border: "1px solid #e0f2fe",
          fontSize: 12, fontWeight: 600, color: "#0284c7",
          boxShadow: "0 1px 4px rgba(14,165,233,.15)",
        }}>
          <Zap size={11} fill="#0284c7" color="#0284c7" /> AI-Powered Recruitment Platform
        </div>

        <h1 style={{ fontSize: "clamp(36px,6vw,68px)", fontWeight: 900, lineHeight: 1.06, letterSpacing: "-2px", marginBottom: 24, color: "#0f172a" }}>
          Hire smarter with<br />
          <span style={{ background: "linear-gradient(135deg,#0ea5e9,#6366f1,#a855f7)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            six AI agents
          </span>
        </h1>

        <p style={{ fontSize: 19, color: "#475569", lineHeight: 1.7, marginBottom: 40, maxWidth: 600, margin: "0 auto 40px" }}>
          One platform for job seekers and recruiters. Search jobs, decode market trends,
          find LinkedIn candidates, analyse CVs, and run AI-powered interviews.
        </p>

        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          {isLoggedIn ? (
            <Link to="/app" style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "14px 32px", borderRadius: 12, fontWeight: 700, fontSize: 15,
              background: "linear-gradient(135deg,#0ea5e9,#6366f1)", color: "white",
              textDecoration: "none", boxShadow: "0 4px 16px rgba(14,165,233,.4)",
            }}>
              Go to Dashboard <ArrowRight size={16} />
            </Link>
          ) : (
            <>
              <Link to="/register" style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "14px 32px", borderRadius: 12, fontWeight: 700, fontSize: 15,
                background: "linear-gradient(135deg,#0ea5e9,#6366f1)", color: "white",
                textDecoration: "none", boxShadow: "0 4px 16px rgba(14,165,233,.4)",
              }}>
                Start free <ArrowRight size={16} />
              </Link>
              <Link to="/login" style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "14px 32px", borderRadius: 12, fontWeight: 600, fontSize: 15,
                border: "1.5px solid #e2e8f0", color: "#374151",
                textDecoration: "none", background: "white",
                boxShadow: "0 1px 4px rgba(0,0,0,.06)",
              }}>
                Sign in
              </Link>
            </>
          )}
        </div>

        {/* STATS */}
        <div style={{ display: "flex", justifyContent: "center", gap: 48, marginTop: 64, flexWrap: "wrap" }}>
          {STATS.map(({ value, label }) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 32, fontWeight: 900, color: "#0f172a", letterSpacing: "-1px" }}>{value}</div>
              <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2, textTransform: "uppercase", letterSpacing: "1px", fontWeight: 600 }}>{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── MODULES ── */}
      <section style={{ padding: "96px 5%", maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 64 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "2px", textTransform: "uppercase", color: "#94a3b8", marginBottom: 12 }}>
            SIX SPECIALISED MODULES
          </div>
          <h2 style={{ fontSize: "clamp(28px,4vw,44px)", fontWeight: 800, letterSpacing: "-1px", color: "#0f172a", marginBottom: 16 }}>
            Every tool you need to hire smarter
          </h2>
          <p style={{ fontSize: 17, color: "#64748b", maxWidth: 560, margin: "0 auto" }}>
            Each module is an independent AI agent, grouped below by <strong>Individual</strong> (personal job search) and <strong>Business</strong> (recruiting & talent ops) — they share the same database so your data compounds.
          </p>
        </div>

        <ModuleGroupHeading label="Individual" sub="Personal Job Search" color="#0ea5e9" />
        {MODULES.filter(m => INDIVIDUAL_NAMES.includes(m.name))
          .sort((a, b) => INDIVIDUAL_NAMES.indexOf(a.name) - INDIVIDUAL_NAMES.indexOf(b.name))
          .map((m, i) => <ModuleCard key={m.name} m={m} isEven={i % 2 === 0} />)}

        <ModuleGroupHeading label="Business" sub="Recruiting & Talent Ops" color="#fb923c" />
        {MODULES.filter(m => BUSINESS_NAMES.includes(m.name))
          .sort((a, b) => BUSINESS_NAMES.indexOf(a.name) - BUSINESS_NAMES.indexOf(b.name))
          .map((m, i) => <ModuleCard key={m.name} m={m} isEven={i % 2 === 0} />)}
      </section>

      {/* ── WHY ── */}
      <section style={{ background: "#f8fafc", borderTop: "1px solid #f1f5f9", borderBottom: "1px solid #f1f5f9", padding: "80px 5%" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: 56 }}>
            <h2 style={{ fontSize: "clamp(26px,4vw,40px)", fontWeight: 800, letterSpacing: "-.5px", color: "#0f172a", marginBottom: 12 }}>Why TalentIQ?</h2>
            <p style={{ fontSize: 16, color: "#64748b" }}>Built for teams that want AI-powered hiring without the SaaS sprawl.</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }}>
            {[
              { icon: Shield, color: "#0ea5e9", title: "Every click saved", body: "Every search, match, and profile is persisted to PostgreSQL — your data compounds over time." },
              { icon: Download, color: "#6366f1", title: "Export anywhere", body: "Download job matches, market reports, and candidate lists as Excel spreadsheets at any point." },
              { icon: TrendingUp, color: "#f59e0b", title: "Grows with you", body: "Start with job hunting. Add market intelligence. Build a recruiting pipeline. Each module is composable." },
              { icon: Zap, color: "#34d399", title: "LangChain + Groq", body: "Each module is a composable LangChain agent — easy to extend, chain, and deploy for your workflow." },
              { icon: Globe, color: "#f472b6", title: "No vendor lock-in", body: "Self-hosted, open architecture. Swap any LLM, API, or database. Your keys, your data." },
              { icon: Database, color: "#fb923c", title: "One platform, six tools", body: "Stop juggling six SaaS products. TalentIQ unifies job search, market research, and recruiting." },
            ].map(({ icon: Icon, color, title, body }) => (
              <div key={title} style={{
                padding: 28, background: "white", borderRadius: 16,
                border: "1.5px solid #f1f5f9",
                boxShadow: "0 2px 8px rgba(0,0,0,.04)",
              }}>
                <div style={{ width: 42, height: 42, borderRadius: 12, background: `${color}15`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
                  <Icon size={20} color={color} />
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", marginBottom: 8 }}>{title}</div>
                <div style={{ fontSize: 13, color: "#64748b", lineHeight: 1.7 }}>{body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{
        background: "linear-gradient(135deg, #0ea5e9 0%, #6366f1 50%, #a855f7 100%)",
        padding: "80px 5%", textAlign: "center",
      }}>
        <h2 style={{ fontSize: "clamp(28px,5vw,52px)", fontWeight: 900, letterSpacing: "-1.5px", marginBottom: 16, color: "white" }}>
          Ready to hire smarter?
        </h2>
        <p style={{ fontSize: 18, color: "rgba(255,255,255,.8)", marginBottom: 40 }}>
          Free to start. All six modules included. Your data stays yours.
        </p>
        {isLoggedIn ? (
          <Link to="/app" style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "16px 40px", borderRadius: 12, fontWeight: 700, fontSize: 16,
            background: "white", color: "#6366f1",
            textDecoration: "none", boxShadow: "0 4px 20px rgba(0,0,0,.2)",
          }}>
            Go to Dashboard <ArrowRight size={17} />
          </Link>
        ) : (
          <Link to="/register" style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "16px 40px", borderRadius: 12, fontWeight: 700, fontSize: 16,
            background: "white", color: "#6366f1",
            textDecoration: "none", boxShadow: "0 4px 20px rgba(0,0,0,.2)",
          }}>
            Create free account <ArrowRight size={17} />
          </Link>
        )}
      </section>

      {/* ── FOOTER ── */}
      <footer style={{ background: "#0f172a", color: "white", padding: "56px 5% 32px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 40, marginBottom: 48 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, background: "linear-gradient(135deg,#0ea5e9,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Zap size={16} color="white" fill="white" />
                </div>
                <span style={{ fontSize: 16, fontWeight: 800 }}>TalentIQ</span>
              </div>
              <p style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.7, maxWidth: 240 }}>
                The full-stack AI platform for intelligent hiring. Five modules, one database, zero vendor lock-in.
              </p>
              <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                {[Twitter, Linkedin, Mail].map((Icon, i) => (
                  <div key={i} style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #1e293b", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                    <Icon size={15} color="#64748b" />
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "#475569", marginBottom: 16 }}>Modules</div>
              {MODULES.map(m => (
                <Link key={m.name} to={m.route} style={{ display: "block", fontSize: 13, color: "#64748b", textDecoration: "none", marginBottom: 10 }}
                  onMouseEnter={e => (e.currentTarget.style.color = "white")}
                  onMouseLeave={e => (e.currentTarget.style.color = "#64748b")}>
                  {m.name}
                </Link>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "#475569", marginBottom: 16 }}>Platform</div>
              {[["Sign in", "/login"], ["Register", "/register"], ["Dashboard", "/app"]].map(([label, to]) => (
                <Link key={label} to={to} style={{ display: "block", fontSize: 13, color: "#64748b", textDecoration: "none", marginBottom: 10 }}
                  onMouseEnter={e => (e.currentTarget.style.color = "white")}
                  onMouseLeave={e => (e.currentTarget.style.color = "#64748b")}>
                  {label}
                </Link>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "#475569", marginBottom: 16 }}>Tech Stack</div>
              {["React + TypeScript", "FastAPI (Python)", "PostgreSQL (Neon)", "LangChain + Groq", "Playwright"].map(t => (
                <div key={t} style={{ fontSize: 13, color: "#475569", marginBottom: 10 }}>{t}</div>
              ))}
            </div>
          </div>
          <div style={{ borderTop: "1px solid #1e293b", paddingTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 12, color: "#475569" }}>© {new Date().getFullYear()} TalentIQ Platform. All rights reserved.</div>
            <div style={{ fontSize: 12, color: "#475569" }}>Built with LangChain · Groq · Playwright · Neon</div>
          </div>
        </div>
      </footer>
    </div>
  );
}