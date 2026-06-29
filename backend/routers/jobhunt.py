"""
TalentIQ – JobHunt Router
Endpoints: job search, resume upload, matching, cover letters, export
"""

import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import pandas as pd
import fitz  # PyMuPDF
import docx2txt

from db.database import get_db
from models.models import User, Resume, JobSearch, Job, JobMatch, UserAPIKey
from schemas.schemas import (
    JobSearchRequest, JobSearchOut, ResumeOut,
    MatchRequest, JobMatchOut, JobOut,
)
from utils.auth_utils import get_current_user
from agents.jobhunt_agent import (
    scrape_jobs_adzuna, parse_resume_text,
    calculate_match, generate_cover_letter,
)

router = APIRouter()


async def _get_user_api_key(user_id: int, service: str, key_name: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(UserAPIKey.key_value).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.service == service,
            UserAPIKey.key_name == key_name,
        )
    )
    row = result.scalar_one_or_none()
    return row


async def _extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    filename = file.filename or ""
    if filename.endswith(".pdf"):
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    elif filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(content))
    elif filename.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Use PDF, DOCX, or TXT.")


# ─── UPLOAD RESUME ────────────────────────────

@router.post("/resume", response_model=ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_text = await _extract_text_from_file(file)
    parsed = parse_resume_text(raw_text)

    resume = Resume(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=raw_text,
        applicant_name=parsed.get("applicant_name"),
        skills=parsed.get("skills", []),
        experience_years=parsed.get("experience_years"),
        parsed_data=parsed,
    )
    db.add(resume)
    await db.flush()
    return ResumeOut.model_validate(resume)


@router.get("/resumes", response_model=List[ResumeOut])
async def list_resumes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id)
        .order_by(Resume.uploaded_at.desc())
    )
    return [ResumeOut.model_validate(r) for r in result.scalars().all()]


# ─── JOB SEARCH ───────────────────────────────

@router.post("/search", response_model=JobSearchOut, status_code=201)
async def search_jobs(
    payload: JobSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get user's Adzuna keys (fallback to env defaults)
    adzuna_id = await _get_user_api_key(current_user.id, "adzuna", "app_id", db) or "638c0962"
    adzuna_key = await _get_user_api_key(current_user.id, "adzuna", "app_key", db) or "04681adc21daeda69c41b271627d448a"

    raw_jobs = scrape_jobs_adzuna(
        role=payload.role,
        location=payload.location,
        job_type=payload.job_type or "All",
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        adzuna_app_id=adzuna_id,
        adzuna_app_key=adzuna_key,
    )

    # Persist search
    search = JobSearch(
        user_id=current_user.id,
        role=payload.role,
        location=payload.location,
        industry=payload.industry,
        job_type=payload.job_type,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        results_count=len(raw_jobs),
    )
    db.add(search)
    await db.flush()

    # Persist jobs
    job_objs = []
    for j in raw_jobs:
        job = Job(
            search_id=search.id,
            title=j.get("title"),
            company=j.get("company"),
            location=j.get("location"),
            job_type=j.get("job_type"),
            description=j.get("description"),
            source=j.get("source"),
            apply_link=j.get("apply_link"),
            published_date=j.get("published_date"),
            source_site=j.get("source_site"),
            salary_min=j.get("salary_min"),
            salary_max=j.get("salary_max"),
        )
        db.add(job)
        job_objs.append(job)

    await db.flush()
    search.jobs = job_objs

    return JobSearchOut(
        id=search.id,
        role=search.role,
        location=search.location,
        results_count=search.results_count,
        searched_at=search.searched_at,
        jobs=[JobOut.model_validate(j) for j in job_objs],
    )


@router.get("/searches", response_model=List[JobSearchOut])
async def list_searches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobSearch).where(JobSearch.user_id == current_user.id)
        .order_by(JobSearch.searched_at.desc()).limit(20)
    )
    searches = result.scalars().all()
    out = []
    for s in searches:
        jobs_result = await db.execute(select(Job).where(Job.search_id == s.id))
        jobs = [JobOut.model_validate(j) for j in jobs_result.scalars().all()]
        out.append(JobSearchOut(
            id=s.id, role=s.role, location=s.location,
            results_count=s.results_count, searched_at=s.searched_at, jobs=jobs
        ))
    return out


# ─── MATCH RESUME TO JOBS ─────────────────────

@router.post("/match", response_model=List[JobMatchOut], status_code=201)
async def match_resume(
    payload: MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume_result = await db.execute(
        select(Resume).where(Resume.id == payload.resume_id, Resume.user_id == current_user.id)
    )
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    jobs_result = await db.execute(
        select(Job).where(Job.search_id == payload.search_id)
    )
    jobs = jobs_result.scalars().all()
    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found for this search")

    groq_key = await _get_user_api_key(current_user.id, "groq", "api_key", db)

    match_objs = []
    for job in jobs:
        job_dict = {
            "title": job.title,
            "company": job.company,
            "description": job.description or "",
            "apply_link": job.apply_link,
        }
        match_data = calculate_match(resume.raw_text or "", job_dict, groq_key)
        cover = generate_cover_letter(
            resume.raw_text or "", resume.parsed_data or {}, job_dict, groq_key
        )

        match_obj = JobMatch(
            user_id=current_user.id,
            resume_id=resume.id,
            job_id=job.id,
            ats_score=match_data["ats_score"],
            strengths=match_data["strengths"],
            improvements=match_data["improvements"],
            summary=match_data["summary"],
            cover_letter=cover,
        )
        db.add(match_obj)
        match_objs.append((match_obj, job))

    await db.flush()

    return [
        JobMatchOut(
            id=m.id,
            job_id=m.job_id,
            job_title=j.title or "",
            company=j.company or "",
            location=j.location,
            ats_score=m.ats_score,
            strengths=m.strengths,
            improvements=m.improvements,
            summary=m.summary,
            cover_letter=m.cover_letter,
            apply_link=j.apply_link,
            matched_at=m.matched_at,
        )
        for m, j in sorted(match_objs, key=lambda x: x[0].ats_score, reverse=True)
    ]


@router.get("/matches", response_model=List[JobMatchOut])
async def list_matches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == current_user.id)
        .order_by(JobMatch.ats_score.desc()).limit(50)
    )
    return [
        JobMatchOut(
            id=m.id, job_id=m.job_id,
            job_title=j.title or "", company=j.company or "",
            location=j.location, ats_score=m.ats_score,
            strengths=m.strengths, improvements=m.improvements,
            summary=m.summary, cover_letter=m.cover_letter,
            apply_link=j.apply_link, matched_at=m.matched_at,
        )
        for m, j in result.all()
    ]


# ─── EXPORT TO EXCEL ──────────────────────────

@router.get("/export/{search_id}")
async def export_to_excel(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .join(JobSearch, Job.search_id == JobSearch.id)
        .where(
            JobMatch.user_id == current_user.id,
            JobSearch.id == search_id,
        )
        .order_by(JobMatch.ats_score.desc())
    )
    rows = result.all()

    data = [
        {
            "Job Title": j.title,
            "Company": j.company,
            "Location": j.location,
            "ATS Score (%)": m.ats_score,
            "Key Strengths": "; ".join(m.strengths or []),
            "Improvement Areas": "; ".join(m.improvements or []),
            "Apply Link": j.apply_link,
            "Published": j.published_date,
            "Source": j.source,
            "Cover Letter": m.cover_letter,
        }
        for m, j in rows
    ]

    if not data:
        raise HTTPException(status_code=404, detail="No matched jobs to export")

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Job Matches")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=job_matches_{search_id}.xlsx"},
    )
