"""
TalentIQ – SQLAlchemy ORM Models
All tables prefixed tiq_ to coexist with AccFino on the same Neon database.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON,
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


class UserAPIKey(Base):
    __tablename__ = "tiq_user_api_keys"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
    service    = Column(String(100), nullable=False)
    key_name   = Column(String(100), nullable=False)
    key_value  = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


# ══════════════════════════════════════════════════════════════════════════════
# JOBHUNT
# ══════════════════════════════════════════════════════════════════════════════

class Resume(Base):
    __tablename__ = "tiq_resumes"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
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
    user_id       = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
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
    search_id      = Column(Integer, ForeignKey("tiq_job_searches.id"), nullable=False)
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
    user_id      = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
    resume_id    = Column(Integer, ForeignKey("tiq_resumes.id"), nullable=False)
    job_id       = Column(Integer, ForeignKey("tiq_jobs.id"), nullable=False)
    ats_score    = Column(Float, default=0)
    strengths    = Column(JSON)
    improvements = Column(JSON)
    summary      = Column(JSON)
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
    user_id              = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
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
    run_id             = Column(Integer, ForeignKey("tiq_jobintel_runs.id"), nullable=False)
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
    user_id        = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
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
    search_id       = Column(Integer, ForeignKey("tiq_linklens_searches.id"), nullable=False)
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
    user_id    = Column(Integer, ForeignKey("tiq_users.id"), nullable=True)
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
    user_id        = Column(Integer, ForeignKey("tiq_users.id"), nullable=False)
    jd_text        = Column(Text)
    jd_skills      = Column(JSON, default=list)
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
    session_id          = Column(Integer, ForeignKey("tiq_joblens_sessions.id"), nullable=False)
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
    resume_summary      = Column(JSON, default=list)   # 10-statement AI resume summary
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

    session = relationship("JobLensSession", back_populates="candidates")