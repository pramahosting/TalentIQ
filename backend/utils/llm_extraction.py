"""
TalentIQ - Shared structured LLM extraction.

Used by CVAnalysis, JobHunter, and CandidateLens so all three present JD
requirements and candidate strengths the same way, and so improving the
prompt/schema only has to happen in one place (unlike the skill-matching
taxonomy, which unfortunately ended up triplicated across the three
routers before this).

Two extraction calls:
  - extract_jd_requirements_categorized: JD -> role/location/company +
    requirements split into Essential / Good to Have / Optional tiers.
  - extract_candidate_strengths: resume (+ the JD requirements above) ->
    strengths split into Essential (matched), Technical, Business, Soft
    Skills, Significant Experience, and Certifications & Degrees, plus
    gaps and a summary.

Both fall back to keyword heuristics (no LLM) when no Groq key is
available, so the app still returns *something* — just less nuanced.
"""
import json
import re
from typing import List, Optional

_PLACEHOLDER_VALUES = {
    "nil", "n/a", "na", "none", "-", "--", "tbd", "tba", "blank", "n.a.",
    "not specified", "not applicable", "unknown", "null",
}


def _clean_field(value: Optional[str]) -> str:
    if not value:
        return ""
    v = value.strip()
    if not v or v.lower() in _PLACEHOLDER_VALUES or len(v) > 160:
        return ""
    return v


def _parse_json_response(raw: str) -> Optional[dict]:
    text = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# JD REQUIREMENTS — categorized into Essential / Good to Have / Optional
# ══════════════════════════════════════════════════════════════════════════

async def extract_jd_requirements_categorized(
    jd_text: str, groq_key: Optional[str], groq_model: str,
) -> dict:
    """Returns:
    {"role": str, "location": str, "company": str,
     "essential": [str,...], "good_to_have": [str,...], "optional": [str,...],
     "min_years_experience": int, "education_requirement": str}
    essential/good_to_have/optional cover skills, tools, certifications, AND
    experience/education requirements — not skills only — since a JD's
    "5+ years in cloud architecture" or "Bachelor's in Computer Science" is
    just as much a requirement as a named tool.
    """
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0.1)
            prompt = f"""You are a senior recruiter reading a job description. Extract the
fields below precisely — if something genuinely isn't stated, use an empty
string/value rather than guessing, and never return placeholder text like
"Nil"/"N/A"/"TBD" as if it were a real value.

Categorize every requirement (skills, tools, certifications, experience,
education — not just technical skills) into exactly one tier, based on how
the JD phrases it:
- "essential": stated as required / must-have / mandatory
- "good_to_have": stated as preferred / desirable / advantageous, not mandatory
- "optional": mentioned only in passing, or a minor/bonus item

Job Description:
\"\"\"{jd_text[:3500]}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "role": "<job title, or empty string>",
  "location": "<work location, or empty string>",
  "company": "<hiring company name, or empty string>",
  "essential": ["<requirement>", ...],
  "good_to_have": ["<requirement>", ...],
  "optional": ["<requirement>", ...],
  "min_years_experience": <integer, 0 if not stated>,
  "education_requirement": "<short phrase, or empty string>"
}}"""
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = _parse_json_response(resp.content)
            if data and (data.get("essential") or data.get("good_to_have")):
                return {
                    "role": _clean_field(data.get("role")),
                    "location": _clean_field(data.get("location")),
                    "company": _clean_field(data.get("company")),
                    "essential": [s for s in data.get("essential", []) if s][:20],
                    "good_to_have": [s for s in data.get("good_to_have", []) if s][:12],
                    "optional": [s for s in data.get("optional", []) if s][:8],
                    "min_years_experience": int(data.get("min_years_experience") or 0),
                    "education_requirement": _clean_field(data.get("education_requirement")),
                    "ai_powered": True,
                }
        except Exception:
            pass
    return _fallback_jd_requirements(jd_text)


def _fallback_jd_requirements(jd_text: str, domain_skills: Optional[List[str]] = None) -> dict:
    from routers.cvintel import DOMAIN_SKILLS as _bank  # reuse the one large curated bank
    jd_lower = jd_text.lower()
    found = [s for s in (domain_skills or _bank) if s in jd_lower]

    role_m = re.search(r"(?:job\s*title|role|position\s*title)\s*[:\-]\s*(.+)", jd_text, re.IGNORECASE)
    loc_m = re.search(r"(?:location|based\s*in|located\s*in)\s*[:\-]\s*(.+)", jd_text, re.IGNORECASE)
    comp_m = re.search(r"(?:company|organisation|employer)\s*[:\-]\s*(.+)", jd_text, re.IGNORECASE)
    years_m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", jd_lower)
    edu_m = re.search(r"(bachelor'?s?|master'?s?|phd|degree|diploma)[^.\n]{0,80}", jd_lower)

    return {
        "role": _clean_field(role_m.group(1).split("\n")[0] if role_m else None),
        "location": _clean_field(loc_m.group(1).split("\n")[0] if loc_m else None),
        "company": _clean_field(comp_m.group(1).split("\n")[0] if comp_m else None),
        "essential": found[:15],
        "good_to_have": found[15:20],
        "optional": [],
        "min_years_experience": int(years_m.group(1)) if years_m else 0,
        "education_requirement": edu_m.group().strip().capitalize() if edu_m else "",
        "ai_powered": False,
    }


# ══════════════════════════════════════════════════════════════════════════
# CANDIDATE STRENGTHS — categorized breakdown, evidence-based against the JD
# ══════════════════════════════════════════════════════════════════════════

async def extract_candidate_strengths(
    resume_text: str, jd_requirements: dict, groq_key: Optional[str], groq_model: str,
) -> dict:
    """Returns:
    {"essential_matched": [...], "technical_skills": [...], "business_skills": [...],
     "soft_skills": [...], "significant_experience": [...],
     "certifications_degrees": [...], "gaps": [...], "summary": str,
     "years_experience": int, "education": str, "ai_powered": bool}
    """
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0.15)
            req_block = json.dumps({
                "essential": jd_requirements.get("essential", []),
                "good_to_have": jd_requirements.get("good_to_have", []),
            }, indent=2)[:1800]

            prompt = f"""You are an expert recruiter evaluating a candidate against a specific
role. You already have these JD requirements:
{req_block}

Now read the resume below and produce an evidence-based breakdown. Only
credit something the resume actually supports — do not invent skills or
experience it doesn't contain.

RESUME:
\"\"\"{resume_text[:4500]}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "essential_matched": ["<which ESSENTIAL JD requirements this candidate clearly satisfies, worded specifically>"],
  "technical_skills": ["<candidate's technical/hard skills relevant to this role — tools, languages, platforms>"],
  "business_skills": ["<business/domain skills — stakeholder management, budgeting, domain expertise, strategy>"],
  "soft_skills": ["<interpersonal skills evidenced in the resume — leadership, communication, problem solving>"],
  "significant_experience": ["<notable experience highlights with specifics — seniority, scale, achievements, years>"],
  "certifications_degrees": ["<certifications and degrees found in the resume>"],
  "gaps": ["<JD essential/good_to_have items NOT evidenced in the resume>"],
  "summary": "<2-3 sentence evidence-based overall assessment>",
  "years_experience": <integer, best estimate>,
  "education": "<highest qualification found, or empty string>"
}}"""
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = _parse_json_response(resp.content)
            if data and (data.get("technical_skills") or data.get("essential_matched")):
                return {
                    "essential_matched": [s for s in data.get("essential_matched", []) if s][:12],
                    "technical_skills": [s for s in data.get("technical_skills", []) if s][:10],
                    "business_skills": [s for s in data.get("business_skills", []) if s][:8],
                    "soft_skills": [s for s in data.get("soft_skills", []) if s][:8],
                    "significant_experience": [s for s in data.get("significant_experience", []) if s][:6],
                    "certifications_degrees": [s for s in data.get("certifications_degrees", []) if s][:8],
                    "gaps": [s for s in data.get("gaps", []) if s][:10],
                    "summary": (data.get("summary") or "").strip(),
                    "years_experience": int(data.get("years_experience") or 0),
                    "education": _clean_field(data.get("education")),
                    "ai_powered": True,
                }
        except Exception:
            pass
    return _fallback_candidate_strengths(resume_text, jd_requirements)


async def extract_candidate_strengths_general(
    resume_text: str, groq_key: Optional[str], groq_model: str,
) -> dict:
    """Same categorized breakdown as extract_candidate_strengths, but not
    evaluated against any specific JD — used by JobHunter, which matches
    ONE resume against MANY jobs: this extraction happens once per batch
    (the categorization is resume-intrinsic and doesn't change per job),
    while essential_matched/gaps per job are computed deterministically
    against each job's own requirements (see calculate_match)."""
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0.15)
            prompt = f"""You are an expert recruiter. Read the resume below and produce an
evidence-based categorized breakdown. Only credit something the resume
actually supports — do not invent skills or experience it doesn't contain.

RESUME:
\"\"\"{resume_text[:4500]}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "technical_skills": ["<technical/hard skills — tools, languages, platforms>"],
  "business_skills": ["<business/domain skills — stakeholder management, budgeting, strategy>"],
  "soft_skills": ["<interpersonal skills evidenced — leadership, communication, problem solving>"],
  "significant_experience": ["<notable experience highlights with specifics — seniority, scale, achievements>"],
  "certifications_degrees": ["<certifications and degrees found>"],
  "years_experience": <integer, best estimate>,
  "education": "<highest qualification found, or empty string>"
}}"""
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = _parse_json_response(resp.content)
            if data and data.get("technical_skills") is not None:
                return {
                    "technical_skills": [s for s in data.get("technical_skills", []) if s][:10],
                    "business_skills": [s for s in data.get("business_skills", []) if s][:8],
                    "soft_skills": [s for s in data.get("soft_skills", []) if s][:8],
                    "significant_experience": [s for s in data.get("significant_experience", []) if s][:6],
                    "certifications_degrees": [s for s in data.get("certifications_degrees", []) if s][:8],
                    "years_experience": int(data.get("years_experience") or 0),
                    "education": _clean_field(data.get("education")),
                    "ai_powered": True,
                }
        except Exception:
            pass
    return _fallback_candidate_strengths(resume_text, {"essential": []})


def _fallback_candidate_strengths(resume_text: str, jd_requirements: dict) -> dict:
    from routers.cvintel import DOMAIN_SKILLS as _bank
    resume_lower = resume_text.lower()

    essential = jd_requirements.get("essential", []) or []
    essential_matched = [s for s in essential if s.lower() in resume_lower]

    all_found = [s for s in _bank if s in resume_lower]
    # Heuristic split — genuinely categorizing skill "type" needs an LLM;
    # without one, put everything found in technical_skills so it's at
    # least visible, rather than mis-bucketing it.
    technical_skills = all_found[:10]

    years_m = re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", resume_lower)
    years = max((int(y) for y in years_m), default=0)

    edu_m = re.search(r"(bachelor'?s?|master'?s?|phd|degree|diploma)[^.\n]{0,80}", resume_lower)
    cert_m = re.findall(r"\b([A-Z]{2,6}(?:\s?-?\s?certified)?)\b", resume_text)
    certifications_degrees = []
    if edu_m:
        certifications_degrees.append(edu_m.group().strip().capitalize())

    gaps = [s for s in essential if s not in essential_matched]

    return {
        "essential_matched": essential_matched,
        "technical_skills": technical_skills,
        "business_skills": [],
        "soft_skills": [],
        "significant_experience": [f"{years}+ years of relevant experience"] if years else [],
        "certifications_degrees": certifications_degrees,
        "gaps": gaps,
        "summary": f"Matches {len(essential_matched)} of {len(essential)} essential requirements based on keyword analysis.",
        "years_experience": years,
        "education": certifications_degrees[0] if certifications_degrees else "",
        "ai_powered": False,
    }
