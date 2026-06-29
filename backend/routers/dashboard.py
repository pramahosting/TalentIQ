"""
TalentIQ – Dashboard Router
Aggregates stats across JobHunt, JobIntel, LinkLens for the user dashboard.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.database import get_db
from models.models import (
    User, JobSearch, Job, JobMatch, JobIntelRun,
    LinkLensSearch, LinkedInProfile, AuditLog,
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

    total_searches = (await db.execute(
        select(func.count()).select_from(JobSearch).where(JobSearch.user_id == uid)
    )).scalar() or 0

    total_jobs = (await db.execute(
        select(func.count()).select_from(Job)
        .join(JobSearch).where(JobSearch.user_id == uid)
    )).scalar() or 0

    total_matches = (await db.execute(
        select(func.count()).select_from(JobMatch).where(JobMatch.user_id == uid)
    )).scalar() or 0

    avg_score_result = (await db.execute(
        select(func.avg(JobMatch.ats_score)).where(JobMatch.user_id == uid)
    )).scalar()
    avg_ats = round(avg_score_result or 0, 1)

    total_intel = (await db.execute(
        select(func.count()).select_from(JobIntelRun).where(JobIntelRun.user_id == uid)
    )).scalar() or 0

    total_ll_searches = (await db.execute(
        select(func.count()).select_from(LinkLensSearch).where(LinkLensSearch.user_id == uid)
    )).scalar() or 0

    total_profiles = (await db.execute(
        select(func.count()).select_from(LinkedInProfile)
        .join(LinkLensSearch).where(LinkLensSearch.user_id == uid)
    )).scalar() or 0

    # Recent audit log
    recent_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == uid)
        .order_by(AuditLog.created_at.desc()).limit(10)
    )
    recent = [
        {"action": a.action, "resource": a.resource, "created_at": a.created_at.isoformat()}
        for a in recent_result.scalars().all()
    ]

    return DashboardStats(
        total_job_searches=total_searches,
        total_jobs_found=total_jobs,
        total_matches=total_matches,
        avg_ats_score=avg_ats,
        total_intel_runs=total_intel,
        total_linkedin_searches=total_ll_searches,
        total_profiles_found=total_profiles,
        recent_activity=recent,
    )
