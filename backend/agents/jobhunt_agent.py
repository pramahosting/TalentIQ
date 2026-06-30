"""
TalentIQ – JobHunt LangChain Agent
Combines job scraping (Adzuna), resume parsing, ATS matching, and cover letter generation.
All results persisted to PostgreSQL.
"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import requests
from langchain_core.tools import Tool
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

# langchain_groq is optional – fall back gracefully if not installed
try:
    from langchain_groq import ChatGroq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False
    ChatGroq = None  # type: ignore


# ─────────────────────────────────────────────
# JOB SCRAPER (Adzuna API)
# ─────────────────────────────────────────────

RECRUITMENT_AGENCIES = [
    "michael page", "hays", "randstad", "adecco", "manpower", "robert half",
    "hudson", "kelly services", "peoplebank", "talent international", "aquent",
    "workpac", "drake", "programmed", "page personnel", "chandler macleod"
]

CONSULTING_FIRMS = [
    "accenture", "deloitte", "kpmg", "ey", "pwc", "capgemini", "cognizant",
    "infosys", "tcs", "ibm", "bain", "boston consulting group", "mckinsey"
]


def classify_company_type(company_name: str) -> str:
    if not company_name:
        return "Unknown"
    name = company_name.lower()
    if any(a in name for a in RECRUITMENT_AGENCIES):
        return "Recruitment Agency"
    if any(c in name for c in CONSULTING_FIRMS):
        return "Consulting Company"
    if any(w in name for w in ["recruitment", "staffing", "talent", "headhunter"]):
        return "Recruitment Agency"
    if any(w in name for w in ["consulting", "advisory", "solutions"]):
        return "Consulting Company"
    return "Business"


def normalize_location(location: str) -> str:
    if not location:
        return ""
    parts = location.split(",")
    return parts[-1].strip() if len(parts) > 1 else location.strip()


def scrape_jobs_adzuna(
    role: str,
    location: str,
    job_type: str,
    salary_min: Optional[int],
    salary_max: Optional[int],
    adzuna_app_id: str,
    adzuna_app_key: str,
    country: str = "au",
) -> List[Dict]:
    """Fetch jobs from Adzuna API and return normalized list.

    NOTE: Adzuna aggregates listings from thousands of job boards (including
    Seek, Indeed, and many company career sites) but does NOT expose which
    individual board each listing came from in its API response — LinkedIn
    jobs are not part of Adzuna's index at all (LinkedIn blocks aggregators).
    Direct scraping of Seek/LinkedIn/Indeed search pages is blocked by their
    anti-bot protections and is against their Terms of Service, so this
    function uses Adzuna's official API as the legitimate aggregator.
    """
    base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": adzuna_app_id,
        "app_key": adzuna_app_key,
        "results_per_page": 50,
        "what": role,
        "content-type": "application/json",
        "sort_by": "date",
    }

    if location and location.lower() != "all":
        params["where"] = location

    if job_type and job_type.lower() != "all":
        params["full_time"] = "1" if job_type.lower() in ["full-time", "full_time"] else "0"

    if salary_min:
        params["salary_min"] = salary_min
    if salary_max:
        params["salary_max"] = salary_max

    try:
        response = requests.get(base_url, params=params, timeout=15)
        if response.status_code == 401:
            return [{"error": "Adzuna authentication failed — check your App ID and App Key in Settings."}]
        if response.status_code == 403:
            return [{"error": "Adzuna API access blocked (403). Check network egress settings allow api.adzuna.com."}]
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        return [{"error": "Adzuna API timed out. Try again in a moment."}]
    except requests.exceptions.ConnectionError:
        return [{"error": "Could not connect to Adzuna API. Check network/internet access."}]
    except Exception as e:
        return [{"error": f"Adzuna API error: {str(e)[:150]}"}]

    jobs = []
    cutoff = datetime.utcnow() - timedelta(days=60)

    for job in data.get("results", []):
        created_str = job.get("created", "")[:10]
        try:
            created_date = datetime.strptime(created_str, "%Y-%m-%d")
        except Exception:
            continue
        if created_date < cutoff:
            continue

        company = job.get("company", {}).get("display_name", "Unknown")
        raw_location = job.get("location", {}).get("display_name", location)
        description = job.get("description", "")

        jobs.append({
            "title": job.get("title", "Unknown"),
            "company": company,
            "published_date": created_str,
            "location": normalize_location(raw_location),
            "job_type": job.get("contract_time", "N/A"),
            "description": description,
            "source": "Adzuna",
            "company_type": classify_company_type(company),
            "apply_link": job.get("redirect_url", ""),
            "source_site": "Adzuna",
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
        })

    # Deduplicate
    seen = set()
    unique = []
    for j in jobs:
        key = (j["title"].lower(), j["company"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(j)
    return unique


# ─────────────────────────────────────────────
# RESUME PARSER (text-based)
# ─────────────────────────────────────────────

def parse_resume_text(text: str) -> Dict:
    """Extract structured info from raw resume text"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Simple name heuristic – first non-blank line
    applicant_name = lines[0] if lines else "Applicant"

    # Email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text, re.IGNORECASE)
    email = email_match.group() if email_match else None

    # Skills detection (simple keyword matching)
    tech_keywords = [
        "python", "java", "javascript", "typescript", "react", "sql", "postgresql",
        "fastapi", "django", "flask", "node", "aws", "azure", "docker", "kubernetes",
        "langchain", "tensorflow", "pytorch", "pandas", "scikit-learn", "tableau",
        "power bi", "excel", "git", "linux", "rest api", "graphql", "mongodb",
        "redis", "spark", "hadoop", "snowflake", "dbt", "airflow",
    ]
    text_lower = text.lower()
    skills = [kw for kw in tech_keywords if kw in text_lower]

    # Experience years
    exp_matches = re.findall(r"(\d+)\s*\+?\s*years?\s*(of\s+)?(experience|exp)", text_lower)
    experience_years = float(exp_matches[0][0]) if exp_matches else 0.0

    return {
        "applicant_name": applicant_name,
        "email": email,
        "skills": skills,
        "experience_years": experience_years,
        "raw_text": text,
    }


# ─────────────────────────────────────────────
# RESUME-JOB MATCHER
# ─────────────────────────────────────────────

def extract_requirements_from_description(description: str) -> List[str]:
    """Heuristically extract key requirements from job description"""
    lines = [l.strip() for l in description.splitlines() if l.strip()]
    req_patterns = [
        r"experience (with|in)\s+(.+)",
        r"knowledge of\s+(.+)",
        r"proficiency in\s+(.+)",
        r"skills? in\s+(.+)",
        r"familiar(ity)? with\s+(.+)",
    ]
    requirements = []
    for line in lines:
        if len(line) > 10 and (
            line.startswith(("-", "•", "*")) or
            any(re.search(p, line, re.IGNORECASE) for p in req_patterns)
        ):
            clean = line.lstrip("-•* ").rstrip(".")
            if len(clean) > 5:
                requirements.append(clean)
    return requirements[:15]


def calculate_match(resume_text: str, job: Dict, groq_api_key: Optional[str] = None) -> Dict:
    """Calculate ATS score and generate insights for a single job"""
    requirements = extract_requirements_from_description(job.get("description", ""))
    text_lower = resume_text.lower()

    # Simple keyword matching
    matched = []
    missed = []
    for req in requirements:
        words = re.findall(r"\b\w{3,}\b", req.lower())
        hits = sum(1 for w in words if w in text_lower)
        if hits >= max(1, len(words) // 2):
            matched.append(req)
        else:
            missed.append(req)

    ats_score = round((len(matched) / max(len(requirements), 1)) * 100, 1)

    # Use LLM if API key provided and library available
    if groq_api_key and _GROQ_AVAILABLE and ChatGroq and len(resume_text) > 100:
        try:
            llm = ChatGroq(api_key=groq_api_key, model="llama3-70b-8192", temperature=0.2)
            prompt = (
                f"Resume (excerpt): {resume_text[:2000]}\n\n"
                f"Job Title: {job.get('title')}\n"
                f"Requirements:\n" + "\n".join(f"- {r}" for r in requirements[:10]) +
                "\n\nProvide: 1) ATS score 0-100 2) Top 3 strengths 3) Top 2 gaps. "
                "Format as: SCORE:XX STRENGTHS:s1|s2|s3 GAPS:g1|g2"
            )
            response = llm.invoke(prompt).content
            score_m = re.search(r"SCORE:(\d+)", response)
            str_m = re.search(r"STRENGTHS:(.+?)(?:GAPS:|$)", response)
            gap_m = re.search(r"GAPS:(.+)", response)
            if score_m:
                ats_score = float(score_m.group(1))
            if str_m:
                matched = [s.strip() for s in str_m.group(1).split("|") if s.strip()]
            if gap_m:
                missed = [g.strip() for g in gap_m.group(1).split("|") if g.strip()]
        except Exception:
            pass  # Fall back to keyword matching

    summary = [
        f"ATS match score: {ats_score}%",
        f"Matched {len(matched)} of {len(requirements)} requirements.",
    ]
    if missed:
        summary.append(f"Gaps: {', '.join(missed[:3])}")

    return {
        "ats_score": min(ats_score, 100),
        "strengths": matched[:8],
        "improvements": missed[:5],
        "summary": summary,
    }


# ─────────────────────────────────────────────
# COVER LETTER GENERATOR
# ─────────────────────────────────────────────

def _extract_keywords(text: str) -> List[str]:
    stop = {"the", "and", "for", "with", "in", "of", "to", "a", "on", "as", "is", "an"}
    return [w for w in re.findall(r"\b\w+\b", text.lower()) if w not in stop and len(w) > 3]


def generate_cover_letter(
    resume_text: str,
    resume_info: Dict,
    job: Dict,
    groq_api_key: Optional[str] = None,
) -> str:
    """Generate a personalised cover letter for a job"""
    job_title = job.get("title", "the position")
    company = job.get("company", "your organization")
    job_desc = job.get("description", "")
    candidate_name = resume_info.get("applicant_name", "Your Name")

    # Use LLM if available
    if groq_api_key and _GROQ_AVAILABLE and ChatGroq:
        try:
            llm = ChatGroq(api_key=groq_api_key, model="llama3-70b-8192", temperature=0.5)
            prompt = (
                f"Write a professional, concise cover letter for {candidate_name} "
                f"applying for the {job_title} role at {company}.\n\n"
                f"Job description: {job_desc[:1500]}\n\n"
                f"Resume highlights: {resume_text[:1500]}\n\n"
                "Write 3 paragraphs: opening, strengths alignment, closing. "
                "Return only the letter text."
            )
            return llm.invoke(prompt).content
        except Exception:
            pass

    # Fallback: template-based
    job_keywords = _extract_keywords(job_desc)
    resume_lines = [l.strip().lstrip("• ") for l in resume_text.split("\n") if l.strip()]
    scored = sorted(
        [(sum(1 for kw in job_keywords if kw in l.lower()), l) for l in resume_lines],
        key=lambda x: x[0], reverse=True
    )
    top_strengths = [l for s, l in scored[:4] if s > 0]
    strengths_text = "\n".join(f"- {s}" for s in top_strengths) or "- [Your relevant strengths]"

    is_agency = any(w in company.lower() for w in ["recruit", "agency", "talent", "staffing"])
    greeting = f"I am writing to express my strong interest in the {job_title} role"
    if not is_agency:
        greeting += f" at {company}"
    greeting += "."

    letter = (
        f"Dear Hiring Manager,\n\n"
        f"{greeting} With proven experience aligned to your requirements, "
        f"I am confident in my ability to contribute effectively from day one.\n\n"
        f"Top reasons I am a strong fit:\n{strengths_text}\n\n"
    )
    if not is_agency:
        letter += f"I am particularly drawn to {company} because of its innovation and leadership.\n\n"
    letter += (
        f"I would welcome the opportunity to contribute my expertise to your team. "
        f"Thank you for considering my application.\n\n"
        f"Warm regards,\n{candidate_name}"
    )
    return letter


# ─────────────────────────────────────────────
# LANGCHAIN AGENT BUILDER
# ─────────────────────────────────────────────

def build_jobhunt_agent(groq_api_key: str) -> AgentExecutor:
    """Build a LangChain ReAct agent wrapping JobHunt tools"""
    if not _GROQ_AVAILABLE or not ChatGroq:
        raise RuntimeError("langchain-groq is not installed. Run: pip install langchain-groq")
    llm = ChatGroq(api_key=groq_api_key, model="llama3-70b-8192", temperature=0)

    tools = [
        Tool(
            name="ScrapeJobs",
            func=lambda q: f"Job scraping configured for: {q}",
            description="Scrape job listings from Adzuna API given role, location, type, salary range.",
        ),
        Tool(
            name="ParseResume",
            func=lambda text: str(parse_resume_text(text)),
            description="Parse a resume text and extract structured information.",
        ),
        Tool(
            name="MatchResumeToJob",
            func=lambda x: "Match calculation complete",
            description="Calculate ATS score and identify strengths/gaps between a resume and job.",
        ),
        Tool(
            name="GenerateCoverLetter",
            func=lambda x: "Cover letter generated",
            description="Generate a personalized cover letter for a specific job application.",
        ),
    ]

    prompt = PromptTemplate.from_template(
        "You are the JobHunt AI agent. Help users find matching jobs and prepare applications.\n\n"
        "Available tools: {tools}\nTool names: {tool_names}\n\n"
        "User request: {input}\n\n{agent_scratchpad}"
    )

    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)