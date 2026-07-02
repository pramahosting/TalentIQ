"""
TalentIQ – Pydantic Schemas for Request / Response Validation
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, field_validator


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    company: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class APIKeyCreate(BaseModel):
    service: str
    key_name: str
    key_value: str
    is_global: bool = False   # only honoured for admins + shareable services; see routers/auth.py


class APIKeyOut(BaseModel):
    id: int
    service: str
    key_name: str
    is_global: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# JOBHUNT
# ─────────────────────────────────────────────

class JobSearchRequest(BaseModel):
    role: str
    location: str = "All"
    industry: Optional[str] = None
    job_type: Optional[str] = "All"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: Optional[str] = None
    job_type: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[List[str]] = None
    source: Optional[str] = None
    apply_link: Optional[str] = None
    published_date: Optional[str] = None
    source_site: Optional[str] = None

    model_config = {"from_attributes": True}


class JobSearchOut(BaseModel):
    id: int
    sequence_number: Optional[int] = None
    role: str
    location: Optional[str] = None
    results_count: int
    searched_at: datetime
    jobs: List[JobOut] = []
    notice: Optional[str] = None

    model_config = {"from_attributes": True}


class ResumeOut(BaseModel):
    id: int
    filename: Optional[str] = None
    applicant_name: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[float] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class MatchRequest(BaseModel):
    resume_id: int
    search_id: int


class JobMatchOut(BaseModel):
    id: int
    job_id: int
    job_title: str
    company: str
    location: Optional[str] = None
    ats_score: float
    strengths: Optional[List[str]] = None
    improvements: Optional[List[str]] = None
    summary: Optional[List[str]] = None
    cover_letter: Optional[str] = None
    apply_link: Optional[str] = None
    matched_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# JOBINTEL
# ─────────────────────────────────────────────

class JobIntelRequest(BaseModel):
    role: str
    location: str = "All"
    industry: Optional[str] = None
    max_results: int = 20


class JobIntelRunOut(BaseModel):
    id: int
    role: str
    location: Optional[str] = None
    industry: Optional[str] = None
    status: str
    total_jobs_scraped: int
    insights: Optional[Any] = None
    top_skills: Optional[List[Any]] = None
    top_tools: Optional[List[Any]] = None
    salary_stats: Optional[Any] = None
    job_type_breakdown: Optional[Any] = None
    company_type_breakdown: Optional[Any] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobIntelRecordOut(BaseModel):
    id: int
    title: str
    company: str
    location: Optional[str] = None
    industry: Optional[str] = None
    domain: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    key_skills: Optional[List[str]] = None
    tools_technology: Optional[List[str]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    source_url: Optional[str] = None
    published_date: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# LINKLENS
# ─────────────────────────────────────────────

class LinkLensSearchRequest(BaseModel):
    job_title: str
    country: str = "Australia"
    city: str = "All"
    skills: str = ""
    max_results: int = 25


class LinkedInProfileOut(BaseModel):
    id: int
    profile_url: str
    full_name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[List[Any]] = None
    education: Optional[List[Any]] = None
    email: Optional[str] = None
    connection_degree: Optional[str] = None
    scraped_at: datetime

    model_config = {"from_attributes": True}


class LinkLensSearchOut(BaseModel):
    id: int
    job_title: str
    country: str
    city: Optional[str] = None
    skills: Optional[str] = None
    status: str
    profiles_found: int
    created_at: datetime
    profiles: List[LinkedInProfileOut] = []

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_job_searches: int
    total_jobs_found: int
    total_matches: int
    avg_ats_score: float
    total_intel_runs: int
    total_intel_jobs: int = 0
    total_linkedin_searches: int
    total_profiles_found: int
    total_joblens_sessions: int = 0
    total_candidates: int = 0
    avg_candidate_score: float = 0.0
    total_jds: int = 0
    open_jds: int = 0
    in_progress_jds: int = 0
    closed_jds: int = 0
    recent_activity: List[Any] = []