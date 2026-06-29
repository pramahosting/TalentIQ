"""
TalentIQ – JobIntel Router
Endpoints: run analysis, get results, get analytics dashboard data
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from models.models import User, JobIntelRun, JobIntelRecord, UserAPIKey
from schemas.schemas import JobIntelRequest, JobIntelRunOut, JobIntelRecordOut
from utils.auth_utils import get_current_user
from agents.jobhunt_agent import scrape_jobs_adzuna
from agents.jobintel_agent import enrich_job_record, analyse_jobs

router = APIRouter()


async def _get_key(user_id: int, service: str, key_name: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(UserAPIKey.key_value).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.service == service,
            UserAPIKey.key_name == key_name,
        )
    )
    return result.scalar_one_or_none()


async def _run_intel_analysis(run_id: int, payload: JobIntelRequest, user_id: int):
    """Background task: scrape + analyse + persist"""
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(JobIntelRun).where(JobIntelRun.id == run_id))
            run = result.scalar_one_or_none()
            if not run:
                return

            run.status = "running"

            adzuna_id = await _get_key(user_id, "adzuna", "app_id", db) or "638c0962"
            adzuna_key = await _get_key(user_id, "adzuna", "app_key", db) or "04681adc21daeda69c41b271627d448a"

            raw_jobs = scrape_jobs_adzuna(
                role=payload.role,
                location=payload.location,
                job_type="All",
                salary_min=None,
                salary_max=None,
                adzuna_app_id=adzuna_id,
                adzuna_app_key=adzuna_key,
            )

            enriched = [enrich_job_record(j) for j in raw_jobs[:payload.max_results]]
            insights = analyse_jobs(enriched)

            run.total_jobs_scraped = len(enriched)
            run.insights = insights
            run.top_skills = insights.get("top_skills")
            run.top_tools = insights.get("top_soft_skills")
            run.salary_stats = insights.get("salary_stats")
            run.job_type_breakdown = insights.get("job_type_breakdown")
            run.company_type_breakdown = insights.get("company_type_breakdown")
            run.status = "completed"
            run.completed_at = datetime.utcnow()

            for j in enriched:
                record = JobIntelRecord(
                    run_id=run.id,
                    title=j.get("title"),
                    company=j.get("company"),
                    location=j.get("location"),
                    domain=j.get("domain"),
                    job_type=j.get("job_type"),
                    working_function=j.get("working_function"),
                    experience_level=j.get("experience_level"),
                    key_skills=j.get("key_skills"),
                    soft_skills=j.get("soft_skills"),
                    tools_technology=j.get("tools_technology"),
                    salary_min=j.get("salary_min"),
                    salary_max=j.get("salary_max"),
                    source_url=j.get("apply_link"),
                    source_site=j.get("source_site"),
                    published_date=j.get("published_date"),
                    raw_data=j,
                )
                db.add(record)

            await db.commit()

        except Exception as e:
            result = await db.execute(select(JobIntelRun).where(JobIntelRun.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = "failed"
                await db.commit()


@router.post("/run", response_model=JobIntelRunOut, status_code=202)
async def run_intel(
    payload: JobIntelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = JobIntelRun(
        user_id=current_user.id,
        role=payload.role,
        location=payload.location,
        industry=payload.industry,
        status="pending",
    )
    db.add(run)
    await db.flush()

    background_tasks.add_task(_run_intel_analysis, run.id, payload, current_user.id)

    return JobIntelRunOut.model_validate(run)


@router.get("/runs", response_model=List[JobIntelRunOut])
async def list_runs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobIntelRun)
        .where(JobIntelRun.user_id == current_user.id)
        .order_by(JobIntelRun.created_at.desc()).limit(20)
    )
    return [JobIntelRunOut.model_validate(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=JobIntelRunOut)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobIntelRun).where(
            JobIntelRun.id == run_id, JobIntelRun.user_id == current_user.id
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return JobIntelRunOut.model_validate(run)


@router.get("/runs/{run_id}/records", response_model=List[JobIntelRecordOut])
async def get_run_records(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate ownership
    run_result = await db.execute(
        select(JobIntelRun).where(
            JobIntelRun.id == run_id, JobIntelRun.user_id == current_user.id
        )
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Run not found")

    result = await db.execute(
        select(JobIntelRecord).where(JobIntelRecord.run_id == run_id)
    )
    return [JobIntelRecordOut.model_validate(r) for r in result.scalars().all()]