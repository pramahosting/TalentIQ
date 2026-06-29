import { Link } from "react-router-dom";
import {
  Search, BarChart2, Users, Zap, Shield, Download,
  BrainCircuit, Briefcase, ArrowRight, CheckCircle,
  Globe, Database, Star, TrendingUp, Mail, Twitter, Linkedin,
} from "lucide-react";

const MODULES = [
  {
    icon: Search, color: "#00c7b7", bg: "rgba(0,199,183,.12)",
    name: "JobHunter", route: "/app/jobhunt",
    tagline: "AI-powered job search & resume matching",
    desc: "Upload your resume, set your criteria, and let AI scrape live jobs, score your ATS fit, and draft personalised cover letters — ready to apply in minutes.",
    features: ["Live job scraping via Adzuna API", "ATS resume scoring 0–100%", "AI cover letter generation", "One-click Excel export"],
  },
  {
    icon: BarChart2, color: "#8b5cf6", bg: "rgba(139,92,246,.12)",
    name: "MarketIntel", route: "/app/jobintel",
    tagline: "Job market intelligence & salary analytics",
    desc: "Turn hundreds of job postings into market signals. Track skill demand, salary trends, hiring patterns, and domain breakdowns in one analytics dashboard.",
    features: ["Skill & tool demand ranking", "Salary range extraction", "Experience level breakdown", "Domain & company-type split"],
  },
  {
    icon: Users, color: "#f59e0b", bg: "rgba(245,158,11,.10)",
    name: "LinkExplore", route: "/app/linklens",
    tagline: "LinkedIn candidate search at scale",
    desc: "Search LinkedIn at scale. Find candidates by title, location, and skills, extract structured profiles, guess contact emails, and export to Excel.",
    features: ["Playwright-powered LinkedIn scraping", "Structured profile extraction", "Email pattern guessing", "Bulk candidate export"],
  },
  {
    icon: BrainCircuit, color: "#06b6d4", bg: "rgba(6,182,212,.10)",
    name: "CVAnalysis", route: "/app/cvintel",
    tagline: "ATS resume analyser & gap finder",
    desc: "Score any resume against a job description instantly. Get matched skills, missing skills, ATS formatting warnings, and AI-powered improvement suggestions.",
    features: ["Instant ATS keyword scoring", "Matched vs missing skills", "AI improvement suggestions", "ATS formatting checker"],
  },
  {
    icon: Briefcase, color: "#10b981", bg: "rgba(16,185,129,.10)",
    name: "CandidateLens", route: "/app/joblens",
    tagline: "AI recruitment engine & video interviews",
    desc: "Upload a JD and multiple CVs. AI ranks candidates by ATS score, generates tailored interview questions, and runs video interviews with emotion analysis.",
    features: ["Multi-CV batch scoring", "AI interview question generation", "Webcam video interviews", "Emotion analysis & Excel export"],
  },
];

const STATS = [
  { value: "5", label: "AI Modules", icon: Zap },
  { value: "100%", label: "Data Ownership", icon: Database },
  { value: "∞", label: "Searches Saved", icon: Globe },
  { value: "AI", label: "Groq LLM Powered", icon: Star },
];

const WHY = [
  { icon: Shield, color: "#00c7b7", title: "Every click saved", body: "Every search, match, and profile is persisted to your PostgreSQL database — your data compounds over time." },
  { icon: Download, color: "#8b5cf6", title: "Export anywhere", body: "Download job matches, market reports, and candidate lists as Excel spreadsheets at any point." },
  { icon: TrendingUp, color: "#f59e0b", title: "Grows with you", body: "Start with job hunting. Add market intelligence. Build a recruiting pipeline. Each module is independent and composable." },
  { icon: Zap, color: "#10b981", title: "LangChain under the hood", body: "Each module is a composable LangChain agent — easy to extend, chain, and deploy for your own workflow." },
  { icon: Globe, color: "#06b6d4", title: "No vendor lock-in", body: "Self-hosted, open architecture. Swap any LLM, API, or database. Your keys, your data, your infrastructure." },
  { icon: Database, color: "#a855f7", title: "One platform, five tools", body: "Stop juggling five different SaaS products. TalentIQ unifies job search, market research, and recruiting in one place." },
];

export default function LandingPage() {
  return (
    <div style={{ background: "#060811", color: "white", minHeight: "100vh", fontFamily: "var(--font-sans, system-ui)" }}>

      {/* ── NAV ── */}
      <nav style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "0 48px", height: 64,
        borderBottom: "1px solid rgba(255,255,255,.06)",
        background: "rgba(6,8,17,.85)", backdropFilter: "blur(12px)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.5px" }}>
          TalentIQ <span style={{ color: "rgba(255,255,255,.25)", fontWeight: 300 }}>Platform</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {MODULES.map(m => (
            <Link key={m.name} to={m.route} style={{ fontSize: 12, color: "rgba(255,255,255,.45)", padding: "6px 10px", borderRadius: 6, textDecoration: "none", transition: "color .2s" }}
              onMouseEnter={e => (e.currentTarget.style.color = "white")}
              onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,.45)")}>
              {m.name}
            </Link>
          ))}
          <div style={{ width: 1, height: 20, background: "rgba(255,255,255,.1)", margin: "0 4px" }} />
          <Link to="/login" style={{ fontSize: 13, color: "rgba(255,255,255,.6)", padding: "7px 14px", borderRadius: 8, textDecoration: "none" }}>Sign in</Link>
          <Link to="/register" style={{
            fontSize: 13, fontWeight: 600, padding: "8px 18px", borderRadius: 8,
            background: "linear-gradient(135deg,#00c7b7,#0891b2)",
            color: "white", textDecoration: "none",
          }}>Get started →</Link>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section style={{ textAlign: "center", padding: "100px 24px 80px", maxWidth: 860, margin: "0 auto" }}>
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 24,
          padding: "6px 16px", borderRadius: 20, border: "1px solid rgba(0,199,183,.25)",
          background: "rgba(0,199,183,.08)", fontSize: 12, fontWeight: 600, color: "#00c7b7",
          letterSpacing: ".3px",
        }}>
          <Zap size={11} /> AI-Powered Recruitment Platform
        </div>

        <h1 style={{ fontSize: 64, fontWeight: 900, lineHeight: 1.05, letterSpacing: "-2px", marginBottom: 24 }}>
          The full-stack platform<br />
          for <span style={{
            background: "linear-gradient(135deg,#00c7b7,#8b5cf6)",
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
          }}>intelligent hiring</span>
        </h1>

        <p style={{ fontSize: 19, color: "rgba(255,255,255,.5)", lineHeight: 1.7, marginBottom: 40, maxWidth: 640, margin: "0 auto 40px" }}>
          Five AI agents. One platform. Search smarter jobs, decode market intelligence,
          find LinkedIn candidates, analyse CVs, and run AI-powered recruiting — all saved to your database.
        </p>

        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          <Link to="/register" style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "14px 32px", borderRadius: 10, fontWeight: 700, fontSize: 15,
            background: "linear-gradient(135deg,#00c7b7,#0891b2)", color: "white",
            textDecoration: "none", boxShadow: "0 0 32px rgba(0,199,183,.3)",
          }}>
            Start free <ArrowRight size={16} />
          </Link>
          <Link to="/login" style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "14px 32px", borderRadius: 10, fontWeight: 600, fontSize: 15,
            border: "1px solid rgba(255,255,255,.12)", color: "rgba(255,255,255,.7)",
            textDecoration: "none", background: "rgba(255,255,255,.03)",
          }}>
            Sign in
          </Link>
        </div>
      </section>

      {/* ── STATS BAR ── */}
      <section style={{
        maxWidth: 900, margin: "0 auto 80px",
        display: "grid", gridTemplateColumns: "repeat(4,1fr)",
        border: "1px solid rgba(255,255,255,.07)", borderRadius: 16,
        overflow: "hidden", background: "rgba(255,255,255,.02)",
      }}>
        {STATS.map(({ value, label, icon: Icon }, i) => (
          <div key={label} style={{
            padding: "28px 24px", textAlign: "center",
            borderRight: i < 3 ? "1px solid rgba(255,255,255,.07)" : "none",
          }}>
            <Icon size={20} color="#00c7b7" style={{ margin: "0 auto 10px" }} />
            <div style={{ fontSize: 32, fontWeight: 900, letterSpacing: "-1px" }}>{value}</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,.35)", marginTop: 4, textTransform: "uppercase", letterSpacing: ".5px" }}>{label}</div>
          </div>
        ))}
      </section>

      {/* ── MODULES ── */}
      <section style={{ maxWidth: 1200, margin: "0 auto 100px", padding: "0 24px" }}>
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "2px", textTransform: "uppercase", color: "rgba(255,255,255,.25)", marginBottom: 12 }}>
            FIVE SPECIALISED MODULES
          </div>
          <h2 style={{ fontSize: 40, fontWeight: 800, letterSpacing: "-1px", marginBottom: 16 }}>
            Every tool you need to hire smarter
          </h2>
          <p style={{ fontSize: 16, color: "rgba(255,255,255,.4)", maxWidth: 560, margin: "0 auto" }}>
            Each module is an independent AI agent. Use one or all five — they share the same database so your data compounds.
          </p>
        </div>

        {MODULES.map((m, i) => {
          const Icon = m.icon;
          const isEven = i % 2 === 0;
          return (
            <div key={m.name} style={{
              display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48,
              marginBottom: 72, alignItems: "center",
              direction: isEven ? "ltr" : "rtl",
            }}>
              <div style={{ direction: "ltr" }}>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 16, padding: "8px 16px", borderRadius: 20, background: m.bg, border: `1px solid ${m.color}30` }}>
                  <Icon size={16} color={m.color} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: m.color }}>{m.name}</span>
                </div>
                <h3 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-.5px", marginBottom: 12, lineHeight: 1.2 }}>{m.tagline}</h3>
                <p style={{ fontSize: 15, color: "rgba(255,255,255,.45)", lineHeight: 1.8, marginBottom: 24 }}>{m.desc}</p>
                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 28px" }}>
                  {m.features.map(f => (
                    <li key={f} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, fontSize: 14, color: "rgba(255,255,255,.65)" }}>
                      <CheckCircle size={14} color={m.color} style={{ flexShrink: 0 }} />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link to="/register" style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "10px 22px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  background: m.bg, border: `1px solid ${m.color}40`,
                  color: m.color, textDecoration: "none",
                }}>
                  Try {m.name} <ArrowRight size={13} />
                </Link>
              </div>

              {/* Module visual card */}
              <div style={{ direction: "ltr" }}>
                <div style={{
                  background: "rgba(255,255,255,.02)", border: `1px solid ${m.color}20`,
                  borderRadius: 20, padding: 32, boxShadow: `0 0 60px ${m.color}10`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: m.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Icon size={22} color={m.color} />
                    </div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700 }}>{m.name}</div>
                      <div style={{ fontSize: 12, color: "rgba(255,255,255,.3)" }}>AI Module</div>
                    </div>
                    <div style={{ marginLeft: "auto", padding: "4px 10px", borderRadius: 20, background: m.bg, fontSize: 11, color: m.color, fontWeight: 600 }}>Active</div>
                  </div>
                  {m.features.map((f, fi) => (
                    <div key={f} style={{
                      display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                      background: fi % 2 === 0 ? "rgba(255,255,255,.02)" : "transparent",
                      borderRadius: 8, marginBottom: 4, fontSize: 13, color: "rgba(255,255,255,.5)",
                    }}>
                      <div style={{ width: 6, height: 6, borderRadius: "50%", background: m.color, flexShrink: 0 }} />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </section>

      {/* ── WHY TALENTIQ ── */}
      <section style={{ background: "rgba(255,255,255,.01)", borderTop: "1px solid rgba(255,255,255,.05)", borderBottom: "1px solid rgba(255,255,255,.05)", padding: "80px 24px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: 56 }}>
            <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-.5px", marginBottom: 12 }}>Why TalentIQ?</h2>
            <p style={{ fontSize: 15, color: "rgba(255,255,255,.4)" }}>Built for teams that want AI-powered hiring without the SaaS sprawl.</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 24 }}>
            {WHY.map(({ icon: Icon, color, title, body }) => (
              <div key={title} style={{ padding: 28, background: "rgba(255,255,255,.02)", borderRadius: 14, border: "1px solid rgba(255,255,255,.06)" }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: `${color}18`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
                  <Icon size={18} color={color} />
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{title}</div>
                <div style={{ fontSize: 13, color: "rgba(255,255,255,.38)", lineHeight: 1.7 }}>{body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ textAlign: "center", padding: "100px 24px" }}>
        <h2 style={{ fontSize: 48, fontWeight: 900, letterSpacing: "-1.5px", marginBottom: 16 }}>
          Ready to hire smarter?
        </h2>
        <p style={{ fontSize: 17, color: "rgba(255,255,255,.4)", marginBottom: 40 }}>
          Free to start. All five modules included. Your data stays yours.
        </p>
        <Link to="/register" style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "16px 40px", borderRadius: 12, fontWeight: 700, fontSize: 16,
          background: "linear-gradient(135deg,#00c7b7,#0891b2)", color: "white",
          textDecoration: "none", boxShadow: "0 0 40px rgba(0,199,183,.35)",
        }}>
          Create free account <ArrowRight size={17} />
        </Link>
      </section>

      {/* ── FOOTER ── */}
      <footer style={{ borderTop: "1px solid rgba(255,255,255,.06)", padding: "48px 48px 32px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 40, marginBottom: 48 }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 12 }}>TalentIQ</div>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,.35)", lineHeight: 1.7, maxWidth: 260 }}>
                The full-stack AI platform for intelligent hiring. Five modules, one database, zero vendor lock-in.
              </p>
              <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                {[Twitter, Linkedin, Mail].map((Icon, i) => (
                  <div key={i} style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid rgba(255,255,255,.1)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                    <Icon size={15} color="rgba(255,255,255,.4)" />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "rgba(255,255,255,.25)", marginBottom: 16 }}>Modules</div>
              {MODULES.map(m => (
                <Link key={m.name} to={m.route} style={{ display: "block", fontSize: 13, color: "rgba(255,255,255,.45)", textDecoration: "none", marginBottom: 10 }}
                  onMouseEnter={e => (e.currentTarget.style.color = "white")}
                  onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,.45)")}>
                  {m.name}
                </Link>
              ))}
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "rgba(255,255,255,.25)", marginBottom: 16 }}>Platform</div>
              {[["Sign in", "/login"], ["Register", "/register"], ["Dashboard", "/app"], ["Settings", "/app/settings"]].map(([label, to]) => (
                <Link key={label} to={to} style={{ display: "block", fontSize: 13, color: "rgba(255,255,255,.45)", textDecoration: "none", marginBottom: 10 }}
                  onMouseEnter={e => (e.currentTarget.style.color = "white")}
                  onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,.45)")}>
                  {label}
                </Link>
              ))}
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "rgba(255,255,255,.25)", marginBottom: 16 }}>Tech Stack</div>
              {["React + TypeScript", "FastAPI (Python)", "PostgreSQL (Neon)", "LangChain + Groq", "Playwright"].map(t => (
                <div key={t} style={{ fontSize: 13, color: "rgba(255,255,255,.35)", marginBottom: 10 }}>{t}</div>
              ))}
            </div>
          </div>

          <div style={{ borderTop: "1px solid rgba(255,255,255,.06)", paddingTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,.2)" }}>© {new Date().getFullYear()} TalentIQ Platform. All rights reserved.</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,.2)" }}>Built with LangChain · Groq · Playwright · Neon</div>
          </div>
        </div>
      </footer>
    </div>
  );
}
