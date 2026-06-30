"""
TalentIQ - CandidateLens Router
Mirrors the original JobLens scoring logic:
  1. LLM extracts skills from JD (Groq instead of Ollama)
  2. Keyword match CV text against extracted skills
  3. Bonus for degree/experience mentions
  4. Generate interview questions via LLM
All persisted to PostgreSQL (tiq_joblens_* tables).
"""
import io
import re
import os
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from db.database import get_db, AsyncSessionLocal
from models.models import User, UserAPIKey, JobLensSession, JobLensCandidate
from utils.auth_utils import get_current_user

router = APIRouter()


# ── TEXT EXTRACTION ─────────────────────────────────────────────────────────

def extract_text(content: bytes, filename: str) -> str:
    fname = (filename or "").lower()
    if fname.endswith(".txt"):
        for enc in ("utf-8", "latin-1", "cp1252"):
            try: return content.decode(enc)
            except: continue
        return ""
    if fname.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                t = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
                if t: return t
        except: pass
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(content))
            t = "\n".join(p.extract_text() or "" for p in r.pages).strip()
            if t: return t
        except: pass
        return ""
    if fname.endswith((".docx", ".doc")):
        # Try python-docx first (works on .docx)
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip(): parts.append(cell.text.strip())
            t = "\n".join(parts).strip()
            if t: return t
        except: pass
        # Try docx2txt
        try:
            import docx2txt
            t = docx2txt.process(io.BytesIO(content))
            if t and t.strip(): return t.strip()
        except: pass
        # Fallback for old binary .doc (OLE2 format): extract ASCII text stream
        if fname.endswith(".doc"):
            try:
                import re as _re
                raw = content.decode("latin-1", errors="ignore")
                chunks = _re.findall(r"[\x20-\x7e\r\n\t]{3,}", raw)
                text = "\n".join(c.strip() for c in chunks if c.strip())
                # Remove common .doc binary artifacts
                text = _re.sub(r"bjbj[a-zA-Z0-9]+", "", text)
                text = _re.sub(r"WW8Num\w+", "", text)
                text = _re.sub(r'HYPERLINK\s+"[^"]+"', "", text)
                text = _re.sub(r"\\r", "\n", text)
                text = _re.sub(r"\s{4,}", "\n", text)
                text = _re.sub(r"\n{3,}", "\n\n", text).strip()
                if len(text) > 100:
                    return text
            except: pass
        return ""
    for enc in ("utf-8", "latin-1"):
        try: return content.decode(enc).strip()
        except: continue
    return ""


# ── CANDIDATE INFO EXTRACTION ────────────────────────────────────────────────

def extract_candidate_info(text: str, filename: str) -> dict:
    """Extract name, email, phone — mirrors original extractCandidateDetails."""
    # Email
    email_m = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,6}", text)
    email = email_m.group() if email_m else ""

    # Phone — original regex: (+?\d{1,4}[\s-]?\(?\d{1,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4})
    phone_m = re.search(r"(\+?\d{1,4}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})", text)
    phone = phone_m.group().replace(" ", "").strip() if phone_m else ""
    # Reject cert numbers: must have spaces/dashes or start with +
    if phone and not re.search(r"[\s\-\+\(\)]", phone_m.group() if phone_m else ""):
        phone = ""

    # Name — mirrors original: first non-email, non-4digit, <=5 word line
    name = ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:25]:
        if "@" in line:
            continue
        if re.search(r"\d{4,}", line):
            continue
        if len(line.split()) <= 5 and len(line) > 2:
            candidate = re.sub(r"[^a-zA-Z\s\-\.]", "", line).strip()
            if candidate and len(candidate) > 2:
                name = candidate
                break

    if not name:
        name = Path(filename).stem.replace("_", " ").replace("-", " ").title()

    return {"name": name, "email": email, "phone": phone}


# ── SKILL EXTRACTION FROM JD (LLM) ──────────────────────────────────────────

async def extract_skills_from_jd(jd_text: str, groq_key: str) -> list:
    """Mirrors buildKeywordExtractPrompt + callOllamaGenerate — uses Groq instead."""
    try:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.1)
        prompt = f"""You are a recruitment AI assistant.
Extract the most important role-related keywords from the Job Description below.
These keywords should reflect skills, tools, certifications, and responsibilities.

Job Description:
\"\"\"{jd_text[:3000]}\"\"\"

Return ONLY valid JSON in this format:
{{
  "role": "<job role>",
  "skills": ["skill1", "skill2", "skill3"]
}}"""

        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        skills = data.get("skills", [])
        return [s.lower().strip() for s in skills if s]
    except Exception:
        return _keyword_extract_jd(jd_text)


def _keyword_extract_jd(jd_text: str) -> list:
    """Fallback keyword extraction — returns only real skills, not JD prose."""
    DOMAIN_SKILLS = [
        "python","javascript","typescript","react","node","sql","postgresql","mongodb",
        "aws","azure","gcp","docker","kubernetes","git","agile","rest","api","graphql",
        "machine learning","ai","data science","excel","power bi","tableau","salesforce",
        "figma","django","flask","java","c#","c++","go","spark","kafka","dbt","snowflake",
        "databricks","redshift","bigquery","data architecture","data governance","etl",
        "xero","myob","quickbooks","sap","oracle","dynamics","netsuite",
        "cpa","ca","acca","cma","mba","cfa","accounting","tax","audit","payroll",
        "financial reporting","budgeting","forecasting","reconciliation","ifrs","gaap",
        "leadership","communication","problem solving","scrum","project management",
        "togaf","pmp","csm","hadoop","hive","datastage","tibco","react native",
        "devops","ci/cd","terraform","ansible","linux","bash","swift","kotlin",
        "microservices","restful","graphql","redis","elasticsearch","rabbitmq",
    ]
    jd_lower = jd_text.lower()
    found = [s for s in DOMAIN_SKILLS if s in jd_lower]
    return list(dict.fromkeys(found))[:30]


# ── SCORING (mirrors calculateScore exactly) ─────────────────────────────────

def calculate_score(cv_text: str, jd_skills: list) -> dict:
    """Direct port of the original JS calculateScore function."""
    # Clean CV text same way as original
    cv_lower = cv_text.lower()
    cv_lower = re.sub(r"\b(an|the|and|or|of|in|on|for|with|to|be|is|are|it|at|from|as|by|that|this|if|we|you)\b", "", cv_lower)
    cv_lower = re.sub(r"[^a-z0-9+#.\-]", " ", cv_lower)

    matched = [s for s in jd_skills if s in cv_lower]
    gap     = [s for s in jd_skills if s not in cv_lower]

    score = (len(matched) / len(jd_skills) * 100) if jd_skills else 0
    bonus = 0
    reasons = []

    if re.search(r"bachelor|master|degree", cv_lower):
        bonus += 10
        reasons.append("Degree +10")

    if re.search(r"experience|\d+\s+(years|year)", cv_lower):
        bonus += 10
        reasons.append("Experience +10")

    score = min(100, score + bonus)

    return {
        "score":   round(score, 1),
        "matched": matched,
        "gap":     gap,
        "bonus":   bonus,
        "reasons": "; ".join(reasons),
    }


# ── QUESTION GENERATION ──────────────────────────────────────────────────────

async def generate_questions(jd_text: str, candidate_name: str, matched_skills: list, groq_key: str) -> list:
    """Mirrors buildQuestionPrompt + callOllamaGenerate."""
    try:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.4)
        skills_str = ", ".join(matched_skills[:8]) if matched_skills else "relevant skills"
        prompt = f"""You are a recruitment AI assistant.
Generate exactly 5 interview questions for {candidate_name} based on the Job Description below.
Focus on required skills ({skills_str}), tools, and responsibilities.

Job Description:
\"\"\"{jd_text[:1500]}\"\"\"

Return ONLY valid JSON:
{{
  "questions": ["Question 1","Question 2","Question 3","Question 4","Question 5"]
}}"""

        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return data.get("questions", [])[:5]
    except Exception:
        return _default_questions(candidate_name, matched_skills)


def _default_questions(name: str, skills: list) -> list:
    qs = []
    if skills:
        qs.append(f"Tell me about a project where you used {skills[0]}.")
        if len(skills) > 1:
            qs.append(f"Rate your proficiency in {skills[1]} and give a real example.")
        if len(skills) > 2:
            qs.append(f"What challenges have you faced with {skills[2]}?")
    qs.append(f"Why are you the right candidate for this role, {name}?")
    qs.append("Where do you see yourself in 3 years?")
    return qs[:5]


# ── FORMAT _FORMAT_CANDIDATE ─────────────────────────────────────────────────

def _fmt(c: JobLensCandidate) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "filename": c.filename,
        "ats_score": round(c.ats_score, 1),
        "status": c.status,
        "matched_skills": c.matched_skills or [],
        "missing_skills": c.missing_skills or [],
        "bonus": c.bonus,
        "bonus_reasons": c.bonus_reasons,
        "video_status": c.video_status,
        "shortlisted": c.shortlisted,
        "interview_questions": c.interview_questions or [],
        "emotion_happy": c.emotion_happy,
        "emotion_neutral": c.emotion_neutral,
        "emotion_sad": c.emotion_sad,
        "emotion_angry": c.emotion_angry,
        "emotion_fear": c.emotion_fear,
        "emotion_disgust": c.emotion_disgust,
        "emotion_surprise": c.emotion_surprise,
        "dominant_emotion": c.dominant_emotion,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/run")
async def run_joblens(
    jd_text: str = Form(""),
    low_threshold: int = Form(40),
    high_threshold: int = Form(70),
    jd_file: Optional[UploadFile] = File(None),
    cv_files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ── Extract JD ────────────────────────────────────────────────────
    final_jd = jd_text.strip()
    if jd_file and jd_file.filename:
        raw = await jd_file.read()
        extracted = extract_text(raw, jd_file.filename)
        if extracted.strip():
            final_jd = extracted
    if not final_jd:
        raise HTTPException(400, "Job description is required.")
    if not cv_files:
        raise HTTPException(400, "At least one CV is required.")

    # ── Get Groq key ──────────────────────────────────────────────────
    kr = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == current_user.id,
            UserAPIKey.service == "groq",
        )
    )
    groq_key = next((k.key_value for k in kr.scalars().all() if k.key_name == "api_key"), None)

    # ── Extract JD skills (LLM or keyword) ───────────────────────────
    if groq_key:
        jd_skills = await extract_skills_from_jd(final_jd, groq_key)
    else:
        jd_skills = _keyword_extract_jd(final_jd)

    # ── Create session ─────────────────────────────────────────────────
    try:
        session = JobLensSession(
            user_id=current_user.id,
            jd_text=final_jd,
            jd_skills=jd_skills,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            status="completed",
            cv_count=len(cv_files),
            created_at=datetime.utcnow(),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    except Exception as e:
        raise HTTPException(500, f"DB error creating session: {str(e)}")

    # ── Score each CV ──────────────────────────────────────────────────
    candidates = []
    for upload in cv_files:
        try:
            content = await upload.read()
            cv_text = extract_text(content, upload.filename)
            if not cv_text.strip():
                continue

            info   = extract_candidate_info(cv_text, upload.filename)
            result = calculate_score(cv_text, jd_skills)

            score  = result["score"]
            status = "Not Qualified"
            if score >= high_threshold:
                status = "Qualified"
            elif score >= low_threshold:
                status = "Review"

            # Generate questions immediately if Groq available
            questions = []
            if groq_key:
                questions = await generate_questions(
                    final_jd, info["name"], result["matched"], groq_key
                )
            else:
                questions = _default_questions(info["name"], result["matched"])

            candidate = JobLensCandidate(
                session_id=session.id,
                name=info["name"],
                email=info["email"],
                phone=info["phone"],
                filename=upload.filename,
                ats_score=score,
                status=status,
                matched_skills=result["matched"],
                missing_skills=result["gap"],
                bonus=result["bonus"],
                bonus_reasons=result["reasons"],
                interview_questions=questions,
                video_status="Pending",
                shortlisted=False,
            )
            db.add(candidate)
            candidates.append(candidate)
        except Exception as e:
            print(f"Error processing {upload.filename}: {e}")
            continue

    await db.commit()
    for c in candidates:
        await db.refresh(c)

    candidates.sort(key=lambda c: c.ats_score, reverse=True)

    return {
        "session_id": session.id,
        "jd_skills":  jd_skills[:30],
        "ai_powered": groq_key is not None,
        "total":      len(candidates),
        "candidates": [_fmt(c) for c in candidates],
    }


@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(JobLensSession)
        .where(JobLensSession.user_id == current_user.id)
        .order_by(JobLensSession.created_at.desc())
    )
    return [
        {
            "id": s.id, "cv_count": s.cv_count,
            "low_threshold": s.low_threshold, "high_threshold": s.high_threshold,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "jd_preview": (s.jd_text or "")[:120] + "...",
            "ai_powered": False,
        }
        for s in r.scalars().all()
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sr = await db.execute(
        select(JobLensSession).where(
            JobLensSession.id == session_id,
            JobLensSession.user_id == current_user.id,
        )
    )
    session = sr.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    cr = await db.execute(
        select(JobLensCandidate)
        .where(JobLensCandidate.session_id == session_id)
        .order_by(JobLensCandidate.ats_score.desc())
    )
    candidates = cr.scalars().all()

    return {
        "id": session.id,
        "jd_text": session.jd_text,
        "jd_skills": session.jd_skills,
        "low_threshold": session.low_threshold,
        "high_threshold": session.high_threshold,
        "status": session.status,
        "cv_count": session.cv_count,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "candidates": [_fmt(c) for c in candidates],
    }


@router.post("/sessions/{session_id}/candidates/{candidate_id}/questions")
async def get_questions(
    session_id: int,
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sr = await db.execute(
        select(JobLensSession).where(
            JobLensSession.id == session_id,
            JobLensSession.user_id == current_user.id,
        )
    )
    session = sr.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    candidate = cr.scalar_one_or_none()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    # Return existing questions or regenerate
    if candidate.interview_questions:
        return {"questions": candidate.interview_questions, "ai_powered": False}

    kr = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == current_user.id,
            UserAPIKey.service == "groq",
        )
    )
    groq_key = next((k.key_value for k in kr.scalars().all() if k.key_name == "api_key"), None)

    if groq_key:
        questions = await generate_questions(
            session.jd_text or "", candidate.name,
            candidate.matched_skills or [], groq_key
        )
    else:
        questions = _default_questions(candidate.name, candidate.matched_skills or [])

    candidate.interview_questions = questions
    await db.commit()
    return {"questions": questions, "ai_powered": groq_key is not None}


@router.put("/candidates/{candidate_id}/shortlist")
async def toggle_shortlist(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.shortlisted = not c.shortlisted
    await db.commit()
    return {"shortlisted": c.shortlisted}


class InterviewResult(BaseModel):
    happy: int = 0
    neutral: int = 0
    sad: int = 0
    angry: int = 0
    fear: int = 0
    disgust: int = 0
    surprise: int = 0
    dominant: str = "Neutral"


@router.post("/candidates/{candidate_id}/interview-result")
async def save_interview_result(
    candidate_id: int,
    result: InterviewResult,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.emotion_happy    = result.happy
    c.emotion_neutral  = result.neutral
    c.emotion_sad      = result.sad
    c.emotion_angry    = result.angry
    c.emotion_fear     = result.fear
    c.emotion_disgust  = result.disgust
    c.emotion_surprise = result.surprise
    c.dominant_emotion = result.dominant
    c.video_status     = "Completed"
    await db.commit()
    return {"status": "saved"}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import pandas as pd

    sr = await db.execute(
        select(JobLensSession).where(
            JobLensSession.id == session_id,
            JobLensSession.user_id == current_user.id,
        )
    )
    session = sr.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    cr = await db.execute(
        select(JobLensCandidate)
        .where(JobLensCandidate.session_id == session_id)
        .order_by(JobLensCandidate.ats_score.desc())
    )
    candidates = cr.scalars().all()

    rows = []
    for i, c in enumerate(candidates, 1):
        rows.append({
            "Rank":            i,
            "Name":            c.name,
            "Email":           c.email,
            "Phone":           c.phone,
            "ATS Score":       f"{c.ats_score:.1f}%",
            "Status":          c.status,
            "Matched Skills":  ", ".join(c.matched_skills or []),
            "Missing Skills":  ", ".join(c.missing_skills or []),
            "Bonus Points":    c.bonus,
            "Bonus Reasons":   c.bonus_reasons,
            "Video Status":    c.video_status,
            "Happy %":         c.emotion_happy or 0,
            "Neutral %":       c.emotion_neutral or 0,
            "Sad %":           c.emotion_sad or 0,
            "Angry %":         c.emotion_angry or 0,
            "Fear %":          c.emotion_fear or 0,
            "Disgust %":       c.emotion_disgust or 0,
            "Surprise %":      c.emotion_surprise or 0,
            "Dominant Emotion": c.dominant_emotion or "Neutral",
            "Shortlisted":     "Yes" if c.shortlisted else "No",
        })

    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=candidatelens_{session_id}.xlsx"},
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a CandidateLens session and all its candidates."""
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        select(JobLensSession).where(
            JobLensSession.id == session_id,
            JobLensSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    await db.execute(sql_delete(JobLensCandidate).where(JobLensCandidate.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/sessions")
async def delete_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete ALL sessions for the current user."""
    from sqlalchemy import delete as sql_delete
    ids_r = await db.execute(
        select(JobLensSession.id).where(JobLensSession.user_id == current_user.id)
    )
    ids = [r[0] for r in ids_r.all()]
    if ids:
        await db.execute(sql_delete(JobLensCandidate).where(JobLensCandidate.session_id.in_(ids)))
        await db.execute(sql_delete(JobLensSession).where(JobLensSession.user_id == current_user.id))
        await db.commit()
    return {"message": f"Deleted {len(ids)} sessions"}