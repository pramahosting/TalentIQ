import { } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLatestMutation } from "../hooks/useLatestMutation";
import {
  Users, Upload, FileText, Play, Download, ChevronDown, ChevronUp,
  CheckCircle, Clock, XCircle, Star, Video, RefreshCw, Sparkles, BarChart2,
  Trash2, Mail, Building2 } from "lucide-react";
import { api } from "../lib/api";
import JDManagementTab from "../components/candidatetrack/JDManagementTab";
import VendorManagementTab from "../components/candidatetrack/VendorManagementTab";
import CandidateTrackingTab from "../components/candidatetrack/CandidateTrackingTab";
import ClientManagementTab from "../components/candidatetrack/ClientManagementTab";

// Fetches a protected file (video/resume) via the authenticated axios
// client — a plain <a href> wouldn't carry the Bearer token, since that's
// sent as a header, not a cookie — then opens it in a new tab as a blob URL.
async function openBlobInNewTab(url: string, fallbackType?: string) {
  try {
    const res = await api.get(url, { responseType: "blob" });
    const blob = fallbackType ? new Blob([res.data], { type: fallbackType }) : res.data;
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, "_blank");
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch {
    alert("Could not load the file.");
  }
}
import HistoryDropdown from "../components/HistoryDropdown";

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
  getMorphcastKey: () =>
    api.get(`/api/joblens/morphcast-key`).then(r => r.data),
  markContacted: (cid: number) =>
    api.post(`/api/joblens/candidates/${cid}/mark-contacted`).then(r => r.data),
  uploadVideo: (cid: number, blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "interview.webm");
    return api.post(`/api/joblens/candidates/${cid}/video`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then(r => r.data);
  },
  reanalyzeVideo: (cid: number) =>
    api.post(`/api/joblens/candidates/${cid}/reanalyze-video`).then(r => r.data),
  jdOptions: () =>
    api.get(`/api/joblens/jd-options`).then(r => r.data),
  vendorCandidates: (jdId: number) =>
    api.get(`/api/joblens/vendor-candidates`, { params: { jd_id: jdId } }).then(r => r.data),
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

// License key is fetched at runtime from Settings > API Keys (service:
// morphcast) via jobLensApi.getMorphcastKey() — MorphCast's SDK now
// requires a real key on every load, there's no keyless trial mode.

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
  onClose: () => void; onDone: (emotions: any, videoBlob: Blob | null) => void;
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
  const [licenseKey, setLicenseKey] = useState("");
  const [keyChecked, setKeyChecked] = useState(false);

  // Fetch the recruiter's MorphCast key as soon as the modal mounts, so
  // it's ready by the time Start Interview triggers initMorphcast().
  useEffect(() => {
    jobLensApi.getMorphcastKey()
      .then(r => setLicenseKey(r.license_key || ""))
      .catch(() => setLicenseKey(""))
      .finally(() => setKeyChecked(true));
  }, []);

  // Keep ref in sync so the MorphCast event handler (closure) sees current value
  isRecordingRef.current = recording;

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" }, audio: true,
      });
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      setStarted(true);
      // Record the WHOLE interview as a single continuous MediaRecorder
      // session (started once, stopped once) — starting/stopping a new
      // recorder per-question would produce several independent WebM
      // fragments that can't simply be concatenated into one playable file.
      try {
        const mr = new MediaRecorder(stream, { mimeType: "video/webm" });
        mediaRef.current = mr;
        chunksRef.current = [];
        mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
        mr.start();
      } catch { /* MediaRecorder unsupported — emotion AI + timer still work */ }
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
    if (keyChecked && !licenseKey) {
      setMcStatus("Emotion AI not configured (add a free MorphCast license key in Settings > API Keys) — interview will continue without facial analysis.");
      return;
    }
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
      if (licenseKey) loader = loader.licenseKey(licenseKey);

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
    // Actual video capture already started once in startCamera() and runs
    // continuously for the whole interview — this just drives the
    // per-question UI (timer, REC indicator).
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
    setRecording(false);
    speechSynthesis.cancel();
    try { await engineRef.current?.stop?.(); await engineRef.current?.destroy?.(); } catch {}

    // Stop the single continuous recorder and wait for it to fully flush
    // its last chunk (fires asynchronously) before building the final blob.
    const videoBlob: Blob | null = await new Promise(resolve => {
      const mr = mediaRef.current;
      if (!mr || mr.state === "inactive") {
        resolve(chunksRef.current.length ? new Blob(chunksRef.current, { type: "video/webm" }) : null);
        return;
      }
      mr.onstop = () => {
        resolve(chunksRef.current.length ? new Blob(chunksRef.current, { type: "video/webm" }) : null);
      };
      mr.stop();
    });

    const tracks = (videoRef.current?.srcObject as MediaStream)?.getTracks?.() || [];
    tracks.forEach(t => t.stop());

    const emotions = samples > 0
      ? { ...avgAgg, dominant }
      : { happy: 0, neutral: 100, sad: 0, angry: 0, disgust: 0, fear: 0, surprise: 0, dominant: "Neutral" };
    onDone(emotions, videoBlob);
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

        {started && (
          <div style={{ fontSize: 11, color: mcReady ? "#0d9488" : "#6b7280", marginTop: 8 }}>
            {mcStatus}
          </div>
        )}

        {started && (
          <div style={{ margin: "16px 0", padding: 14, background: "#f3f4f6", borderRadius: 10, borderLeft: "4px solid #0d9488" }}>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Question {qIdx + 1} / {questions.length}</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "#111827" }}>{currentQ}</div>
          </div>
        )}

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
type PopoverState = { kind: PopoverKind; x: number; y: number; width: number } | null;

function CandidateRow({
  c, rank, sessionId, lowT, highT, onRefresh, theadRef
}: { c: any; rank: number; sessionId: number; lowT: number; highT: number; onRefresh: () => void; theadRef: React.RefObject<HTMLTableSectionElement> }) {
  const [expanded, setExpanded] = useState(false);
  const [interviewOpen, setInterviewOpen] = useState(false);
  const [questions, setQuestions] = useState<string[]>(c.interview_questions || []);
  const [genLoading, setGenLoading] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contacted, setContacted] = useState(!!c.contacted);
  const [inviteToken, setInviteToken] = useState<string | null>(c.interview_token || null);
  const [preparingInvite, setPreparingInvite] = useState(false);
  const [popover, setPopover] = useState<PopoverState>(null);
  const [showTranscript, setShowTranscript] = useState(false);

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

  const reanalyzeMut = useMutation({
    mutationFn: () => jobLensApi.reanalyzeVideo(c.id),
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

  const handleInterviewDone = async (emotions: any, videoBlob: Blob | null) => {
    await jobLensApi.saveInterviewResult(c.id, emotions);
    if (videoBlob) {
      try { await jobLensApi.uploadVideo(c.id, videoBlob); } catch { /* score/result already saved; video upload failure is non-fatal */ }
    }
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
    const cell = (e.currentTarget as HTMLElement).closest("td");
    const cellRect = cell?.getBoundingClientRect();
    const headerBottom = theadRef.current?.getBoundingClientRect().bottom;
    if (!cellRect) return;
    setPopover({
      kind,
      x: cellRect.left,
      y: headerBottom ?? cellRect.bottom + 6,
      width: cellRect.width,
    });
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
        <td style={{ fontSize: 12 }}>{c.source_vendor_name || "—"}</td>

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
          <td colSpan={11} style={{ padding: "14px 20px", background: "var(--bg-secondary)" }}>
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
                <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                  {c.has_video && (
                    <button type="button" onClick={() => openBlobInNewTab(`/api/joblens/candidates/${c.id}/video`, "video/webm")}
                      style={{ background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", fontSize: 11, color: "var(--teal-500)" }}>
                      ▶ View recorded video
                    </button>
                  )}
                  {c.has_resume_file && (
                    <button type="button" onClick={() => openBlobInNewTab(`/api/joblens/candidates/${c.id}/resume-file`)}
                      style={{ background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", fontSize: 11, color: "var(--teal-500)" }}>
                      📄 View original resume
                    </button>
                  )}
                </div>
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

            {/* AI Video Interview Analysis — auto-generated after the video uploads */}
            {c.has_video && (
              <div style={{ marginBottom: 16, paddingBottom: 14, borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                    AI Video Interview Analysis
                  </div>
                  <button className="tiq-btn tiq-btn-ghost tiq-btn-sm" style={{ fontSize: 10 }}
                    disabled={c.video_analysis_status === "Pending" || c.video_analysis_status === "Processing" || reanalyzeMut.isPending}
                    onClick={() => reanalyzeMut.mutate()}>
                    <RefreshCw size={10} /> {reanalyzeMut.isPending ? "Queuing…" : "Re-run Video Analysis"}
                  </button>
                </div>
                {(c.video_analysis_status === "Pending" || c.video_analysis_status === "Processing") && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
                    <span className="tiq-spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                    {c.video_analysis_status === "Processing" ? "Transcribing and analysing…" : "Queued for analysis…"}
                  </div>
                )}
                {c.video_analysis_status === "Failed" && (
                  <div style={{ fontSize: 12, color: "var(--rose-500)" }}>
                    Analysis failed{c.video_analysis?.error ? `: ${c.video_analysis.error}` : "."}
                  </div>
                )}
                {c.video_analysis_status === "Completed" && c.video_analysis && (
                  <div>
                    <div style={{ display: "flex", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
                      {[
                        ["Overall", c.video_analysis.overall_score, "var(--violet-500)"],
                        ["Communication", c.video_analysis.communication_score, "#0d9488"],
                        ["Relevance", c.video_analysis.relevance_score, "#0d9488"],
                        ["Confidence", c.video_analysis.confidence_score, "#0d9488"],
                      ].map(([label, val, color]: any) => (
                        <div key={label} style={{ textAlign: "center" }}>
                          <div style={{ fontSize: 18, fontWeight: 800, color }}>{val ?? "—"}</div>
                          <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{label}</div>
                        </div>
                      ))}
                    </div>
                    {c.video_analysis.summary && (
                      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10, lineHeight: 1.6 }}>
                        {c.video_analysis.summary}
                      </p>
                    )}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      {c.video_analysis.strengths?.length > 0 && (
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--teal-500)", marginBottom: 4 }}>STRENGTHS</div>
                          <ul style={{ margin: 0, paddingLeft: 14, fontSize: 12 }}>
                            {c.video_analysis.strengths.map((s: string, i: number) => <li key={i}>{s}</li>)}
                          </ul>
                        </div>
                      )}
                      {c.video_analysis.concerns?.length > 0 && (
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--rose-500)", marginBottom: 4 }}>CONCERNS</div>
                          <ul style={{ margin: 0, paddingLeft: 14, fontSize: 12 }}>
                            {c.video_analysis.concerns.map((s: string, i: number) => <li key={i}>{s}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                    {c.video_transcript && (
                      <button type="button" onClick={() => setShowTranscript(t => !t)}
                        style={{ marginTop: 10, background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 11, color: "var(--teal-500)" }}>
                        {showTranscript ? "Hide full transcript ▲" : "View full transcript ▼"}
                      </button>
                    )}
                    {showTranscript && c.video_transcript && (
                      <div style={{ marginTop: 8, padding: 10, background: "var(--bg-secondary)", borderRadius: 8, fontSize: 12, lineHeight: 1.6, maxHeight: 240, overflowY: "auto", whiteSpace: "pre-wrap" }}>
                        {c.video_transcript}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

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
        <AnchoredPopover x={popover.x} y={popover.y} width={popover.width} onClose={() => setPopover(null)}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>Full Resume Summary</div>
          <ol style={{ margin: 0, paddingLeft: 16, fontSize: 11, lineHeight: 1.6 }}>
            {resumeSummary.map((s, i) => <li key={i} style={{ marginBottom: 4 }}>{s}</li>)}
          </ol>
        </AnchoredPopover>
      )}

      {popover?.kind === "matched" && (
        <AnchoredPopover x={popover.x} y={popover.y} width={popover.width} onClose={() => setPopover(null)}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 8 }}>All Key Strengths</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(c.matched_skills || []).map((s: string) => (
              <span key={s} style={{ background: "#0d9488", color: "#fff", fontSize: 10, padding: "3px 8px", borderRadius: 999 }}>{s}</span>
            ))}
          </div>
        </AnchoredPopover>
      )}

      {popover?.kind === "missing" && (
        <AnchoredPopover x={popover.x} y={popover.y} width={popover.width} onClose={() => setPopover(null)}>
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

  // New Analysis: optional sourcing from JD Management + Vendor Management,
  // additive to the original paste/upload flow (which stays default/unchanged).
  const [jdSource, setJdSource] = useState<"upload" | "jdManagement">("upload");
  const [selectedJdRecordId, setSelectedJdRecordId] = useState<number | "">("");
  const [cvSource, setCvSource] = useState<"upload" | "vendor">("upload");
  const [selectedVendorCandidateIds, setSelectedVendorCandidateIds] = useState<number[]>([]);

  const { data: jdOptions = [] } = useQuery({
    queryKey: ["joblens-jd-options"],
    queryFn: jobLensApi.jdOptions,
    enabled: jdSource === "jdManagement",
  });
  const { data: vendorCandidateOptions = [] } = useQuery({
    queryKey: ["joblens-vendor-candidates", selectedJdRecordId],
    queryFn: () => jobLensApi.vendorCandidates(selectedJdRecordId as number),
    enabled: cvSource === "vendor" && !!selectedJdRecordId,
  });
  const [lowT, setLowT] = useState(40);
  const [highT, setHighT] = useState(70);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [tab, setTab] = useState<"new"|"history"|"management">("new");
  const [managementView, setManagementView] = useState<"clients"|"jds"|"vendors"|"tracking">("clients");
  const jdFileRef = useRef<HTMLInputElement>(null);
  const cvFileRef = useRef<HTMLInputElement>(null);
  const theadRef = useRef<HTMLTableSectionElement>(null);

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
    // Automatic video analysis runs in the background after upload — poll
    // while any candidate is still Pending/Processing so the result shows
    // up without the user needing to manually hit Refresh.
    refetchInterval: (query) => {
      const candidates = (query.state.data as any)?.candidates || [];
      const stillWorking = candidates.some((c: any) =>
        c.video_analysis_status === "Pending" || c.video_analysis_status === "Processing"
      );
      return stillWorking ? 5000 : false;
    },
  });

  const runMut = useMutation({
    mutationKey: ["joblens-run"],
    mutationFn: () => {
      const form = new FormData();
      form.append("jd_text", jdSource === "upload" ? jdText : "");
      form.append("low_threshold", String(lowT));
      form.append("high_threshold", String(highT));
      if (jdSource === "upload" && jdFile) form.append("jd_file", jdFile);
      if (jdSource === "jdManagement" && selectedJdRecordId) form.append("jd_record_id", String(selectedJdRecordId));
      if (cvSource === "upload" && cvFiles) for (let i = 0; i < cvFiles.length; i++) form.append("cv_files", cvFiles[i]);
      if (cvSource === "vendor" && selectedVendorCandidateIds.length) form.append("source_candidate_ids", selectedVendorCandidateIds.join(","));
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
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div className="tiq-tabs">
            <button className={`tiq-tab${tab === "management" ? " active" : ""}`} onClick={() => setTab("management")}>
              <Building2 size={12} style={{ display: "inline", marginRight: 6 }} /> Management
            </button>
            <button className={`tiq-tab${tab === "new" ? " active" : ""}`} onClick={() => setTab("new")}>
              <Play size={12} style={{ display: "inline", marginRight: 6 }} /> New Analysis
            </button>
            <button className={`tiq-tab${tab === "history" ? " active" : ""}`} onClick={() => setTab("history")}>
              <BarChart2 size={12} style={{ display: "inline", marginRight: 6 }} /> Results
              {sessions.length > 0 && <span className="tiq-badge tiq-badge-slate" style={{ marginLeft: 8, fontSize: 10 }}>{sessions.length}</span>}
            </button>
          </div>

          {tab === "history" && sessions.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, maxWidth: 380, width: "100%" }}>
            <HistoryDropdown
              value={activeSessionId}
              onChange={id => setActiveSessionId(id as number | null)}
              options={sessions.map((s: any) => ({
                id: s.id,
                label: `Session #${s.sequence_number || s.id} · ${s.cv_count} CVs · ${new Date(s.created_at).toLocaleDateString()}`,
              }))}
              onDelete={id => deleteMutation.mutate(id as number)}
              placeholder="Select a session…"
              confirmDeleteMessage="Delete this session?"
            />
          </div>
          )}
        </div>

        {tab === "management" && (
          <select className="tiq-input" style={{ maxWidth: 260 }}
            value={managementView}
            onChange={e => setManagementView(e.target.value as typeof managementView)}>
            <option value="clients">Client Management</option>
            <option value="jds">JD Management</option>
            <option value="vendors">Vendor Management</option>
            <option value="tracking">Candidate Tracking</option>
          </select>
        )}
      </div>

      {tab === "management" && managementView === "clients" && <ClientManagementTab />}
      {tab === "management" && managementView === "jds" && <JDManagementTab />}
      {tab === "management" && managementView === "vendors" && <VendorManagementTab />}
      {tab === "management" && managementView === "tracking" && <CandidateTrackingTab />}

      {tab === "new" && (
        <div style={{ maxWidth: 900 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
            {/* JD */}
            <div className="tiq-card">
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FileText size={15} color="var(--violet-500)" /> Job Description
              </div>
              <div style={{ display: "flex", gap: 14, marginBottom: 12, fontSize: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
                  <input type="radio" checked={jdSource === "upload"} onChange={() => setJdSource("upload")} />
                  Paste / Upload
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
                  <input type="radio" checked={jdSource === "jdManagement"} onChange={() => setJdSource("jdManagement")} />
                  From JD Management
                </label>
              </div>

              {jdSource === "jdManagement" ? (
                <div className="tiq-form-group">
                  <label className="tiq-label">Select JD</label>
                  <select className="tiq-input" value={selectedJdRecordId}
                    onChange={e => { setSelectedJdRecordId(e.target.value ? Number(e.target.value) : ""); setSelectedVendorCandidateIds([]); }}>
                    <option value="">Select a JD…</option>
                    {jdOptions.map((j: any) => (
                      <option key={j.id} value={j.id}>{j.jd_title} — {j.client_name || "No client"}</option>
                    ))}
                  </select>
                  {jdOptions.length === 0 && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                      No JDs yet — create one in the JD Management tab first.
                    </div>
                  )}
                </div>
              ) : (
                <>
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
                </>
              )}
            </div>

            {/* CVs + Settings */}
            <div className="tiq-card">
              <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Users size={15} color="var(--teal-500)" /> CV Files & Thresholds
              </div>
              <div style={{ display: "flex", gap: 14, marginBottom: 12, fontSize: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
                  <input type="radio" checked={cvSource === "upload"} onChange={() => setCvSource("upload")} />
                  Upload Files
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: jdSource === "jdManagement" && selectedJdRecordId ? "pointer" : "not-allowed" }}>
                  <input type="radio" checked={cvSource === "vendor"} disabled={!(jdSource === "jdManagement" && selectedJdRecordId)}
                    onChange={() => setCvSource("vendor")} />
                  From Vendor Management
                </label>
              </div>

              {cvSource === "vendor" ? (
                <div style={{ marginBottom: 16 }}>
                  {!selectedJdRecordId ? (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Select a JD (from JD Management) on the left first.</div>
                  ) : vendorCandidateOptions.length === 0 ? (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No vendor-submitted candidates for this JD yet.</div>
                  ) : (
                    <div style={{ border: "1px solid var(--border)", borderRadius: 8, maxHeight: 220, overflowY: "auto", padding: 8 }}>
                      {vendorCandidateOptions.map((vc: any) => (
                        <label key={vc.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px", fontSize: 12, cursor: vc.has_resume ? "pointer" : "not-allowed", opacity: vc.has_resume ? 1 : 0.5 }}>
                          <input type="checkbox" disabled={!vc.has_resume}
                            checked={selectedVendorCandidateIds.includes(vc.id)}
                            onChange={e => setSelectedVendorCandidateIds(prev => e.target.checked ? [...prev, vc.id] : prev.filter(id => id !== vc.id))} />
                          <span style={{ flex: 1 }}>{vc.name}</span>
                          <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{vc.vendor_name}</span>
                          {!vc.has_resume && <span style={{ color: "var(--rose-500)", fontSize: 10 }}>No resume</span>}
                        </label>
                      ))}
                    </div>
                  )}
                  {selectedVendorCandidateIds.length > 0 && (
                    <div style={{ fontSize: 12, color: "var(--teal-500)", marginTop: 6, fontWeight: 600 }}>
                      {selectedVendorCandidateIds.length} candidate{selectedVendorCandidateIds.length > 1 ? "s" : ""} selected
                    </div>
                  )}
                </div>
              ) : (
                <>
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
                </>
              )}

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
              disabled={
                runState.status === "pending" ||
                (jdSource === "upload" ? (!jdText.trim() && !jdFile) : !selectedJdRecordId) ||
                (cvSource === "upload" ? !cvFiles?.length : selectedVendorCandidateIds.length === 0)
              }>
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

              {/* JD Summary — role/location/company extracted server-side
                  (LLM when available, filtered heuristic otherwise), not
                  guessed from raw text client-side. */}
              {activeSession.jd_text && (activeSession.jd_role || activeSession.jd_location || activeSession.jd_company || (activeSession.jd_skills || []).length > 0) && (
                <div className="tiq-card tiq-mb-4" style={{ borderLeft: "4px solid var(--violet-500)" }}>
                  <div className="tiq-card-title" style={{ fontSize: 12, marginBottom: 12 }}>Job Description Summary</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {activeSession.jd_role && (
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0 }}>JD TITLE</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{activeSession.jd_role}</span>
                      </div>
                    )}
                    {activeSession.jd_location && (
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0 }}>LOCATION</span>
                        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{activeSession.jd_location}</span>
                      </div>
                    )}
                    {(activeSession.jd_client_name || activeSession.jd_company) && (
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0 }}>CLIENT NAME</span>
                        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{activeSession.jd_client_name || activeSession.jd_company}</span>
                      </div>
                    )}

                    {(activeSession.jd_essential_skills?.length > 0 || activeSession.jd_good_to_have_skills?.length > 0 || activeSession.jd_optional_skills?.length > 0) ? (
                      <>
                        {activeSession.jd_essential_skills?.length > 0 && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "#ef4444", width: 90, flexShrink: 0, paddingTop: 2 }}>ESSENTIAL</span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {activeSession.jd_essential_skills.slice(0, 25).map((s: string) => (
                                <span key={s} className="tiq-badge" style={{ fontSize: 10, background: "#ef444420", color: "#ef4444" }}>{s}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {activeSession.jd_good_to_have_skills?.length > 0 && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "#f59e0b", width: 90, flexShrink: 0, paddingTop: 2 }}>GOOD TO HAVE</span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {activeSession.jd_good_to_have_skills.slice(0, 25).map((s: string) => (
                                <span key={s} className="tiq-badge" style={{ fontSize: 10, background: "#f59e0b20", color: "#f59e0b" }}>{s}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {activeSession.jd_optional_skills?.length > 0 && (
                          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0, paddingTop: 2 }}>OPTIONAL</span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {activeSession.jd_optional_skills.slice(0, 25).map((s: string) => (
                                <span key={s} className="tiq-badge tiq-badge-slate" style={{ fontSize: 10 }}>{s}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (activeSession.jd_skills || []).length > 0 && (
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", width: 90, flexShrink: 0, paddingTop: 2 }}>SKILLS</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {(activeSession.jd_skills || []).slice(0, 25).map((s: string) => (
                            <span key={s} className="tiq-badge tiq-badge-violet" style={{ fontSize: 10 }}>{s}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
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
                    <thead ref={theadRef}>
                      <tr>
                        <th>#</th>
                        <th>Candidate</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Vendor</th>
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
                          theadRef={theadRef}
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