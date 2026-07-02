"""
TalentIQ - CVAnalysis Router
Resume vs Job Description ATS analyser.
Supports PDF, DOCX, TXT for both resume and job description.
"""
import io
import re
import json
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from models.models import User, UserAPIKey, CVAnalysisRecord
from utils.auth_utils import get_current_user
from utils.credentials import get_credential
from utils.sequencing import next_sequence_number

router = APIRouter()


def _extract_text(content: bytes, filename: str) -> str:
    """Extract plain text from file bytes. Tries multiple libraries with fallbacks."""
    fname = (filename or "").lower().strip()

    # ── TXT ──────────────────────────────────────────────────────────────
    if fname.endswith(".txt"):
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return content.decode(enc)
            except Exception:
                continue
        return ""

    # ── PDF ──────────────────────────────────────────────────────────────
    if fname.endswith(".pdf"):
        # Try pdfplumber first
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                text = "\n".join(pages).strip()
                if text:
                    return text
        except Exception:
            pass

        # Try pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text
        except Exception:
            pass

        # Try PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc).strip()
            if text:
                return text
        except Exception:
            pass

        return ""

    # ── DOCX ─────────────────────────────────────────────────────────────
    if fname.endswith((".docx", ".doc")):
        # Try python-docx
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))

            # Headers can contain name/email/phone in letterhead-style resumes.
            # python-docx's section.header only reads ONE header per section,
            # but a docx can store up to 3 (header1/2/3.xml) — read all via XML.
            header_footer_parts = []
            try:
                import re as _re2
                import zipfile as _zipfile
                with _zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if _re2.match(r"word/(header|footer)\d*\.xml$", name):
                            xml = z.read(name).decode("utf-8", errors="ignore")
                            texts = _re2.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
                            joined = "".join(texts).strip()
                            if joined:
                                header_footer_parts.append(joined)
            except Exception:
                pass

            paragraphs = list(header_footer_parts)
            paragraphs += [p.text for p in doc.paragraphs if p.text.strip()]
            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            paragraphs.append(cell.text.strip())
            text = "\n".join(paragraphs).strip()
            if text:
                return text
        except Exception:
            pass

        # Try docx2txt
        try:
            import docx2txt
            text = docx2txt.process(io.BytesIO(content))
            if text and text.strip():
                return text.strip()
        except Exception:
            pass

        return ""

    # ── Fallback: try decoding as text ────────────────────────────────────
    for enc in ("utf-8", "latin-1"):
        try:
            text = content.decode(enc).strip()
            if text:
                return text
        except Exception:
            continue
    return ""


# ── KEYWORD SCORING ────────────────────────────────────────────────────────────

DOMAIN_SKILLS = [
    "python","javascript","typescript","react","node","sql","postgresql","mongodb",
    "aws","azure","gcp","docker","kubernetes","git","agile","rest","api","graphql",
    "machine learning","ai","artificial intelligence","data science","excel","power bi","tableau","salesforce",
    "figma","django","flask","java","c#","c++","go","spark","kafka","airflow","dbt",
    "snowflake","databricks","redshift","bigquery","data architecture","data governance",
    "data modelling","data modeling","data warehouse","data lake","data lakehouse","lakehouse",
    "etl","elt","data pipeline","solution design","data mesh","data fabric","data vault",
    "dimensional modelling","dimensional modeling","enterprise data warehouse","edw",
    "master data management","mdm","data quality","data catalog","data cataloguing",
    "collibra","alation","informatica","talend","teradata","hadoop","hive","hbase",
    "adls","synapse","azure data factory","azure synapse","event-driven architecture",
    "real-time data","streaming","microservices architecture","enterprise architecture",
    "solution architecture","cloud architecture","togaf","zachman",
    "stakeholder management","cloud architecture","microservices","devops","ci/cd",
    "xero","myob","quickbooks","sap","oracle","dynamics","netsuite","sage",
    "cpa","ca","acca","cma","mba","cfa","fcpa","aca","phd",
    "accounting","tax","audit","payroll","bookkeeping","bas","gst",
    "financial reporting","budgeting","forecasting","reconciliation",
    "accounts payable","accounts receivable","ifrs","gaap",
    "leadership","communication","problem solving","teamwork","stakeholder",
    "management","strategy","operations","project management","scrum","nlp","llm",
    "basel","basel iii","banking","bfsi","insurance","lending","regulatory compliance",
    "risk management","governance framework","data governance framework",
]

STOPWORDS = {"a","an","the","and","or","of","in","on","for","with","to","be","is",
             "are","it","at","from","as","by","that","this","we","you","have","has"}


# ══════════════════════════════════════════════════════════════════════════════
# ATS SCORING — two-stage structured extraction + deterministic weighted scoring
#
# The old approach asked the LLM for a single overall number directly, which
# is exactly the kind of unreliable, unrepeatable scoring that makes ATS
# tools untrustworthy. This mirrors what real ATS-checker products (Jobscan,
# Enhancv, etc.) actually do instead:
#   1. Extract structured JD requirements (hard skills, experience, education)
#   2. Extract a structured candidate profile from the resume
#   3. Compute the score with plain, transparent, reproducible Python math —
#      the LLM's job is understanding text, not doing arithmetic.
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_skill(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _skill_present(skill: str, candidate_skills: set, resume_lower: str) -> bool:
    """A skill counts as present if it's in the extracted skill list OR
    appears as a substring in the raw resume text (catches skills the LLM
    extraction missed, e.g. mentioned once in a project description)."""
    sk = _normalize_skill(skill)
    if any(sk in cs or cs in sk for cs in candidate_skills):
        return True
    return sk in resume_lower


async def _extract_jd_requirements(jd: str, groq_key: Optional[str]) -> dict:
    """Structured requirements extraction. Falls back to a keyword-bank
    heuristic when no Groq key is configured."""
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.1)
            prompt = f"""You are an expert technical recruiter. Read the job description below
and extract its requirements precisely — do not invent requirements that
aren't stated or clearly implied.

JOB DESCRIPTION:
\"\"\"{jd[:4000]}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "role_title": "<best-guess title>",
  "required_hard_skills": ["<skill>", ...],
  "nice_to_have_skills": ["<skill>", ...],
  "min_years_experience": <integer, 0 if not stated>,
  "education_requirement": "<short phrase, or empty string if not stated>",
  "seniority_level": "<Junior|Mid|Senior|Lead|Executive|Not specified>",
  "key_responsibilities": ["<responsibility>", ...]
}}"""
            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip()
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(raw)
            if data.get("required_hard_skills"):
                return data
        except Exception:
            pass
    return _fallback_jd_requirements(jd)


def _fallback_jd_requirements(jd: str) -> dict:
    jd_lower = jd.lower()
    found = [s for s in DOMAIN_SKILLS if s in jd_lower]
    # Also pick up capitalised/technical-looking tokens not in our bank
    extra = []
    for t in re.findall(r"\b([a-zA-Z][a-zA-Z0-9+#.\-]{2,})\b", jd):
        tl = t.lower()
        if tl not in STOPWORDS and tl not in found and tl not in extra and len(t) > 3:
            extra.append(tl)
    all_skills = list(dict.fromkeys(found + extra))[:25]

    years_m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", jd_lower)
    min_years = int(years_m.group(1)) if years_m else 0

    edu = ""
    edu_m = re.search(r"(bachelor'?s?|master'?s?|phd|degree|diploma)[^.]{0,80}", jd_lower)
    if edu_m:
        edu = edu_m.group().strip().capitalize()

    return {
        "role_title": "",
        "required_hard_skills": all_skills[:15],
        "nice_to_have_skills": all_skills[15:20],
        "min_years_experience": min_years,
        "education_requirement": edu,
        "seniority_level": "Not specified",
        "key_responsibilities": [],
    }


async def _extract_candidate_profile(resume: str, jd_requirements: dict, groq_key: Optional[str]) -> dict:
    """Structured candidate profile extraction, plus narrative feedback
    written WITH the JD requirements in view (so strengths/gaps are
    specific to this job, not generic resume advice). Falls back to a
    keyword heuristic profile (no narrative) when no Groq key is set."""
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.15)
            prompt = f"""You are an expert ATS engine and recruitment analyst. You have already
extracted these requirements from the job description:
{json.dumps(jd_requirements, indent=2)[:1500]}

Now read the resume below and extract the candidate's profile, then give
specific feedback comparing them to the requirements above. Be precise and
factual — do not credit skills or experience the resume doesn't support.

RESUME:
\"\"\"{resume[:4000]}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "candidate_hard_skills": ["<skill>", ...],
  "years_experience": <integer, best estimate from resume>,
  "education": "<highest qualification found, or empty string>",
  "seniority_level": "<Junior|Mid|Senior|Lead|Executive>",
  "strengths": ["<specific to this JD>", "<...>", "<...>"],
  "gaps": ["<specific missing requirement>", "<...>", "<...>"],
  "suggestions": ["<actionable, specific>", "<...>", "<...>", "<...>"],
  "summaryAssessment": "<2-3 sentences, specific to this role>",
  "formatWarnings": ["<...>", "<...>"]
}}"""
            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip()
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(raw)
            if data.get("candidate_hard_skills") is not None:
                data["_ai_powered"] = True
                return data
        except Exception:
            pass
    return _fallback_candidate_profile(resume)


def _fallback_candidate_profile(resume: str) -> dict:
    resume_lower = resume.lower()
    found_skills = [s for s in DOMAIN_SKILLS if s in resume_lower]

    years_m = re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", resume_lower)
    years = max((int(y) for y in years_m), default=0)

    education = ""
    edu_m = re.search(r"(bachelor'?s?|master'?s?|phd|degree|diploma)[^.\n]{0,80}", resume_lower)
    if edu_m:
        education = edu_m.group().strip().capitalize()

    return {
        "candidate_hard_skills": found_skills,
        "years_experience": years,
        "education": education,
        "seniority_level": "Not specified",
        "strengths": [],
        "gaps": [],
        "suggestions": [],
        "summaryAssessment": "",
        "formatWarnings": [],
        "_ai_powered": False,
    }


def _compute_weighted_score(jd_req: dict, profile: dict, resume: str) -> dict:
    """Deterministic, transparent scoring — plain Python math over the
    structured fields extracted above. Weights: hard-skill coverage 50%,
    experience-level fit 25%, education fit 10%, nice-to-have bonus 10%,
    baseline content-depth allowance 5%."""
    resume_lower = resume.lower()
    candidate_skill_set = {_normalize_skill(s) for s in profile.get("candidate_hard_skills", [])}

    required = [_normalize_skill(s) for s in jd_req.get("required_hard_skills", []) if s]
    nice = [_normalize_skill(s) for s in jd_req.get("nice_to_have_skills", []) if s]

    matched = [s for s in required if _skill_present(s, candidate_skill_set, resume_lower)]
    missing = [s for s in required if s not in matched]
    matched_nice = [s for s in nice if _skill_present(s, candidate_skill_set, resume_lower)]

    skills_pct = round(len(matched) / len(required) * 100) if required else 70

    min_years = jd_req.get("min_years_experience") or 0
    cand_years = profile.get("years_experience") or 0
    if min_years <= 0:
        experience_pct = 85
    else:
        experience_pct = max(20, min(100, round(cand_years / min_years * 100)))

    edu_req = (jd_req.get("education_requirement") or "").lower()
    edu_cand = (profile.get("education") or "").lower()
    if not edu_req:
        education_pct = 90
    elif edu_cand and (edu_cand in edu_req or edu_req in edu_cand or
                        any(w in edu_cand for w in ["bachelor", "master", "phd", "degree", "diploma"] if w in edu_req)):
        education_pct = 100
    else:
        education_pct = 45

    nice_bonus_pct = min(100, len(matched_nice) * 25) if nice else 60

    overall = (
        skills_pct * 0.50 +
        experience_pct * 0.25 +
        education_pct * 0.10 +
        nice_bonus_pct * 0.10 +
        75 * 0.05
    )
    overall = max(8, min(98, round(overall)))

    return {
        "overall": overall,
        "skills_pct": skills_pct,
        "experience_pct": experience_pct,
        "education_pct": education_pct,
        "matched": matched,
        "missing": missing,
        "matched_nice": matched_nice,
    }


async def _score_resume(resume: str, jd: str, groq_key: Optional[str]) -> dict:
    jd_req = await _extract_jd_requirements(jd, groq_key)
    profile = await _extract_candidate_profile(resume, jd_req, groq_key)
    scoring = _compute_weighted_score(jd_req, profile, resume)
    ai_powered = bool(profile.pop("_ai_powered", False))

    matched, missing = scoring["matched"], scoring["missing"]
    overall = scoring["overall"]

    strengths = profile.get("strengths") or []
    gaps = profile.get("gaps") or []
    suggestions = profile.get("suggestions") or []
    summary = profile.get("summaryAssessment") or ""
    format_warnings = profile.get("formatWarnings") or []

    # Deterministic fallback narrative if the LLM path wasn't used (or
    # returned thin content) — grounded directly in the computed match,
    # not a separate guess.
    if not strengths:
        if matched:
            strengths.append(f"Matches {len(matched)} of {len(jd_req.get('required_hard_skills', []) or [1])} required skills: {', '.join(matched[:6])}")
        if scoring["experience_pct"] >= 90:
            strengths.append("Experience level meets or exceeds the role's requirement")
        if not strengths:
            strengths.append("Resume presents a relevant professional background")
    if not gaps:
        gaps = [f"Missing required skill: {s}" for s in missing[:6]] or ["No major skill gaps detected against the extracted requirements"]
    if not suggestions:
        suggestions = [f'Add specific, verifiable experience with "{s}" if you have it' for s in missing[:4]]
        suggestions += [
            "Quantify achievements with concrete metrics (%, $, time saved)",
            "Mirror the exact terminology used in the job description",
        ]
    if not summary:
        exp_clause = f" and roughly {scoring['experience_pct']}% of the target experience level" if jd_req.get('min_years_experience') else ""
        summary = (
            f"Matches {scoring['skills_pct']}% of the required hard skills{exp_clause}. "
            f"Overall fit: {'Strong' if overall >= 75 else 'Moderate' if overall >= 55 else 'Needs improvement'}."
        )
    if not format_warnings:
        format_warnings = [
            "Use standard ATS-compatible section headers (Experience, Education, Skills)",
            "Avoid tables, columns, or text boxes — ATS parsers often can't read them",
        ]

    return {
        "overallScore": overall,
        "strengths": strengths[:6],
        "gaps": gaps[:6],
        "suggestions": suggestions[:6],
        "summaryAssessment": summary,
        "formatWarnings": format_warnings[:4],
        "detailedScores": {
            "skillsMatch": scoring["skills_pct"],
            "experience": scoring["experience_pct"],
            "tools": scoring["skills_pct"],
            "domain": max(30, overall - 5),
            "softSkills": max(30, overall - 10),
            "format": min(92, overall + 8),
        },
        "matchedSkills": [s.title() for s in matched][:15],
        "missingSkills": [s.title() for s in missing][:15],
        "aiPowered": ai_powered,
        "extractedRequirements": {
            "roleTitle": jd_req.get("role_title", ""),
            "minYearsExperience": jd_req.get("min_years_experience", 0),
            "educationRequirement": jd_req.get("education_requirement", ""),
            "seniorityLevel": jd_req.get("seniority_level", ""),
        },
        "candidateProfile": {
            "yearsExperience": profile.get("years_experience", 0),
            "education": profile.get("education", ""),
            "seniorityLevel": profile.get("seniority_level", ""),
        },
    }


# ── ENDPOINT ───────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_resume(
    job_description: str   = Form(""),
    resume_text: str       = Form(""),
    file:     Optional[UploadFile] = File(None),
    jd_file:  Optional[UploadFile] = File(None),
    current_user: User     = Depends(get_current_user),
    db: AsyncSession       = Depends(get_db),
):
    # ── Extract resume text ────────────────────────────────────────────
    final_resume = resume_text.strip()
    if file and file.filename:
        raw = await file.read()
        extracted = _extract_text(raw, file.filename)
        if extracted.strip():
            final_resume = extracted
        elif not final_resume:
            raise HTTPException(
                400,
                f"Could not extract text from '{file.filename}'. "
                "Try copy-pasting the text directly into the text box instead."
            )

    # ── Extract JD text ────────────────────────────────────────────────
    final_jd = job_description.strip()
    if jd_file and jd_file.filename:
        raw_jd = await jd_file.read()
        extracted_jd = _extract_text(raw_jd, jd_file.filename)
        if extracted_jd.strip():
            final_jd = (final_jd + "\n" + extracted_jd).strip() if final_jd else extracted_jd
        elif not final_jd:
            raise HTTPException(
                400,
                f"Could not extract text from '{jd_file.filename}'. "
                "Try copy-pasting the job description text instead."
            )

    # ── Validate ───────────────────────────────────────────────────────
    if not final_resume:
        raise HTTPException(400, "Resume is required. Upload a PDF/DOCX/TXT file or paste the text.")
    if not final_jd:
        raise HTTPException(400, "Job description is required. Upload a file or paste the text.")

    # ── Score (structured JD/requirement extraction + deterministic weighting) ──
    groq_key = await get_credential(db, current_user.id, "groq", "api_key")

    result = await _score_resume(final_resume, final_jd, groq_key)
    if not groq_key:
        result["note"] = "Add a Groq API key in Settings for AI-powered requirement extraction and feedback"

    return result


# ── HISTORY (persisted server-side, so it survives browsers/devices/refresh) ──

from pydantic import BaseModel


class SaveHistoryRequest(BaseModel):
    source_name: str = "Resume"
    overall_score: float = 0
    result: dict
    candidate_info: dict = {}
    jd_info: dict = {}


def _fmt_history(r: CVAnalysisRecord) -> dict:
    return {
        "id": r.id,
        "sequenceNumber": r.sequence_number or r.id,
        "sourceName": r.source_name,
        "overallScore": r.overall_score,
        "result": r.result or {},
        "candidateInfo": r.candidate_info or {},
        "jdInfo": r.jd_info or {},
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/history")
async def save_history(
    payload: SaveHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    seq_num = await next_sequence_number(db, CVAnalysisRecord, current_user.id)
    record = CVAnalysisRecord(
        user_id=current_user.id,
        sequence_number=seq_num,
        source_name=payload.source_name,
        overall_score=payload.overall_score,
        result=payload.result,
        candidate_info=payload.candidate_info,
        jd_info=payload.jd_info,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _fmt_history(record)


@router.get("/history")
async def list_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(CVAnalysisRecord)
        .where(CVAnalysisRecord.user_id == current_user.id)
        .order_by(CVAnalysisRecord.created_at.desc())
        .limit(50)
    )
    return [_fmt_history(rec) for rec in r.scalars().all()]


@router.delete("/history/{record_id}")
async def delete_history_item(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(CVAnalysisRecord).where(
            CVAnalysisRecord.id == record_id,
            CVAnalysisRecord.user_id == current_user.id,
        )
    )
    rec = r.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "History item not found")
    await db.delete(rec)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/history")
async def delete_all_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(CVAnalysisRecord).where(CVAnalysisRecord.user_id == current_user.id))
    await db.commit()
    return {"message": "Deleted"}