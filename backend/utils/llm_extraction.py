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


def _mask_key_for_log(key_value: Optional[str]) -> str:
    """Masked identifier (last 4 chars) for log lines — lets a specific
    request be traced back to which key served it, without ever printing
    the real value. Same masking convention as utils/groq_pool.py and the
    admin pool UI."""
    if not key_value:
        return "(none)"
    tail = key_value[-4:] if len(key_value) >= 4 else key_value
    return f"...{tail}"

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


def _is_rate_limit_error(e: Exception) -> bool:
    """Detects a 429 'too many requests right now' error specifically —
    unlike a 413 (this exact request is too big, will never succeed
    without shrinking it), a 429 is transient: the SAME request will very
    likely succeed if retried after the rate-limit window passes. This
    matters a lot with the chunked/concurrent architecture used below —
    firing several concurrent Groq requests for one analysis measurably
    increases the odds that one of them lands during a moment the
    account's shared (organization-wide, not per-key) rate limit is
    briefly exhausted, even when the account has plenty of headroom
    overall. Previously, ANY single chunk hitting this meant the whole
    analysis fell back to the weak keyword heuristic — losing real,
    already-succeeded AI results from the other chunks over one transient
    blip. Retrying just the affected chunk fixes that."""
    msg = str(e).lower()
    return "429" in msg or "rate limit reached" in msg or "rate_limit_exceeded" in msg


def _is_tpm_error(e: Exception) -> bool:
    """Distinguishes a TOKENS-per-minute limit from a requests-per-minute
    one — confirmed directly from a real production log where 3 concurrent
    chunks hit this exact error, waited 5s, retried, and hit it again.
    TPM uses a rolling 60-second window: a short wait doesn't meaningfully
    reduce "tokens used in the last 60 seconds" the way it would for a
    simple request-count limit, since the tokens already sent are still
    inside that window. A 5-second wait was never going to clear this —
    it needs to wait closer to the actual window, not a token-agnostic
    short retry."""
    msg = str(e).lower()
    return "tokens per minute" in msg or " tpm" in msg or "tpm)" in msg


def _parse_retry_after_seconds(e: Exception, cap: float = 5.0) -> float:
    """Groq's 429 error message often includes a suggested wait, e.g.
    "Please try again in 6m11.52s" — parsed here so the retry waits a
    sensible amount rather than guessing. Genuine exhaustion can suggest
    minutes-long waits, which is far too long to make a user wait
    synchronously for one request — capped at `cap` seconds; if the
    suggested wait exceeds that, the caller should treat this as not
    worth retrying right now rather than blocking the user for minutes."""
    m = re.search(r"try again in\s+(?:(\d+)m)?([\d.]+)s", str(e), re.IGNORECASE)
    if not m:
        return min(1.0, cap)  # no hint available — a short default wait
    minutes = int(m.group(1)) if m.group(1) else 0
    seconds = float(m.group(2))
    return min(minutes * 60 + seconds, cap)


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


def race_llm_providers(attempts: dict) -> dict:
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
    returning None on failure}.

    Returns {"winner": name|None, "result": dict|None,
    "is_rate_limit_failure": bool} — the last field matters specifically
    for the pool: a plain failure (bad key, parse error) isn't worth
    retrying with a different key, but a rate-limit failure means the
    key itself is fine, just temporarily throttled — worth telling the
    async caller so it can mark this key cooling down and try a
    genuinely different one, rather than giving up entirely.

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
        return {"winner": None, "result": None, "is_rate_limit_failure": False}
    if len(attempts) == 1:
        name, fn = next(iter(attempts.items()))
        try:
            result = fn()
            if result:
                return {"winner": name, "result": result, "is_rate_limit_failure": False}
            return {"winner": None, "result": None, "is_rate_limit_failure": False}
        except Exception as e:
            print(f"  WARNING: {name} provider failed — {type(e).__name__}: {str(e)[:200]}")
            return {"winner": None, "result": None, "is_rate_limit_failure": _is_rate_limit_error(e)}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(attempts))
    future_to_name = {executor.submit(fn): name for name, fn in attempts.items()}
    errors = []
    winner = None
    any_rate_limit = False
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
                if name == "groq" and _is_rate_limit_error(e):
                    any_rate_limit = True
    finally:
        executor.shutdown(wait=False)

    if winner is None:
        print(f"  WARNING: all LLM providers failed in race — {'; '.join(errors)}")
        return {"winner": None, "result": None, "is_rate_limit_failure": any_rate_limit}
    return {"winner": winner[0], "result": winner[1], "is_rate_limit_failure": False}


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
    db=None, user_id: Optional[int] = None,
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
                "_groqKeyPreview": _mask_key_for_log(groq_key),
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
                llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)
                _t0 = time.time()
                print(f"  TIMING: extract_jd_requirements_categorized attempting Groq call ({groq_model}, key {_mask_key_for_log(groq_key)})")
                resp = llm.invoke([HumanMessage(content=_build_prompt(jd_limit))])
                _elapsed = time.time() - _t0
                print(f"  TIMING: extract_jd_requirements_categorized Groq call ({groq_model}, key {_mask_key_for_log(groq_key)}) took {_elapsed:.2f}s, prompt size {jd_limit} chars")
                return _build_result(_parse_json_response(resp.content))
            except Exception as e:
                last_error = e
                if _is_token_limit_error(e):
                    new_limit = _safe_retry_chars(e, jd_limit)
                    if new_limit:
                        print(f"  WARNING: extract_jd_requirements_categorized request too large at {jd_limit}-char JD budget, retrying at computed safe size {new_limit} — {str(e)[:150]}")
                        jd_limit = new_limit
                        continue
                # Rate limits are NOT retried here with the same key — the
                # outer loop (see below) rotates to a genuinely different
                # pool key instead, which is the actual fix rather than
                # waiting and hoping the identical key recovers.
                raise
        if last_error:
            raise last_error
        return None

    # If db/user_id are available, resolve from the shared pool instead of
    # using the passed-in groq_key directly — reassigning these local
    # names works because _try_groq/_try_ollama above close over them by
    # name, evaluated when actually called, not when defined.
    _pool_id = None
    if db is not None and user_id is not None:
        from utils.groq_pool import resolve_groq_key
        _kr = await resolve_groq_key(db, user_id)
        groq_key = _kr["groq_key"]
        groq_model = _kr["model"] or groq_model
        _pool_id = _kr["pool_id"] if _kr["source"] == "pool" else None

    # ── Race Ollama and Groq concurrently — total latency is bounded by
    # whichever is faster, not the sum of a failed attempt plus the other.
    for _outer_attempt in range(2):
        attempts = {}
        if ollama_base_url:
            attempts["ollama"] = _try_ollama
        if groq_key:
            attempts["groq"] = _try_groq
        if not attempts:
            break
        _race_t0 = time.time()
        outcome = await _run_in_llm_pool(race_llm_providers, attempts)
        _race_elapsed = time.time() - _race_t0
        winner, result, is_rate_limit = outcome["winner"], outcome["result"], outcome["is_rate_limit_failure"]

        if winner:
            if _pool_id is not None:
                from utils.groq_pool import record_key_outcome
                await record_key_outcome(db, _pool_id, success=True)
            print(f"  TIMING: extract_jd_requirements_categorized total {_race_elapsed:.2f}s, winner: {winner}")
            return result

        print(f"  TIMING: extract_jd_requirements_categorized total {_race_elapsed:.2f}s, all providers failed")

        # A rate-limit failure means the KEY is fine, just temporarily
        # throttled — mark it cooling down and ask the pool for a
        # genuinely different one, rather than giving up. This is the
        # actual fix for a real bug found directly in production logs:
        # the previous version waited and retried the IDENTICAL key that
        # had just been rate-limited, which obviously never helped and
        # defeated the entire purpose of having multiple pool keys.
        if is_rate_limit and _pool_id is not None and db is not None and user_id is not None and _outer_attempt == 0:
            from utils.groq_pool import record_key_outcome, resolve_groq_key
            await record_key_outcome(db, _pool_id, success=False)
            _kr = await resolve_groq_key(db, user_id)
            if _kr["groq_key"] and _kr["key_preview"] != _mask_key_for_log(groq_key):
                print(f"  WARNING: extract_jd_requirements_categorized — key {_mask_key_for_log(groq_key)} was rate-limited, retrying with a different pool key {_kr['key_preview']}")
                groq_key = _kr["groq_key"]
                groq_model = _kr["model"] or groq_model
                _pool_id = _kr["pool_id"] if _kr["source"] == "pool" else None
                continue
        break

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
# RESUME FACTS — pure resume-level extraction, deliberately independent of
# any specific JD's requirements (see docstring below for why this exists
# as its own function)
# ══════════════════════════════════════════════════════════════════════════

async def extract_resume_facts(
    resume_text: str, groq_key: Optional[str], groq_model: str,
    ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None,
    db=None, user_id: Optional[int] = None,
) -> Optional[dict]:
    """Returns:
    {"technical_skills": [...], "business_skills": [...], "soft_skills": [...],
     "significant_experience": [...], "certifications_degrees": [...],
     "summary": str, "years_experience": int, "education": str,
     "ai_powered": bool}

    Deliberately extracts ONLY facts about the resume itself — what skills
    it shows, how much experience, what education — with no reference to
    any specific job's requirements at all. This used to be bundled into
    the SAME call as good-to-have JD matching (see extract_candidate_
    strengths below), which meant it could only start after JD
    categorization had already finished, even though it doesn't actually
    need anything JD categorization produces. Splitting it out means a
    caller can run this CONCURRENTLY with extract_jd_requirements_
    categorized instead of waiting for it — the two are independent until
    the actual matching step, which is the only part that genuinely needs
    both a resume and a specific JD's requirements at once.

    Same race/rotation behavior as extract_jd_requirements_categorized:
    races Ollama vs Groq when both configured, and on a Groq rate limit,
    rotates to a different pool key rather than retrying the same one.
    """
    def _try_ollama() -> Optional[dict]:
        ollama_mdl = ollama_model or "llama3"
        raw = _call_ollama(_build_resume_facts_prompt(resume_text, OLLAMA_DOC_CHARS), ollama_base_url, ollama_mdl)
        return _build_resume_facts_result(_parse_json_response(raw))

    def _try_groq() -> Optional[dict]:
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage

        limit = MAX_DOC_CHARS
        last_error = None
        for _attempt in range(4):
            try:
                llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=2000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)
                _t0 = time.time()
                print(f"  TIMING: extract_resume_facts attempting Groq call ({groq_model}, key {_mask_key_for_log(groq_key)})")
                resp = llm.invoke([HumanMessage(content=_build_resume_facts_prompt(resume_text, limit))])
                _elapsed = time.time() - _t0
                print(f"  TIMING: extract_resume_facts Groq call ({groq_model}, key {_mask_key_for_log(groq_key)}) took {_elapsed:.2f}s, prompt size {limit} chars")
                return _build_resume_facts_result(_parse_json_response(resp.content))
            except Exception as e:
                last_error = e
                if _is_token_limit_error(e):
                    new_limit = _safe_retry_chars(e, limit)
                    if new_limit:
                        limit = new_limit
                        continue
                raise
        if last_error:
            raise last_error
        return None

    for _outer_attempt in range(2):
        attempts = {}
        if ollama_base_url:
            attempts["ollama"] = _try_ollama
        if groq_key:
            attempts["groq"] = _try_groq
        if not attempts:
            break
        outcome = await _run_in_llm_pool(race_llm_providers, attempts)
        winner, result, is_rate_limit = outcome["winner"], outcome["result"], outcome["is_rate_limit_failure"]

        if winner:
            return result

        if is_rate_limit and db is not None and user_id is not None and _outer_attempt == 0:
            from utils.groq_pool import resolve_groq_key
            kr = await resolve_groq_key(db, user_id)
            if kr["groq_key"] and kr["key_preview"] != _mask_key_for_log(groq_key):
                print(f"  WARNING: extract_resume_facts — key {_mask_key_for_log(groq_key)} was rate-limited, retrying with a different pool key {kr['key_preview']}")
                groq_key = kr["groq_key"]
                groq_model = kr["model"] or groq_model
                continue
        break

    return None


def _build_resume_facts_prompt(resume_text: str, resume_limit: int) -> str:
    return f"""You are an expert recruiter reading a resume. Extract the following —
this is about the CANDIDATE only, not tied to any specific job:

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text", resume_limit)}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "technical_skills": ["<candidate's technical/hard skills — tools, languages, platforms>"],
  "business_skills": ["<business/domain skills — stakeholder management, budgeting, domain expertise, strategy>"],
  "soft_skills": ["<interpersonal skills evidenced in the resume — leadership, communication, problem solving>"],
  "significant_experience": ["<notable experience highlights with specifics — seniority, scale, achievements, years>"],
  "certifications_degrees": ["<certifications and degrees found in the resume>"],
  "summary": "<2-3 sentence evidence-based overall assessment of the candidate>",
  "years_experience": <integer, best estimate>,
  "education": "<highest qualification found, or empty string>"
}}"""


def _build_resume_facts_result(data: dict) -> Optional[dict]:
    if not data:
        return None
    return {
        "technical_skills": [s for s in data.get("technical_skills", []) if s][:10],
        "business_skills": [s for s in data.get("business_skills", []) if s][:8],
        "soft_skills": [s for s in data.get("soft_skills", []) if s][:8],
        "significant_experience": [s for s in data.get("significant_experience", []) if s][:6],
        "certifications_degrees": [s for s in data.get("certifications_degrees", []) if s][:8],
        "summary": (data.get("summary") or "").strip(),
        "years_experience": int(data.get("years_experience") or 0),
        "education": _clean_field(data.get("education")),
        "ai_powered": True,
    }


# ══════════════════════════════════════════════════════════════════════════
# CANDIDATE STRENGTHS — categorized breakdown, evidence-based against the JD
# ══════════════════════════════════════════════════════════════════════════

async def extract_candidate_strengths(
    resume_text: str, jd_requirements: dict, groq_key: Optional[str], groq_model: str,
    ollama_base_url: Optional[str] = None, ollama_model: Optional[str] = None,
    known_terms_hint: Optional[List[str]] = None,
    db=None, user_id: Optional[int] = None,
    pre_extracted_facts: Optional[dict] = None,
) -> dict:
    """Returns:
    {"essential_matched": [...], "essential_missing": [...], "good_to_have_matched": [...],
     "technical_skills": [...], "business_skills": [...],
     "soft_skills": [...], "significant_experience": [...],
     "certifications_degrees": [...], "gaps": [...], "summary": str,
     "years_experience": int, "education": str, "ai_powered": bool}

    Each essential/good_to_have requirement is evaluated INDIVIDUALLY by the
    LLM (matched: true/false per item, not a free-text summary) for
    genuine reading comprehension — a requirement like "Data Modeling"
    should match a resume saying "Dimensional Modeling" (a specific
    technique that IS a form of it), and a literal substring/keyword check
    can't judge that reliably.

    IMPORTANT — why this is chunked rather than one big request: asking a
    reasoning model to judge up to 25 items against a full resume in a
    SINGLE call measurably took 50+ seconds in production (confirmed via
    direct timing — the exact same model handling a simpler single-pass
    JD-categorization task took under 5 seconds). Lowering reasoning
    effort/format settings didn't fix this, because the issue isn't how
    much the model deliberates per item, it's that judging 25 separate
    things against a full document is genuinely 25x the work of judging
    one — no config flag changes that. So essential requirements are split
    into small chunks (max 8 items) and evaluated CONCURRENTLY, each chunk
    a separate lightweight request; good-to-have verdicts and the
    resume-level skills/summary extraction run as their own concurrent
    call alongside those chunks. Total wall-clock time is bounded by the
    SLOWEST single chunk, not the sum of all judgments — the actual fix
    for "one big call is slow," rather than hoping a smaller model or a
    reasoning-effort setting papers over an inherently large task.

    Races Ollama and Groq concurrently PER CHUNK when both are configured.
    Falls to the deterministic heuristic only if the whole thing fails.
    known_terms_hint (from the accumulated skill taxonomy) nudges
    categorization toward terminology already seen before.

    Pass db + user_id to have EACH concurrent chunk independently draw its
    own key from the shared Groq key pool (see utils/groq_pool.py) rather
    than all chunks sharing the single `groq_key` passed in — this is what
    lets one user's single request use multiple pool keys simultaneously,
    for genuinely more combined throughput on a large analysis, not just
    spreading different USERS' requests across the pool. If db/user_id
    aren't provided, every chunk falls back to the single passed-in
    groq_key exactly as before — fully backward compatible.

    Pass pre_extracted_facts (from extract_resume_facts, called separately
    and concurrently with JD categorization by the caller) to skip
    re-extracting technical_skills/business_skills/summary/etc. here —
    the good-to-have call becomes JUST the good-to-have judgment, a
    lighter/faster prompt, and the pre-extracted facts are merged into the
    final result directly. If not provided, this function extracts those
    facts itself as part of the good-to-have call, exactly as before —
    fully backward compatible either way.
    """
    essential = [s for s in jd_requirements.get("essential", []) if s][:15]
    good_to_have = [s for s in jd_requirements.get("good_to_have", []) if s][:10]

    if not essential and not good_to_have:
        return _fallback_candidate_strengths(resume_text, jd_requirements)

    hint_block = ""
    if known_terms_hint:
        hint_block = (
            "\n\nFor consistency with previous extractions on this platform, here are skill "
            "terms commonly seen before — if the resume clearly demonstrates one of these, use "
            "the SAME wording rather than a slightly different phrasing (only apply ones that "
            "genuinely fit; do not force-fit unrelated terms):\n"
            + ", ".join(known_terms_hint[:30])
        )

    async def _race_for(build_prompt, parse_result, call_groq_key, call_groq_model):
        """Races Ollama vs Groq (whichever configured) for a single prompt/
        parse pair, with Groq's 413-retry sequence built in.

        Returns (result_or_None, is_rate_limit_failure: bool).

        Deliberately does NOT touch the database at all — this function
        runs concurrently with OTHER chunks via asyncio.gather, sharing
        the same DB session, and SQLAlchemy's AsyncSession isn't safe to
        use concurrently across tasks. An earlier version of this
        function tried to rotate to a different pool key internally on a
        rate limit, which meant committing to the DB from inside the
        concurrent gather — confirmed directly via a real
        IllegalStateChangeError in testing. Rotation now happens at the
        OUTER, sequential level instead (see the retry-round logic below,
        after this gather completes) — this function just reports
        whether a rate limit was the cause, so the caller can decide."""
        def _try_ollama() -> Optional[dict]:
            ollama_mdl = ollama_model or "llama3"
            raw = _call_ollama(build_prompt(OLLAMA_DOC_CHARS), ollama_base_url, ollama_mdl)
            return parse_result(_parse_json_response(raw))

        def _try_groq() -> Optional[dict]:
            from langchain_groq import ChatGroq
            from langchain.schema import HumanMessage

            limit = MAX_DOC_CHARS
            last_error = None
            for _attempt in range(4):
                try:
                    llm = ChatGroq(api_key=call_groq_key, model=call_groq_model, temperature=0, max_tokens=2000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)
                    _t0 = time.time()
                    print(f"  TIMING: extract_candidate_strengths chunk attempting Groq call ({call_groq_model}, key {_mask_key_for_log(call_groq_key)})")
                    resp = llm.invoke([HumanMessage(content=build_prompt(limit))])
                    _elapsed = time.time() - _t0
                    print(f"  TIMING: extract_candidate_strengths chunk Groq call ({call_groq_model}, key {_mask_key_for_log(call_groq_key)}) took {_elapsed:.2f}s, prompt size {limit} chars")
                    return parse_result(_parse_json_response(resp.content))
                except Exception as e:
                    last_error = e
                    if _is_token_limit_error(e):
                        new_limit = _safe_retry_chars(e, limit)
                        if new_limit:
                            limit = new_limit
                            continue
                    raise
            if last_error:
                raise last_error
            return None

        attempts = {}
        if ollama_base_url:
            attempts["ollama"] = _try_ollama
        if call_groq_key:
            attempts["groq"] = _try_groq
        if not attempts:
            return None, False
        outcome = await _run_in_llm_pool(race_llm_providers, attempts)
        return outcome["result"], outcome["is_rate_limit_failure"]

    async def _verdict_chunk(items: list, call_groq_key, call_groq_model) -> Optional[list]:
        """Returns a list of booleans (one per item, in order), or None on
        total failure for this chunk."""
        if not items:
            return [], False
        block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(items))

        def _build(resume_limit: int) -> str:
            return f"""You are an expert recruiter. For EACH numbered requirement below, judge
whether the resume provides genuine evidence for it — reading for meaning
and equivalent experience, not exact wording. A requirement may be a
specific skill ("Data Modeling") or a broad capability statement — judge
both the same way: does the resume's actual content support this, even if
described using different terms or a more specific technique? For
example, a resume mentioning "Dimensional Modeling", "Data Vault", or
"Star Schema design" DOES satisfy a requirement for "Data Modeling".
{hint_block}

REQUIREMENTS:
{block}

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text", resume_limit)}\"\"\"

Return ONLY valid JSON, no markdown, no commentary — a flat array of
exactly {len(items)} booleans, one per requirement above, IN THE SAME ORDER:
{{"matched": [true, false, true]}}"""

        def _parse(data: dict) -> Optional[list]:
            if not data or data.get("matched") is None:
                return None
            v = data.get("matched") or []
            return [bool(v[i]) if i < len(v) else False for i in range(len(items))]

        return await _race_for(_build, _parse, call_groq_key, call_groq_model)

    async def _good_to_have_and_skills(call_groq_key, call_groq_model) -> Optional[dict]:
        """One lighter call: good-to-have verdicts (fewer, usually simpler
        items), plus — ONLY if pre_extracted_facts wasn't already supplied
        by the caller — the resume-level skills/experience/education
        extraction that doesn't need per-item judgment. When facts ARE
        already available (extracted concurrently with JD categorization
        by the caller, see extract_resume_facts), this becomes JUST the
        good-to-have judgment: a noticeably lighter, faster prompt, since
        it no longer needs to also generate 8 extra fields of resume
        analysis it already has the answer to."""
        good_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(good_to_have)) or "(none)"

        def _build(resume_limit: int) -> str:
            gth_instructions = (
                f'"good_to_have_matched" must be a flat array of exactly {len(good_to_have)} '
                f"booleans, one per good-to-have requirement below, in the same order:\n\n"
                f"GOOD-TO-HAVE REQUIREMENTS:\n{good_block}\n\n"
                if good_to_have else ""
            )
            if pre_extracted_facts is not None:
                return f"""You are an expert recruiter reading a resume. {gth_instructions}
{hint_block}

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text", resume_limit)}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
  "good_to_have_matched": [true, false]
}}"""
            return f"""You are an expert recruiter reading a resume. {gth_instructions}
Also extract the following from the resume itself (not tied to any
specific requirement):
{hint_block}

RESUME:
\"\"\"{_truncate_for_llm(resume_text, "resume text", resume_limit)}\"\"\"

Return ONLY valid JSON, no markdown, no commentary:
{{
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

        def _parse(data: dict) -> Optional[dict]:
            if not data:
                return None
            return data

        return await _race_for(_build, _parse, call_groq_key, call_groq_model)

    # Chunk size raised from 8 to 15 (matching the essential-items cap)
    # after direct evidence this session: 3 concurrent chunks each resend
    # the FULL resume text, and for an account with a tight TPM (tokens
    # per minute) budget, that redundant volume — not just request count —
    # was enough to blow through the limit in under a second, on BOTH the
    # original attempt and the retry. Chunking still helps by running
    # good-to-have/skills extraction CONCURRENTLY rather than sequentially
    # bundled with essential judgment, but splitting essential ITSELF into
    # multiple pieces was adding token volume for comparatively little
    # latency benefit, at real cost to reliability on tighter accounts.
    # With this size, a typical (<=15) essential list becomes exactly ONE
    # chunk rather than 2-3 — cutting concurrent Groq calls for a typical
    # analysis from 3 down to 2, meaningfully reducing burst token volume.
    ESSENTIAL_CHUNK_SIZE = 15
    essential_chunks = [
        essential[i:i + ESSENTIAL_CHUNK_SIZE]
        for i in range(0, len(essential), ESSENTIAL_CHUNK_SIZE)
    ] or [[]]

    # Resolve a key for each concurrent piece of work SEQUENTIALLY, before
    # any of the actual (slow) LLM calls are dispatched — key resolution
    # is a DB read/write, and SQLAlchemy's AsyncSession isn't safe to use
    # concurrently across multiple tasks sharing the same session. Doing
    # every DB touch up front, one at a time, then running only the LLM
    # calls themselves concurrently, avoids that entirely while still
    # letting each chunk draw a DIFFERENT pool key for real parallel
    # throughput on a single request.
    num_slots = len(essential_chunks) + 1  # + 1 for the good-to-have/skills call
    resolved_keys: list = []
    for _ in range(num_slots):
        if db is not None and user_id is not None:
            from utils.groq_pool import resolve_groq_key
            kr = await resolve_groq_key(db, user_id)
            resolved_keys.append((kr["groq_key"], kr["model"] or groq_model, kr["pool_id"] if kr["source"] == "pool" else None))
        else:
            resolved_keys.append((groq_key, groq_model, None))

    _t0 = time.time()
    round1_results = await asyncio.gather(
        *[_verdict_chunk(chunk, resolved_keys[i][0], resolved_keys[i][1]) for i, chunk in enumerate(essential_chunks)],
        _good_to_have_and_skills(resolved_keys[-1][0], resolved_keys[-1][1]),
    )
    print(f"  TIMING: extract_candidate_strengths round 1 (chunked, concurrent) {time.time() - _t0:.2f}s")

    final_results = list(round1_results)
    final_keys_used = [rk[0] for rk in resolved_keys]

    if db is not None and user_id is not None:
        from utils.groq_pool import record_key_outcome, resolve_groq_key

        # Sequentially report every pool-sourced slot's round-1 outcome —
        # safe here since the concurrent gather has already completed.
        for i, (result, _is_rl) in enumerate(round1_results):
            pool_id = resolved_keys[i][2]
            if pool_id is not None:
                await record_key_outcome(db, pool_id, success=(result is not None))

        # Retry, with a FRESH key, any slot that failed specifically due
        # to a rate limit — the key itself is fine, just temporarily
        # throttled, and having just marked it cooling down above,
        # resolve_groq_key will naturally offer a genuinely different key
        # if the pool has one, rather than the identical key that just
        # failed. This is the actual fix for a confirmed real bug: a
        # production log showed the SAME key being retried three times
        # against the same rate limit, never once trying a different pool
        # key, even though the whole point of a multi-key pool is to
        # route around exactly this.
        retry_assignments = {}
        for i, (result, is_rl) in enumerate(round1_results):
            if result is None and is_rl:
                kr = await resolve_groq_key(db, user_id)
                if kr["groq_key"] and kr["key_preview"] != _mask_key_for_log(resolved_keys[i][0]):
                    retry_assignments[i] = kr
                    print(f"  WARNING: extract_candidate_strengths slot {i} — key {_mask_key_for_log(resolved_keys[i][0])} was rate-limited, retrying with a different pool key {kr['key_preview']} instead of hammering the same one")
                elif kr["groq_key"]:
                    print(f"  WARNING: extract_candidate_strengths slot {i} — key {_mask_key_for_log(resolved_keys[i][0])} was rate-limited, but no other key is currently available (pool exhausted or only one key configured) — not retrying")

        if retry_assignments:
            async def _retry_one(i):
                kr = retry_assignments[i]
                key, model = kr["groq_key"], kr["model"] or groq_model
                if i < len(essential_chunks):
                    result, is_rl = await _verdict_chunk(essential_chunks[i], key, model)
                else:
                    result, is_rl = await _good_to_have_and_skills(key, model)
                return i, result, is_rl

            _t1 = time.time()
            retry_outcomes = await asyncio.gather(*[_retry_one(i) for i in retry_assignments])
            print(f"  TIMING: extract_candidate_strengths retry round (chunked, concurrent) {time.time() - _t1:.2f}s")

            # Sequentially report retry outcomes too — again, safe here
            # since this retry gather has also already completed.
            for i, result, _is_rl in retry_outcomes:
                final_results[i] = (result, _is_rl)
                kr = retry_assignments[i]
                final_keys_used[i] = kr["groq_key"]
                if kr["pool_id"] is not None:
                    await record_key_outcome(db, kr["pool_id"], success=(result is not None))

    # Clear, single-line summary of every DISTINCT key this analysis
    # actually drew from — built from the FINAL key each slot actually
    # used, including any that were rotated to a different key after a
    # rate limit. Since chunking can genuinely span multiple pool keys,
    # piecing that together from scattered per-chunk log lines isn't
    # practical — this is the line to look for when you need "which
    # account(s) actually served this specific request".
    distinct_key_previews = sorted(set(_mask_key_for_log(k) for k in final_keys_used if k))
    print(f"  SUMMARY: extract_candidate_strengths used {len(distinct_key_previews)} distinct key(s): {', '.join(distinct_key_previews) if distinct_key_previews else '(none)'}")

    essential_chunk_verdicts = [r[0] for r in final_results[:-1]]
    gth_and_skills = final_results[-1][0]

    if gth_and_skills is None or any(v is None for v in essential_chunk_verdicts):
        print("  WARNING: extract_candidate_strengths — one or more concurrent chunks failed, falling back to keyword heuristic")
        return _fallback_candidate_strengths(resume_text, jd_requirements)

    ev: list = []
    for chunk_verdicts in essential_chunk_verdicts:
        ev.extend(chunk_verdicts)

    essential_matched = [r for i, r in enumerate(essential) if i < len(ev) and ev[i]]
    essential_missing = [r for i, r in enumerate(essential) if not (i < len(ev) and ev[i])]
    gv = gth_and_skills.get("good_to_have_matched") or []
    good_matched = [r for i, r in enumerate(good_to_have) if i < len(gv) and gv[i]]

    # Facts come from pre_extracted_facts if the caller already ran
    # extract_resume_facts concurrently with JD categorization; otherwise
    # from this same gth_and_skills call, exactly as before.
    facts_source = pre_extracted_facts if pre_extracted_facts is not None else gth_and_skills

    return {
        "essential_matched": essential_matched[:15],
        "essential_missing": essential_missing[:15],
        "good_to_have_matched": good_matched[:10],
        "technical_skills": [s for s in facts_source.get("technical_skills", []) if s][:10],
        "business_skills": [s for s in facts_source.get("business_skills", []) if s][:8],
        "soft_skills": [s for s in facts_source.get("soft_skills", []) if s][:8],
        "significant_experience": [s for s in facts_source.get("significant_experience", []) if s][:6],
        "certifications_degrees": [s for s in facts_source.get("certifications_degrees", []) if s][:8],
        "gaps": essential_missing[:10],
        "summary": (facts_source.get("summary") or "").strip(),
        "years_experience": int(facts_source.get("years_experience") or 0),
        "education": _clean_field(facts_source.get("education")),
        "ai_powered": True,
        "_groqKeyPreviews": distinct_key_previews,
    }


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

            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0, max_tokens=4000, reasoning_format="hidden", reasoning_effort="low", max_retries=0)
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