import { useState, useRef, useEffect } from "react";
import { } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BrainCircuit, FileText, Target, CheckCircle, AlertTriangle,
  TrendingUp, Upload, X, Sparkles, ChevronDown, ChevronUp,
  User, MapPin, Briefcase, List,
} from "lucide-react";
import { api, cvintelApi } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { useLatestMutation } from "../hooks/useLatestMutation";

interface AnalysisResult {
  overallScore: number;
  strengths: string[];
  gaps: string[];
  suggestions: string[];
  summaryAssessment: string;
  formatWarnings: string[];
  detailedScores: Record<string, number>;
  matchedSkills: string[];
  missingSkills: string[];
  aiPowered?: boolean;
  groqModel?: string | null;
  note?: string;
  aiError?: string;
  strengthsBreakdown?: {
    essentialMatched: string[];
    technicalSkills: string[];
    businessSkills: string[];
    softSkills: string[];
    significantExperience: string[];
    certificationsDegrees: string[];
  };
  jdRequirements?: {
    roleTitle: string;
    location: string;
    company: string;
    essential: string[];
    goodToHave: string[];
    optional: string[];
    minYearsExperience: number;
    educationRequirement: string;
  };
  candidateProfile?: {
    yearsExperience: number;
    education: string;
  };
}

interface AnalyseData extends AnalysisResult {
  candidateInfo: any;
  jdInfo: any;
  sourceName: string;
}

// ── Collapsible text panel ───────────────────────────────────────────────────
function TextPanel({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: "1.5px solid var(--border)", borderRadius: 10, overflow: "hidden", marginTop: 12 }}>
      <button type="button" onClick={() => setOpen(o => !o)} style={{
        width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", background: open ? "var(--bg-secondary)" : "transparent",
        border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
        color: open ? "var(--text-primary)" : "var(--text-secondary)",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <FileText size={13} color="var(--text-muted)" />
          {label}
          {value && <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 10, background: "var(--teal-500)", color: "white", fontWeight: 700 }}>✓</span>}
        </span>
        {open ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
      </button>
      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
            style={{ width: "100%", minHeight: 160, padding: 10, fontSize: 12, fontFamily: "monospace",
              border: "1px solid var(--border)", borderRadius: 8, resize: "vertical", outline: "none",
              background: "var(--bg-tertiary)", color: "var(--text-primary)", marginTop: 8 }} />
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, textAlign: "right" }}>{value.length} chars</div>
        </div>
      )}
    </div>
  );
}

// ── Upload zone ──────────────────────────────────────────────────────────────
function UploadZone({ label, file, accept, onFile, onClear }: {
  label: string; file: File | null; accept: string;
  onFile: (f: File) => void; onClear: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  if (file) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
      background: "rgba(0,199,183,.08)", borderRadius: 10, border: "1px solid rgba(0,199,183,.2)" }}>
      <FileText size={15} color="var(--teal-500)" />
      <span style={{ fontSize: 13, fontWeight: 600, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{file.name}</span>
      <button onClick={onClear} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex" }}><X size={14} /></button>
    </div>
  );
  return (
    <div onClick={() => ref.current?.click()} style={{
      border: "2px dashed var(--border)", borderRadius: 10, padding: "18px 16px",
      textAlign: "center", cursor: "pointer", transition: "border-color .2s",
    }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--teal-500)")}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}>
      <Upload size={22} color="var(--text-muted)" style={{ margin: "0 auto 6px" }} />
      <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>PDF, DOCX, TXT</div>
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
    </div>
  );
}

// ── Score components ─────────────────────────────────────────────────────────
function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 75 ? "var(--teal-500)" : value >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 13 }}>
        <span style={{ fontWeight: 500 }}>{label.replace(/([A-Z])/g, " $1").trim()}</span>
        <span style={{ fontWeight: 700, color }}>{value}%</span>
      </div>
      <div style={{ height: 7, background: "var(--bg-tertiary)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value}%`, background: color, borderRadius: 4, transition: "width 0.6s ease" }} />
      </div>
    </div>
  );
}

function ScoreDial({ score }: { score: number }) {
  const color = score >= 75 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
  const label = score >= 75 ? "Strong Match" : score >= 50 ? "Moderate Match" : "Needs Work";
  return (
    <div style={{ textAlign: "center", padding: "16px 0" }}>
      <div style={{ fontSize: 64, fontWeight: 900, color, lineHeight: 1 }}>{score}</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>/100</div>
      <div style={{ marginTop: 8, display: "inline-block", padding: "4px 14px", borderRadius: 20, background: color + "20", color, fontWeight: 700, fontSize: 13 }}>{label}</div>
    </div>
  );
}

// ── Parse candidate info from resume text ────────────────────────────────────
function parseCandidateInfo(text: string, filename: string) {
  const emailM = text.match(/[\w.+-]+@[\w.-]+\.\w+/);
  const phoneM = text.match(/(\+?\d[\d\s\-(]{7,18}\d)/);
  const locM   = text.match(/\b(Sydney|Melbourne|Brisbane|Perth|Adelaide|Auckland|London|New York|Singapore|Mumbai|Delhi|Bangalore|Toronto|Vancouver|Dubai|Remote)\b/i);
  // Name: first non-empty line that looks like a name
  let name = "";
  for (const line of text.split("\n").slice(0, 10)) {
    const l = line.trim();
    if (l && !l.includes("@") && !l.match(/^\d/) && l.split(" ").length <= 5 && l.length > 3 && l.length < 60) {
      name = l; break;
    }
  }
  if (!name) name = filename.replace(/\.[^.]+$/, "").replace(/[-_]/g, " ");
  return {
    name,
    email: emailM?.[0] || "",
    phone: phoneM?.[0]?.trim() || "",
    location: locM?.[0] || "",
  };
}

// ── Parse JD info ────────────────────────────────────────────────────────────
function parseJDInfo(text: string, filename: string) {
  // Role: first line or line containing "role" / "position"
  let role = "";
  for (const line of text.split("\n").slice(0, 8)) {
    const l = line.trim();
    if (l && l.length > 5 && l.length < 100 && !l.toLowerCase().startsWith("about")) {
      role = l; break;
    }
  }
  if (!role) role = filename.replace(/\.[^.]+$/, "").replace(/[-_]/g, " ");

  // Key requirements: bullet points or lines starting with common patterns
  const reqs: string[] = [];
  const lines = text.split("\n");
  let inReqs = false;
  for (const line of lines) {
    const l = line.trim();
    if (/requirement|qualification|what you.ll need|must have|key skills/i.test(l)) { inReqs = true; continue; }
    if (inReqs && l && (l.startsWith("•") || l.startsWith("-") || l.startsWith("*") || /^\d+\./.test(l))) {
      reqs.push(l.replace(/^[•\-*\d.]+\s*/, "").trim());
      if (reqs.length >= 5) break;
    }
    if (inReqs && !l) continue;
    if (inReqs && reqs.length > 0 && l.length > 80 && !l.startsWith("•")) break;
  }

  return { role, requirements: reqs };
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function CVAnalysisPage() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [extractedResumeText, setExtractedResumeText] = useState("");

  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);

  const [formError, setFormError] = useState("");
  const qc = useQueryClient();

  // History now lives server-side (survives browsers/devices/refresh),
  // matching every other module. Normalize the backend shape into the
  // same {id, name, score, result, ts} shape the render logic below uses.
  const { data: historyRaw = [] } = useQuery({
    queryKey: ["cvintel-history"],
    queryFn: cvintelApi.listHistory,
  });
  const history: Array<{ id: number; name: string; jd: string; score: number; result: AnalyseData; ts: string }> =
    historyRaw.map((r: any) => ({
      id: r.id,
      name: r.sourceName || "Resume",
      jd: r.jdInfo?.role || "",
      score: r.overallScore,
      result: { ...r.result, candidateInfo: r.candidateInfo, jdInfo: r.jdInfo, sourceName: r.sourceName },
      ts: r.createdAt ? new Date(r.createdAt).toLocaleString() : "",
    }));

  // null = "show the live/latest analysis"; set when the user manually
  // browses a past entry from the History strip below.
  const [viewingHistId, setViewingHistId] = useState<number | null>(null);
  // The mutation cache (liveResult, below) is deliberately independent of
  // the history list — it survives navigation and doesn't know or care
  // whether its corresponding history record still exists in the DB. That
  // means deleting the history entry for the result currently on screen
  // does nothing to the display unless we track that dismissal ourselves.
  const [liveResultDismissed, setLiveResultDismissed] = useState(false);

  const analyseMut = useMutation({
    mutationKey: ["cvintel-analyze"],
    mutationFn: async (): Promise<AnalyseData> => {
      const form = new FormData();
      form.append("job_description", jdText);
      form.append("resume_text", resumeText);
      if (resumeFile) form.append("file", resumeFile);
      if (jdFile)     form.append("jd_file", jdFile);
      const res = await api.post("/api/cvintel/analyze", form, {
        headers: { "Content-Type": "multipart/form-data" },
        // Two sequential extraction calls happen server-side (JD then
        // resume), each potentially trying Ollama before falling back to
        // Groq — the default 60s timeout doesn't leave enough margin for
        // that worst case.
        timeout: 180_000,
      });
      // Bundle the derived candidate/JD summary info together with the API
      // result so it's all captured atomically in the mutation cache — this
      // is what lets it survive the user navigating to another agent page
      // and back, since it no longer depends on local component state.
      const rText = resumeText || extractedResumeText;
      return {
        ...res.data,
        candidateInfo: parseCandidateInfo(rText, resumeFile?.name || "Resume"),
        jdInfo: parseJDInfo(jdText, jdFile?.name || "Job Description"),
        sourceName: resumeFile?.name || "Resume",
      };
    },
  });

  // Reads the same mutation from the shared, app-level mutation cache —
  // this is what actually survives navigating to another agent page while
  // analysis is still running (the request itself keeps going regardless;
  // this just lets any mount of this page find the result again).
  const genState = useLatestMutation<AnalyseData>(["cvintel-analyze"]);
  const liveResult = genState.status === "success" ? genState.data ?? null : null;
  const displayResult: AnalyseData | null = viewingHistId
    ? history.find(h => h.id === viewingHistId)?.result ?? null
    : (liveResultDismissed ? null : liveResult);

  // Save each newly-completed analysis to the backend. Driven off the
  // shared cache (not the mutation's own onSuccess) so it reliably fires
  // even if this page was unmounted when the request actually finished.
  const lastSavedSubmittedAt = useRef<number | null>(null);
  useEffect(() => {
    if (genState.status === "success" && genState.data && genState.submittedAt
        && genState.submittedAt !== lastSavedSubmittedAt.current) {
      lastSavedSubmittedAt.current = genState.submittedAt;
      const data = genState.data;
      const { candidateInfo, jdInfo, sourceName, ...bareResult } = data;
      cvintelApi.saveHistory({
        source_name: sourceName || "Resume",
        overall_score: data.overallScore,
        result: bareResult,
        candidate_info: candidateInfo || {},
        jd_info: jdInfo || {},
      }).then(() => {
        qc.invalidateQueries({ queryKey: ["cvintel-history"] });
      }).catch(() => { /* non-fatal — the on-screen result is still shown */ });
      setViewingHistId(null);
    }
  }, [genState.status, genState.submittedAt, genState.data, qc]);

  const runAnalyse = () => {
    setFormError("");
    if (!jdText.trim() && !jdFile) { setFormError("Please provide a job description."); return; }
    if (!resumeText.trim() && !resumeFile) { setFormError("Please provide your resume."); return; }
    setViewingHistId(null);
    setLiveResultDismissed(false);
    analyseMut.mutate();
  };

  const resumeReady = !!(resumeFile || resumeText.trim());
  const jdReady     = !!(jdFile || jdText.trim());
  const pageError = formError || (genState.status === "error" ? ((genState.error as any)?.response?.data?.detail || "Analysis failed") : "");

  // Aliases so the render logic below can keep referring to `result`,
  // `candidateInfo`, `jdInfo` regardless of whether they came from the
  // live mutation or a manually-selected history entry.
  const result = displayResult;
  const candidateInfo = displayResult?.candidateInfo ?? null;
  const jdInfo = displayResult?.jdInfo ?? null;

  return (
    <div>
      {/* ── Header ── */}
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="tiq-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BrainCircuit size={22} color="var(--violet-500)" /> CVAnalysis
          </h1>
          <p className="tiq-page-sub">Score your resume against any job description</p>
        </div>
      </div>

      {pageError && <div className="tiq-alert tiq-alert-error tiq-mb-4">{pageError}</div>}

      {/* ── Input section — ALWAYS VISIBLE ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        {/* Resume */}
        <div className="tiq-card">
          <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <User size={15} color="var(--teal-500)" /> Your Resume
            {resumeReady && <span className="tiq-badge tiq-badge-teal" style={{ fontSize: 10 }}>Ready</span>}
          </div>
          <UploadZone label="Upload Resume (PDF, DOCX, TXT)" file={resumeFile} accept=".pdf,.doc,.docx,.txt"
            onFile={f => setResumeFile(f)} onClear={() => setResumeFile(null)} />
          <TextPanel label="Or paste resume text" value={resumeText} onChange={setResumeText}
            placeholder="Paste your complete resume text here..." />
        </div>

        {/* JD */}
        <div className="tiq-card">
          <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Briefcase size={15} color="var(--violet-500)" /> Job Description
            {jdReady && <span className="tiq-badge tiq-badge-violet" style={{ fontSize: 10 }}>Ready</span>}
          </div>
          <UploadZone label="Upload JD (PDF, DOCX, TXT)" file={jdFile} accept=".pdf,.doc,.docx,.txt"
            onFile={f => setJdFile(f)} onClear={() => setJdFile(null)} />
          <TextPanel label="Or paste job description text" value={jdText} onChange={setJdText}
            placeholder="Paste the complete job description here..." />
        </div>
      </div>

      {/* ── Analyse button ── */}
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <button className="tiq-btn tiq-btn-primary"
          style={{ padding: "12px 40px", fontSize: 15, justifyContent: "center" }}
          onClick={runAnalyse} disabled={genState.status === "pending" || !resumeReady || !jdReady}>
          {genState.status === "pending"
            ? <><span className="tiq-spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Analysing…</>
            : <><Sparkles size={16} /> {result ? "Re-analyse" : "Run ATS Analysis"}</>}
        </button>
        {genState.status === "pending" && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            This keeps running even if you switch to another page.
          </div>
        )}
        {!resumeReady || !jdReady ? (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            {!resumeReady && "Upload or paste resume · "}
            {!jdReady && "Upload or paste job description"}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            {result ? "Files kept — update them above and re-analyse anytime" : "Add a Groq API key in Settings for AI-powered analysis"}
          </div>
        )}
      </div>

      {/* ── Session History ── */}
      {history.length > 0 && (
        <div className="tiq-card tiq-mb-4">
          <div className="tiq-card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <BrainCircuit size={14} color="var(--violet-500)" /> Past Analyses ({history.length})
            </span>
            <button onClick={() => {
                if (!confirm("Clear all history?")) return;
                cvintelApi.deleteAllHistory()
                  .then(() => { qc.invalidateQueries({ queryKey: ["cvintel-history"] }); setViewingHistId(null); setLiveResultDismissed(true); })
                  .catch((e: any) => alert(`Failed to clear history: ${e?.response?.data?.detail || e.message}`));
              }}
              style={{ background:"none",border:"none",cursor:"pointer",fontSize:11,color:"var(--rose-500)",display:"flex",alignItems:"center",gap:4 }}>
              <X size={11} /> Clear all
            </button>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {history.map(h => (
              <div key={h.id}
                onClick={() => setViewingHistId(h.id)}
                style={{
                  padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
                  background: viewingHistId === h.id ? "rgba(139,92,246,.12)" : "var(--bg-secondary)",
                  border: viewingHistId === h.id ? "1.5px solid var(--violet-500)" : "1.5px solid var(--border)",
                  color: viewingHistId === h.id ? "var(--violet-500)" : "var(--text-secondary)",
                  display: "flex", alignItems: "center", gap: 6,
                }}>
                <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.3 }}>
                  <span>{h.name}</span>
                  {h.jd && <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 500 }}>JD: {h.jd}</span>}
                </span>
                <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10,
                  background: h.score >= 75 ? "#10b98120" : h.score >= 50 ? "#f59e0b20" : "#ef444420",
                  color: h.score >= 75 ? "#10b981" : h.score >= 50 ? "#f59e0b" : "#ef4444" }}>
                  {h.score}%
                </span>
                <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{h.ts}</span>
                <button type="button" onClick={e => {
                    e.stopPropagation();
                    const wasShowingThisAsLive = viewingHistId === null && history[0]?.id === h.id;
                    cvintelApi.deleteHistoryItem(h.id)
                      .then(() => {
                        qc.invalidateQueries({ queryKey: ["cvintel-history"] });
                        if (viewingHistId === h.id) setViewingHistId(null);
                        if (wasShowingThisAsLive) setLiveResultDismissed(true);
                      })
                      .catch((err: any) => alert(`Failed to delete: ${err?.response?.data?.detail || err.message}`));
                  }}
                  style={{ background: "none", border: "none", padding: 0, color: "var(--text-muted)", cursor: "pointer", display: "flex" }}>
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Results ── */}
      {result && (
        <div>
          {isAdmin && (result.aiPowered ? (
            <div className="tiq-alert tiq-alert-success tiq-mb-4" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Sparkles size={14} /> AI-powered analysis by Groq LLM{result.groqModel ? ` (${result.groqModel})` : ""}
            </div>
          ) : (
            <div className="tiq-alert tiq-mb-4" style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(239,68,68,.08)", border: "1px solid rgba(239,68,68,.3)", color: "#ef4444" }}>
              <AlertTriangle size={14} />
              <span>
                <strong>Fallback mode:</strong> the LLM extraction failed, so this result uses basic keyword
                matching only — expect sparser skill categories and a less accurate score. Check that your
                Groq API key and model in Settings → API Keys are valid, and that Ollama is reachable if
                you're relying on it as a fallback.
              </span>
            </div>
          ))}

          {/* ── Candidate + JD summary cards ── */}
          {(candidateInfo || jdInfo) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
              {candidateInfo && (
                <div className="tiq-card" style={{ borderLeft: "4px solid var(--teal-500)", padding: "14px 18px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".5px", color: "var(--text-muted)", marginBottom: 10 }}>Candidate</div>
                  <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>{candidateInfo.name}</div>
                  {candidateInfo.email && (
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>📧 {candidateInfo.email}</div>
                  )}
                  {candidateInfo.phone && (
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>📞 {candidateInfo.phone}</div>
                  )}
                  {candidateInfo.location && (
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 4 }}>
                      <MapPin size={11} /> {candidateInfo.location}
                    </div>
                  )}
                  <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {(result.matchedSkills || []).slice(0, 5).map(s => (
                      <span key={s} className="tiq-badge tiq-badge-teal" style={{ fontSize: 10 }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}

              {jdInfo && (
                <div className="tiq-card" style={{ borderLeft: "4px solid var(--violet-500)", padding: "14px 18px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".5px", color: "var(--text-muted)", marginBottom: 10 }}>Job Description</div>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 10 }}>{jdInfo.role}</div>
                  {(() => {
                    // Prefer the backend's LLM-extracted requirements (reliable)
                    // over the client-side regex bullet-parser used only for the
                    // instant pre-analysis preview (fragile — many JDs don't use
                    // a bullet format it can detect).
                    const essential = result.jdRequirements?.essential || [];
                    const goodToHave = result.jdRequirements?.goodToHave || [];
                    const combined = essential.length || goodToHave.length
                      ? [...essential, ...goodToHave]
                      : (jdInfo.requirements || []);
                    if (combined.length === 0) return null;
                    return (
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 6, display: "flex", alignItems: "center", gap: 5 }}>
                          <List size={11} /> Key Requirements
                        </div>
                        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                          {combined.slice(0, 6).map((r: string, i: number) => (
                            <li key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4, paddingLeft: 12, position: "relative" }}>
                              <span style={{ position: "absolute", left: 0, color: "var(--violet-500)" }}>·</span>
                              {r}
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          )}

          {/* ── Score + breakdown ── */}
          <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20, marginBottom: 20 }}>
            <div className="tiq-card" style={{ textAlign: "center" }}>
              <div className="tiq-card-title">ATS Score</div>
              <ScoreDial score={result.overallScore} />
              {result.missingSkills?.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 6 }}>Missing Skills</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, justifyContent: "center" }}>
                    {result.missingSkills.slice(0, 6).map(s => (
                      <span key={s} className="tiq-badge tiq-badge-rose" style={{ fontSize: 10 }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="tiq-card">
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <TrendingUp size={15} /> Score Breakdown
              </div>
              {Object.entries(result.detailedScores || {}).map(([k, v]) => (
                <ScoreBar key={k} label={k} value={v} />
              ))}
            </div>
          </div>

          {/* JD Requirements — categorized, mirrors CandidateLens's JD Summary */}
          {result.jdRequirements && (result.jdRequirements.essential?.length > 0 || result.jdRequirements.goodToHave?.length > 0) && (
            <div className="tiq-card tiq-mb-4" style={{ borderLeft: "4px solid var(--violet-500)" }}>
              <div className="tiq-card-title" style={{ fontSize: 13, marginBottom: 10 }}>Job Description Requirements</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(result.jdRequirements.roleTitle || result.jdRequirements.company) && (
                  <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                    {result.jdRequirements.roleTitle && <span><strong>{result.jdRequirements.roleTitle}</strong></span>}
                    {result.jdRequirements.company && <span> · {result.jdRequirements.company}</span>}
                    {result.jdRequirements.location && <span> · {result.jdRequirements.location}</span>}
                  </div>
                )}
                {(result.jdRequirements.minYearsExperience > 0 || result.jdRequirements.educationRequirement) && (
                  <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
                    {result.jdRequirements.minYearsExperience > 0 && (
                      <span><strong>Experience Required:</strong> {result.jdRequirements.minYearsExperience}+ years</span>
                    )}
                    {result.jdRequirements.educationRequirement && (
                      <span><strong>Education Required:</strong> {result.jdRequirements.educationRequirement}</span>
                    )}
                  </div>
                )}
                {result.jdRequirements.essential?.length > 0 && (
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#ef4444", width: 90, flexShrink: 0, paddingTop: 2 }}>ESSENTIAL</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {result.jdRequirements.essential.map((s: string) => (
                        <span key={s} className="tiq-badge" style={{ fontSize: 10, background: "#ef444420", color: "#ef4444" }}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {result.jdRequirements.goodToHave?.length > 0 && (
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#f59e0b", width: 90, flexShrink: 0, paddingTop: 2 }}>GOOD TO HAVE</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {result.jdRequirements.goodToHave.map((s: string) => (
                        <span key={s} className="tiq-badge" style={{ fontSize: 10, background: "#f59e0b20", color: "#f59e0b" }}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {result.jdRequirements.optional?.length > 0 && (
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0, paddingTop: 2 }}>OPTIONAL</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {result.jdRequirements.optional.map((s: string) => (
                        <span key={s} className="tiq-badge tiq-badge-slate" style={{ fontSize: 10 }}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
            <div className="tiq-card" style={{ borderLeft: "4px solid #10b981" }}>
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <CheckCircle size={14} color="#10b981" /> Strengths
              </div>
              {result.strengthsBreakdown ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {((result.candidateProfile?.yearsExperience ?? 0) > 0 || result.candidateProfile?.education) && (
                    <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)", paddingBottom: 8, borderBottom: "1px solid var(--border)" }}>
                      {(result.candidateProfile?.yearsExperience ?? 0) > 0 && (
                        <span><strong>Experience:</strong> {result.candidateProfile?.yearsExperience}+ years</span>
                      )}
                      {result.candidateProfile?.education && (
                        <span><strong>Education:</strong> {result.candidateProfile.education}</span>
                      )}
                    </div>
                  )}
                  {[
                    ["Essential Matched", result.strengthsBreakdown.essentialMatched, "#10b981"],
                    ["Technical Skills", result.strengthsBreakdown.technicalSkills, "#3b82f6"],
                    ["Business Skills", result.strengthsBreakdown.businessSkills, "#8b5cf6"],
                    ["Soft Skills", result.strengthsBreakdown.softSkills, "#ec4899"],
                    ["Significant Experience", result.strengthsBreakdown.significantExperience, "#f59e0b"],
                    ["Certifications & Degrees", result.strengthsBreakdown.certificationsDegrees, "#06b6d4"],
                  ].map(([label, items, color]: any) => items?.length > 0 && (
                    <div key={label}>
                      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color, marginBottom: 4 }}>{label}</div>
                      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                        {items.map((s: string, i: number) => (
                          <li key={i} style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 12 }}>
                            <CheckCircle size={11} color={color} style={{ flexShrink: 0, marginTop: 2 }} />{s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {result.strengths.map((s, i) => (
                    <li key={i} style={{ display: "flex", gap: 10, marginBottom: 10, fontSize: 13 }}>
                      <CheckCircle size={13} color="#10b981" style={{ flexShrink: 0, marginTop: 2 }} />{s}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="tiq-card" style={{ borderLeft: "4px solid #ef4444" }}>
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <AlertTriangle size={14} color="#ef4444" /> Gaps
              </div>
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {result.gaps.map((g, i) => (
                  <li key={i} style={{ display: "flex", gap: 10, marginBottom: 10, fontSize: 13 }}>
                    <AlertTriangle size={13} color="#ef4444" style={{ flexShrink: 0, marginTop: 2 }} />{g}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="tiq-card tiq-mb-4" style={{ borderLeft: "4px solid var(--violet-500)" }}>
            <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--violet-500)" /> Suggestions to Improve
            </div>
            <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {result.suggestions.map((s, i) => (
                <li key={i} style={{ display: "flex", gap: 12, marginBottom: 12, fontSize: 13 }}>
                  <div style={{ width: 22, height: 22, borderRadius: "50%", background: "rgba(139,92,246,.15)",
                    color: "var(--violet-500)", fontWeight: 700, fontSize: 12, flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</div>
                  <span style={{ paddingTop: 2 }}>{s}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="tiq-card tiq-mb-4">
            <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <BrainCircuit size={14} color="#6366f1" /> Summary Assessment
            </div>
            <p style={{ fontSize: 14, lineHeight: 1.7, color: "var(--text-secondary)" }}>{result.summaryAssessment}</p>
          </div>

          {result.formatWarnings?.length > 0 && (
            <div className="tiq-card" style={{ borderLeft: "4px solid #f59e0b" }}>
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <AlertTriangle size={14} color="#f59e0b" /> ATS Formatting Warnings
              </div>
              {result.formatWarnings.map((w, i) => (
                <div key={i} style={{ display: "flex", gap: 10, marginBottom: 8, fontSize: 13 }}>
                  <AlertTriangle size={12} color="#f59e0b" style={{ flexShrink: 0, marginTop: 2 }} />{w}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}