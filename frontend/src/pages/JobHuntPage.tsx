import { } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Search, Target, Download, ExternalLink, ChevronDown, ChevronUp, FileText, Trash2 } from "lucide-react";
import { jobhuntApi, downloadBlob } from "../lib/api";
import { useLatestMutation } from "../hooks/useLatestMutation";

export default function JobHunterPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"search" | "matches">("search");
  const [expandedJob, setExpandedJob] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Resume
  const { data: resumes = [] } = useQuery({ queryKey: ["resumes"], queryFn: jobhuntApi.listResumes });
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => jobhuntApi.uploadResume(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      setSelectedResumeId(data.id);
    },
  });

  // Job search form
  const [searchForm, setSearchForm] = useState({
    role: "", location: "", job_type: "All",
    salary_min: "", salary_max: "", industry: "",
  });
  const searchMutation = useMutation({
    mutationKey: ["jobhunt-search"],
    mutationFn: () => jobhuntApi.searchJobs({
      ...searchForm,
      salary_min: searchForm.salary_min ? parseInt(searchForm.salary_min) : null,
      salary_max: searchForm.salary_max ? parseInt(searchForm.salary_max) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });

  // Shared-cache view of the same mutation — lets the search survive the
  // user switching to another agent page while jobs are still being
  // scraped, and shows the result here again whenever they come back,
  // regardless of which mount originally triggered it.
  const searchState = useLatestMutation<any>(["jobhunt-search"]);
  const currentSearch = searchState.status === "success" ? searchState.data ?? null : null;

  // Match
  const deleteMutation = useMutation({
    mutationFn: (id: number) => jobhuntApi.deleteSearch(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["searches"] }),
  });

  const deleteAllMutation = useMutation({
    mutationFn: () => jobhuntApi.deleteAllSearches(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["searches"] }),
  });

  const matchMutation = useMutation({
    mutationKey: ["jobhunt-match"],
    mutationFn: () => jobhuntApi.matchResume({ resume_id: selectedResumeId!, search_id: currentSearch!.id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["matches"] });
      setTab("matches");
    },
  });

  const matchState = useLatestMutation<any>(["jobhunt-match"]);
  const lastSeenMatch = useRef<number | null>(null);
  useEffect(() => {
    if (matchState.status === "success" && matchState.submittedAt && matchState.submittedAt !== lastSeenMatch.current) {
      lastSeenMatch.current = matchState.submittedAt;
      qc.invalidateQueries({ queryKey: ["matches"] });
      setTab("matches");
    }
  }, [matchState.status, matchState.submittedAt, qc]);

  const { data: matches = [], isLoading: matchLoading } = useQuery({
    queryKey: ["matches"],
    queryFn: jobhuntApi.listMatches,
  });

  const exportMutation = useMutation({
    mutationFn: (searchId: number) => jobhuntApi.exportExcel(searchId),
    onSuccess: (blob, searchId) => downloadBlob(blob, `job_matches_${searchId}.xlsx`),
  });

  const setF = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setSearchForm((f) => ({ ...f, [k]: e.target.value }));

  const jobs = currentSearch?.jobs || [];

  return (
    <div>
      <div className="tiq-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <h1 className="tiq-page-title">JobHunter Agent</h1>
        <p className="tiq-page-sub">Search live jobs, match your resume, generate cover letters</p>
      </div>

      {/* TABS */}
      <div className="tiq-tabs">
        <button className={`tiq-tab${tab === "search" ? " active" : ""}`} onClick={() => setTab("search")}>
          Search & Match
        </button>
        <button className={`tiq-tab${tab === "matches" ? " active" : ""}`} onClick={() => setTab("matches")}>
          My Matches ({matches.length})
        </button>
      </div>

      {tab === "search" && (
        <div>
          {/* RESUME UPLOAD */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <FileText size={16} /> Resume
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              {resumes.length > 0 && (
                <select
                  className="tiq-input tiq-select"
                  style={{ maxWidth: 260 }}
                  value={selectedResumeId || ""}
                  onChange={(e) => setSelectedResumeId(Number(e.target.value))}
                >
                  <option value="">Select a resume</option>
                  {resumes.map((r: any) => (
                    <option key={r.id} value={r.id}>
                      {r.filename}
                    </option>
                  ))}
                </select>
              )}
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadMutation.mutate(f);
                }}
              />
              <button className="tiq-btn tiq-btn-outline" onClick={() => fileRef.current?.click()}
                disabled={uploadMutation.isPending}>
                <Upload size={14} />
                {uploadMutation.isPending ? "Uploading…" : "Upload resume"}
              </button>
              {uploadMutation.isSuccess && (
                <span className="tiq-badge tiq-badge-teal">✓ Uploaded</span>
              )}
            </div>
            {selectedResumeId && resumes.find((r: any) => r.id === selectedResumeId) && (
              <div style={{ marginTop: 12, padding: "10px 14px", background: "var(--slate-100)", borderRadius: 8, fontSize: 13 }}>
                <strong>Skills detected:</strong>{" "}
                {resumes.find((r: any) => r.id === selectedResumeId)?.skills?.slice(0, 8).join(", ") || "—"}
              </div>
            )}
          </div>

          {/* SEARCH FORM */}
          <div className="tiq-card tiq-mb-6">
            <div className="tiq-card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Search size={16} /> Search jobs
            </div>
            <div className="tiq-grid-3" style={{ marginBottom: 16 }}>
              <div className="tiq-form-group">
                <label className="tiq-label">Role / Title *</label>
                <input className="tiq-input" value={searchForm.role} onChange={setF("role")} placeholder="e.g. Data Analyst" />
              </div>
              <div className="tiq-form-group">
                <label className="tiq-label">Location</label>
                <input className="tiq-input" value={searchForm.location} onChange={setF("location")} placeholder="e.g. Sydney" />
              </div>
              <div className="tiq-form-group">
                <label className="tiq-label">Job Type</label>
                <select className="tiq-input tiq-select" value={searchForm.job_type} onChange={setF("job_type")}>
                  {["All", "full-time", "part-time", "contract", "casual"].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="tiq-form-group">
                <label className="tiq-label">Min Salary ($)</label>
                <input className="tiq-input" type="number" value={searchForm.salary_min} onChange={setF("salary_min")} placeholder="e.g. 80000" />
              </div>
              <div className="tiq-form-group">
                <label className="tiq-label">Max Salary ($)</label>
                <input className="tiq-input" type="number" value={searchForm.salary_max} onChange={setF("salary_max")} placeholder="e.g. 140000" />
              </div>
              <div className="tiq-form-group">
                <label className="tiq-label">Industry</label>
                <input className="tiq-input" value={searchForm.industry} onChange={setF("industry")} placeholder="e.g. Technology" />
              </div>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                className="tiq-btn tiq-btn-primary"
                onClick={() => searchMutation.mutate()}
                disabled={!searchForm.role || searchState.status === "pending"}
              >
                <Search size={14} />
                {searchState.status === "pending" ? "Searching…" : "Search jobs"}
              </button>
              {currentSearch && selectedResumeId && (
                <button
                  className="tiq-btn tiq-btn-outline"
                  onClick={() => matchMutation.mutate()}
                  disabled={matchState.status === "pending"}
                >
                  <Target size={14} />
                  {matchState.status === "pending" ? "Matching…" : "Match my resume"}
                </button>
              )}
              {currentSearch && (
                <button
                  className="tiq-btn tiq-btn-ghost"
                  onClick={() => exportMutation.mutate(currentSearch.id)}
                  disabled={exportMutation.isPending}
                >
                  <Download size={14} />
                  Export Excel
                </button>
              )}
            </div>
            {searchState.status === "pending" && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
                This keeps running even if you switch to another page.
              </div>
            )}
            {searchState.status === "error" && (
              <div className="tiq-alert tiq-alert-error" style={{ marginTop: 12 }}>
                Search failed: {(searchState.error as any)?.response?.data?.detail || (searchState.error as any)?.message || "Unknown error. Check the backend logs."}
              </div>
            )}
            {uploadMutation.isError && (
              <div className="tiq-alert tiq-alert-error" style={{ marginTop: 12 }}>
                Resume upload failed: {(uploadMutation.error as any)?.response?.data?.detail || (uploadMutation.error as any)?.message || "Unsupported file type or server error."}
              </div>
            )}
          </div>

          {/* JOB RESULTS */}
          {currentSearch?.notice && (
            <div className="tiq-alert tiq-alert-warning" style={{ marginBottom: 12 }}>
              {currentSearch.notice}
            </div>
          )}
          {jobs.length > 0 && (
            <div className="tiq-card">
              <div className="tiq-card-title">
                {jobs.length} jobs found for "{currentSearch?.role}"
              </div>
              {jobs.map((job: any) => (
                <div key={job.id} style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-display)" }}>
                        {job.title}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 3 }}>
                        {job.company} · {job.location} · {job.job_type}
                      </div>
                      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                        <span className="tiq-badge tiq-badge-slate">{job.source}</span>
                        <span className="tiq-badge tiq-badge-slate">{job.published_date}</span>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      {job.apply_link && (
                        <a href={job.apply_link} target="_blank" rel="noopener noreferrer"
                          className="tiq-btn tiq-btn-primary tiq-btn-sm">
                          <ExternalLink size={12} /> Apply
                        </a>
                      )}
                      <button className="tiq-btn tiq-btn-ghost tiq-btn-sm"
                        onClick={() => setExpandedJob(expandedJob === job.id ? null : job.id)}>
                        {expandedJob === job.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </div>
                  </div>
                  {expandedJob === job.id && (
                    <div style={{ marginTop: 12, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.7,
                      background: "var(--slate-100)", padding: "12px 14px", borderRadius: 8 }}>
                      {job.description?.slice(0, 600) || "No description available."}
                      {(job.description?.length || 0) > 600 && "…"}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "matches" && (
        <div>
          {matchLoading ? (
            <div className="tiq-spinner-wrap"><div className="tiq-spinner" /></div>
          ) : matches.length === 0 ? (
            <div className="tiq-empty">
              <Target size={40} />
              <div className="tiq-empty-title">No matches yet</div>
              <div>Search for jobs and click "Match my resume" to see scored results here</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {matches.map((m: any) => (
                <div key={m.id} className="tiq-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "var(--font-display)", marginBottom: 4 }}>
                        {m.job_title}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                        {m.company} · {m.location}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "var(--font-display)",
                        color: m.ats_score >= 70 ? "var(--teal-500)" : m.ats_score >= 50 ? "#f59e0b" : "#f43f5e" }}>
                        {m.ats_score}%
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>ATS Score</div>
                    </div>
                  </div>

                  <div className="tiq-score-bar" style={{ marginTop: 12, marginBottom: 16 }}>
                    <div className="tiq-score-bar-fill" style={{ width: `${m.ats_score}%`,
                      background: m.ats_score >= 70 ? "linear-gradient(90deg, #00c7b7, #5ee8db)" :
                        m.ats_score >= 50 ? "linear-gradient(90deg, #f59e0b, #fcd34d)" : "linear-gradient(90deg, #f43f5e, #fb7185)" }} />
                  </div>

                  <div className="tiq-grid-2" style={{ gap: 16, marginBottom: 16 }}>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                        Strengths
                      </div>
                      {m.strengths?.slice(0, 4).map((s: string, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4, display: "flex", gap: 6, alignItems: "flex-start" }}>
                          <span style={{ color: "var(--teal-500)", flexShrink: 0 }}>✓</span> {s}
                        </div>
                      ))}
                    </div>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                        Gaps to address
                      </div>
                      {m.improvements?.slice(0, 3).map((s: string, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4, display: "flex", gap: 6, alignItems: "flex-start" }}>
                          <span style={{ color: "#f59e0b", flexShrink: 0 }}>△</span> {s}
                        </div>
                      ))}
                    </div>
                  </div>

                  {m.cover_letter && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", color: "var(--teal-500)", marginBottom: 8 }}>
                        View cover letter
                      </summary>
                      <div className="tiq-cover-letter">{m.cover_letter}</div>
                    </details>
                  )}

                  <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                    {m.apply_link && (
                      <a href={m.apply_link} target="_blank" rel="noopener noreferrer"
                        className="tiq-btn tiq-btn-primary tiq-btn-sm">
                        <ExternalLink size={12} /> Apply
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}