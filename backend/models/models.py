"""
TalentIQ – SQLAlchemy ORM Models
All tables prefixed tiq_ to coexist with AccFino on the same Neon database.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, Date, ForeignKey, JSON, LargeBinary, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.database import Base


# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "tiq_users"

    id                  = Column(Integer, primary_key=True, index=True)
    name                = Column(String(200))
    email               = Column(String(200), unique=True, index=True, nullable=False)
    password_hash       = Column(String(255))
    company             = Column(String(200))
    phone               = Column(String(50))
    address             = Column(Text)
    role                = Column(String(50), default="user")
    is_active           = Column(Boolean, default=True)
    reset_token         = Column(String(255))
    reset_token_expiry  = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login          = Column(DateTime)

    # Relationships
    api_keys          = relationship("UserAPIKey",      back_populates="user", cascade="all, delete-orphan")
    resumes           = relationship("Resume",          back_populates="user", cascade="all, delete-orphan")
    job_searches      = relationship("JobSearch",       back_populates="user", cascade="all, delete-orphan")
    job_matches       = relationship("JobMatch",        back_populates="user", cascade="all, delete-orphan")
    jobintel_runs     = relationship("JobIntelRun",     back_populates="user", cascade="all, delete-orphan")
    linklens_searches = relationship("LinkLensSearch",  back_populates="user", cascade="all, delete-orphan")
    audit_logs        = relationship("AuditLog",        back_populates="user", cascade="all, delete-orphan")
    joblens_sessions  = relationship("JobLensSession",  back_populates="user", cascade="all, delete-orphan")
    jd_documents      = relationship("JDDocument",      back_populates="user", cascade="all, delete-orphan")
    cvanalysis_records = relationship("CVAnalysisRecord", back_populates="user", cascade="all, delete-orphan")
    jd_records         = relationship("JDRecord",         back_populates="user", cascade="all, delete-orphan")
    vendors            = relationship("Vendor",           back_populates="user", cascade="all, delete-orphan")
    tracked_candidates = relationship("TrackedCandidate",  back_populates="user", cascade="all, delete-orphan")
    clients            = relationship("Client",            back_populates="user", cascade="all, delete-orphan")


class UserAPIKey(Base):
    __tablename__ = "tiq_user_api_keys"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    service    = Column(String(100), nullable=False)
    key_name   = Column(String(100), nullable=False)
    key_value  = Column(Text, nullable=False)
    is_global  = Column(Boolean, default=False, nullable=False)
    # is_global=True means this credential is a platform-wide fallback,
    # usable by every user — ONLY permitted for services in
    # utils.credentials.SHAREABLE_SERVICES (groq/ollama/adzuna), and only
    # settable by an admin. Enforced in routers/auth.py, not just here.
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class SkillTaxonomy(Base):
    """A persistent, continuously-growing bank of real skill/requirement
    terms — accumulated automatically from every successful LLM extraction
    (JD categorization, candidate strengths) across every module. Unlike a
    hand-maintained static skill list, this grows to reflect whatever
    terminology actually shows up in real JDs and resumes over time, and
    is used two ways: (1) fed back into future LLM prompts as a short
    "known terms" reference so extractions stay consistent with what's
    been seen before — especially valuable for a local/smaller Ollama
    model, which benefits more from concrete grounding than a larger
    hosted model does — and (2) used to strengthen the deterministic
    keyword-only fallback matcher, so even the last-resort path (no LLM
    available at all) gets more comprehensive over time instead of being
    permanently limited to one fixed, hand-written list."""
    __tablename__ = "tiq_skill_taxonomy"

    id            = Column(Integer, primary_key=True, index=True)
    skill_name    = Column(String(200), nullable=False, unique=True, index=True)  # normalized lowercase
    category      = Column(String(50), nullable=False)  # technical/business/soft/essential/certification
    frequency     = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at  = Column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
# JOBHUNT
# ══════════════════════════════════════════════════════════════════════════════

class Resume(Base):
    __tablename__ = "tiq_resumes"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    filename         = Column(String(255))
    raw_text         = Column(Text)
    applicant_name   = Column(String(200))
    skills           = Column(JSON)
    experience_years = Column(Float)
    education        = Column(Text)
    parsed_data      = Column(JSON)
    uploaded_at      = Column(DateTime, default=datetime.utcnow)

    user        = relationship("User",     back_populates="resumes")
    job_matches = relationship("JobMatch", back_populates="resume", cascade="all, delete-orphan")


class JobSearch(Base):
    __tablename__ = "tiq_job_searches"

    id            = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id       = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    role          = Column(String(200))
    location      = Column(String(200))
    industry      = Column(String(200))
    job_type      = Column(String(100))
    salary_min    = Column(Integer)
    salary_max    = Column(Integer)
    results_count = Column(Integer, default=0)
    searched_at   = Column(DateTime, default=datetime.utcnow)

    user = relationship("User",    back_populates="job_searches")
    jobs = relationship("Job",     back_populates="search", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "tiq_jobs"

    id             = Column(Integer, primary_key=True, index=True)
    search_id      = Column(Integer, ForeignKey("tiq_job_searches.id"), index=True, nullable=False)
    title          = Column(String(300))
    company        = Column(String(300))
    location       = Column(String(300))
    job_type       = Column(String(100))
    salary_min     = Column(Integer)
    salary_max     = Column(Integer)
    description    = Column(Text)
    requirements   = Column(JSON)
    source         = Column(String(100))
    apply_link     = Column(Text)
    published_date = Column(String(50))
    source_site    = Column(String(200))
    scraped_at     = Column(DateTime, default=datetime.utcnow)

    search  = relationship("JobSearch", back_populates="jobs")
    matches = relationship("JobMatch",  back_populates="job", cascade="all, delete-orphan")


class JobMatch(Base):
    __tablename__ = "tiq_job_matches"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    resume_id    = Column(Integer, ForeignKey("tiq_resumes.id"), index=True, nullable=False)
    job_id       = Column(Integer, ForeignKey("tiq_jobs.id"), index=True, nullable=False)
    ats_score    = Column(Float, default=0)
    strengths    = Column(JSON)
    improvements = Column(JSON)
    summary      = Column(JSON)
    strengths_breakdown = Column(JSON)  # technical/business/soft skills, experience, certs — see utils/llm_extraction.py
    jd_requirements     = Column(JSON)  # essential/good_to_have/optional
    cover_letter = Column(Text)
    matched_at   = Column(DateTime, default=datetime.utcnow)

    user   = relationship("User",   back_populates="job_matches")
    resume = relationship("Resume", back_populates="job_matches")
    job    = relationship("Job",    back_populates="matches")


# ══════════════════════════════════════════════════════════════════════════════
# JOBINTEL
# ══════════════════════════════════════════════════════════════════════════════

class JobIntelRun(Base):
    __tablename__ = "tiq_jobintel_runs"

    id                   = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id              = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    role                 = Column(String(200))
    location             = Column(String(200))
    industry             = Column(String(200))
    status               = Column(String(50), default="pending")
    total_jobs_scraped   = Column(Integer, default=0)
    insights             = Column(JSON)
    top_skills           = Column(JSON)
    top_tools            = Column(JSON)
    salary_stats         = Column(JSON)
    job_type_breakdown   = Column(JSON)
    company_type_breakdown = Column(JSON)
    created_at           = Column(DateTime, default=datetime.utcnow)
    completed_at         = Column(DateTime)

    user             = relationship("User", back_populates="jobintel_runs")
    job_intel_records = relationship("JobIntelRecord", back_populates="run", cascade="all, delete-orphan")


class JobIntelRecord(Base):
    __tablename__ = "tiq_jobintel_records"

    id                 = Column(Integer, primary_key=True, index=True)
    run_id             = Column(Integer, ForeignKey("tiq_jobintel_runs.id"), index=True, nullable=False)
    title              = Column(String(300))
    job_group          = Column(String(200))
    company            = Column(String(300))
    company_type       = Column(String(200))
    location           = Column(String(300))
    industry           = Column(String(200))
    domain             = Column(String(200))
    job_type           = Column(String(100))
    working_function   = Column(String(200))
    experience_years   = Column(String(50))
    experience_level   = Column(String(100))
    responsibilities   = Column(JSON)
    key_skills         = Column(JSON)
    soft_skills        = Column(JSON)
    tools_technology   = Column(JSON)
    certifications     = Column(JSON)
    education          = Column(Text)
    salary_min         = Column(Integer)
    salary_max         = Column(Integer)
    source_url         = Column(Text)
    source_site        = Column(String(200))
    published_date     = Column(String(50))
    raw_data           = Column(JSON)

    run = relationship("JobIntelRun", back_populates="job_intel_records")


# ══════════════════════════════════════════════════════════════════════════════
# LINKLENS
# ══════════════════════════════════════════════════════════════════════════════

class LinkLensSearch(Base):
    __tablename__ = "tiq_linklens_searches"

    id             = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id        = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    job_title      = Column(String(300))
    country        = Column(String(200))
    city           = Column(String(200))
    skills         = Column(Text)
    max_results    = Column(Integer, default=25)
    status         = Column(String(50), default="pending")
    profiles_found = Column(Integer, default=0)
    created_at     = Column(DateTime, default=datetime.utcnow)
    completed_at   = Column(DateTime)

    user     = relationship("User",            back_populates="linklens_searches")
    profiles = relationship("LinkedInProfile", back_populates="search", cascade="all, delete-orphan")


class LinkedInProfile(Base):
    __tablename__ = "tiq_linkedin_profiles"

    id              = Column(Integer, primary_key=True, index=True)
    search_id       = Column(Integer, ForeignKey("tiq_linklens_searches.id"), index=True, nullable=False)
    profile_url     = Column(Text)
    full_name       = Column(String(300))
    headline        = Column(Text)
    location        = Column(String(300))
    current_title   = Column(String(300))
    current_company = Column(String(300))
    summary         = Column(Text)
    skills          = Column(JSON)
    experience      = Column(JSON)
    education       = Column(JSON)
    certifications  = Column(JSON)
    email           = Column(String(200))
    phone           = Column(String(100))
    connection_degree = Column(String(10))
    raw_data        = Column(JSON)
    scraped_at      = Column(DateTime, default=datetime.utcnow)

    search = relationship("LinkLensSearch", back_populates="profiles")


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT
# ══════════════════════════════════════════════════════════════════════════════

class AuditLog(Base):
    __tablename__ = "tiq_audit_logs"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=True)
    action     = Column(String(200), nullable=False)
    resource   = Column(String(200))
    detail     = Column(JSON)
    ip_address = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


# ══════════════════════════════════════════════════════════════════════════════
# JOBLENS
# ══════════════════════════════════════════════════════════════════════════════

class JobLensSession(Base):
    __tablename__ = "tiq_joblens_sessions"

    id             = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id        = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    jd_text        = Column(Text)
    jd_skills      = Column(JSON, default=list)
    jd_role        = Column(String(300))     # extracted by LLM/heuristic — not guessed client-side
    jd_location    = Column(String(300))
    jd_company     = Column(String(300))
    jd_record_id   = Column(Integer, ForeignKey("tiq_jd_records.id"), index=True, nullable=True)  # optional link to JD Management
    jd_client_name = Column(String(300))     # denormalized client name, for display without extra joins
    jd_essential_skills   = Column(JSON, default=list)
    jd_good_to_have_skills = Column(JSON, default=list)
    jd_optional_skills    = Column(JSON, default=list)
    low_threshold  = Column(Integer, default=40)
    high_threshold = Column(Integer, default=70)
    cv_count       = Column(Integer, default=0)
    status         = Column(String(50), default="completed")
    created_at     = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User",             back_populates="joblens_sessions")
    candidates = relationship("JobLensCandidate", back_populates="session", cascade="all, delete-orphan")


class JobLensCandidate(Base):
    __tablename__ = "tiq_joblens_candidates"

    id                  = Column(Integer, primary_key=True, index=True)
    session_id          = Column(Integer, ForeignKey("tiq_joblens_sessions.id"), index=True, nullable=False)
    name                = Column(String(200))
    email               = Column(String(200))
    phone               = Column(String(100))
    filename            = Column(String(300))
    ats_score           = Column(Float, default=0.0)
    status              = Column(String(50), default="Not Qualified")
    matched_skills      = Column(JSON, default=list)
    missing_skills      = Column(JSON, default=list)
    bonus               = Column(Integer, default=0)
    bonus_reasons       = Column(Text)
    experience_years    = Column(String(20))
    summary             = Column(Text)
    interview_questions = Column(JSON, default=list)
    resume_summary      = Column(JSON, default=dict)   # categorized bullets: experience/skills/education/achievements/availability_work_rights
    strengths_breakdown = Column(JSON)  # technical/business/soft skills, experience, certs — see utils/llm_extraction.py
    interview_token     = Column(String(64), unique=True, index=True, nullable=True)
    contacted           = Column(Boolean, default=False)  # invite email sent
    video_status        = Column(String(50), default="Pending")
    emotion_happy       = Column(Integer, default=0)
    emotion_neutral     = Column(Integer, default=0)
    emotion_sad         = Column(Integer, default=0)
    emotion_angry       = Column(Integer, default=0)
    emotion_fear        = Column(Integer, default=0)
    emotion_disgust     = Column(Integer, default=0)
    emotion_surprise    = Column(Integer, default=0)
    dominant_emotion    = Column(String(20), default="Neutral")
    shortlisted         = Column(Boolean, default=False)

    # ── Resume + interview video stored directly on this row ──────────────
    # Kept as blobs (not files on disk) so the candidate's full record —
    # score, resume, and interview footage — lives in one place and is
    # covered by the same row-level access control as everything else.
    # If this candidate was sourced from Vendor Management (rather than a
    # raw manual CV upload), these point back to that origin.
    source_vendor_id   = Column(Integer, ForeignKey("tiq_vendors.id"), index=True, nullable=True)
    source_vendor_name = Column(String(300))  # denormalized, for display without extra joins
    source_tracked_candidate_id = Column(Integer, ForeignKey("tiq_tracked_candidates.id"), index=True, nullable=True)

    resume_file_blob     = Column(LargeBinary)
    resume_file_mimetype = Column(String(100))
    video_blob            = Column(LargeBinary)
    video_mimetype         = Column(String(50), default="video/webm")

    # ── Automatic post-interview video analysis (runs once the video blob
    # above is stored) — transcript + LLM-scored performance, on the same
    # row as everything else for this candidate.
    video_transcript      = Column(Text)
    video_analysis        = Column(JSON)              # structured scores/observations
    video_analysis_status = Column(String(20), default="Pending")  # Pending/Processing/Completed/Failed

    session = relationship("JobLensSession", back_populates="candidates")


# ══════════════════════════════════════════════════════════════════════════════
# JD CREATOR
# ══════════════════════════════════════════════════════════════════════════════

class JDDocument(Base):
    __tablename__ = "tiq_jd_documents"

    id                  = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id             = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    role_title          = Column(String(300), nullable=False)
    company_name        = Column(String(300))
    job_type            = Column(String(50))    # Full time / Fix term / Contract
    contract_duration   = Column(String(50))    # e.g. "6 Months", "12 Months", or a specific end date
    issue_date          = Column(String(20))
    expiry_date         = Column(String(20))
    skills_required     = Column(JSON, default=list)
    experience_required = Column(Text)
    education_required  = Column(Text)
    position_purpose    = Column(Text)     # AI-generated summary paragraph
    organisational_context = Column(Text)  # AI-generated context paragraph
    responsibilities    = Column(JSON, default=list)  # AI-generated bullet list (12-15 items)
    required_qualifications = Column(JSON, default=list)   # AI-generated rich bullet list
    preferred_qualifications = Column(JSON, default=list)  # AI-generated nice-to-have bullet list
    ai_powered          = Column(Boolean, default=False)
    llm_provider        = Column(String(20))   # "groq" or "ollama"
    created_at          = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="jd_documents")


# ══════════════════════════════════════════════════════════════════════════════
# CVANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

class CVAnalysisRecord(Base):
    __tablename__ = "tiq_cvanalysis_records"

    id                = Column(Integer, primary_key=True, index=True)
    sequence_number = Column(Integer)  # per-user sequential display number (1, 2, 3...)
    user_id           = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    source_name       = Column(String(300))         # resume filename, or "Resume"
    overall_score     = Column(Float, default=0.0)
    result            = Column(JSON, default=dict)   # full AnalysisResult payload
    candidate_info    = Column(JSON, default=dict)
    jd_info           = Column(JSON, default=dict)
    created_at        = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cvanalysis_records")


# ══════════════════════════════════════════════════════════════════════════════
# JD MANAGEMENT / VENDOR MANAGEMENT / CANDIDATE TRACKING
# A separate hiring-lifecycle tracker: JDs move through a status pipeline,
# vendors submit candidates against JDs, and candidates are tracked
# end-to-end independent of any single JD or vendor view.
# ══════════════════════════════════════════════════════════════════════════════

JD_STATUSES = ["Open", "Shortlisting", "Interviewing", "Offer Stage", "Closed"]
JD_IN_PROGRESS_STATUSES = ["Shortlisting", "Interviewing", "Offer Stage"]

CANDIDATE_STATUSES = [
    "Applied", "Shortlisted", "Interview Scheduled", "Interview Completed",
    "Selected", "Offered", "Rejected",
]

WORK_PERMISSION_OPTIONS = ["Work Visa", "Permanent Resident", "Citizenship"]


class JDRecord(Base):
    __tablename__ = "tiq_jd_records"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    sequence_number = Column(Integer)             # per-user sequential display number (1, 2, 3...)
    title           = Column(String(300), nullable=False)
    client_id       = Column(Integer, ForeignKey("tiq_clients.id"), index=True, nullable=True)  # sole link to the client — no redundant free-text copy (3NF)
    status          = Column(String(30), default="Open")
    description     = Column(Text)
    # Categorized requirements — extracted once (LLM or heuristic) when the
    # JD is created/edited and persisted here, rather than re-extracted from
    # `description` on every read. Modeled as owned JSON arrays rather than
    # a separate requirement-per-row child table: each JD wholly owns and
    # replaces its own requirement list as a unit (never referenced
    # independently elsewhere), so a child table would add join/CRUD
    # overhead without a normalization benefit in practice — see the
    # architecture doc for the fully-normalized reference design.
    essential_skills      = Column(JSON, default=list)
    good_to_have_skills   = Column(JSON, default=list)
    optional_skills       = Column(JSON, default=list)
    min_years_experience  = Column(Integer, default=0)
    education_requirement = Column(String(300))
    # Optional uploaded JD document (Word/PDF) — description text field
    # above is still the source used for requirement extraction; this is
    # the original document for reference/download.
    jd_file_blob     = Column(LargeBinary)
    jd_file_filename = Column(String(300))
    jd_file_mimetype = Column(String(100))
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user       = relationship("User", back_populates="jd_records")
    client     = relationship("Client", back_populates="jds")
    candidates = relationship("TrackedCandidate", back_populates="jd", cascade="all, delete-orphan")


class Vendor(Base):
    __tablename__ = "tiq_vendors"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    sequence_number  = Column(Integer)   # per-user sequential display number
    name             = Column(String(300), nullable=False)
    address          = Column(String(300))
    contact_email    = Column(String(200))
    contact_phone    = Column(String(50))
    coverage_region  = Column(String(300))   # e.g. "APAC", "Sydney/Melbourne", "Remote"
    technical_area   = Column(String(300))   # e.g. "Data Engineering, Cloud"
    company_details  = Column(Text)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user       = relationship("User", back_populates="vendors")
    candidates = relationship("TrackedCandidate", back_populates="vendor", cascade="all, delete-orphan")


class Client(Base):
    __tablename__ = "tiq_clients"

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    name              = Column(String(300), nullable=False)
    address           = Column(String(300))
    abn               = Column(String(50))
    area_of_work      = Column(String(300))
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="clients")
    jds  = relationship("JDRecord", back_populates="client")


class TrackedCandidate(Base):
    __tablename__ = "tiq_tracked_candidates"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("tiq_users.id"), index=True, nullable=False)
    jd_id            = Column(Integer, ForeignKey("tiq_jd_records.id"), index=True, nullable=False)
    vendor_id        = Column(Integer, ForeignKey("tiq_vendors.id"), index=True, nullable=False)
    name             = Column(String(200), nullable=False)
    email            = Column(String(200))
    phone            = Column(String(50))
    resume_blob      = Column(LargeBinary)
    resume_filename  = Column(String(300))
    resume_mimetype  = Column(String(100))
    status           = Column(String(30), default="Applied")
    address          = Column(String(300))
    work_permission  = Column(String(50))   # "Work Visa" / "Permanent Resident" / "Citizenship"

    # Duplicate handling: the FIRST submitted candidate for a given JD with
    # matching email/phone stays primary (is_duplicate=False); any later
    # submission from any vendor gets flagged, but is kept as its own row
    # (not merged/discarded) so vendor attribution is fully auditable.
    is_duplicate    = Column(Boolean, default=False)
    duplicate_of_id = Column(Integer, ForeignKey("tiq_tracked_candidates.id"), index=True, nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user         = relationship("User", back_populates="tracked_candidates")
    jd           = relationship("JDRecord", back_populates="candidates")
    vendor       = relationship("Vendor", back_populates="candidates")
    status_logs  = relationship(
        "CandidateStatusLog", back_populates="candidate",
        cascade="all, delete-orphan", foreign_keys="CandidateStatusLog.candidate_id",
    )


class CandidateStatusLog(Base):
    __tablename__ = "tiq_candidate_status_log"

    id           = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("tiq_tracked_candidates.id"), index=True, nullable=False)
    old_status   = Column(String(30))
    new_status   = Column(String(30))
    changed_at   = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("TrackedCandidate", back_populates="status_logs", foreign_keys=[candidate_id])


class JDVendorLink(Base):
    """Explicit junction table for the JD <-> Vendor many-to-many
    relationship ("one JD can receive candidates from multiple vendors;
    one vendor can submit to multiple JDs"). Auto-maintained whenever a
    candidate is submitted (see _link_jd_vendor in routers/candidatetrack.py)
    — never exposed as its own tab or CRUD screen; it exists purely to back
    "vendors involved in this JD" / "JDs this vendor is involved in" with a
    real indexed relationship table instead of a DISTINCT scan over
    tracked_candidates on every read.
    """
    __tablename__ = "tiq_jd_vendor_links"
    __table_args__ = (UniqueConstraint("jd_id", "vendor_id", name="uq_jd_vendor"),)

    id             = Column(Integer, primary_key=True, index=True)
    jd_id          = Column(Integer, ForeignKey("tiq_jd_records.id"), nullable=False, index=True)
    vendor_id      = Column(Integer, ForeignKey("tiq_vendors.id"), nullable=False, index=True)
    first_linked_at = Column(DateTime, default=datetime.utcnow)


class GroqKeyPool(Base):
    """A pool of shared/global Groq API keys, load-balanced automatically
    based on real-time health rather than a fixed per-user quota.

    Why this exists: Groq's rate limits are per API key, not per user of
    this platform. With only ONE shared key, heavy usage from even a
    single account can exhaust its rate limit for every other user relying
    on that same fallback -- the exact 429/413 storm diagnosed the hard way
    earlier this session. A hard per-user quota "solves" that by blocking
    users, but that doesn't scale UP with demand, it just rations a fixed
    ceiling more fairly. This does the opposite: capacity grows simply by
    an admin adding another Groq key to the pool (any tier, even multiple
    free-tier keys), and the system automatically spreads load across
    whichever keys are currently healthy -- no user is ever blocked because
    of another user's usage, and adding capacity is a one-row insert, not
    a code change.

    Health tracking is DB-backed (not in-process memory) specifically so
    it stays correct if this app ever runs as multiple replicas behind a
    load balancer -- an in-memory-only tracker would let each replica
    independently keep hammering a key the OTHER replicas already know is
    rate-limited.

    Managed via the existing generic admin table editor (Settings -> File
    Manager -> tiq_groq_key_pool) -- no dedicated UI needed; adding a row
    IS adding capacity."""
    __tablename__ = "tiq_groq_key_pool"

    id                 = Column(Integer, primary_key=True, index=True)
    key_value          = Column(Text, nullable=False, unique=True)
    model              = Column(String(200), nullable=True)  # per-key model override; falls back to the account's configured model if empty
    is_active          = Column(Boolean, default=True, nullable=False)  # admin can disable a key (e.g. suspected revoked) without deleting it
    consecutive_errors = Column(Integer, default=0, nullable=False)
    cooldown_until     = Column(DateTime, nullable=True)  # if set and in the future, this key is skipped until then
    last_used_at       = Column(DateTime, nullable=True)
    added_at           = Column(DateTime, default=datetime.utcnow)
