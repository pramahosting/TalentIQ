"""
TalentIQ - CVAnalysis Router
Resume vs Job Description ATS analyser.
Supports PDF, DOCX, TXT for both resume and job description.
"""
import io
import re
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from models.models import User, UserAPIKey
from utils.auth_utils import get_current_user

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
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
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
    "machine learning","ai","data science","excel","power bi","tableau","salesforce",
    "figma","django","flask","java","c#","c++","go","spark","kafka","airflow","dbt",
    "snowflake","databricks","redshift","bigquery","data architecture","data governance",
    "data modelling","data warehouse","data lake","etl","elt","data pipeline","solution design",
    "stakeholder management","cloud architecture","microservices","devops","ci/cd",
    "xero","myob","quickbooks","sap","oracle","dynamics","netsuite","sage",
    "cpa","ca","acca","cma","mba","cfa","fcpa","aca",
    "accounting","tax","audit","payroll","bookkeeping","bas","gst",
    "financial reporting","budgeting","forecasting","reconciliation",
    "accounts payable","accounts receivable","ifrs","gaap",
    "leadership","communication","problem solving","teamwork","stakeholder",
    "management","strategy","operations","project management","scrum","nlp","llm",
]

STOPWORDS = {"a","an","the","and","or","of","in","on","for","with","to","be","is",
             "are","it","at","from","as","by","that","this","we","you","have","has"}


def _keyword_score(resume: str, jd: str) -> dict:
    jd_lower = jd.lower()
    cv_lower = resume.lower()

    # Collect JD skills
    jd_skills = []
    for s in DOMAIN_SKILLS:
        if s in jd_lower:
            jd_skills.append(s)
    # Add single-word JD tokens not in stopwords
    for t in re.findall(r"\b([a-zA-Z][a-zA-Z0-9+#.\-]{2,})\b", jd):
        tl = t.lower()
        if tl not in STOPWORDS and tl not in jd_skills and len(t) > 3:
            jd_skills.append(tl)

    jd_skills = list(dict.fromkeys(jd_skills))  # dedup
    matched  = [s for s in jd_skills if s in cv_lower]
    missing  = [s for s in jd_skills if s not in cv_lower]

    skill_pct = round(len(matched) / len(jd_skills) * 100) if jd_skills else 50

    bonus = 0
    bonus_notes = []
    if re.search(r"bachelor|master|degree|phd|mba", cv_lower):
        bonus += 10; bonus_notes.append("Education")
    if re.search(r"\d+\s*\+?\s*years?", cv_lower, re.I):
        bonus += 10; bonus_notes.append("Experience years")

    overall = min(95, max(30, round(skill_pct * 0.7 + bonus * 0.3)))

    strengths = []
    if matched:
        strengths.append(f"Strong skill alignment: {', '.join(matched[:6])}")
    if re.search(r"\d+\s*\+?\s*years?", cv_lower, re.I):
        strengths.append("Resume highlights relevant years of experience")
    if len(resume) > 800:
        strengths.append("Resume has sufficient depth and detail")
    if not strengths:
        strengths.append("Resume presents relevant professional background")

    gaps = [f"Missing or underemphasised: {s}" for s in missing[:6]]
    gaps.append("Consider adding quantifiable achievements with metrics")

    suggestions = [f'Add "{s}" if you have relevant experience' for s in missing[:5]]
    suggestions += [
        "Quantify achievements (e.g. 'Reduced processing time by 30%')",
        "Mirror exact keywords from the job description",
        "Use standard section headers for ATS compatibility (Experience, Education, Skills)",
    ]

    return {
        "overallScore": overall,
        "strengths": strengths,
        "gaps": gaps,
        "suggestions": suggestions[:6],
        "summaryAssessment": (
            f"Resume shows {skill_pct}% keyword alignment with the job requirements. "
            f"{'Matched skills: ' + ', '.join(matched[:4]) + '. ' if matched else ''}"
            f"{'Key gaps: ' + ', '.join(missing[:3]) + '.' if missing else ''} "
            f"Overall fit: {'Strong' if overall>=75 else 'Moderate' if overall>=55 else 'Needs improvement'}."
        ),
        "formatWarnings": [
            "Use standard ATS-compatible section headers (Experience, Education, Skills)",
            "Avoid tables, columns or text boxes — ATS parsers often miss them",
        ],
        "detailedScores": {
            "skillsMatch":  skill_pct,
            "experience":   min(90, 50 + bonus * 2),
            "tools":        max(30, skill_pct - 8),
            "domain":       max(35, overall - 5),
            "softSkills":   max(35, overall - 12),
            "format":       min(88, overall + 5),
        },
        "matchedSkills": matched[:15],
        "missingSkills": missing[:15],
        "aiPowered": False,
    }


async def _groq_score(resume: str, jd: str, groq_key: str) -> dict:
    try:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.1)
        prompt = f"""You are an expert ATS engine and recruitment analyst.
Analyse this resume against the job description. Return ONLY valid JSON, no markdown, no explanation.

JOB DESCRIPTION (first 2000 chars):
{jd[:2000]}

RESUME (first 2500 chars):
{resume[:2500]}

Return exactly this JSON structure:
{{
  "overallScore": <integer 0-100>,
  "strengths": ["<str>","<str>","<str>"],
  "gaps": ["<str>","<str>","<str>"],
  "suggestions": ["<str>","<str>","<str>","<str>"],
  "summaryAssessment": "<2-3 sentences>",
  "formatWarnings": ["<str>","<str>"],
  "detailedScores": {{
    "skillsMatch": <int>,
    "experience": <int>,
    "tools": <int>,
    "domain": <int>,
    "softSkills": <int>,
    "format": <int>
  }},
  "matchedSkills": ["<str>"],
  "missingSkills": ["<str>"]
}}"""

        resp = llm.invoke([HumanMessage(content=prompt)])
        raw  = resp.content.strip()
        raw  = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(raw)

        return {
            "overallScore":      int(data.get("overallScore", 60)),
            "strengths":         data.get("strengths", []),
            "gaps":              data.get("gaps", []),
            "suggestions":       data.get("suggestions", []),
            "summaryAssessment": data.get("summaryAssessment", ""),
            "formatWarnings":    data.get("formatWarnings", []),
            "detailedScores":    data.get("detailedScores", {}),
            "matchedSkills":     data.get("matchedSkills", []),
            "missingSkills":     data.get("missingSkills", []),
            "aiPowered":         True,
        }
    except Exception as e:
        result = _keyword_score(resume, jd)
        result["aiError"] = str(e)[:120]
        return result


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

    # ── Score ──────────────────────────────────────────────────────────
    keys_r = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == current_user.id,
            UserAPIKey.service == "groq",
        )
    )
    groq_key = next(
        (k.key_value for k in keys_r.scalars().all() if k.key_name == "api_key"), None
    )

    if groq_key:
        result = await _groq_score(final_resume, final_jd, groq_key)
    else:
        result = _keyword_score(final_resume, final_jd)
        result["note"] = "Add a Groq API key in Settings for AI-powered analysis"

    return result
