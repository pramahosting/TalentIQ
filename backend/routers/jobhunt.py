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
from utils.credentials import get_credential, get_groq_model
from utils.sequencing import next_sequence_number
from agents.jobhunt_agent import (
    scrape_jobs_adzuna, parse_resume_text,
    calculate_match, generate_cover_letter, extract_candidate_profile,
)

router = APIRouter()


async def _get_user_api_key(user_id: int, service: str, key_name: str, db: AsyncSession) -> str | None:
    # Delegates to the centralized, policy-enforcing lookup — Adzuna and
    # Groq (used below) are allowed to fall back to an admin-configured
    # global key; every other service never would.
    return await get_credential(db, user_id, service, key_name)


async def _extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)
        except Exception:
            import pypdf, io as _io
            r = pypdf.PdfReader(_io.BytesIO(content))
            return "\n".join(p.extract_text() or "" for p in r.pages)
    elif filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(content))
    elif filename.endswith(".doc"):
        # Old binary Word format — extract ASCII text stream
        import re as _re
        raw = content.decode("latin-1", errors="ignore")
        chunks = _re.findall(r"[\x20-\x7e\r\n\t]{3,}", raw)
        text = "\n".join(c.strip() for c in chunks if c.strip())
        text = _re.sub(r"bjbj[a-zA-Z0-9]+", "", text)
        text = _re.sub(r"WW8Num\w+", "", text)
        text = _re.sub(r'HYPERLINK\s+"[^"]+"', "", text)
        text = _re.sub(r"\s{4,}", "\n", text)
        return text.strip()
    elif filename.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{filename.split('.')[-1]}'. Please upload PDF, DOCX, DOC, or TXT."
        )


# ─── UPLOAD RESUME ────────────────────────────

@router.post("/resume", response_model=ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_text = await _extract_text_from_file(file)
    parsed = parse_resume_text(raw_text)

    # If same filename already exists for this user, update it instead of duplicating
    existing = await db.execute(
        select(Resume).where(
            Resume.user_id == current_user.id,
            Resume.filename == file.filename,
        )
    )
    resume = existing.scalar_one_or_none()
    if resume:
        resume.raw_text = raw_text
        resume.applicant_name = parsed.get("applicant_name")
        resume.skills = parsed.get("skills", [])
        resume.experience_years = parsed.get("experience_years")
        resume.parsed_data = parsed
    else:
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
    await db.commit()
    await db.refresh(resume)
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
    # Deduplicate by filename — keep most recent per filename
    seen = set()
    resumes = []
    for r in result.scalars().all():
        if r.filename not in seen:
            seen.add(r.filename)
            resumes.append(ResumeOut.model_validate(r))
    return resumes


# ─── JOB SEARCH ───────────────────────────────

@router.post("/search", response_model=JobSearchOut, status_code=201)
async def search_jobs(
    payload: JobSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get user's Adzuna keys (fallback to env defaults)
    # No hardcoded fallback credentials — Adzuna is a shareable service, so
    # if the current user hasn't saved their own key, this transparently
    # falls back to whatever an admin has configured as the platform-wide
    # global key (see utils/credentials.py). If neither exists, the search
    # below will simply return Adzuna's own auth-failure error.
    adzuna_id = await _get_user_api_key(current_user.id, "adzuna", "app_id", db)
    adzuna_key = await _get_user_api_key(current_user.id, "adzuna", "app_key", db)

    # Detect country code for Adzuna from location text
    location_lower = (payload.location or "").lower()
    country_code = "au"
    if any(c in location_lower for c in ["usa", "united states", "new york", "california", "texas"]):
        country_code = "us"
    elif any(c in location_lower for c in ["uk", "united kingdom", "london", "manchester"]):
        country_code = "gb"
    elif any(c in location_lower for c in ["canada", "toronto", "vancouver"]):
        country_code = "ca"
    elif any(c in location_lower for c in ["india", "bangalore", "mumbai", "delhi"]):
        country_code = "in"
    elif "singapore" in location_lower:
        country_code = "sg"
    elif any(c in location_lower for c in ["new zealand", "auckland", "wellington"]):
        country_code = "nz"

    raw_jobs = scrape_jobs_adzuna(
        role=payload.role,
        location=payload.location,
        job_type=payload.job_type or "All",
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        adzuna_app_id=adzuna_id,
        adzuna_app_key=adzuna_key,
        country=country_code,
    )

    adzuna_error = None
    # If Adzuna failed or returned error dict, use simulation fallback
    if not raw_jobs or (len(raw_jobs) == 1 and "error" in raw_jobs[0]):
        adzuna_error = raw_jobs[0].get("error", "No results from Adzuna for this search.") if raw_jobs else "No results"
        # Fall back to simulated jobs so the user gets data
        from agents.jobintel_simulator import simulate_jobs
        location = payload.location or "Australia"
        # Detect country from location
        country = "Australia"
        for c in ["USA", "UK", "India", "Canada", "Singapore"]:
            if c.lower() in location.lower():
                country = c
                break
        sim_jobs = simulate_jobs(country=country, domain=payload.industry or "Technology", count=20)
        # Filter by role keyword
        role_lower = payload.role.lower()
        raw_jobs = []
        for j in sim_jobs:
            title = (j.get("title") or "").lower()
            # Include if title matches role keywords or include all if no match
            if any(w in title for w in role_lower.split()) or len(raw_jobs) < 10:
                raw_jobs.append({
                    "title": j["title"],
                    "company": j["company"],
                    "location": j["location"],
                    "job_type": j["job_type"],
                    "description": f"Key skills: {', '.join(j.get('key_skills', [])[:5])}. "
                                   f"Experience: {j.get('experience_years')} years. "
                                   f"Tools: {', '.join(j.get('tools_technologies', [])[:3])}.",
                    "source": j["source"],
                    "apply_link": j["source_url"],
                    "published_date": j["date_posted"],
                    "source_site": j["source"],
                    "salary_min": j.get("salary_min"),
                    "salary_max": j.get("salary_max"),
                })
            if len(raw_jobs) >= 20:
                break

    # Persist search
    seq_num = await next_sequence_number(db, JobSearch, current_user.id)
    search = JobSearch(
        user_id=current_user.id,
        sequence_number=seq_num,
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

    # Persist jobs — skip any error dicts
    job_objs = []
    for j in raw_jobs:
        if "error" in j:
            continue
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
    await db.commit()
    await db.refresh(search)

    return JobSearchOut(
        id=search.id,
        sequence_number=search.sequence_number or search.id,
        role=search.role,
        location=search.location,
        results_count=search.results_count,
        searched_at=search.searched_at,
        jobs=[JobOut.model_validate(j) for j in job_objs],
        notice=(
            f"Live job board unavailable ({adzuna_error}). Showing AI-simulated listings instead."
            if adzuna_error else None
        ),
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
            id=s.id, sequence_number=s.sequence_number or s.id, role=s.role, location=s.location,
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
    groq_model = await get_groq_model(db, current_user.id)

    # Extract the candidate's profile ONCE for this batch — reused across
    # every job below instead of re-extracting the same resume repeatedly.
    candidate_profile = await extract_candidate_profile(resume.raw_text or "", groq_key, groq_model)

    match_objs = []
    for job in jobs:
        job_dict = {
            "title": job.title,
            "company": job.company,
            "description": job.description or "",
            "apply_link": job.apply_link,
        }
        match_data = await calculate_match(resume.raw_text or "", job_dict, groq_key, candidate_profile, groq_model)
        cover = generate_cover_letter(
            resume.raw_text or "", resume.parsed_data or {}, job_dict, groq_key, groq_model
        )

        match_obj = JobMatch(
            user_id=current_user.id,
            resume_id=resume.id,
            job_id=job.id,
            ats_score=match_data["ats_score"],
            strengths=match_data["strengths"],
            improvements=match_data["improvements"],
            summary=match_data["summary"],
            strengths_breakdown=match_data.get("strengths_breakdown", {}),
            jd_requirements=match_data.get("jd_requirements", {}),
            cover_letter=cover,
        )
        db.add(match_obj)
        match_objs.append((match_obj, job))

    await db.commit()

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
            strengths_breakdown=m.strengths_breakdown,
            jd_requirements=m.jd_requirements,
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
            summary=m.summary, strengths_breakdown=m.strengths_breakdown,
            jd_requirements=m.jd_requirements, cover_letter=m.cover_letter,
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


# ─── DELETE SEARCH ─────────────────────────────

@router.delete("/searches/{search_id}")
async def delete_search(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a job search and all its jobs/matches."""
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        select(JobSearch).where(
            JobSearch.id == search_id,
            JobSearch.user_id == current_user.id,
        )
    )
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(404, "Search not found")
    # Get job IDs
    job_ids_r = await db.execute(select(Job.id).where(Job.search_id == search_id))
    job_ids = [r[0] for r in job_ids_r.all()]
    if job_ids:
        await db.execute(sql_delete(JobMatch).where(JobMatch.job_id.in_(job_ids)))
        await db.execute(sql_delete(Job).where(Job.search_id == search_id))
    await db.delete(search)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/searches")
async def delete_all_searches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all job searches for the current user."""
    from sqlalchemy import delete as sql_delete
    searches_r = await db.execute(
        select(JobSearch.id).where(JobSearch.user_id == current_user.id)
    )
    search_ids = [r[0] for r in searches_r.all()]
    if search_ids:
        job_ids_r = await db.execute(select(Job.id).where(Job.search_id.in_(search_ids)))
        job_ids = [r[0] for r in job_ids_r.all()]
        if job_ids:
            await db.execute(sql_delete(JobMatch).where(JobMatch.job_id.in_(job_ids)))
        await db.execute(sql_delete(Job).where(Job.search_id.in_(search_ids)))
        await db.execute(sql_delete(JobSearch).where(JobSearch.user_id == current_user.id))
    await db.commit()
    return {"message": f"Deleted {len(search_ids)} searches"}