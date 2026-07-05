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

LLM provider order: Ollama first (a local instance has no per-token cost,
no external rate limits, and no dependency on a third-party API being up
— all real pain points hit while relying on Groq), then Groq if Ollama
isn't configured/reachable or fails, then a deterministic keyword
heuristic as the last resort so the app always returns *something*.

Every successful extraction (either provider) feeds a persistent, growing
skill taxonomy (models.SkillTaxonomy) — real terms actually seen in JDs
and resumes, accumulated over time rather than a fixed hand-written list.
That taxonomy is used two ways: as a short "known terms" reference
injected into future prompts (grounding a smaller local model's output in
terminology it's seen before), and to strengthen the keyword-only
fallback matcher, so even the no-LLM-available path gets more
comprehensive the more the system is used.
"""
import json
import re
import time
import requests
import asyncio
import concurrent.futures
from typing import List, Optional

# asyncio.to_thread() uses Python's DEFAULT executor, sized at
# min(32, cpu_count + 4) — on a modest 1-2 vCPU cloud instance, that's
# only 5-6 worker threads for the ENTIRE application, not just LLM calls.
# Since every Groq/Ollama call in this module went through asyncio.to_
# thread, that default sizing became an invisible concurrency ceiling far
# below what the app could otherwise handle: only 5-6 requests could ever
# have an LLM call in flight at once, everything else silently queued
# behind them, regardless of how many concurrent users hit the app or how
# much headroom Groq's own rate limits actually had.
#
# These calls are I/O-bound (waiting on network response), not CPU-bound —
# a thread sits mostly idle waiting for Groq/Ollama to respond, so having
# far more threads than CPU cores is safe and correct here, unlike CPU-
# bound work where more threads than cores just adds contention. A
# dedicated pool sized for expected concurrent request volume avoids
# competing with (or being limited by) whatever else might use the
# default executor elsewhere in the app.
_LLM_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=40, thread_name_prefix="llm-call",
)


async def _run_in_llm_pool(fn, *args):
    """Runs a blocking function in the dedicated LLM thread pool instead of
    asyncio's default (CPU-count-sized) executor — see _LLM_THREAD_POOL
    above for why this matters."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_LLM_THREAD_POOL, fn, *args)


# ── Document length budget for LLM prompts ──────────────────────────────
# Rough estimate: ~4 characters per token for English text. Even Groq's
# more conservative current models support 8K+ token context windows;
# reserving ~2K tokens for the prompt template itself plus the expected
# JSON response leaves a safe ~6K tokens (~24,000 characters) of headroom
# for the actual document. Set a little below that for margin across
# model variance, since the exact model in use is user-configurable.
#
# This used to be several different hardcoded, much smaller limits
# (1,500-5,000 chars) scattered across CVAnalysis/CandidateLens/JobHunter,
# which silently dropped entire sections of longer real-world JDs (a
# Required Qualifications section starting past the cutoff point, for
# example — every hard requirement in that JD was invisible to the LLM
# as a result, with no indication anything had been cut at all).
#
# IMPORTANT: raising the number alone doesn't make this robust — an
# unusually long outlier document run at scale (hundreds of JDs against
# thousands of resumes) could still exceed even a generous fixed limit.
# _truncate_for_llm() logs a visible warning whenever it actually has to
# cut something, so that case is never silent again.
MAX_DOC_CHARS = 20000

# Ollama is a genuinely different situation from Groq, not just "a slower
# version of the same thing" — it's a local model (often a 7-8B parameter
# model on modest consumer hardware, sometimes CPU-only) versus Groq's
# purpose-built fast inference hardware for much larger models. Sending it
# the same ~20,000-character prompt built for Groq isn't just slower, it
# can genuinely hang past any reasonable timeout. Ollama gets its own,
# much smaller budget so it has a realistic chance to actually finish
# within OLLAMA_TIMEOUT_SECONDS instead of always timing out and paying
# for the attempt without ever succeeding.
OLLAMA_DOC_CHARS = 6000
# A genuinely healthy local model given a 6,000-character prompt should
# respond within a few seconds on any reasonably modern machine, even
# CPU-only for a small model. If it's consistently taking longer than
# this, it's not a "just needs a bit more patience" situation — it's not
# a viable fast option today, and RACE_PROVIDERS below means that's fine:
# Groq wins that particular race and the user still gets a fast answer.
OLLAMA_TIMEOUT_SECONDS = 8


def _truncate_for_llm(text: str, label: str, limit: int = MAX_DOC_CHARS) -> str:
    """Truncates text for an LLM prompt, logging a visible warning if it
    actually had to cut anything."""
    if text and len(text) > limit:
        print(f"  WARNING: {label} is {len(text)} chars — truncating to {limit} for LLM "
              f"context budget. Content past this point will NOT be seen by extraction.")
        return text[:limit]
    return text


def _is_token_limit_error(e: Exception) -> bool:
    """Detects Groq's 413 'Request too large ... tokens per minute (TPM)'
    error specifically. This is a hard per-request ceiling tied to the
    account's tier and the specific model in use — unlike a transient 429
    rate limit (too many requests right now, try again shortly), the exact
    same oversized request will keep failing every single time no matter
    how many times it's retried, UNLESS the input itself is made smaller.
    Some Groq tiers/models have quite low limits (seen as low as 6,000 TPM
    on the free/on-demand tier for some models) — comfortably fitting a
    long resume/JD plus prompt instructions can exceed that even though
    the same content would fit fine on a higher tier or a different model.
    """
    msg = str(e).lower()
    return "413" in msg or "too large" in msg or "tokens per minute" in msg or " tpm" in msg


def _safe_retry_chars(e: Exception, current_chars: int) -> Optional[int]:
    """Groq's 413 error message states the exact limit and how much was
    requested (e.g. "Limit 6000, Requested 7347"). Rather than blindly
    guessing a smaller fixed size and possibly still being over (or
    needlessly under) the real limit, compute a precise new character
    budget from the actual numbers the error already gave us — this
    reaches a size that fits on the FIRST retry instead of potentially
    several guesses, each of which is a wasted network round-trip that
    adds pure latency for a request already known to be doomed. Returns
    None if the message doesn't match the expected pattern (falls back to
    the fixed-size retry sequence in that case)."""
    m = re.search(r"limit\s+(\d+),\s*requested\s+(\d+)", str(e), re.IGNORECASE)
    if not m:
        return None
    limit, requested = int(m.group(1)), int(m.group(2))
    if requested <= 0 or limit <= 0:
        return None
    # 15% safety margin: the 4-chars-per-token estimate is approximate,
    # and other parts of the prompt (instructions, JD requirement lists)
    # aren't being scaled down here, only the document text.
    ratio = (limit / requested) * 0.85
    new_chars = max(500, int(current_chars * ratio))
    return new_chars if new_chars < current_chars else None


def _call_ollama(prompt: str, base_url: str, model: str, timeout: int = OLLAMA_TIMEOUT_SECONDS) -> str:
    """Same implementation already proven working in routers/jdcreator.py
    — kept identical rather than reinvented, including the proxy bypass
    (without it, `requests` can route localhost/private Ollama traffic
    through a system proxy, which 404s it even though curl reaches it
    directly).

    timeout defaults to a short 8s. This is one contender in a RACE
    against Groq (see race_llm_providers below), not a sequential
    waterfall step — a slow/unreachable/hung local instance shouldn't add
    latency to the response at all, since Groq is running at the same
    time regardless of how long Ollama takes."""
    url = base_url.rstrip("/") + "/api/generate"
    resp = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
        timeout=timeout,
        proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def race_llm_providers(attempts: dict) -> Optional[tuple]:
    """Runs multiple LLM provider attempts CONCURRENTLY (in real OS threads,
    since both `requests` and langchain's ChatGroq.invoke are blocking
    calls) and returns the result from whichever succeeds FIRST, without
    waiting for the rest. This is the actual fix for "must respond in
    seconds, not minutes" — a sequential waterfall (try Ollama, wait for it
    to fail or time out, THEN try Groq) means total latency is the SUM of
    every failed attempt plus whichever one eventually works. Racing means
    total latency is bounded by the FASTEST one that works, regardless of
    how slow the others are or whether they fail at all — a slow/
    unreachable local Ollama costs nothing when Groq answers in a couple
    of seconds.

    attempts: {name: zero-arg callable returning a dict, or raising/
    returning None on failure}. Returns (name, result) from the first
    callable to return a truthy result, or None if all of them fail.

    Deliberately does NOT use `with ThreadPoolExecutor() as executor:` —
    that context manager's __exit__ calls shutdown(wait=True), which
    blocks until EVERY submitted thread finishes, including ones whose
    result we no longer need. That would silently defeat the entire point
    of racing (returning early is worthless if returning still waits for
    the slow one). Threads that haven't finished when we return keep
    running in the background until they naturally complete or time out —
    Python can't forcibly kill a thread — but the function itself returns
    as soon as we have an answer, which is what actually matters here.
    """
    import concurrent.futures

    if not attempts:
        return None
    if len(attempts) == 1:
        name, fn = next(iter(attempts.items()))
        try:
            result = fn()
            return (name, result) if result else None
        except Exception as e:
            print(f"  WARNING: {name} provider failed — {type(e).__name__}: {str(e)[:200]}")
            return None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(attempts))
    future_to_name = {executor.submit(fn): name for name, fn in attempts.items()}
    errors = []
    winner = None
    try:
        for future in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result()
                if result:
                    winner = (name, result)
                    break
                errors.append(f"{name}: empty/unparseable response")
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:150]}")
    finally:
        executor.shutdown(wait=False)

    if winner is None:
        print(f"  WARNING: all LLM providers failed in race — {'; '.join(errors)}")
    return winner


async def get_taxonomy_hint(db, category: Optional[str] = None, limit: int = 30) -> List[str]:
    """Returns the most-frequently-seen accumulated skill terms, most
    common first — injected into future prompts as a short "known terms"
    reference so extractions (especially from a smaller local Ollama
    model) stay grounded in terminology the system has actually
    encountered before, rather than reinventing categorization from
    scratch on every single call. Safe to call even before the taxonomy
    table exists or has any rows — returns an empty list rather than
    raising, so this is never a hard dependency for extraction to work."""
    try:
        from sqlalchemy import select
        from models.models import SkillTaxonomy
        stmt = select(SkillTaxonomy.skill_name).order_by(SkillTaxonomy.frequency.desc()).limit(limit)
        if category:
            stmt = stmt.where(SkillTaxonomy.category == category)
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows)
    except Exception:
        return []


async def enrich_skill_taxonomy(db, skills_by_category: dict) -> None:
    """Accumulates newly-seen skill/requirement terms from a successful
    extraction (either provider) into the persistent taxonomy — the more
    the platform is used, the more comprehensive this gets, entirely from
    real terms actually seen rather than manual maintenance. Best-effort:
    failures here are logged but never allowed to break the calling
    extraction, since this is a background enrichment step, not a
    required part of returning a result.

    skills_by_category: e.g. {"technical": [...], "business": [...],
    "soft": [...], "essential": [...], "certification": [...]}
    """
    try:
        from sqlalchemy import select
        from datetime import datetime
        from models.models import SkillTaxonomy

        now = datetime.utcnow()
        # Tracks skill names already handled (found-and-bumped, or newly
        # added) WITHIN this single call — without this, the same
        # normalized term appearing in more than one category (or twice in
        # the same list) would query the DB, find nothing yet because
        # nothing's been committed, and get added twice in the same
        # transaction: a guaranteed unique-constraint violation on commit.
        already_handled: set = set()
        for category, terms in (skills_by_category or {}).items():
            for term in (terms or []):
                normalized = (term or "").strip().lower()
                if not normalized or len(normalized) > 200:
                    continue
                if normalized in already_handled:
                    continue
                already_handled.add(normalized)
                existing = (await db.execute(
                    select(SkillTaxonomy).where(SkillTaxonomy.skill_name == normalized)
                )).scalar_one_or_none()
                if existing:
                    existing.frequency += 1
                    existing.last_seen_at = now
                else:
                    db.add(SkillTaxonomy(
                        skill_name=normalized, category=category,
                        frequency=1, first_seen_at=now, last_seen_at=now,
                    ))
        await db.commit()
    except Exception as e:
        print(f"  WARNING: enrich_skill_taxonomy failed (non-fatal, continuing) — {type(e).__name__}: {str(e)[:200]}")
        try:
            await db.rollback()
        except Exception:
            pass


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
        pass
    # One repair attempt for the most common near-miss issues: a stray
    # "..." left in from a schema example, or a trailing comma before a
    # closing bracket — both otherwise cause a full parse failure and silent
    # fallback to the much weaker heuristic path.
    try:
        repaired = re.sub(r",?\s*\.\.\.\s*", "", text)
        repaired = re.sub(r",(\s*[\]}])", r"\1", repaired)
        return json.loads(repaired)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# JD REQUIREMENTS — categorized into Essential / Good to Have / Optional
# ══════════════════════════════════════════════════════════════════════════

async def extract_jd_requirements_categorized(
    jd_text: str, groq_key: Optional[str], groq_model: str,
    ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None,
    known_terms_hint: Optional[List[str]] = None,
) -> dict:
    """Returns:
    {"role": str, "location": str, "company": str,
     "essential": [str,...], "good_to_have": [str,...], "optional": [str,...],
     "min_years_experience": int, "education_requirement": str}
    essential/good_to_have/optional cover skills, tools, certifications, AND
    experience/education requirements — not skills only — since a JD's
    "5+ years in cloud architecture" or "Bachelor's in Computer Science" is
    just as much a requirement as a named tool.

    Races Ollama and Groq concurrently when both are configured — total
    latency is bounded by whichever responds first, not the sum of a
    failed/slow attempt plus the other (see race_llm_providers). Falls to
    a deterministic keyword heuristic only if every configured provider
    fails. known_terms_hint (from the accumulated skill taxonomy — see
    get_taxonomy_hint) is injected as a short consistency reference so
    extractions align with terminology already seen, most valuable for a
    smaller local Ollama model.
    """
    hint_block = ""
    if known_terms_hint:
        hint_block = (
            "\n\nFor consistency with previous extractions on this platform, here are terms "
            "commonly seen before — if the JD clearly refers to one of these, use the SAME "
            "wording rather than inventing a slightly different phrasing (but only apply ones "
            "that genuinely fit; do not force-fit unrelated terms):\n"
            + ", ".join(known_terms_hint[:30])
        )

    def _build_prompt(jd_limit: int) -> str:
        return f"""You are a senior recruiter reading a job description. Extract the
fields below precisely — if something genuinely isn't stated, use an empty
string/value rather than guessing, and never return placeholder text like
"Nil"/"N/A"/"TBD" as if it were a real value.

Categorize every requirement (skills, tools, certifications, experience,
education — not just technical skills) into exactly one tier, based on how
the JD phrases it:
- "essential": stated as required / must-have / mandatory
- "good_to_have": stated as preferred / desirable / advantageous, not mandatory
- "optional": mentioned only in passing, or a minor/bonus item
{hint_block}

Job Description:
\"\"\"{_truncate_for_llm(jd_text, "JD text", jd_limit)}\"\"\"

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

    def _build_result(data: dict) -> Optional[dict]:
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
        return None

    def _try_ollama() -> Optional[dict]:
        ollama_mdl = ollama_model or "llama3"
        raw = _call_ollama(_build_prompt(OLLAMA_DOC_CHARS), ollama_base_url, ollama_mdl)
        return _build_result(_parse_json_response(raw))

    def _try_groq() -> Optional[dict]:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        # Retries with a shrinking budget specifically on a 413 token-limit
        # error rather than giving up immediately — some Groq tiers have
        # per-request limits (seen as low as 6,000 TPM) that a long JD can
        # exceed even after the normal, generous truncation. Sizes the
        # retry from the EXACT limit/requested numbers in Groq's own error
        # message (see _safe_retry_chars) rather than guessing fixed sizes
        # — reaches a size that fits on the first retry instead of
        # potentially several, each an extra network round-trip of pure
        # latency for a request already known to fail. This whole sequence
        # happens inside Groq's single "slot" in the race below — Ollama
        # isn't held up waiting for it.
        jd_limit = MAX_DOC_CHARS
        last_error = None
        for _attempt in range(4):
            try:
                llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low")
                _t0 = time.time()
                resp = llm.invoke([HumanMessage(content=_build_prompt(jd_limit))])
                _elapsed = time.time() - _t0
                print(f"  TIMING: extract_jd_requirements_categorized Groq call ({groq_model}) took {_elapsed:.2f}s, prompt size {jd_limit} chars")
                return _build_result(_parse_json_response(resp.content))
            except Exception as e:
                last_error = e
                if _is_token_limit_error(e):
                    new_limit = _safe_retry_chars(e, jd_limit)
                    if new_limit:
                        print(f"  WARNING: extract_jd_requirements_categorized request too large at {jd_limit}-char JD budget, retrying at computed safe size {new_limit} — {str(e)[:150]}")
                        jd_limit = new_limit
                        continue
                raise
        if last_error:
            raise last_error
        return None

    # ── Race Ollama and Groq concurrently — total latency is bounded by
    # whichever is faster, not the sum of a failed attempt plus the other.
    attempts = {}
    if ollama_base_url:
        attempts["ollama"] = _try_ollama
    if groq_key:
        attempts["groq"] = _try_groq
    if attempts:
        _race_t0 = time.time()
        outcome = await _run_in_llm_pool(race_llm_providers, attempts)
        _race_elapsed = time.time() - _race_t0
        if outcome:
            winner, result = outcome
            print(f"  TIMING: extract_jd_requirements_categorized total {_race_elapsed:.2f}s, winner: {winner}")
            return result
        print(f"  TIMING: extract_jd_requirements_categorized total {_race_elapsed:.2f}s, all providers failed")

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
    ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None,
    known_terms_hint: Optional[List[str]] = None,
) -> dict:
    """Returns:
    {"essential_matched": [...], "essential_missing": [...], "good_to_have_matched": [...],
     "technical_skills": [...], "business_skills": [...],
     "soft_skills": [...], "significant_experience": [...],
     "certifications_degrees": [...], "gaps": [...], "summary": str,
     "years_experience": int, "education": str, "ai_powered": bool}

    Each essential/good_to_have requirement is evaluated INDIVIDUALLY by the
    LLM (matched: true/false per item, not a free-text summary) — this is
    the actual scoring signal used downstream. Requirements are often long,
    abstract capability statements ("Strong ability to translate business
    needs into data architecture...") or use different terminology than the
    resume (e.g. JD says "Data Modeling", resume says "Dimensional
    Modeling" — a specific technique that IS a form of it). Neither a
    literal substring match nor a "does every word appear somewhere" check
    can reliably judge either case — that needs actual reading
    comprehension.

    The verdicts come back as a compact boolean array (one true/false per
    requirement, in order) rather than a numbered object per item
    ({"n": 1, "matched": true}) — functionally identical accuracy, but a
    fraction of the output tokens. That matters a lot in practice: with a
    reasoning-capable model, a longer/more complex required output format
    is more likely to exhaust the model's response budget on reasoning
    before it finishes writing the JSON, which silently drops this whole
    call down to the much weaker keyword-only fallback — at that point
    "more accurate in theory" loses to "actually completes successfully"
    most of the time.

    Races Ollama and Groq concurrently when both are configured — total
    latency is bounded by whichever responds first (see
    race_llm_providers), not the sum of a slow/failed attempt plus the
    other. Falls to the deterministic heuristic only if every configured
    provider fails. known_terms_hint (from the accumulated skill taxonomy)
    nudges the categorization toward terminology already seen before.
    """
    essential = [s for s in jd_requirements.get("essential", []) if s][:15]
    good_to_have = [s for s in jd_requirements.get("good_to_have", []) if s][:10]

    if not essential and not good_to_have:
        return _fallback_candidate_strengths(resume_text, jd_requirements)

    essential_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(essential)) or "(none)"
    good_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(good_to_have)) or "(none)"
    hint_block = ""
    if known_terms_hint:
        hint_block = (
            "\n\nFor consistency with previous extractions on this platform, here are skill "
            "terms commonly seen before — if the resume clearly demonstrates one of these, use "
            "the SAME wording rather than a slightly different phrasing (only apply ones that "
            "genuinely fit; do not force-fit unrelated terms):\n"
            + ", ".join(known_terms_hint[:30])
        )

    def _build_prompt(resume_limit: int) -> str:
        return f"""You are an expert recruiter evaluating a candidate's resume against a
specific job's requirements. For EACH numbered requirement below, judge
whether the resume provides genuine evidence for it — reading for meaning
and equivalent experience, not exact wording. Some requirements are
phrased as skills ("Data Modeling"), others as broad capability statements
("Strong ability to translate business needs into data architecture") —
judge both the same way: does the resume's actual content support this,
even if described using different terms, a more specific technique, or
different phrasing? For example, a resume mentioning "Dimensional
Modeling", "Data Vault", or "Star Schema design" DOES satisfy a
requirement for "Data Modeling", since those are specific forms of it.
Only mark something matched if the resume genuinely supports it — do not
be generous with unrelated content.
{hint_block}

ESSENTIAL REQUIREMENTS:
{essential_block}

GOOD-TO-HAVE REQUIREMENTS:
{good_block}

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text", resume_limit)}\"\"\"

Return ONLY valid JSON, no markdown, no commentary. "essential_matched" must
be a flat array of exactly {len(essential)} booleans, one per essential
requirement above IN THE SAME ORDER (true if genuinely matched, false if
not) — not an object, not a list of names, just booleans in order.
Likewise "good_to_have_matched" must have exactly {len(good_to_have)}
booleans in order:
{{
  "essential_matched": [true, false, true],
  "good_to_have_matched": [true, false],
  "technical_skills": ["<candidate's technical/hard skills relevant to this role — tools, languages, platforms>"],
  "business_skills": ["<business/domain skills — stakeholder management, budgeting, domain expertise, strategy>"],
  "soft_skills": ["<interpersonal skills evidenced in the resume — leadership, communication, problem solving>"],
  "significant_experience": ["<notable experience highlights with specifics — seniority, scale, achievements, years>"],
  "certifications_degrees": ["<certifications and degrees found in the resume>"],
  "summary": "<2-3 sentence evidence-based overall assessment>",
  "years_experience": <integer, best estimate>,
  "education": "<highest qualification found, or empty string>"
}}"""

    def _build_result(data: dict) -> Optional[dict]:
        if not data or (data.get("essential_matched") is None and not data.get("technical_skills")):
            return None
        ev = data.get("essential_matched") or []
        gv = data.get("good_to_have_matched") or []
        essential_matched = [r for i, r in enumerate(essential) if i < len(ev) and ev[i]]
        essential_missing = [r for i, r in enumerate(essential) if not (i < len(ev) and ev[i])]
        good_matched = [r for i, r in enumerate(good_to_have) if i < len(gv) and gv[i]]
        return {
            "essential_matched": essential_matched[:15],
            "essential_missing": essential_missing[:15],
            "good_to_have_matched": good_matched[:10],
            "technical_skills": [s for s in data.get("technical_skills", []) if s][:10],
            "business_skills": [s for s in data.get("business_skills", []) if s][:8],
            "soft_skills": [s for s in data.get("soft_skills", []) if s][:8],
            "significant_experience": [s for s in data.get("significant_experience", []) if s][:6],
            "certifications_degrees": [s for s in data.get("certifications_degrees", []) if s][:8],
            "gaps": essential_missing[:10],
            "summary": (data.get("summary") or "").strip(),
            "years_experience": int(data.get("years_experience") or 0),
            "education": _clean_field(data.get("education")),
            "ai_powered": True,
        }

    def _try_ollama() -> Optional[dict]:
        ollama_mdl = ollama_model or "llama3"
        raw = _call_ollama(_build_prompt(OLLAMA_DOC_CHARS), ollama_base_url, ollama_mdl)
        return _build_result(_parse_json_response(raw))

    def _try_groq() -> Optional[dict]:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        # A 413 "request too large / tokens per minute" error is a hard
        # per-request ceiling for this account tier + model — retrying the
        # SAME request changes nothing, it needs to be smaller. Some Groq
        # tiers have quite low limits (seen as low as 6,000 TPM), which a
        # long resume plus JD requirements plus prompt instructions can
        # exceed even after truncation to the normal (generous) budget.
        # Sizes the retry from the EXACT limit/requested numbers in Groq's
        # own error message (see _safe_retry_chars) rather than guessing
        # fixed sizes — reaches a size that fits on the first retry
        # instead of potentially several, each an extra network round-trip
        # of pure latency for a request already known to fail. This whole
        # sequence happens inside Groq's single "slot" in the race below —
        # Ollama isn't held up waiting for it.
        resume_limit = MAX_DOC_CHARS
        last_error = None
        for _attempt in range(4):
            try:
                llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low")
                _t0 = time.time()
                resp = llm.invoke([HumanMessage(content=_build_prompt(resume_limit))])
                _elapsed = time.time() - _t0
                print(f"  TIMING: extract_candidate_strengths Groq call ({groq_model}) took {_elapsed:.2f}s, prompt size {resume_limit} chars")
                return _build_result(_parse_json_response(resp.content))
            except Exception as e:
                last_error = e
                if _is_token_limit_error(e):
                    new_limit = _safe_retry_chars(e, resume_limit)
                    if new_limit:
                        print(f"  WARNING: extract_candidate_strengths request too large at {resume_limit}-char resume budget, retrying at computed safe size {new_limit} — {str(e)[:150]}")
                        resume_limit = new_limit
                        continue
                raise
        if last_error:
            raise last_error
        return None

    # ── Race Ollama and Groq concurrently — total latency is bounded by
    # whichever is faster, not the sum of a failed attempt plus the other.
    attempts = {}
    if ollama_base_url:
        attempts["ollama"] = _try_ollama
    if groq_key:
        attempts["groq"] = _try_groq
    if attempts:
        _race_t0 = time.time()
        outcome = await _run_in_llm_pool(race_llm_providers, attempts)
        _race_elapsed = time.time() - _race_t0
        if outcome:
            winner, result = outcome
            print(f"  TIMING: extract_candidate_strengths total {_race_elapsed:.2f}s, winner: {winner}")
            return result
        print(f"  TIMING: extract_candidate_strengths total {_race_elapsed:.2f}s, all providers failed")

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

            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low")
            prompt = f"""You are an expert recruiter. Read the resume below and produce an
evidence-based categorized breakdown. Only credit something the resume
actually supports — do not invent skills or experience it doesn't contain.

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text")}\"\"\"

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
        except Exception as e:
            print(f"  WARNING: extract_candidate_strengths_general LLM call failed, falling back to keyword heuristic — {type(e).__name__}: {str(e)[:300]}")
    return _fallback_candidate_strengths(resume_text, {"essential": []})


def _fallback_candidate_strengths(resume_text: str, jd_requirements: dict) -> dict:
    from routers.cvintel import DOMAIN_SKILLS as _bank, _skill_present, _normalize_skill, _normalize_text

    resume_lower = _normalize_text(resume_text)
    candidate_skill_set = {_normalize_skill(s) for s in _bank if s in resume_lower}

    essential = jd_requirements.get("essential", []) or []
    good_to_have = jd_requirements.get("good_to_have", []) or []
    essential_matched = [s for s in essential if _skill_present(_normalize_skill(s), candidate_skill_set, resume_lower)]
    essential_missing = [s for s in essential if s not in essential_matched]
    good_to_have_matched = [s for s in good_to_have if _skill_present(_normalize_skill(s), candidate_skill_set, resume_lower)]

    all_found = [s for s in _bank if s in resume_lower]
    # Heuristic split — genuinely categorizing skill "type" needs an LLM;
    # without one, put everything found in technical_skills so it's at
    # least visible, rather than mis-bucketing it.
    technical_skills = all_found[:10]

    years_m = re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?experience", resume_lower)
    years = max((int(y) for y in years_m), default=0)

    edu_m = re.search(r"(bachelor'?s?|master'?s?|phd|degree|diploma)[^.\n]{0,80}", resume_lower)
    certifications_degrees = []
    if edu_m:
        certifications_degrees.append(edu_m.group().strip().capitalize())

    return {
        "essential_matched": essential_matched,
        "essential_missing": essential_missing,
        "good_to_have_matched": good_to_have_matched,
        "technical_skills": technical_skills,
        "business_skills": [],
        "soft_skills": [],
        "significant_experience": [f"{years}+ years of relevant experience"] if years else [],
        "certifications_degrees": certifications_degrees,
        "gaps": essential_missing,
        "summary": f"Matches {len(essential_matched)} of {len(essential)} essential requirements based on keyword analysis.",
        "years_experience": years,
        "education": certifications_degrees[0] if certifications_degrees else "",
        "ai_powered": False,
    }
