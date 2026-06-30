"""
TalentIQ – MarketIntel Router
Simulates job market data (mirrors original JobIntel Agent) and stores per-user sessions.
Each user sees ONLY their own runs — no cross-user leakage.
Supports: run, list, get, delete run, delete all runs.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from db.database import get_db, AsyncSessionLocal
from models.models import User, JobIntelRun, JobIntelRecord
from schemas.schemas import JobIntelRequest, JobIntelRunOut, JobIntelRecordOut
from utils.auth_utils import get_current_user

router = APIRouter()


# ── BACKGROUND TASK ───────────────────────────────────────────────────────────

async def _run_simulation(run_id: int, payload: JobIntelRequest, user_id: int):
    """Background: simulate job data and persist records."""
    from agents.jobintel_simulator import simulate_jobs, analyse_simulated_jobs

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(JobIntelRun).where(
                    JobIntelRun.id == run_id,
                    JobIntelRun.user_id == user_id,
                )
            )
            run = result.scalar_one_or_none()
            if not run:
                return

            run.status = "running"
            await db.commit()

            # Simulate data
            count = max(50, min(payload.max_results or 100, 10000))
            country = payload.location or "Australia"
            domain = payload.industry or payload.role or "Technology"

            jobs = simulate_jobs(country=country, domain=domain, count=count)
            insights = analyse_simulated_jobs(jobs)

            # Update run
            run.total_jobs_scraped = len(jobs)
            run.insights = insights
            run.top_skills = insights.get("top_skills")
            run.top_tools = insights.get("top_tools")
            run.salary_stats = insights.get("salary_stats")
            run.job_type_breakdown = insights.get("job_type_breakdown")
            run.company_type_breakdown = insights.get("company_type_breakdown")
            run.status = "completed"
            run.completed_at = datetime.utcnow()

            # Persist job records
            for j in jobs:
                record = JobIntelRecord(
                    run_id=run.id,
                    title=j.get("title"),
                    job_group=j.get("job_group"),
                    company=j.get("company"),
                    company_type=j.get("company_type"),
                    location=j.get("location"),
                    domain=j.get("domain"),
                    job_type=j.get("job_type"),
                    working_function=j.get("working_function"),
                    experience_level=j.get("experience_level"),
                    experience_years=j.get("experience_years"),
                    key_skills=j.get("key_skills", []),
                    soft_skills=j.get("soft_skills", []),
                    tools_technology=j.get("tools_technologies", []),
                    certifications=j.get("certifications", []),
                    education=j.get("education_required"),
                    salary_min=j.get("salary_min"),
                    salary_max=j.get("salary_max"),
                    source_site=j.get("source"),
                    source_url=j.get("source_url"),
                    published_date=j.get("date_posted"),
                )
                db.add(record)

            await db.commit()

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[JobIntel ERROR] Run {run_id} failed:\n{tb}")
            async with AsyncSessionLocal() as db2:
                r2 = await db2.execute(
                    select(JobIntelRun).where(JobIntelRun.id == run_id)
                )
                run2 = r2.scalar_one_or_none()
                if run2:
                    run2.status = "failed"
                    run2.insights = {"error": str(e), "traceback": tb[-800:]}
                    await db2.commit()


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_analysis(
    payload: JobIntelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new MarketIntel simulation run for the current user."""
    run = JobIntelRun(
        user_id=current_user.id,
        role=payload.role,
        location=payload.location,
        industry=payload.industry,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(_run_simulation, run.id, payload, current_user.id)

    return {"id": run.id, "status": run.status, "created_at": run.created_at.isoformat()}


@router.get("/runs")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all runs for the CURRENT user only."""
    result = await db.execute(
        select(JobIntelRun)
        .where(JobIntelRun.user_id == current_user.id)   # ← user isolation
        .order_by(JobIntelRun.created_at.desc())
        .limit(50)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "role": r.role,
            "location": r.location,
            "industry": r.industry,
            "status": r.status,
            "total_jobs_scraped": r.total_jobs_scraped or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific run — only if it belongs to the current user."""
    result = await db.execute(
        select(JobIntelRun).where(
            JobIntelRun.id == run_id,
            JobIntelRun.user_id == current_user.id,   # ← user isolation
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    return {
        "id": run.id,
        "role": run.role,
        "location": run.location,
        "industry": run.industry,
        "status": run.status,
        "total_jobs_scraped": run.total_jobs_scraped or 0,
        "insights": run.insights,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/runs/{run_id}/records")
async def get_run_records(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get job records for a run — only if the run belongs to current user."""
    # Verify ownership first
    run_result = await db.execute(
        select(JobIntelRun).where(
            JobIntelRun.id == run_id,
            JobIntelRun.user_id == current_user.id,
        )
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(404, "Run not found")

    records_result = await db.execute(
        select(JobIntelRecord)
        .where(JobIntelRecord.run_id == run_id)
        .limit(10000)
    )
    records = records_result.scalars().all()

    return [
        {
            "id": r.id,
            "title": r.title,
            "job_group": r.job_group,
            "company": r.company,
            "company_type": r.company_type,
            "location": r.location,
            "domain": r.domain,
            "job_type": r.job_type,
            "working_function": r.working_function,
            "experience_level": r.experience_level,
            "experience_years": r.experience_years,
            "key_skills": r.key_skills or [],
            "soft_skills": r.soft_skills or [],
            "tools": r.tools_technology or [],
            "certifications": r.certifications or [],
            "salary_min": r.salary_min,
            "salary_max": r.salary_max,
            "source": r.source_site,
            "source_url": r.source_url,
            "published_date": r.published_date,
        }
        for r in records
    ]


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a specific run and all its records."""
    result = await db.execute(
        select(JobIntelRun).where(
            JobIntelRun.id == run_id,
            JobIntelRun.user_id == current_user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    # Delete records first
    await db.execute(
        delete(JobIntelRecord).where(JobIntelRecord.run_id == run_id)
    )
    await db.delete(run)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/runs")
async def delete_all_runs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete ALL runs for the current user."""
    # Get all run IDs for this user
    run_ids_result = await db.execute(
        select(JobIntelRun.id).where(JobIntelRun.user_id == current_user.id)
    )
    run_ids = [r[0] for r in run_ids_result.all()]

    if run_ids:
        await db.execute(
            delete(JobIntelRecord).where(JobIntelRecord.run_id.in_(run_ids))
        )
        await db.execute(
            delete(JobIntelRun).where(JobIntelRun.user_id == current_user.id)
        )
        await db.commit()

    return {"message": f"Deleted {len(run_ids)} runs"}