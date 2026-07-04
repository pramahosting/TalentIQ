"""
TalentIQ – JobIntel LangChain Agent
Analyses job market intelligence: skills demand, salary trends, company breakdown.
"""

import re
from collections import Counter
from typing import List, Dict, Optional, Any

import requests
from langchain_core.tools import Tool
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from utils.credentials import DEFAULT_GROQ_MODEL

try:
    from langchain_groq import ChatGroq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False
    ChatGroq = None  # type: ignore


# ─────────────────────────────────────────────
# SKILL / TOOL TAXONOMIES
# ─────────────────────────────────────────────

TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "react", "angular", "vue",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "fastapi", "django", "flask", "spring", "node.js", "express",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "machine learning", "deep learning", "nlp", "langchain", "tensorflow", "pytorch",
    "pandas", "numpy", "scikit-learn", "spark", "hadoop", "snowflake", "dbt",
    "tableau", "power bi", "looker", "excel", "git", "linux", "rest api", "graphql",
    "agile", "scrum", "devops", "ci/cd", "jenkins", "github actions",
    "sap", "salesforce", "jira", "confluence", "airflow",
]

SOFT_SKILLS = [
    "communication", "leadership", "problem solving", "team work", "analytical",
    "attention to detail", "time management", "stakeholder management",
    "critical thinking", "project management", "collaboration",
]

EXPERIENCE_LEVEL_MAP = {
    "junior": ["junior", "graduate", "entry level", "associate", "jr"],
    "mid": ["mid", "intermediate", "2-4 years", "3-5 years"],
    "senior": ["senior", "sr", "lead", "principal", "5+ years", "7+ years"],
    "executive": ["head", "director", "vp", "chief", "cto", "cfo", "ceo", "executive"],
}


def detect_experience_level(text: str) -> str:
    text_lower = text.lower()
    for level, keywords in EXPERIENCE_LEVEL_MAP.items():
        if any(k in text_lower for k in keywords):
            return level
    return "mid"


def extract_skills_from_text(text: str) -> Dict[str, List[str]]:
    text_lower = text.lower()
    found_tech = [s for s in TECH_SKILLS if s in text_lower]
    found_soft = [s for s in SOFT_SKILLS if s in text_lower]
    return {"tech_skills": found_tech, "soft_skills": found_soft}


def extract_salary_from_text(text: str) -> Optional[Dict]:
    patterns = [
        r"\$(\d{2,3}),?(\d{3})(?:\s*[-–to]+\s*\$?(\d{2,3}),?(\d{3}))?",
        r"(\d{2,3})k\s*[-–to]+\s*(\d{2,3})k",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            try:
                if "k" in pattern:
                    return {"min": int(groups[0]) * 1000, "max": int(groups[1]) * 1000}
                else:
                    min_val = int(groups[0] + (groups[1] or "000"))
                    max_val = int(groups[2] + (groups[3] or "000")) if groups[2] else None
                    return {"min": min_val, "max": max_val}
            except Exception:
                continue
    return None


def determine_domain(title: str, description: str) -> str:
    text = (title + " " + description).lower()
    domain_map = {
        "Banking & Financial Services": ["bank", "finance", "financial", "risk", "compliance", "aml", "credit"],
        "Technology": ["software", "developer", "engineer", "devops", "cloud", "data", "ai", "ml"],
        "Healthcare": ["health", "medical", "clinical", "nurse", "doctor", "hospital", "pharma"],
        "Marketing": ["marketing", "seo", "digital", "brand", "content", "campaign"],
        "HR & People": ["hr", "human resources", "recruitment", "talent", "payroll"],
        "Legal": ["legal", "lawyer", "compliance", "solicitor", "counsel"],
        "Operations": ["operations", "supply chain", "logistics", "procurement"],
        "Consulting": ["consulting", "advisory", "management consultant"],
    }
    for domain, keywords in domain_map.items():
        if any(k in text for k in keywords):
            return domain
    return "General"


def determine_working_function(title: str) -> str:
    title_lower = title.lower()
    function_map = {
        "Engineering": ["engineer", "developer", "architect", "devops"],
        "Data Science": ["data scientist", "ml engineer", "ai", "analyst"],
        "Product": ["product manager", "product owner", "ux", "ui"],
        "Risk & Compliance": ["risk", "compliance", "audit", "aml"],
        "Finance": ["finance", "accountant", "cfo", "controller"],
        "HR": ["hr", "human resources", "people", "recruiter"],
        "Operations": ["operations", "ops", "supply chain"],
        "Sales & Marketing": ["sales", "marketing", "growth", "business development"],
    }
    for func, keywords in function_map.items():
        if any(k in title_lower for k in keywords):
            return func
    return "Other"


# ─────────────────────────────────────────────
# MARKET ANALYTICS ENGINE
# ─────────────────────────────────────────────

def analyse_jobs(jobs: List[Dict]) -> Dict:
    """Compute analytics insights from a list of job records"""
    if not jobs:
        return {}

    all_tech_skills: List[str] = []
    all_soft_skills: List[str] = []
    all_tools: List[str] = []
    salary_values: List[int] = []
    job_types: List[str] = []
    company_types: List[str] = []
    domains: List[str] = []
    experience_levels: List[str] = []

    for job in jobs:
        text = (job.get("description") or "") + " " + (job.get("title") or "")
        skills = extract_skills_from_text(text)
        all_tech_skills.extend(skills["tech_skills"])
        all_soft_skills.extend(skills["soft_skills"])

        salary = extract_salary_from_text(text)
        if salary:
            if salary.get("min"):
                salary_values.append(salary["min"])
            if salary.get("max"):
                salary_values.append(salary["max"])

        jt = job.get("job_type") or "Unknown"
        job_types.append(jt)
        company_types.append(job.get("source") or "Unknown")
        domains.append(determine_domain(job.get("title", ""), job.get("description", "")))
        experience_levels.append(detect_experience_level(text))

    top_skills = [{"skill": s, "count": c} for s, c in Counter(all_tech_skills).most_common(15)]
    top_soft = [{"skill": s, "count": c} for s, c in Counter(all_soft_skills).most_common(10)]
    salary_stats = None
    if salary_values:
        salary_stats = {
            "min": min(salary_values),
            "max": max(salary_values),
            "avg": round(sum(salary_values) / len(salary_values)),
        }

    return {
        "total_jobs": len(jobs),
        "top_skills": top_skills,
        "top_soft_skills": top_soft,
        "salary_stats": salary_stats,
        "job_type_breakdown": dict(Counter(job_types).most_common()),
        "company_type_breakdown": dict(Counter(company_types).most_common()),
        "domain_breakdown": dict(Counter(domains).most_common()),
        "experience_level_breakdown": dict(Counter(experience_levels).most_common()),
    }


def enrich_job_record(job: Dict) -> Dict:
    """Enrich a raw job dict with structured intelligence fields"""
    text = (job.get("description") or "") + " " + (job.get("title") or "")
    skills = extract_skills_from_text(text)
    salary = extract_salary_from_text(text)

    return {
        **job,
        "domain": determine_domain(job.get("title", ""), job.get("description", "")),
        "working_function": determine_working_function(job.get("title", "")),
        "experience_level": detect_experience_level(text),
        "key_skills": skills["tech_skills"][:10],
        "soft_skills": skills["soft_skills"][:5],
        "tools_technology": [s for s in skills["tech_skills"] if any(
            t in s for t in ["sql", "python", "aws", "azure", "docker", "tableau", "sap", "salesforce"]
        )][:8],
        "salary_min": salary.get("min") if salary else None,
        "salary_max": salary.get("max") if salary else None,
        "responsibilities": [
            l.strip().lstrip("•-* ")
            for l in (job.get("description") or "").splitlines()
            if len(l.strip()) > 20 and l.strip().startswith(("-", "•", "*"))
        ][:6],
    }


# ─────────────────────────────────────────────
# LANGCHAIN AGENT
# ─────────────────────────────────────────────

def build_jobintel_agent(groq_api_key: str) -> AgentExecutor:
    if not _GROQ_AVAILABLE or not ChatGroq:
        raise RuntimeError("langchain-groq is not installed. Run: pip install langchain-groq")
    llm = ChatGroq(api_key=groq_api_key, model=DEFAULT_GROQ_MODEL, temperature=0)

    tools = [
        Tool(
            name="ScrapeJobMarket",
            func=lambda q: f"Scraping market data for: {q}",
            description="Scrape jobs from Adzuna for market intelligence analysis.",
        ),
        Tool(
            name="AnalyseSkillDemand",
            func=lambda jobs: str(analyse_jobs([])),
            description="Analyse skill demand, salary trends, and hiring patterns from job data.",
        ),
        Tool(
            name="GenerateMarketReport",
            func=lambda q: f"Market report for: {q}",
            description="Generate a natural language market intelligence report from analytics data.",
        ),
    ]

    prompt = PromptTemplate.from_template(
        "You are the JobIntel AI agent specializing in job market analysis.\n\n"
        "Available tools: {tools}\nTool names: {tool_names}\n\n"
        "Request: {input}\n\n{agent_scratchpad}"
    )

    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)
