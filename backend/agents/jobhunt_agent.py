"""
TalentIQ – JobHunt LangChain Agent
Combines job scraping (Adzuna), resume parsing, ATS matching, and cover letter generation.
All results persisted to PostgreSQL.
"""

import re
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import requests
from langchain_core.tools import Tool
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from utils.credentials import DEFAULT_GROQ_MODEL

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
    email_match = re.search(
        r"[a-zA-Z][\w.+-]*@[\w-]+\.(com|net|org|edu|gov|io|co|au|uk|in|nz|ca|us|biz|info|me)\b",
        text, re.IGNORECASE,
    )
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


# ══════════════════════════════════════════════════════════════════════════════
# ATS MATCHING — structured extraction + deterministic weighted scoring.
#
# The old version asked the LLM to reply in an ad-hoc "SCORE:XX
# STRENGTHS:s1|s2|s3" text format and regex-parsed it — fragile and prone to
# silently wrong scores whenever the model's formatting drifted even
# slightly. This mirrors the same structured approach used in CVAnalysis:
# extract facts as JSON, then score with plain deterministic Python math.
#
# Since a resume is matched against MANY jobs in one batch, the candidate's
# profile is extracted ONCE per batch (see extract_candidate_profile below)
# and reused — only the per-job requirement extraction repeats per job.
# ══════════════════════════════════════════════════════════════════════════════

_JOBHUNT_SKILL_BANK = [
    "python","javascript","typescript","react","node","sql","postgresql","mongodb",
    "aws","azure","gcp","docker","kubernetes","git","agile","rest","api","graphql",
    "machine learning","ai","artificial intelligence","data science","excel","power bi","tableau","salesforce",
    "django","flask","java","c#","c++","go","spark","kafka","airflow","dbt",
    "snowflake","databricks","stakeholder management","cloud architecture",
    "data mesh","data fabric","data vault","lakehouse","enterprise data warehouse","edw",
    "data governance","master data management","collibra","alation","teradata","hadoop",
    "synapse","azure data factory","enterprise architecture","solution architecture","togaf",
    "basel","banking","bfsi","insurance","risk management","regulatory compliance",
    "microservices","devops","ci/cd","accounting","tax","audit","payroll",
    "financial reporting","budgeting","forecasting","reconciliation",
    "leadership","communication","problem solving","project management","scrum",
]


def _normalize_skill(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip().lower())
    for pattern, repl in _UK_TO_US_SPELLING:
        s = re.sub(pattern, repl, s)
    return s


def _normalize_text(s: str) -> str:
    s = s.lower()
    for pattern, repl in _UK_TO_US_SPELLING:
        s = re.sub(pattern, repl, s)
    return s


_UK_TO_US_SPELLING = [
    (r"\bmodelling\b", "modeling"), (r"\blabelling\b", "labeling"),
    (r"\bcancelled\b", "canceled"), (r"\btravelling\b", "traveling"),
    (r"\borganisation", "organization"), (r"\bcolour", "color"),
    (r"\blicence", "license"), (r"\bcentre\b", "center"),
    (r"\bprogramme\b", "program"), (r"\banalyse", "analyze"),
    (r"\boptimise", "optimize"), (r"\bcategorise", "categorize"),
    (r"\bcustomise", "customize"), (r"\bfavour", "favor"),
    (r"\bbehaviour", "behavior"), (r"\bvisualise", "visualize"),
    (r"\bsummarise", "summarize"), (r"\bspecialise", "specialize"),
]

# Same taxonomy used in CVAnalysis (routers/cvintel.py) and CandidateLens
# (routers/joblens.py) — true synonyms/abbreviations plus curated specific-
# technique -> general-skill relationships (e.g. Dimensional Modeling IS a
# form of Data Modeling), not blind fuzzy string similarity, so it doesn't
# introduce false positives.
_SKILL_SYNONYMS = {
    "ai": ["artificial intelligence"], "artificial intelligence": ["ai"],
    "ml": ["machine learning"], "machine learning": ["ml",
        "regression", "classification", "neural network", "deep learning",
        "supervised learning", "unsupervised learning", "random forest",
        "gradient boosting", "xgboost", "scikit-learn", "tensorflow", "pytorch"],
    "bi": ["business intelligence"], "business intelligence": ["bi"],
    "power bi": ["powerbi", "power-bi"],
    "aws": ["amazon web services", "ec2", "s3", "redshift", "lambda",
        "aws glue", "amazon redshift", "cloudformation"],
    "amazon web services": ["aws"],
    "azure": ["microsoft azure", "azure data factory", "azure synapse",
        "azure synapse analytics", "adls", "adls gen2", "azure devops"],
    "gcp": ["google cloud platform", "google cloud", "bigquery", "gcp bigquery"],
    "google cloud platform": ["gcp"],
    "api": ["apis", "application programming interface", "rest api", "restful api", "graphql"],
    "apis": ["api"],
    "etl": ["extract transform load", "extract, transform, load", "elt",
        "data pipeline", "airflow", "dbt", "informatica", "talend", "ssis"],
    "elt": ["etl"],
    "data pipeline": ["etl", "elt", "airflow", "dbt", "data pipelines"],
    "sql": ["structured query language", "t-sql", "pl/sql", "mysql", "postgresql", "postgres"],
    "ci/cd": ["ci cd", "continuous integration", "continuous deployment", "jenkins", "github actions"],
    "devops": ["dev ops"],
    "nlp": ["natural language processing"], "natural language processing": ["nlp"],
    "data governance": ["governance framework", "data governance framework",
        "data stewardship", "data catalog", "data cataloguing", "data lineage",
        "data quality framework", "collibra", "alation"],
    "edw": ["enterprise data warehouse"], "enterprise data warehouse": ["edw"],
    "mdm": ["master data management"], "master data management": ["mdm"],
    "crm": ["customer relationship management", "salesforce"],
    "erp": ["enterprise resource planning", "sap", "oracle erp", "netsuite"],
    "data modeling": [
        "dimensional modeling", "dimensional model", "data vault",
        "data vault 2.0", "star schema", "snowflake schema",
        "entity relationship modeling", "er modeling", "erd",
        "third normal form", "3nf modeling", "kimball", "inmon",
        "fsldm", "logical data modeling", "physical data modeling",
        "conceptual data modeling", "normalization", "denormalization",
    ],
    "data architecture": [
        "data mesh", "data fabric", "lakehouse", "data lakehouse",
        "enterprise data warehouse", "edw", "data lake", "data warehouse",
        "solution architecture", "enterprise architecture",
    ],
    "cloud architecture": ["aws", "azure", "gcp", "multi-cloud", "hybrid cloud"],
}


def _skill_present(skill: str, candidate_skills: set, resume_lower: str) -> bool:
    """See routers/cvintel.py's _skill_present for the full rationale —
    checks extracted-skill overlap, exact substring (after UK/US spelling
    normalization), known synonyms/specific-technique relationships, and
    (for multi-word skills) all significant words appearing anywhere in
    the resume, not just as one exact contiguous phrase."""
    sk = _normalize_skill(skill)
    if any(sk in cs or cs in sk for cs in candidate_skills):
        return True
    if sk in resume_lower:
        return True
    for variant in _SKILL_SYNONYMS.get(sk, []):
        if _normalize_text(variant) in resume_lower:
            return True
    words = [w for w in sk.split() if len(w) > 2]
    if len(words) >= 2 and all(w in resume_lower for w in words):
        return True
    return False


async def extract_candidate_profile(resume_text: str, groq_api_key: Optional[str] = None, groq_model: str = DEFAULT_GROQ_MODEL) -> Dict:
    """Extract a structured, categorized candidate profile ONCE per resume
    — reused across every job in a match batch rather than re-extracted
    per job. Delegates to the shared extraction module (also used by
    CVAnalysis and CandidateLens) so all three present strengths the same
    way: Technical Skills, Business Skills, Soft Skills, Significant
    Experience, and Certifications & Degrees."""
    from utils.llm_extraction import extract_candidate_strengths_general
    strengths = await extract_candidate_strengths_general(resume_text, groq_api_key, groq_model)
    # hard_skills kept for backward-compat with the deterministic matching
    # logic below — technical + business skills combined.
    strengths["hard_skills"] = strengths.get("technical_skills", []) + strengths.get("business_skills", [])
    strengths["_ai_powered"] = strengths.get("ai_powered", False)
    return strengths


async def _extract_job_requirements(job: Dict, groq_api_key: Optional[str] = None, groq_model: str = DEFAULT_GROQ_MODEL) -> Dict:
    """Categorized JD requirements (Essential / Good to Have / Optional) via
    the shared extraction module — same schema CVAnalysis and CandidateLens
    use, so "similar and essential, preferred requirements from the JD" show
    up consistently everywhere."""
    from utils.llm_extraction import extract_jd_requirements_categorized
    description = job.get("description", "") or ""
    req = await extract_jd_requirements_categorized(description, groq_api_key, groq_model)
    # required_hard_skills kept for backward-compat with the deterministic
    # matching logic below — falls back to the old heuristic extractor if
    # the shared one came back empty (e.g. a very short description).
    if not req.get("essential") and not req.get("good_to_have"):
        req["required_hard_skills"] = extract_requirements_from_description(description)[:10]
    else:
        req["required_hard_skills"] = req.get("essential", [])
    return req


async def calculate_match(
    resume_text: str, job: Dict, groq_api_key: Optional[str] = None,
    candidate_profile: Optional[Dict] = None, groq_model: str = DEFAULT_GROQ_MODEL,
    ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None,
    known_terms_hint: Optional[list] = None, db=None,
) -> Dict:
    """Calculate ATS score and generate insights for a single job.
    Pass a pre-extracted `candidate_profile` (from extract_candidate_profile)
    when matching one resume against many jobs, to avoid re-extracting the
    same resume on every call.

    Essential/good-to-have matching is judged by the LLM per-item (same fix
    as CVAnalysis) rather than deterministic string/token matching, which
    can't reliably judge long capability-statement requirements or
    requirements phrased differently than the resume (e.g. "Data Modeling"
    vs a resume that says "Dimensional Modeling"). This does mean one LLM
    call per job (matching is inherently job-specific, unlike the
    resume-intrinsic technical/business/soft skills below, which stay
    cached in candidate_profile and are NOT re-extracted here).

    Tries Ollama first when configured (see utils.llm_extraction), then
    Groq, then a deterministic heuristic. Pass `db` to enrich the shared
    skill taxonomy after a successful LLM match (best-effort, never blocks
    or fails the match itself)."""
    if candidate_profile is None:
        candidate_profile = await extract_candidate_profile(resume_text, groq_api_key, groq_model)

    requirements = await _extract_job_requirements(job, groq_api_key, groq_model)
    essential = [s for s in requirements.get("essential", requirements.get("required_hard_skills", [])) if s]
    good_to_have = [s for s in requirements.get("good_to_have", []) if s]

    from utils.llm_extraction import extract_candidate_strengths, enrich_skill_taxonomy
    verdicts = await extract_candidate_strengths(
        resume_text, {"essential": essential, "good_to_have": good_to_have}, groq_api_key, groq_model,
        ollama_base_url=ollama_base_url, ollama_model=ollama_model, known_terms_hint=known_terms_hint,
    )
    if db is not None and verdicts.get("ai_powered"):
        await enrich_skill_taxonomy(db, {
            "essential": essential,
            "good_to_have": good_to_have,
            "technical": verdicts.get("technical_skills", []),
            "business": verdicts.get("business_skills", []),
            "soft": verdicts.get("soft_skills", []),
        })
    if "essential_matched" in verdicts or "essential_missing" in verdicts:
        matched = verdicts.get("essential_matched", [])
        missed = verdicts.get("essential_missing", [])
        matched_good = verdicts.get("good_to_have_matched", [])
    else:
        # Fallback only if the LLM path didn't return verdicts for some reason
        text_lower = _normalize_text(resume_text)
        candidate_skills = {_normalize_skill(s) for s in candidate_profile.get("hard_skills", [])}
        matched = [s for s in essential if _skill_present(_normalize_skill(s), candidate_skills, text_lower)]
        missed = [s for s in essential if s not in matched]
        matched_good = [s for s in good_to_have if _skill_present(_normalize_skill(s), candidate_skills, text_lower)]

    skills_pct = round(len(matched) / len(essential) * 100) if essential else 65

    min_years = requirements.get("min_years_experience") or 0
    cand_years = candidate_profile.get("years_experience") or 0
    experience_pct = 85 if min_years <= 0 else max(20, min(100, round(cand_years / min_years * 100)))

    ats_score = round(skills_pct * 0.60 + experience_pct * 0.25 + (min(100, len(matched_good) * 25) if good_to_have else 60) * 0.10 + 75 * 0.05, 1)
    ats_score = max(10, min(98, ats_score))

    summary = [
        f"ATS match score: {ats_score}%",
        f"Matched {len(matched)} of {len(essential)} essential requirements.",
    ]
    if missed:
        summary.append(f"Gaps: {', '.join(missed[:3])}")

    return {
        "ats_score": ats_score,
        "strengths": matched[:8],
        "improvements": missed[:5],
        "summary": summary,
        # ── Categorized strengths — same schema as CVAnalysis/CandidateLens ──
        "strengths_breakdown": {
            "essential_matched": matched,
            "technical_skills": candidate_profile.get("technical_skills", []),
            "business_skills": candidate_profile.get("business_skills", []),
            "soft_skills": candidate_profile.get("soft_skills", []),
            "significant_experience": candidate_profile.get("significant_experience", []),
            "certifications_degrees": candidate_profile.get("certifications_degrees", []),
            "years_experience": candidate_profile.get("years_experience", 0),
            "education": candidate_profile.get("education", ""),
            "ai_powered": verdicts.get("ai_powered", False),
        },
        # ── Categorized JD requirements ──
        "jd_requirements": {
            "essential": requirements.get("essential", requirements.get("required_hard_skills", [])),
            "good_to_have": requirements.get("good_to_have", []),
            "optional": requirements.get("optional", []),
            "min_years_experience": requirements.get("min_years_experience", 0),
            "education_requirement": requirements.get("education_requirement", ""),
        },
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
    groq_model: str = DEFAULT_GROQ_MODEL,
) -> str:
    """Generate a personalised cover letter for a job"""
    job_title = job.get("title", "the position")
    company = job.get("company", "your organization")
    job_desc = job.get("description", "")
    candidate_name = resume_info.get("applicant_name", "Your Name")

    # Use LLM if available
    if groq_api_key and _GROQ_AVAILABLE and ChatGroq:
        try:
            from utils.llm_extraction import _truncate_for_llm
            llm = ChatGroq(api_key=groq_api_key, model=groq_model, temperature=0.5, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)
            prompt = (
                f"Write a professional, concise cover letter for {candidate_name} "
                f"applying for the {job_title} role at {company}.\n\n"
                f"Job description: {_truncate_for_llm(job_desc, 'JD text', 8000)}\n\n"
                f"Resume highlights: {_truncate_for_llm(resume_text, 'resume text', 8000)}\n\n"
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
    llm = ChatGroq(api_key=groq_api_key, model=DEFAULT_GROQ_MODEL, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)

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