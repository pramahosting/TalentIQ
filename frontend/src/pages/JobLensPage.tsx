import { } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLatestMutation } from "../hooks/useLatestMutation";
import {
  Users, Upload, FileText, Play, Download, ChevronDown, ChevronUp,
  CheckCircle, Clock, XCircle, Star, Video, RefreshCw, Sparkles, BarChart2,
  Trash2, Mail } from "lucide-react";
import { api } from "../lib/api";

// ─── API ───────────────────────────────────────────────────────────────────
const jobLensApi = {
  deleteSession: (id: number) => api.delete(`/api/joblens/sessions/${id}`).then(r => r.data),
  run: (form: FormData) => api.post("/api/joblens/run", form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data),
  sessions: () => api.get("/api/joblens/sessions").then(r => r.data),
  session: (id: number) => api.get(`/api/joblens/sessions/${id}`).then(r => r.data),
  generateQuestions: (sid: number, cid: number) =>
    api.post(`/api/joblens/sessions/${sid}/candidates/${cid}/questions`).then(r => r.data),
  toggleShortlist: (cid: number) =>
    api.put(`/api/joblens/candidates/${cid}/shortlist`).then(r => r.data),
  saveInterviewResult: (cid: number, result: any) =>
    api.post(`/api/joblens/candidates/${cid}/interview-result`, result).then(r => r.data),
  export: (sid: number) =>
    api.get(`/api/joblens/sessions/${sid}/export`, { responseType: "blob" }).then(r => r.data),
  prepareInvite: (cid: number) =>
    api.post(`/api/joblens/candidates/${cid}/prepare-invite`).then(r => r.data),
  markContacted: (cid: number) =>
    api.post(`/api/joblens/candidates/${cid}/mark-contacted`).then(r => r.data),
};

// ─── HELPERS ───────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    "Qualified":     "tiq-badge-teal",
    "Review":        "tiq-badge-amber",
    "Not Qualified": "tiq-badge-rose",
    "Pending":       "tiq-badge-slate",
    "Completed":     "tiq-badge-teal",
  };
  return <span className={`tiq-badge ${map[status] || "tiq-badge-slate"}`}>{status}</span>;
}

function ScoreCell({ score, low, high }: { score: number; low: number; high: number }) {
  const color = score >= high ? "#10b981" : score >= low ? "#f59e0b" : "#ef4444";
  return (
    <span style={{ fontWeight: 700, color, fontSize: 14 }}>
      {score.toFixed(1)}%
    </span>
  );
}

function ProgressBar({ value, color = "var(--teal-500)" }: { value: number; color?: string }) {
  return (
    <div style={{ height: 6, background: "var(--bg-tertiary)", borderRadius: 3, overflow: "hidden", minWidth: 80 }}>
      <div style={{ height: "100%", width: `${Math.min(100, value)}%`, background: color, borderRadius: 3 }} />
    </div>
  );
}

// ─── ANCHORED POPOVER ───────────────────────────────────────────────────────
// A small, borderless, no-backdrop popover that appears right next to
// whatever triggered it (a "+N more" link, a resume-summary snippet, etc.)
// and closes on outside click. No dimmed background, no centering.
function AnchoredPopover({
  x, y, onClose, width = 300, children
}: { x: number; y: number; onClose: () => void; width?: number; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    const escHandler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", escHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", escHandler);
    };
  }, [onClose]);

  const clampedX = Math.max(8, Math.min(x, window.innerWidth - width - 12));

  return (
    <div ref={ref} style={{
      position: "fixed", left: clampedX, top: y, zIndex: 1500, width,
      maxHeight: 320, overflowY: "auto",
      background: "#ffffff", color: "#111827",
      border: "1px solid #e5e7eb", borderRadius: 10, padding: 12,
      boxShadow: "0 8px 28px rgba(0,0,0,.16)",
    }}>
      {children}
    </div>
  );
}

// ─── MORPHCAST LOADER ───────────────────────────────────────────────────────
declare global {
  interface Window { CY?: any; MphTools?: any; }
}

const MORPHCAST_LICENSE = ""; // optional — leave blank to use trial/dev mode

function loadMorphcastScripts(): Promise<void> {
  function load(src: string, dataConfig?: string) {
    return new Promise<void>((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
      const s = document.createElement("script");
      s.src = src;
      if (dataConfig) s.setAttribute("data-config", dataConfig);
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
  }
  return (async () => {
    await load(
      "https://sdk.morphcast.com/mphtools/v1.1/mphtools.js",
      "cameraPrivacyPopup, compatibilityUI, compatibilityAutoCheck"
    );
    await load("https://ai-sdk.morphcast.com/v1.16/ai-sdk.js");
  })();
}

type EmotionAgg = { angry: number; disgust: number; fear: number; happy: number; sad: number; surprise: number; neutral: number; };
const EMPTY_EMO: EmotionAgg = { angry: 0, disgust: 0, fear: 0, happy: 0, sad: 0, surprise: 0, neutral: 0 };
const ANSWER_SECONDS = 30;

// ─── VIDEO INTERVIEW MODAL ─────────────────────────────────────────────────
function VideoInterviewModal({
  candidate, questions, sessionId, onClose, onDone
}: {
  candidate: any; questions: string[]; sessionId: number;
  onClose: () => void; onDone: (emotions: any) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const engineRef = useRef<any>(null);
  const isRecordingRef = useRef(false);

  const [qIdx, setQIdx] = useState(0);
  const [recording, setRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [timeLeft, setTimeLeft] = useState(ANSWER_SECONDS);
  const [started, setStarted] = useState(false);
  const [mcReady, setMcReady] = useState(false);
  const [mcStatus, setMcStatus] = useState("Initialising camera & emotion AI…");
  const [agg, setAgg] = useState<EmotionAgg>({ ...EMPTY_EMO });
  const [avgAgg, setAvgAgg] = useState<EmotionAgg>({ ...EMPTY_EMO });
  const [samples, setSamples] = useState(0);
  const [dominant, setDominant] = useState("Neutral");

  // Keep ref in sync so the MorphCast event handler (closure) sees current value
  isRecordingRef.current = recording;

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" }, audio: true,
      });
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      setStarted(true);
      await initMorphcast();
      speakQuestion(questions[0] || "");
    } catch {
      alert(
        "Camera/Mic is blocked. Please:\n" +
        "1) Click the padlock in the address bar and allow Camera/Mic\n" +
        "2) Check OS-level privacy settings allow this browser\n" +
        "3) Close other apps using the camera (Zoom/Teams/OBS)"
      );
    }
  };

  const initMorphcast = async () => {
    try {
      await loadMorphcastScripts();
      window.MphTools?.CompatibilityAutoCheck?.run?.();

      const CY = (window as any).CY;
      if (!CY) throw new Error("MorphCast SDK unavailable");

      const source = CY.createSource.fromVideoElement(videoRef.current);
      let loader = CY.loader()
        .addModule(CY.modules().FACE_DETECTOR.name)
        .addModule(CY.modules().FACE_EMOTION.name)
        .source(source);
      if (MORPHCAST_LICENSE) loader = loader.licenseKey(MORPHCAST_LICENSE);

      const engine = await loader.load();
      engineRef.current = engine;

      const handleEmotion = (evt: any) => {
        if (!isRecordingRef.current) return;
        const detail = evt?.detail || evt;
        const out = detail?.output || detail?.data || detail?.result || undefined;
        const emo = out?.face?.emotion || out?.face0?.emotion || out?.emotion || null;
        if (!emo) return;

        const vals: EmotionAgg = {
          angry:    Number(emo.angry ?? emo.Angry ?? 0),
          disgust:  Number(emo.disgust ?? emo.Disgust ?? 0),
          fear:     Number(emo.fear ?? emo.Fear ?? 0),
          happy:    Number(emo.happy ?? emo.Happy ?? 0),
          sad:      Number(emo.sad ?? emo.Sad ?? 0),
          surprise: Number(emo.surprise ?? emo.Surprise ?? 0),
          neutral:  Number(emo.neutral ?? emo.Neutral ?? 0),
        };
        const [domKey] = Object.entries(vals).reduce(
          (max, c) => (c[1] > max[1] ? c : max),
          ["neutral", 0]
        ) as [keyof EmotionAgg, number];

        setAgg(prev => {
          const updated = { ...prev, [domKey]: prev[domKey] + 1 } as EmotionAgg;
          const total = Object.values(updated).reduce((a, b) => a + b, 1);
          setAvgAgg({
            angry: Math.round(updated.angry / total * 100),
            disgust: Math.round(updated.disgust / total * 100),
            fear: Math.round(updated.fear / total * 100),
            happy: Math.round(updated.happy / total * 100),
            sad: Math.round(updated.sad / total * 100),
            surprise: Math.round(updated.surprise / total * 100),
            neutral: Math.round(updated.neutral / total * 100),
          });
          const domEntry = Object.entries(updated).reduce((a, b) => (b[1] > a[1] ? b : a), ["neutral", 0]);
          setDominant(domEntry[0].charAt(0).toUpperCase() + domEntry[0].slice(1));
          setSamples(total);
          return updated;
        });
      };

      window.addEventListener("CY_FACE_EMOTION", handleEmotion);
      window.addEventListener("CY_FACE_EMOTION_RESULT", handleEmotion);
      window.addEventListener("cy.face.emotion", handleEmotion);

      await engine.start();
      setMcReady(true);
      setMcStatus("Emotion AI active — recording only while you answer.");
    } catch (e: any) {
      setMcStatus("Emotion AI unavailable (" + (e?.message || "init failed") + ") — interview will continue without facial analysis.");
    }
  };

  const speakQuestion = (q: string) => {
    if (!q || !("speechSynthesis" in window)) { startRecording(); return; }
    setIsSpeaking(true);
    const utter = new SpeechSynthesisUtterance(q);
    utter.rate = 0.92;
    utter.pitch = 1.05;
    utter.lang = "en-US";
    utter.onend = () => { setIsSpeaking(false); startRecording(); };
    utter.onerror = () => { setIsSpeaking(false); startRecording(); };
    speechSynthesis.cancel();
    speechSynthesis.speak(utter);
  };

  const startRecording = () => {
    const stream = videoRef.current?.srcObject as MediaStream;
    if (!stream) return;
    try {
      const mr = new MediaRecorder(stream, { mimeType: "video/webm" });
      mediaRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.start();
    } catch { /* MediaRecorder unsupported — emotion AI + timer still work */ }
    setRecording(true);
    setTimeLeft(ANSWER_SECONDS);
  };

  // Countdown timer — pauses while TTS is speaking
  const timerTickRef = useRef<any>(null);
  useEffect(() => {
    if (!recording || isSpeaking) return;
    if (timeLeft <= 0) { nextQuestion(); return; }
    timerTickRef.current = setTimeout(() => setTimeLeft(t => t - 1), 1000);
    return () => clearTimeout(timerTickRef.current);
  }, [recording, isSpeaking, timeLeft]);

  const nextQuestion = () => {
    if (timerTickRef.current) { clearTimeout(timerTickRef.current); timerTickRef.current = null; }
    mediaRef.current?.stop();
    setRecording(false);
    if (qIdx < questions.length - 1) {
      setTimeout(() => {
        setQIdx(i => i + 1);
        speakQuestion(questions[qIdx + 1] || "");
      }, 500);
    } else {
      finishInterview();
    }
  };

  const finishInterview = async () => {
    if (timerTickRef.current) { clearTimeout(timerTickRef.current); timerTickRef.current = null; }
    mediaRef.current?.stop();
    setRecording(false);
    speechSynthesis.cancel();
    try { await engineRef.current?.stop?.(); await engineRef.current?.destroy?.(); } catch {}
    const tracks = (videoRef.current?.srcObject as MediaStream)?.getTracks?.() || [];
    tracks.forEach(t => t.stop());

    const emotions = samples > 0
      ? { ...avgAgg, dominant }
      : { happy: 0, neutral: 100, sad: 0, angry: 0, disgust: 0, fear: 0, surprise: 0, dominant: "Neutral" };
    onDone(emotions);
  };

  const currentQ = questions[qIdx] || "Loading...";

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 16, padding: 28, maxWidth: 760, width: "95%", maxHeight: "92vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ fontWeight: 800, fontSize: 17, color: "#111827" }}>
            <Video size={16} style={{ display: "inline", marginRight: 8, color: "#ef4444" }} />
            Video Interview — {candidate.name}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#6b7280", fontSize: 20 }}>×</button>
        </div>

        <div style={{ position: "relative" }}>
          <video ref={videoRef} style={{ width: "100%", borderRadius: 12, background: "#000", minHeight: 240 }} playsInline muted />
          {isSpeaking && (
            <div style={{ position: "absolute", bottom: 12, left: 12, padding: "4px 10px", borderRadius: 20, background: "rgba(0,199,183,.9)", color: "white", fontSize: 11, fontWeight: 700 }}>
              🔊 Reading question…
            </div>
          )}
          {recording && (
            <div style={{ position: "absolute", top: 12, right: 12, padding: "4px 10px", borderRadius: 20, background: "rgba(239,68,68,.9)", color: "white", fontSize: 11, fontWeight: 700 }}>
              ● REC
            </div>
          )}
        </div>

        <div style={{ fontSize: 11, color: mcReady ? "#0d9488" : "#6b7280", marginTop: 8 }}>
          {mcStatus}
        </div>

        <div style={{ margin: "16px 0", padding: 14, background: "#f3f4f6", borderRadius: 10, borderLeft: "4px solid #0d9488" }}>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Question {qIdx + 1} / {questions.length}</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#111827" }}>{currentQ}</div>
        </div>

        {recording && (
          <div style={{ textAlign: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 28, fontWeight: 900, color: "#ef4444" }}>{timeLeft}s</div>
            <div style={{ fontSize: 10, color: "#6b7280" }}>remaining</div>
          </div>
        )}

        <div style={{ display: "flex", gap: 8 }}>
          {!started ? (
            <button className="tiq-btn tiq-btn-primary" onClick={startCamera}>
              <Video size={14} /> Start Interview
            </button>
          ) : (
            <button className="tiq-btn tiq-btn-outline" onClick={nextQuestion} disabled={isSpeaking}>
              {qIdx < questions.length - 1 ? "Next Question →" : "Finish Interview"}
            </button>
          )}
          <button className="tiq-btn tiq-btn-ghost" onClick={finishInterview}>End Now</button>
        </div>
      </div>
    </div>
  );
}

// ─── CANDIDATE CONTACT / SEND INVITE MODAL ─────────────────────────────────
// Produces a plain-text letter (not HTML) and hands off to the person's
// default mail client (e.g. Outlook) via a mailto: link, so the actual
// send happens from their own mailbox.
function ContactModal({
  candidate, token, onClose, onSent
}: { candidate: any; token: string; onClose: () => void; onSent: () => void }) {
  const link = `${window.location.origin}/interview/${token}`;
  const [toEmail, setToEmail] = useState(candidate.email || "");
  const [subject, setSubject] = useState(`Video Interview Invitation - ${candidate.name}`);
  const [body, setBody] = useState(
`Dear ${candidate.name},

Thank you for your application. We would like to invite you to complete a short video interview as the next step in our recruitment process.

Please click the link below to begin. It works directly in your browser — no account or login required:

${link}

Regards,
HR Team`
  );
  const [opened, setOpened] = useState(false);

  const handleSend = async () => {
    const mailto = `mailto:${encodeURIComponent(toEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.location.href = mailto;
    setOpened(true);
    try { await jobLensApi.markContacted(candidate.id); } catch { /* non-fatal */ }
    onSent();
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 14, padding: 24, maxWidth: 560, width: "94%", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 25px 60px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>
            <Mail size={15} style={{ display: "inline", marginRight: 6, color: "#0d9488" }} />
            Send Video Interview Invite — {candidate.name}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b7280" }}>×</button>
        </div>

        {opened ? (
          <div style={{ padding: "20px 0", textAlign: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#0d9488", marginBottom: 8 }}>
              ✅ Draft opened in your email app
            </div>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
              Review it in Outlook (or your default mail app) and click Send there.
            </div>
            <button className="tiq-btn tiq-btn-outline" onClick={onClose}>Close</button>
          </div>
        ) : (
          <>
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>To</label>
              <input className="tiq-input" value={toEmail} onChange={e => setToEmail(e.target.value)} />
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>Subject</label>
              <input className="tiq-input" value={subject} onChange={e => setSubject(e.target.value)} />
            </div>
            <div className="tiq-form-group">
              <label className="tiq-label" style={{ color: "#374151" }}>Message</label>
              <textarea className="tiq-input" style={{ minHeight: 220, fontFamily: "inherit", fontSize: 13, whiteSpace: "pre-wrap" }}
                value={body} onChange={e => setBody(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="tiq-btn tiq-btn-primary" onClick={handleSend} disabled={!toEmail}>
                Send
              </button>
              <button className="tiq-btn tiq-btn-ghost" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── CANDIDATE ROW ─────────────────────────────────────────────────────────
type PopoverKind = "resume" | "matched" | "missing";
type PopoverState = { kind: PopoverKind; x: number; y: number } | null;

function CandidateRow({
  c, rank, sessionId, lowT, highT, onRefresh
}: { c: any; rank: number; sessionId: number; lowT: number; highT: number; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [interviewOpen, setInterviewOpen] = useState(false);
  const [questions, setQuestions] = useState<string[]>(c.interview_questions || []);
  const [genLoading, setGenLoading] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contacted, setContacted] = useState(!!c.contacted);
  const [inviteToken, setInviteToken] = useState<string | null>(c.interview_token || null);
  const [preparingInvite, setPreparingInvite] = useState(false);
  const [popover, setPopover] = useState<PopoverState>(null);

  // Local, instantly-updated shortlist state — decoupled from the parent
  // session refetch so the checkbox never waits on a network round trip.
  const [shortlisted, setShortlisted] = useState(!!c.shortlisted);
  useEffect(() => { setShortlisted(!!c.shortlisted); }, [c.shortlisted]);
  useEffect(() => { setContacted(!!c.contacted); }, [c.contacted]);

  const shortlistMut = useMutation({
    mutationFn: () => jobLensApi.toggleShortlist(c.id),
    onMutate: () => { setShortlisted(s => !s); },
    onError: () => { setShortlisted(s => !s); },
    onSuccess: () => { onRefresh(); },
  });

  const genQuestions = async () => {
    setGenLoading(true);
    try {
      const r = await jobLensApi.generateQuestions(sessionId, c.id);
      setQuestions(r.questions || []);
    } finally {
      setGenLoading(false);
    }
  };

  const handleInterviewDone = async (emotions: any) => {
    await jobLensApi.saveInterviewResult(c.id, emotions);
    setInterviewOpen(false);
    onRefresh();
  };

  const handleContactClick = async () => {
    setPreparingInvite(true);
    try {
      let tok = inviteToken;
      if (!tok) {
        const r = await jobLensApi.prepareInvite(c.id);
        tok = r.token;
        setInviteToken(tok);
      }
      setContactOpen(true);
    } finally {
      setPreparingInvite(false);
    }
  };

  const openPopover = (kind: PopoverKind) => (e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopover({ kind, x: rect.left, y: rect.bottom + 6 });
  };

  const resumeSummary: string[] = c.resume_summary || [];

  return (
    <>
      <tr style={{ background: shortlisted ? "rgba(0,199,183,.05)" : undefined }}>
        <td style={{ fontWeight: 700, color: "var(--text-muted)", fontSize: 12 }}>#{rank}</td>
        <td>
          <div style={{ fontWeight: 600 }}>{c.name}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{c.filename}</div>
        </td>
        <td style={{ fontSize: 12 }}>{c.email}</td>
        <td style={{ fontSize: 12 }}>{c.phone}</td>

        {/* Resume Summary — 2 bullets visible, click for the full 10-statement list */}
        <td style={{ fontSize: 11, minWidth: 200 }}>
          {resumeSummary.length > 0 ? (
            <>
              <ul style={{ margin: 0, paddingLeft: 14 }}>
                {resumeSummary.slice(0, 2).map((s, i) => <li key={i} style={{ marginBottom: 2 }}>{s}</li>)}
              </ul>
              {resumeSummary.length > 2 && (
                <button onClick={openPopover("resume")}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", paddingLeft: 14, fontSize: 10, textDecoration: "underline" }}>
                  +{resumeSummary.length - 2} more
                </button>
              )}
            </>
          ) : (
            <span style={{ color: "var(--text-muted)" }}>
              {c.experience_years || "No resume summary available"}
            </span>
          )}
        </td>

        <td>
          <div><ScoreCell score={c.ats_score} low={lowT} high={highT} /></div>
          <ProgressBar value={c.ats_score}
            color={c.ats_score >= highT ? "#10b981" : c.ats_score >= lowT ? "#f59e0b" : "#ef4444"} />
        </td>

        {/* Key Strength = matched skills, bulleted, up to 5, rest via popover */}
        <td style={{ fontSize: 11, minWidth: 150, color: "var(--teal-500)" }}>
          <ul style={{ margin: 0, paddingLeft: 14 }}>
            {(c.matched_skills || []).slice(0, 5).map((s: string) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          {(c.matched_skills || []).length > 5 && (
            <button onClick={openPopover("matched")}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", paddingLeft: 14, fontSize: 10, textDecoration: "underline" }}>
              +{c.matched_skills.length - 5} more
            </button>
          )}
        </td>

        {/* Considerations = missing skills, bulleted, up to 5, rest via popover */}
        <td style={{ fontSize: 11, minWidth: 150, color: "var(--rose-500)" }}>
          <ul style={{ margin: 0, paddingLeft: 14 }}>
            {(c.missing_skills || []).slice(0, 5).map((s: string) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          {(c.missing_skills || []).length > 5 && (
            <button onClick={openPopover("missing")}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", paddingLeft: 14, fontSize: 10, textDecoration: "underline" }}>
              +{c.missing_skills.length - 5} more
            </button>
          )}
        </td>

        <td><StatusBadge status={c.status} /></td>

        <td>
          <button className="tiq-btn tiq-btn-outline tiq-btn-sm"
            onClick={() => setExpanded(e => !e)}>
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={10} style={{ padding: "14px 20px", background: "var(--bg-secondary)" }}>
            {c.summary && (
              <div style={{ marginBottom: 16, paddingBottom: 14, borderBottom: "1px solid var(--border)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>Profile Summary</div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>{c.summary}</div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
              {/* Video Interview */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>Video Interview</div>
                <button className="tiq-btn tiq-btn-primary tiq-btn-sm"
                  onClick={() => { if (!questions.length) genQuestions(); setInterviewOpen(true); }}>
                  <Video size={12} /> {c.video_status === "Completed" ? "Re-run" : "Start"}
                </button>
                <div style={{ marginTop: 6 }}><StatusBadge status={c.video_status} /></div>
              </div>

              {/* Video Review */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>Video Review</div>
                <div style={{ fontSize: 11, lineHeight: 1.7 }}>
                  <div>😊 Happy: <strong>{c.emotion_happy ?? 0}%</strong></div>
                  <div>😐 Neutral: <strong>{c.emotion_neutral ?? 0}%</strong></div>
                  <div>😢 Sad: <strong>{c.emotion_sad ?? 0}%</strong></div>
                  <div>😡 Angry: <strong>{c.emotion_angry ?? 0}%</strong></div>
                  <div style={{ color: "var(--violet-500)" }}>Dominant: <strong>{c.dominant_emotion || "—"}</strong></div>
                </div>
              </div>

              {/* Candidate Contact — checked once the invite has actually been sent */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>Candidate Contact</div>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={contacted}
                    disabled={preparingInvite}
                    onClick={e => e.preventDefault()}
                    onChange={handleContactClick}
                  />
                  {preparingInvite ? "Preparing…" : contacted ? "Invite sent" : "Send interview invite"}
                </label>
              </div>

              {/* Shortlist */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>Shortlist</div>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12 }}>
                  <input type="checkbox" checked={shortlisted} onChange={() => shortlistMut.mutate()} />
                  Shortlisted
                </label>
              </div>
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>
                Interview Questions
                <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ marginLeft: 8, fontSize: 10 }}
                  onClick={genQuestions} disabled={genLoading}>
                  <Sparkles size={10} /> {genLoading ? "Generating…" : "Generate"}
                </button>
              </div>
              {questions.length > 0 ? (
                <ol style={{ paddingLeft: 16, margin: 0, fontSize: 12 }}>
                  {questions.map((q, i) => <li key={i} style={{ marginBottom: 4 }}>{q}</li>)}
                </ol>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Click Generate to create questions</div>
              )}
            </div>

            {c.bonus > 0 && (
              <div style={{ marginTop: 10, fontSize: 12, color: "#f59e0b" }}>
                🎯 Bonus: +{c.bonus} pts — {c.bonus_reasons}
              </div>
            )}
          </td>
        </tr>
      )}

      {interviewOpen && questions.length > 0 && (
        <VideoInterviewModal
          candidate={c}
          questions={questions}
          sessionId={sessionId}
          onClose={() => setInterviewOpen(false)}
          onDone={handleInterviewDone}
        />
      )}

      {contactOpen && inviteToken && (
        <ContactModal
          candidate={c}
          token={inviteToken}
          onClose={() => setContactOpen(false)}
          onSent={() => setContacted(true)}
        />
      )}

      {popover?.kind === "resume" && (
        <AnchoredPopover x={popover.x} y={popover.y} width={320} onClose={() => setPopover(null)}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>Full Resume Summary</div>
          <ol style={{ margin: 0, paddingLeft: 16, fontSize: 11, lineHeight: 1.6 }}>
            {resumeSummary.map((s, i) => <li key={i} style={{ marginBottom: 4 }}>{s}</li>)}
          </ol>
        </AnchoredPopover>
      )}

      {popover?.kind === "matched" && (
        <AnchoredPopover x={popover.x} y={popover.y} width={280} onClose={() => setPopover(null)}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>All Key Strengths</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(c.matched_skills || []).map((s: string) => (
              <span key={s} style={{ background: "#0d9488", color: "#fff", fontSize: 10, padding: "3px 8px", borderRadius: 999 }}>{s}</span>
            ))}
          </div>
        </AnchoredPopover>
      )}

      {popover?.kind === "missing" && (
        <AnchoredPopover x={popover.x} y={popover.y} width={280} onClose={() => setPopover(null)}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>All Considerations</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(c.missing_skills || []).map((s: string) => (
              <span key={s} style={{ background: "#e11d48", color: "#fff", fontSize: 10, padding: "3px 8px", borderRadius: 999 }}>{s}</span>
            ))}
          </div>
        </AnchoredPopover>
      )}
    </>
  );
}

// ─── MAIN PAGE ─────────────────────────────────────────────────────────────
export default function JobLensPage() {
    const qc = useQueryClient();
  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [cvFiles, setCvFiles] = useState<FileList | null>(null);
  const [lowT, setLowT] = useState(40);
  const [highT, setHighT] = useState(70);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [tab, setTab] = useState<"new"|"history">("new");
  const jdFileRef = useRef<HTMLInputElement>(null);
  const cvFileRef = useRef<HTMLInputElement>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => jobLensApi.deleteSession(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["joblens-sessions"] });
      if (activeSessionId === id) setActiveSessionId(null);
    },
  });

  const { data: sessions = [] } = useQuery({
    queryKey: ["joblens-sessions"],
    queryFn: jobLensApi.sessions,
  });

  const { data: activeSession, refetch: refetchSession } = useQuery({
    queryKey: ["joblens-session", activeSessionId],
    queryFn: () => jobLensApi.session(activeSessionId!),
    enabled: !!activeSessionId,
  });

  const runMut = useMutation({
    mutationKey: ["joblens-run"],
    mutationFn: () => {
      const form = new FormData();
      form.append("jd_text", jdText);
      form.append("low_threshold", String(lowT));
      form.append("high_threshold", String(highT));
      if (jdFile) form.append("jd_file", jdFile);
      if (cvFiles) for (let i = 0; i < cvFiles.length; i++) form.append("cv_files", cvFiles[i]);
      return jobLensApi.run(form);
    },
    onSuccess: (data) => {
      setActiveSessionId(data.session_id);
      setTab("history");
      qc.invalidateQueries({ queryKey: ["joblens-sessions"] });
      qc.invalidateQueries({ queryKey: ["joblens-session", data.session_id] });
    },
  });

  // Reads the same mutation from the shared, app-level mutation cache — this
  // is what survives the user switching to another agent page while a batch
  // of CVs is still being scored, and picks the result back up when they
  // return, whether or not this specific page instance was the one that
  // originally triggered it.
  const runState = useLatestMutation<any>(["joblens-run"]);
  const lastSeenRunSessionId = useRef<number | null>(null);
  useEffect(() => {
    if (runState.status === "success" && runState.data?.session_id
        && runState.data.session_id !== lastSeenRunSessionId.current) {
      lastSeenRunSessionId.current = runState.data.session_id;
      qc.invalidateQueries({ queryKey: ["joblens-sessions"] });
      qc.invalidateQueries({ queryKey: ["joblens-session", runState.data.session_id] });
      setActiveSessionId(runState.data.session_id);
      setTab("history");
    }
  }, [runState.status, runState.data?.session_id, qc]);

  const exportMut = useMutation({
    mutationFn: (id: number) => jobLensApi.export(id),
    onSuccess: (blob, id) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `joblens_${id}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    },
  });

  const candidates: any[] = activeSession?.candidates || [];
  const qualified  = candidates.filter(c => c.status === "Qualified").length;
  const review     = candidates.filter(c => c.status === "Review").length;
  const shortlisted = candidates.filter(c => c.shortlisted).length;

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Users size={22} color="var(--violet-500)" /> CandidateLens
        </h1>
        <p className="tiq-page-sub">AI recruitment engine — rank CVs, score candidates, run video interviews</p>
      </div>

      {/* Tabs row — session dropdown sits inline, right next to the Results tab */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div className="tiq-tabs">
          <button className={`tiq-tab${tab === "new" ? " active" : ""}`} onClick={() => setTab("new")}>
            <Play size={12} style={{ display: "inline", marginRight: 6 }} /> New Analysis
          </button>
          <button className={`tiq-tab${tab === "history" ? " active" : ""}`} onClick={() => setTab("history")}>
            <BarChart2 size={12} style={{ display: "inline", marginRight: 6 }} /> Results
            {sessions.length > 0 && <span className="tiq-badge tiq-badge-slate" style={{ marginLeft: 8, fontSize: 10 }}>{sessions.length}</span>}
          </button>
        </div>

        {tab === "history" && sessions.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <select className="tiq-input" style={{ maxWidth: 320 }}
              value={activeSessionId ?? ""}
              onChange={e => setActiveSessionId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Select a session…</option>
              {sessions.map((s: any) => (
                <option key={s.id} value={s.id}>
                  Session #{s.id} · {s.cv_count} CVs · {new Date(s.created_at).toLocaleDateString()}
                </option>
              ))}
            </select>
            {activeSessionId && (
              <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ color: "var(--rose-500)" }}
                onClick={() => { if (confirm("Delete this session?")) deleteMutation.mutate(activeSessionId); }}>
                <Trash2 size={12} />
              </button>
            )}
          </div>
        )}
      </div>

      {tab === "new" && (
        <div style={{ maxWidth: 900 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
            {/* JD */}
            <div className="tiq-card">
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FileText size={15} color="var(--violet-500)" /> Job Description
              </div>
              <textarea
                value={jdText}
                onChange={e => setJdText(e.target.value)}
                placeholder="Paste job description here..."
                style={{ width: "100%", minHeight: 200, padding: 10, fontSize: 12,
                  fontFamily: "monospace", border: "1.5px solid var(--border)",
                  borderRadius: 8, resize: "vertical", outline: "none",
                  background: "var(--bg-secondary)", color: "var(--text-primary)" }}
              />
              <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>Or upload JD file:</div>
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button className="tiq-btn tiq-btn-outline tiq-btn-sm"
                  onClick={() => jdFileRef.current?.click()}>
                  <Upload size={12} /> Upload JD
                </button>
                {jdFile && <span style={{ fontSize: 12, color: "var(--teal-500)", alignSelf: "center" }}>✓ {jdFile.name}</span>}
              </div>
              <input ref={jdFileRef} type="file" accept=".txt,.pdf,.doc,.docx" style={{ display: "none" }}
                onChange={e => setJdFile(e.target.files?.[0] || null)} />
            </div>

            {/* CVs + Settings */}
            <div className="tiq-card">
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Users size={15} color="var(--teal-500)" /> CV Files & Thresholds
              </div>
              <div
                onClick={() => cvFileRef.current?.click()}
                style={{ border: "2px dashed var(--border)", borderRadius: 10, padding: 20,
                  textAlign: "center", cursor: "pointer", marginBottom: 16 }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--teal-500)")}
                onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
              >
                <Upload size={28} color="var(--text-muted)" style={{ margin: "0 auto 8px" }} />
                <div style={{ fontSize: 13 }}>
                  {cvFiles ? (
                    <span style={{ color: "var(--teal-500)", fontWeight: 600 }}>
                      {cvFiles.length} CV{cvFiles.length > 1 ? "s" : ""} selected
                    </span>
                  ) : (
                    <span>Click to select CVs (PDF, DOCX) — multiple allowed</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>PDF, DOCX supported</div>
              </div>
              <input ref={cvFileRef} type="file" accept=".pdf,.doc,.docx" multiple style={{ display: "none" }}
                onChange={e => setCvFiles(e.target.files)} />

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="tiq-form-group">
                  <label className="tiq-label">Low Threshold (Review)</label>
                  <input type="number" className="tiq-input" value={lowT} min={0} max={100}
                    onChange={e => setLowT(Number(e.target.value))} />
                </div>
                <div className="tiq-form-group">
                  <label className="tiq-label">High Threshold (Qualified)</label>
                  <input type="number" className="tiq-input" value={highT} min={0} max={100}
                    onChange={e => setHighT(Number(e.target.value))} />
                </div>
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                Score ≥ {highT}% → Qualified · {lowT}–{highT}% → Review · &lt;{lowT}% → Not Qualified
              </div>
            </div>
          </div>

          <div style={{ textAlign: "center" }}>
            <button className="tiq-btn tiq-btn-primary"
              style={{ padding: "12px 40px", fontSize: 15, justifyContent: "center" }}
              onClick={() => runMut.mutate()}
              disabled={runState.status === "pending" || (!jdText.trim() && !jdFile) || !cvFiles?.length}>
              {runState.status === "pending"
                ? <><span className="tiq-spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Analysing CVs…</>
                : <><Sparkles size={16} /> Run JobLens Analysis</>}
            </button>
            {runState.status === "pending" && (
              <div style={{ marginTop: 12, fontSize: 13, color: "var(--text-muted)" }}>
                Extracting text, scoring CVs… This keeps running even if you switch to another page.
              </div>
            )}
            {runState.status === "error" && (
              <div className="tiq-alert tiq-alert-error" style={{ marginTop: 12, maxWidth: 500, margin: "12px auto 0" }}>
                {(runState.error as any)?.response?.data?.detail || "Analysis failed"}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "history" && (
        <div>
          {activeSession ? (
            <div>
              {/* Summary */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
                {[
                  { label: "Total Candidates", value: candidates.length, color: "var(--text-primary)", icon: Users },
                  { label: "Qualified", value: qualified, color: "#10b981", icon: CheckCircle },
                  { label: "Review", value: review, color: "#f59e0b", icon: Clock },
                  { label: "Shortlisted", value: shortlisted, color: "var(--violet-500)", icon: Star },
                ].map(({ label, value, color, icon: Icon }) => (
                  <div key={label} className="tiq-card" style={{ textAlign: "center", padding: "16px 12px" }}>
                    <Icon size={18} color={color} style={{ margin: "0 auto 6px" }} />
                    <div style={{ fontSize: 28, fontWeight: 900, color }}>{value}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</div>
                  </div>
                ))}
              </div>

              {activeSession.ai_powered && (
                <div className="tiq-alert tiq-alert-success tiq-mb-4" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Sparkles size={14} /> AI-powered scoring by Groq LLM
                </div>
              )}

              {/* JD Summary */}
              {activeSession.jd_text && (
                <div className="tiq-card tiq-mb-4" style={{ borderLeft: "4px solid var(--violet-500)" }}>
                  <div className="tiq-card-title" style={{ fontSize: 12, marginBottom: 12 }}>Job Description Summary</div>
                  {(() => {
                    const jd = activeSession.jd_text || "";
                    // Extract role — first meaningful line
                    const lines = jd.split("\n").map((l: string) => l.trim()).filter(Boolean);
                    const roleMatch = jd.match(/(?:job\s*title|role|position)\s*[:\-]\s*(.+)/i);
                    const role = roleMatch ? roleMatch[1].trim() : lines[0]?.slice(0, 80);
                    // Extract location
                    const locMatch = jd.match(/(?:location|based\s*in|located\s*in)\s*[:\-]\s*(.+)/i);
                    const location = locMatch ? locMatch[1].trim().split("\n")[0] : "";
                    // Extract company
                    const compMatch = jd.match(/(?:company|organisation|employer|about\s+us)\s*[:\-]\s*(.+)/i);
                    const company = compMatch ? compMatch[1].trim().split("\n")[0] : "";
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {role && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 60, flexShrink: 0 }}>ROLE</span>
                            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{role}</span>
                          </div>
                        )}
                        {location && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 60, flexShrink: 0 }}>LOCATION</span>
                            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{location}</span>
                          </div>
                        )}
                        {company && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 60, flexShrink: 0 }}>COMPANY</span>
                            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{company}</span>
                          </div>
                        )}
                        {(activeSession.jd_skills || []).length > 0 && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 60, flexShrink: 0, paddingTop: 2 }}>SKILLS</span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                              {(activeSession.jd_skills || []).slice(0, 25).map((s: string) => (
                                <span key={s} className="tiq-badge tiq-badge-violet" style={{ fontSize: 10 }}>{s}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}

              {/* Table — full pane width */}
              <div className="tiq-card" style={{ padding: 0 }}>
                <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>
                    Ranked Candidates
                    <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 400, marginLeft: 8 }}>
                      Threshold: {activeSession.low_threshold}% / {activeSession.high_threshold}%
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" onClick={() => refetchSession()}>
                      <RefreshCw size={12} />
                    </button>
                    <button className="tiq-btn tiq-btn-outline tiq-btn-sm"
                      onClick={() => exportMut.mutate(activeSessionId!)} disabled={exportMut.isPending}>
                      <Download size={12} /> Export Excel
                    </button>
                  </div>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="tiq-table" style={{ minWidth: 1100, width: "100%" }}>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Candidate</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Resume Summary</th>
                        <th>ATS Score</th>
                        <th>Key Strength</th>
                        <th>Considerations</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((c, i) => (
                        <CandidateRow
                          key={c.id}
                          c={c}
                          rank={i + 1}
                          sessionId={activeSessionId!}
                          lowT={activeSession.low_threshold}
                          highT={activeSession.high_threshold}
                          onRefresh={refetchSession}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="tiq-card">
              <div className="tiq-empty">
                <Users size={44} color="var(--violet-500)" style={{ opacity: .4 }} />
                <div className="tiq-empty-title">Select a Session</div>
                <div style={{ fontSize: 13 }}>
                  {sessions.length > 0
                    ? "Choose a session from the dropdown above, or run a new analysis."
                    : "No sessions yet — run a new analysis to get started."}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}