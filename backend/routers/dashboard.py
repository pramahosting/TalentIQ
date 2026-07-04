"""
TalentIQ – Dashboard Router
Aggregates stats across all 5 modules: JobHunter, MarketIntel, LinkExplore,
CVAnalysis (session-only, no DB), and CandidateLens — for the user dashboard.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from db.database import get_db
from models.models import (
    User, JobSearch, Job, JobMatch, JobIntelRun, JobIntelRecord,
    LinkLensSearch, LinkedInProfile, JobLensSession, JobLensCandidate,
    JDRecord, JD_IN_PROGRESS_STATUSES,
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

    # ── JD Management (Candidate Tracker) ────────────────────────────────
    jd_statuses_r = await db.execute(select(JDRecord.status).where(JDRecord.user_id == uid))
    jd_statuses = [s for (s,) in jd_statuses_r.all()]
    total_jds = len(jd_statuses)
    open_jds = sum(1 for s in jd_statuses if s == "Open")
    in_progress_jds = sum(1 for s in jd_statuses if s in JD_IN_PROGRESS_STATUSES)
    closed_jds = sum(1 for s in jd_statuses if s == "Closed")

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
        total_jds=total_jds,
        open_jds=open_jds,
        in_progress_jds=in_progress_jds,
        closed_jds=closed_jds,
        recent_activity=[],
    )


@router.get("/jobhunter-summary")
async def jobhunter_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real-time, per-role breakdown of JobHunter activity — grouped by the
    role searched for, since JobHunter has no client/vendor-style entity to
    group by (search criteria is the natural dimension here)."""
    uid = current_user.id

    search_stmt = (
        select(
            func.coalesce(func.nullif(JobSearch.role, ""), "Unspecified").label("role"),
            func.count(func.distinct(JobSearch.id)).label("total_searches"),
            func.count(Job.id).label("total_jobs_found"),
            func.max(JobSearch.searched_at).label("last_search"),
        )
        .select_from(JobSearch)
        .outerjoin(Job, Job.search_id == JobSearch.id)
        .where(JobSearch.user_id == uid)
        .group_by(func.coalesce(func.nullif(JobSearch.role, ""), "Unspecified"))
        .order_by(func.count(func.distinct(JobSearch.id)).desc())
    )
    search_rows = (await db.execute(search_stmt)).all()

    match_stmt = (
        select(
            func.coalesce(func.nullif(JobSearch.role, ""), "Unspecified").label("role"),
            func.count(JobMatch.id).label("total_matches"),
            func.avg(JobMatch.ats_score).label("avg_score"),
        )
        .select_from(JobMatch)
        .join(Job, JobMatch.job_id == Job.id)
        .join(JobSearch, Job.search_id == JobSearch.id)
        .where(JobMatch.user_id == uid)
        .group_by(func.coalesce(func.nullif(JobSearch.role, ""), "Unspecified"))
    )
    match_by_role = {
        r.role: {"total_matches": r.total_matches, "avg_score": round(r.avg_score, 1) if r.avg_score is not None else None}
        for r in (await db.execute(match_stmt)).all()
    }

    return [
        {
            "role": r.role,
            "total_searches": r.total_searches,
            "total_jobs_found": r.total_jobs_found,
            "total_matches": match_by_role.get(r.role, {}).get("total_matches", 0),
            "avg_ats_score": match_by_role.get(r.role, {}).get("avg_score"),
            "last_search": r.last_search.isoformat() if r.last_search else None,
        }
        for r in search_rows
    ]


@router.get("/marketintel-summary")
async def marketintel_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real-time, per-role breakdown of MarketIntel runs."""
    uid = current_user.id
    stmt = (
        select(
            func.coalesce(func.nullif(JobIntelRun.role, ""), "Unspecified").label("role"),
            func.count(JobIntelRun.id).label("total_runs"),
            func.sum(JobIntelRun.total_jobs_scraped).label("total_jobs_analyzed"),
            func.max(JobIntelRun.created_at).label("last_run"),
        )
        .select_from(JobIntelRun)
        .where(JobIntelRun.user_id == uid)
        .group_by(func.coalesce(func.nullif(JobIntelRun.role, ""), "Unspecified"))
        .order_by(func.count(JobIntelRun.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "role": r.role,
            "total_runs": r.total_runs,
            "total_jobs_analyzed": r.total_jobs_analyzed or 0,
            "avg_jobs_per_run": round((r.total_jobs_analyzed or 0) / r.total_runs, 1) if r.total_runs else 0,
            "last_run": r.last_run.isoformat() if r.last_run else None,
        }
        for r in rows
    ]


@router.get("/linkexplore-summary")
async def linkexplore_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real-time, per-job-title breakdown of LinkExplore searches."""
    uid = current_user.id
    stmt = (
        select(
            func.coalesce(func.nullif(LinkLensSearch.job_title, ""), "Unspecified").label("job_title"),
            func.count(LinkLensSearch.id).label("total_searches"),
            func.sum(LinkLensSearch.profiles_found).label("total_profiles"),
            func.count(func.distinct(LinkLensSearch.country)).label("countries"),
            func.max(LinkLensSearch.created_at).label("last_search"),
        )
        .select_from(LinkLensSearch)
        .where(LinkLensSearch.user_id == uid)
        .group_by(func.coalesce(func.nullif(LinkLensSearch.job_title, ""), "Unspecified"))
        .order_by(func.count(LinkLensSearch.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "job_title": r.job_title,
            "total_searches": r.total_searches,
            "total_profiles": r.total_profiles or 0,
            "countries": r.countries or 0,
            "last_search": r.last_search.isoformat() if r.last_search else None,
        }
        for r in rows
    ]