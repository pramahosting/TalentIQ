"""
TalentIQ - CandidateLens Router
Mirrors the original JobLens scoring logic:
  1. LLM extracts skills from JD (Groq instead of Ollama)
  2. Keyword match CV text against extracted skills
  3. Bonus for degree/experience mentions
  4. Generate interview questions via LLM
  5. Generate a 10-statement resume summary via LLM
  6. Send video-interview invite emails with a candidate-facing link
All persisted to PostgreSQL (tiq_joblens_* tables).
"""
import io
import re
import os
import json
import secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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

            # Headers often contain name/email/phone (especially in resumes
            # with a banner/letterhead layout). python-docx's section.header
            # only exposes ONE header per section by default, but a docx can
            # have up to 3 per section (default/first-page/even-page) stored
            # as header1.xml/header2.xml/header3.xml — read them all via the
            # raw XML so we never miss contact details placed there.
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

            parts = list(header_footer_parts)  # put header/footer text first
            parts += [p.text for p in doc.paragraphs if p.text.strip()]
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
    # Word documents with letterhead-style headers often have run-together
    # text with no whitespace between fields (Word renders separate <w:t>
    # runs with different formatting as visually adjacent but textually
    # concatenated), e.g. "NSW 2145resume2@gmail.comLinkedIn:". Insert a
    # space at lowercase→uppercase and digit→letter transitions so regexes
    # below can find clean boundaries — this never touches genuine words.
    norm_text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    norm_text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', norm_text)

    # Email
    email_m = re.search(r"[a-zA-Z][\w.+-]*@[\w.-]+\.[a-zA-Z]{2,6}", norm_text)
    email = email_m.group() if email_m else ""

    # Phone — original regex: (+?\d{1,4}[\s-]?\(?\d{1,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4})
    phone_m = re.search(r"(\+?\d{1,4}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})", text)
    phone = phone_m.group().replace(" ", "").strip() if phone_m else ""
    # Reject cert numbers: must have spaces/dashes or start with +
    if phone and not re.search(r"[\s\-\+\(\)]", phone_m.group() if phone_m else ""):
        phone = ""

    # Name — mirrors original: first non-email, non-4digit, <=5 word line
    name = ""
    NAME_SKIP_PATTERNS = (
        r"^page\s+\d+\s*(of\s+\d+)?$",
        r"^\d+\s*$",
        r"^confidential$",
        r"^curriculum vitae$",
        r"^resume$",
    )
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:25]:
        if "@" in line:
            continue
        if re.search(r"\d{4,}", line):
            continue
        if any(re.match(p, line, re.IGNORECASE) for p in NAME_SKIP_PATTERNS):
            continue
        if len(line.split()) <= 5 and len(line) > 2:
            candidate = re.sub(r"[^a-zA-Z\s\-\.]", "", line).strip()
            if candidate and len(candidate) > 2:
                name = candidate
                break

    if not name:
        name = Path(filename).stem.replace("_", " ").replace("-", " ").title()

    # ── Experience years — look for explicit "X years" mentions ───────
    exp_years = ""
    exp_matches = re.findall(
        r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp\b)",
        text, re.IGNORECASE,
    )
    if exp_matches:
        # Take the highest mentioned figure (usually the headline summary)
        exp_years = f"{max(int(y) for y in exp_matches)}+ years"
    else:
        # Fallback: count distinct 4-digit years mentioned in work history
        # to estimate a rough career span (e.g. 2009 ... 2024)
        years_found = sorted(set(int(y) for y in re.findall(r"\b(19[7-9]\d|20[0-2]\d)\b", text)))
        if len(years_found) >= 2:
            span = years_found[-1] - years_found[0]
            if 0 < span <= 45:
                exp_years = f"~{span} years"

    # ── Summary — first substantial paragraph (career objective / profile) ──
    summary = ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    SUMMARY_SKIP = {"resume", "curriculum vitae", "cv", "page", "contact", "references"}
    for p in paragraphs[:15]:
        clean_p = re.sub(r"\s+", " ", p).strip()
        low = clean_p.lower()
        if len(clean_p) < 80 or len(clean_p) > 700:
            continue
        if any(s in low[:30] for s in SUMMARY_SKIP):
            continue
        if "@" in clean_p or re.search(r"^\s*[\u2022\-\*]", p):
            continue
        # Looks like prose (has multiple sentences / reasonable word count)
        if len(clean_p.split()) >= 12:
            summary = clean_p[:400]
            break

    return {
        "name": name, "email": email, "phone": phone,
        "experience_years": exp_years, "summary": summary,
    }


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


# ── RESUME SUMMARY (10 statements) ──────────────────────────────────────────

async def generate_resume_summary(cv_text: str, groq_key: Optional[str]) -> list:
    """Produce exactly 10 concise, factual statements summarising the resume,
    covering Education, Skills, Experience, Availability, and Citizenship/Work
    Rights status. Uses Groq LLM when a key is available, otherwise falls
    back to heuristic keyword extraction."""
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model="llama3-70b-8192", temperature=0.2)
            prompt = f"""You are a recruitment analyst. Read the resume below and produce
EXACTLY 10 concise, factual, one-sentence statements summarising the candidate.
Cover these areas across the 10 statements: Education, Skills, Experience,
Availability, and Citizenship/Work Rights status. If a topic is not mentioned
in the resume, write a statement saying it was "Not specified in resume."
Do not invent facts that aren't supported by the resume text.

Resume:
\"\"\"{cv_text[:4000]}\"\"\"

Return ONLY valid JSON in this exact format:
{{"statements": ["...", "...", "...", "...", "...", "...", "...", "...", "...", "..."]}}"""

            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            statements = [s for s in data.get("statements", []) if s]
            if statements:
                return statements[:10]
        except Exception:
            pass
    return _fallback_resume_summary(cv_text)


def _fallback_resume_summary(cv_text: str) -> list:
    """Heuristic 10-statement resume summary used when no Groq key is configured."""
    low = cv_text.lower()
    statements = []

    edu_m = re.search(r"(bachelor|master|phd|doctorate|diploma|degree)[^\n.]{0,90}", low)
    statements.append(
        f"Education: {edu_m.group().strip().capitalize()}." if edu_m
        else "Education: Not specified in resume."
    )

    keyword_bank = [
        "python", "java", "javascript", "sql", "excel", "power bi", "tableau",
        "aws", "azure", "gcp", "docker", "kubernetes", "project management",
        "accounting", "communication", "leadership", "react", "node",
        "salesforce", "sap", "financial reporting", "data analysis",
    ]
    found_skills = [s for s in keyword_bank if s in low]
    statements.append(
        f"Skills: Resume indicates experience with {', '.join(found_skills[:6])}." if found_skills
        else "Skills: No specific technical skills clearly listed."
    )

    exp_m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", low)
    statements.append(
        f"Experience: Approximately {exp_m.group(1)}+ years of relevant experience." if exp_m
        else "Experience: Years of experience not explicitly stated in resume."
    )

    statements.append(
        "Experience: Resume references current or recent professional roles." if re.search(r"present|current(ly)?\s+work", low)
        else "Experience: Most recent role not clearly identifiable from resume."
    )

    if re.search(r"immediate(ly)?\s+available|available\s+immediately|notice\s+period", low):
        avail_m = re.search(r"([a-z0-9 ]{0,10}notice\s+period[a-z0-9 ]{0,15}|immediate(ly)?\s+available)", low)
        statements.append(
            f"Availability: {avail_m.group().strip().capitalize()}." if avail_m
            else "Availability: Mentioned in resume."
        )
    else:
        statements.append("Availability: Not specified in resume.")

    if re.search(r"citizen|permanent resident|\bpr\b|work visa|work rights|unrestricted work rights|485 visa|482 visa|sponsorship", low):
        cit_m = re.search(r"([a-z0-9 ]{0,20}(citizen|permanent resident|work visa|work rights|sponsorship)[a-z0-9 ]{0,20})", low)
        statements.append(
            f"Citizenship/Work Rights: {cit_m.group().strip().capitalize()}." if cit_m
            else "Citizenship/Work Rights: Mentioned in resume."
        )
    else:
        statements.append("Citizenship/Work Rights: Not specified in resume.")

    if "@" in cv_text:
        statements.append("Contact: Valid contact email address is present in the resume.")
    else:
        statements.append("Contact: No email address detected in the resume.")

    statements.append(
        "Certifications: Resume mentions professional certification(s)." if re.search(r"certificat", low)
        else "Certifications: No certifications explicitly mentioned."
    )

    statements.append(
        "Project Experience: Resume highlights project-based work experience." if re.search(r"project", low)
        else "Project Experience: No specific projects called out in resume."
    )

    while len(statements) < 10:
        statements.append("No further notable details extracted from resume.")
    return statements[:10]


# ── SMTP EMAIL SENDING ────────────────────────────────────────────────────────

async def _get_smtp_config(user_id: int, db: AsyncSession) -> dict:
    kr = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.service == "smtp",
        )
    )
    return {k.key_name: k.key_value for k in kr.scalars().all()}


def _send_email(smtp_cfg: dict, to_email: str, subject: str, html_body: str):
    host = smtp_cfg.get("host")
    port = int(smtp_cfg.get("port") or 587)
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    from_email = smtp_cfg.get("from_email") or username

    if not (host and username and password and from_email):
        raise HTTPException(
            400,
            "SMTP is not configured. Add credentials in Settings > API Keys "
            "(service: smtp; key names: host, port, username, password, from_email)."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(from_email, [to_email], msg.as_string())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to send email: {str(e)[:200]}")


class SendInviteRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str


# ── FORMAT CANDIDATE ─────────────────────────────────────────────────────────

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
        "experience_years": c.experience_years or "",
        "summary": c.summary or "",
        "resume_summary": c.resume_summary or [],
        "interview_token": c.interview_token,
        "contacted": bool(c.contacted),
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

            # Generate questions and resume summary immediately if Groq available
            if groq_key:
                questions = await generate_questions(
                    final_jd, info["name"], result["matched"], groq_key
                )
            else:
                questions = _default_questions(info["name"], result["matched"])

            resume_summary = await generate_resume_summary(cv_text, groq_key)

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
                experience_years=info.get("experience_years", ""),
                summary=info.get("summary", ""),
                resume_summary=resume_summary,
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


# ── CANDIDATE CONTACT / VIDEO INTERVIEW INVITE ───────────────────────────────

@router.post("/candidates/{candidate_id}/prepare-invite")
async def prepare_invite(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ensures the candidate has a unique interview token and returns it so
    the frontend can build a shareable, no-login video-interview link."""
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    if not c.interview_token:
        c.interview_token = secrets.token_urlsafe(24)
        await db.commit()
        await db.refresh(c)

    return {
        "token": c.interview_token,
        "candidate_name": c.name,
        "candidate_email": c.email,
    }


@router.post("/candidates/{candidate_id}/send-invite")
async def send_invite(
    candidate_id: int,
    payload: SendInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    smtp_cfg = await _get_smtp_config(current_user.id, db)
    _send_email(smtp_cfg, payload.to_email, payload.subject, payload.body_html)

    return {"sent": True}


@router.post("/candidates/{candidate_id}/mark-contacted")
async def mark_contacted(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flips the 'contacted' flag once the recruiter sends the interview
    invite letter (via mailto handoff to their own mail client)."""
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.id == candidate_id)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.contacted = True
    await db.commit()
    return {"contacted": True}


@router.get("/morphcast-key")
async def get_morphcast_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the recruiter's saved MorphCast license key (Settings > API
    Keys, service: morphcast, key: license_key), used client-side by the
    video interview modal for facial emotion analysis. Not a sensitive
    secret in the traditional sense — MorphCast's SDK runs entirely in the
    browser and the key is visible in that SDK's own network calls anyway."""
    kr = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == current_user.id,
            UserAPIKey.service == "morphcast",
        )
    )
    key = next((k.key_value for k in kr.scalars().all() if k.key_name == "license_key"), None)
    return {"license_key": key or ""}


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


# ── PUBLIC (candidate-facing, NO auth required) ──────────────────────────────
# These power the emailed video-interview link so a candidate can complete
# the interview without a TalentIQ login. Access is gated by the unguessable
# token, not a session/auth check.

@router.get("/public/interview/{token}")
async def public_get_interview(token: str, db: AsyncSession = Depends(get_db)):
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.interview_token == token)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "This interview link is invalid or has expired.")
    return {
        "candidate_name": c.name,
        "questions": c.interview_questions or [],
        "video_status": c.video_status,
    }


@router.get("/public/interview/{token}/morphcast-key")
async def public_get_morphcast_key(token: str, db: AsyncSession = Depends(get_db)):
    """Same MorphCast license key as the authenticated endpoint above, but
    resolved via the interview token (no login) — belongs to whichever
    recruiter's account generated this candidate's interview."""
    cr = await db.execute(
        select(JobLensCandidate, JobLensSession)
        .join(JobLensSession, JobLensCandidate.session_id == JobLensSession.id)
        .where(JobLensCandidate.interview_token == token)
    )
    row = cr.first()
    if not row:
        raise HTTPException(404, "This interview link is invalid or has expired.")
    _, session = row

    kr = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == session.user_id,
            UserAPIKey.service == "morphcast",
        )
    )
    key = next((k.key_value for k in kr.scalars().all() if k.key_name == "license_key"), None)
    return {"license_key": key or ""}


@router.post("/public/interview/{token}/result")
async def public_save_interview_result(
    token: str,
    result: InterviewResult,
    db: AsyncSession = Depends(get_db),
):
    cr = await db.execute(
        select(JobLensCandidate).where(JobLensCandidate.interview_token == token)
    )
    c = cr.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "This interview link is invalid or has expired.")
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
            "Rank":              i,
            "Name":              c.name,
            "Email":             c.email,
            "Phone":             c.phone,
            "Resume Summary":    " | ".join(c.resume_summary or []),
            "ATS Score":         f"{c.ats_score:.1f}%",
            "Key Strength":      ", ".join(c.matched_skills or []),
            "Considerations":    ", ".join(c.missing_skills or []),
            "Status":            c.status,
            "Video Status":      c.video_status,
            "Happy %":           c.emotion_happy or 0,
            "Neutral %":         c.emotion_neutral or 0,
            "Sad %":             c.emotion_sad or 0,
            "Angry %":           c.emotion_angry or 0,
            "Fear %":            c.emotion_fear or 0,
            "Disgust %":         c.emotion_disgust or 0,
            "Surprise %":        c.emotion_surprise or 0,
            "Dominant Emotion":  c.dominant_emotion or "Neutral",
            "Shortlisted":       "Yes" if c.shortlisted else "No",
            "Bonus Points":      c.bonus,
            "Bonus Reasons":     c.bonus_reasons,
            "Summary":           c.summary or "",
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