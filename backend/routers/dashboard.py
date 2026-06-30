"""
TalentIQ – Dashboard Router
Aggregates stats across all 5 modules: JobHunter, MarketIntel, LinkExplore,
CVAnalysis (session-only, no DB), and CandidateLens — for the user dashboard.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.database import get_db
from models.models import (
    User, JobSearch, Job, JobMatch, JobIntelRun, JobIntelRecord,
    LinkLensSearch, LinkedInProfile, JobLensSession, JobLensCandidate,
)
from schemas.schemas import DashboardStats
from utils.auth_utils import get_current_user

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id

    # ── JobHunter ──────────────────────────────────────────────────────
    total_searches = (await db.execute(
        select(func.count()).select_from(JobSearch).where(JobSearch.user_id == uid)
    )).scalar() or 0

    total_jobs = (await db.execute(
        select(func.count()).select_from(Job)
        .join(JobSearch, Job.search_id == JobSearch.id)
        .where(JobSearch.user_id == uid)
    )).scalar() or 0

    total_matches = (await db.execute(
        select(func.count()).select_from(JobMatch).where(JobMatch.user_id == uid)
    )).scalar() or 0

    avg_score_result = (await db.execute(
        select(func.avg(JobMatch.ats_score)).where(JobMatch.user_id == uid)
    )).scalar()
    avg_ats = round(float(avg_score_result), 1) if avg_score_result is not None else 0.0

    # ── MarketIntel ────────────────────────────────────────────────────
    total_intel = (await db.execute(
        select(func.count()).select_from(JobIntelRun).where(JobIntelRun.user_id == uid)
    )).scalar() or 0

    total_intel_jobs = (await db.execute(
        select(func.count()).select_from(JobIntelRecord)
        .join(JobIntelRun, JobIntelRecord.run_id == JobIntelRun.id)
        .where(JobIntelRun.user_id == uid)
    )).scalar() or 0

    # ── LinkExplore ────────────────────────────────────────────────────
    total_ll_searches = (await db.execute(
        select(func.count()).select_from(LinkLensSearch).where(LinkLensSearch.user_id == uid)
    )).scalar() or 0

    total_profiles = (await db.execute(
        select(func.count()).select_from(LinkedInProfile)
        .join(LinkLensSearch, LinkedInProfile.search_id == LinkLensSearch.id)
        .where(LinkLensSearch.user_id == uid)
    )).scalar() or 0

    # ── CandidateLens ──────────────────────────────────────────────────
    total_joblens_sessions = (await db.execute(
        select(func.count()).select_from(JobLensSession).where(JobLensSession.user_id == uid)
    )).scalar() or 0

    total_candidates = (await db.execute(
        select(func.count()).select_from(JobLensCandidate)
        .join(JobLensSession, JobLensCandidate.session_id == JobLensSession.id)
        .where(JobLensSession.user_id == uid)
    )).scalar() or 0

    avg_candidate_score_result = (await db.execute(
        select(func.avg(JobLensCandidate.ats_score))
        .join(JobLensSession, JobLensCandidate.session_id == JobLensSession.id)
        .where(JobLensSession.user_id == uid)
    )).scalar()
    avg_candidate_score = (
        round(float(avg_candidate_score_result), 1)
        if avg_candidate_score_result is not None else 0.0
    )

    return DashboardStats(
        total_job_searches=total_searches,
        total_jobs_found=total_jobs,
        total_matches=total_matches,
        avg_ats_score=avg_ats,
        total_intel_runs=total_intel,
        total_intel_jobs=total_intel_jobs,
        total_linkedin_searches=total_ll_searches,
        total_profiles_found=total_profiles,
        total_joblens_sessions=total_joblens_sessions,
        total_candidates=total_candidates,
        avg_candidate_score=avg_candidate_score,
        recent_activity=[],
    )