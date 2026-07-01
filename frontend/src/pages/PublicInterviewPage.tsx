import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Video } from "lucide-react";

// Standalone axios instance — this page is intentionally public (no auth
// token, no session), reached only via the unguessable token in the URL.
const publicApi = axios.create({ baseURL: "", timeout: 60_000 });

declare global {
  interface Window { CY?: any; MphTools?: any; }
}

const MORPHCAST_LICENSE = "";

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

export default function PublicInterviewPage() {
  const { token } = useParams<{ token: string }>();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [candidateName, setCandidateName] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [alreadyDone, setAlreadyDone] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const engineRef = useRef<any>(null);
  const isRecordingRef = useRef(false);

  const [qIdx, setQIdx] = useState(0);
  const [recording, setRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [timeLeft, setTimeLeft] = useState(ANSWER_SECONDS);
  const [started, setStarted] = useState(false);
  const [finished, setFinished] = useState(false);
  const [mcReady, setMcReady] = useState(false);
  const [mcStatus, setMcStatus] = useState("Initialising camera & emotion AI…");
  const [agg, setAgg] = useState<EmotionAgg>({ ...EMPTY_EMO });
  const [avgAgg, setAvgAgg] = useState<EmotionAgg>({ ...EMPTY_EMO });
  const [samples, setSamples] = useState(0);
  const [dominant, setDominant] = useState("Neutral");

  isRecordingRef.current = recording;

  useEffect(() => {
    if (!token) return;
    publicApi.get(`/api/joblens/public/interview/${token}`)
      .then(r => {
        setCandidateName(r.data.candidate_name || "");
        setQuestions(r.data.questions || []);
        setAlreadyDone(r.data.video_status === "Completed");
      })
      .catch(() => setLoadError("This interview link is invalid or has expired. Please contact the recruiter for a new link."))
      .finally(() => setLoading(false));
  }, [token]);

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
      setMcStatus("Ready — please answer naturally.");
    } catch (e: any) {
      setMcStatus("Continuing without facial analysis (" + (e?.message || "init failed") + ").");
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
      mr.start();
    } catch { /* MediaRecorder unsupported — emotion AI + timer still work */ }
    setRecording(true);
    setTimeLeft(ANSWER_SECONDS);
  };

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

    try {
      await publicApi.post(`/api/joblens/public/interview/${token}/result`, emotions);
    } catch { /* still show the thank-you screen even if save failed */ }
    setFinished(true);
  };

  const pageWrap: React.CSSProperties = {
    minHeight: "100vh", background: "#ffffff", color: "#111827",
    display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
  };

  if (loading) {
    return <div style={pageWrap}>Loading interview…</div>;
  }

  if (loadError) {
    return (
      <div style={pageWrap}>
        <div style={{ textAlign: "center", maxWidth: 420 }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Link unavailable</div>
          <div style={{ color: "#6b7280" }}>{loadError}</div>
        </div>
      </div>
    );
  }

  if (finished) {
    return (
      <div style={pageWrap}>
        <div style={{ textAlign: "center", maxWidth: 420 }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#0d9488", marginBottom: 10 }}>
            ✅ Thank you, {candidateName}!
          </div>
          <div style={{ color: "#374151" }}>
            Your video interview has been submitted. The recruitment team will be in touch with next steps.
          </div>
        </div>
      </div>
    );
  }

  if (alreadyDone && !started) {
    return (
      <div style={pageWrap}>
        <div style={{ textAlign: "center", maxWidth: 420 }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Interview already completed</div>
          <div style={{ color: "#6b7280", marginBottom: 16 }}>
            You've already submitted this video interview. If you need to redo it, please contact the recruiter.
          </div>
          <button className="tiq-btn tiq-btn-outline" onClick={() => setAlreadyDone(false)}>
            Retake interview
          </button>
        </div>
      </div>
    );
  }

  const currentQ = questions[qIdx] || "Loading...";

  return (
    <div style={pageWrap}>
      <div style={{ background: "#ffffff", color: "#111827", borderRadius: 16, padding: 28, maxWidth: 760, width: "100%", boxShadow: "0 10px 40px rgba(0,0,0,.12)", border: "1px solid #e5e7eb" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <Video size={18} color="#ef4444" />
          <div style={{ fontWeight: 800, fontSize: 17 }}>Video Interview — {candidateName}</div>
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
          <div style={{ fontSize: 15, fontWeight: 600 }}>{currentQ}</div>
        </div>

        {recording && (
          <div style={{ textAlign: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 28, fontWeight: 900, color: "#ef4444" }}>{timeLeft}s</div>
            <div style={{ fontSize: 10, color: "#6b7280" }}>remaining</div>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
          {!started ? (
            <button className="tiq-btn tiq-btn-primary" onClick={startCamera}>
              <Video size={14} /> Start Interview
            </button>
          ) : (
            <button className="tiq-btn tiq-btn-outline" onClick={nextQuestion} disabled={isSpeaking}>
              {qIdx < questions.length - 1 ? "Next Question →" : "Finish Interview"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
