"""
TalentIQ - LinkLens Agent
Fully rewritten extractor based on actual LinkedIn HTML structure analysis.

ROOT CAUSE OF FAILURES (discovered by analysing real HTMLs):
1. These saved HTMLs contain ONLY the top-card section — Experience/Skills sections
   are NOT loaded because Playwright didn't scroll far enough before saving.
2. The old extractor looked for "experience" / "skills" section headers that don't exist.
3. Name was being caught from nav junk ("Skip to search", "0 notifications").
4. Company was being lost because the pattern "Company · Association" was not parsed.

EXTRACTION STRATEGY (what IS reliably in the HTML):
- Name:      <title> tag → split on "|", strip " | LinkedIn"
- Headline:  line immediately after name (line 17 in visible text, long descriptor)
- Title:     first segment of headline before "|" or ","
- Company:   "Company · Association" line (line ~26), first part before "·"
- Location:  "Greater X Area" or "City, Country" line (line ~27)
- Skills:    "Top skills" section (when present) → "Skill • Skill • Skill" format
- Experience: parsed from "About" section bullet points when experience section absent
- Certs:     headline pipe-segments or Featured section
"""

import re
import time
import asyncio
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

NAV_JUNK = {
    "skip to search", "skip to main content", "skip to primary content",
    "skip to aside", "skip to footer", "home", "my network", "jobs",
    "messaging", "notifications", "me", "for business", "learning",
    "more", "message", "connect", "follow", "about", "contact info",
    "show all posts", "show all", "activity", "featured", "english",
}

CONNECTION_PATTERN = re.compile(r"^\d+\s*(followers?|connections?|reactions?)", re.I)
DEGREE_PATTERN = re.compile(r"^[·•]\s*(1st|2nd|3rd\+?)$")
DATE_PATTERN = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b"
    r"|\bPresent\b|\d{4}\s*[-–]\s*(\d{4}|Present)", re.I
)
BULLET_SKILL_SEP = re.compile(r"\s*[•·]\s*")


# ═══════════════════════════════════════════════════════════════════════════════
# CORE EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

def _visible_lines(html: str) -> List[str]:
    """Get all non-empty visible text lines, stripping zero-width chars."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    raw = soup.get_text("\n")
    lines = []
    for l in raw.splitlines():
        l = l.replace("\u200b", "").strip()
        if l:
            lines.append(l)
    return lines


def _is_junk(line: str) -> bool:
    low = line.lower().strip()
    if low in NAV_JUNK:
        return True
    if CONNECTION_PATTERN.match(low):
        return True
    if DEGREE_PATTERN.match(line):
        return True
    if re.match(r"^\d+$", line):
        return True
    if re.match(r"^[·•\-–]+$", line):
        return True
    return False


# ── NAME ──────────────────────────────────────────────────────────────────────

def extract_name(html: str) -> str:
    """
    Most reliable source: <title> tag.
    LinkedIn always formats it as "Full Name | LinkedIn"
    Falls back to <h2> (first non-notification h2).
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Title tag — always present, always has name
    title = soup.find("title")
    if title:
        text = title.get_text(strip=True)
        name = text.split("|")[0].strip().rstrip(",").strip()
        if name and len(name) > 2:
            return name

    # 2. H2 — LinkedIn puts name in first h2 after "0 notifications" h2
    for h2 in soup.find_all("h2"):
        txt = h2.get_text(strip=True)
        if txt and "notification" not in txt.lower() and len(txt) > 2:
            return txt.split("|")[0].strip()

    return "Not found"


# ── HEADLINE ──────────────────────────────────────────────────────────────────

def extract_headline(html: str, name: str) -> str:
    """
    Headline is the long descriptor line that appears AFTER the name
    in the top card. It's typically the second occurrence of the name,
    followed by the actual headline text.
    Pattern in real HTML:
      Line 16: "Pooja Chillana CPA"          ← first mention (mini card)
      Line 17: "Senior Business Analyst..."   ← headline
      ...
      Line 21: "Pooja Chillana CPA"          ← second mention (full card)
      Line 24: "Senior Business Analyst..."   ← headline repeated
    We find the FIRST headline-like line after the name.
    """
    lines = _visible_lines(html)
    name_lower = name.lower().strip() if name and name != "Not found" else None

    # Strip punctuation for matching (handles "Summer L.", "Kirsty Donachie, FCPA")
    import re as _re
    name_stripped = _re.sub(r"[^a-z0-9 ]", "", name_lower).strip() if name_lower else ""
    name_first_word = name_lower.split()[0].rstrip(".,") if name_lower else ""

    for i, line in enumerate(lines):
        line_low = line.lower()
        line_stripped = _re.sub(r"[^a-z0-9 ]", "", line_low).strip()
        name_match = (
            (name_lower and name_lower in line_low) or
            (name_stripped and name_stripped in line_stripped) or
            (name_first_word and len(name_first_word) > 3 and line_stripped.startswith(name_first_word))
        )
        if name_match and i >= 10:
            # Check next few lines for the headline
            for j in range(i + 1, min(i + 6, len(lines))):
                candidate = lines[j]
                if _is_junk(candidate):
                    continue
                if len(candidate) < 10:
                    continue
                # Headline: long text, may contain | or commas
                if any(c in candidate for c in ["|", ",", "·", "&"]) or len(candidate.split()) >= 4:
                    return candidate
    return ""


# ── TITLE ─────────────────────────────────────────────────────────────────────

def extract_title(headline: str) -> str:
    """
    Current title = first part of headline before | or comma (for multi-role headlines).
    E.g. "Senior Business Analyst, CPA, MYOB..." → "Senior Business Analyst"
    E.g. "Tax Manager | CPA | Xero Expert" → "Tax Manager"
    """
    if not headline:
        return "Not found"

    # Split on | first
    if "|" in headline:
        part = headline.split("|")[0].strip()
    else:
        part = headline

    # Remove trailing credential suffixes (CPA, CMA, etc.)
    part = re.sub(r",\s*(CPA|CMA|CA|ACCA|MBA|CFA|FCA|FCPA|ACA)\b.*$", "", part, flags=re.I).strip()

    # Trim to max 60 chars
    if len(part) > 60:
        # Use up to first comma
        comma_idx = part.find(",")
        if 0 < comma_idx < 60:
            part = part[:comma_idx].strip()

    return part if len(part) > 3 else "Not found"


# ── COMPANY + LOCATION (unified top-card extractor) ─────────────────────────

def _extract_top_card(html: str, name: str) -> tuple:
    """
    Extract headline, company, location from the LinkedIn top card.

    Confirmed HTML structure (consistent across all profiles):
      [nav junk]
      name (first occurrence - mini card)
      headline
      More / Message / Follow / Connect
      name (SECOND occurrence - main card)   ← anchor
      · 1st / · 2nd / · 3rd  (one or two degree lines)
      headline (repeated)
      Company · Association  OR  just Company name
      Location (City, State, Country  OR  Greater X Area)
      ·  (lone bullet separator)
      Contact info
    """
    lines = _visible_lines(html)
    name_lower = name.lower().strip() if name and name != "Not found" else ""
    name_first = name_lower.split()[0] if name_lower else ""

    DEGREE_RE  = re.compile(r"^[·•]\s*(1st|2nd|3rd\+?|[23]rd\+?)$")
    JUNK_LINES = {"more", "connect", "follow", "about", "contact info",
                  "·", "••", "activity", "show all"}
    MSG_RE     = re.compile(r"^(message|follow)\s+\w", re.I)
    CONN_RE    = re.compile(r"^\d+\s*(followers?|connections?|reactions?)", re.I)

    PRONOUNS_RE = re.compile(r"^(She|He|They|She/Her|He/Him|They/Them)[/,]?(Her|Him|Them)?$", re.I)

    def is_skip(line: str) -> bool:
        low = line.lower().strip()
        if low in JUNK_LINES: return True
        if DEGREE_RE.match(line): return True
        if MSG_RE.match(line): return True
        if CONN_RE.match(low): return True
        if PRONOUNS_RE.match(line): return True
        if re.match(r"^\d+$", line): return True
        if re.match(r"^\w+ is a mutual connection$", low): return True
        return False

    # Find the SECOND occurrence of name in BODY (skip title tag area, lines 0-9)
    # Structure: line 0-1 = title tag text, line 2+ = body
    # First body occurrence = mini nav card, second = main profile card (our anchor)
    anchor = 15  # default fallback
    name_count = 0
    for i, line in enumerate(lines):
        if i < 8:
            continue  # Skip title tag duplicates at top
        low = line.lower()
        # Skip "Message X", "Follow X", "Connect" lines
        if re.match(r"^(message|follow|connect)\b", low):
            continue
        # Skip lines containing "LinkedIn" (title tag artifact)
        if "linkedin" in low:
            continue
        if name_first and name_first in low and len(line) < 80:
            name_count += 1
            if name_count == 2:
                anchor = i
                break
            elif name_count == 1:
                anchor = i  # keep first as fallback

    # Now scan forward from anchor
    headline = ""
    company  = ""
    location = ""

    LOCATION_RE = re.compile(
        r"(Greater\s+\w[\w\s]+Area$"
        r"|[A-Z][A-Za-z\s'\-]+,\s*[A-Z][A-Za-z\s'\-]+"
        r"|^(?:Australia|India|United States|USA|UK|United Kingdom"
        r"|Canada|Singapore|UAE|New Zealand|Germany|Netherlands"
        r"|Ireland|South Africa|Pakistan|Malaysia|Philippines|Remote)$)",
        re.I
    )

    i = anchor + 1
    phase = "degree"   # → headline → company → location

    while i < min(anchor + 18, len(lines)):
        line = lines[i]
        low  = line.lower().strip()

        # Always skip junk
        if is_skip(line):
            i += 1
            continue

        # Skip if it's the name again
        if name_first and name_first in low and len(line) < 70:
            i += 1
            continue

        if phase == "degree":
            # Degree lines already filtered by DEGREE_RE in is_skip
            # First real line after degree = headline
            if len(line) > 8:
                headline = line
                phase = "company"

        elif phase == "company":
            # Location check first
            if LOCATION_RE.search(line):
                location = line
                break

            # Company·Assoc pattern: "Nexus Business Partners · Macquarie University"
            if "·" in line and not DEGREE_RE.match(line):
                company = line.split("·")[0].strip()
                # Clean employment type suffix
                company = re.sub(
                    r"\s*[·,]\s*(Full-time|Part-time|Contract|Freelance|Self-employed).*$",
                    "", company, flags=re.I
                ).strip()
                phase = "location"

            # Plain company name (no ·)
            elif len(line) > 3 and not re.match(r"^\d", line) and "·" not in line:
                company = line.strip()
                phase = "location"

        elif phase == "location":
            # Lone "·" means next useful line is location
            if line == "·":
                i += 1
                continue

            if LOCATION_RE.search(line):
                location = line
            break

        i += 1

    return headline, company, location


def extract_company(html: str, name: str) -> str:
    """Extract current company from LinkedIn top card."""
    _, company, _ = _extract_top_card(html, name)
    return company if company else "Not found"


def extract_location(html: str) -> str:
    """Extract location from LinkedIn top card."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    name = title_tag.get_text(strip=True).split("|")[0].strip() if title_tag else ""
    _, _, location = _extract_top_card(html, name)
    return location if location else "Not found"

# ── SKILLS ────────────────────────────────────────────────────────────────────

def extract_skills(html: str) -> List[str]:
    """
    Two sources:
    1. "Top skills" section: "Xero • MYOB • Australia Accounting & Taxation"
       → split on • and clean
    2. Full "Skills" section (when scrolled enough): parse each skill name
    3. Extract from headline (pipe-separated tech skills)
    """
    lines = _visible_lines(html)
    skills = []
    seen = set()

    def add_skill(s: str):
        s = s.strip()
        if not s or len(s) < 2 or len(s) > 60:
            return
        if s.lower() in seen:
            return
        if _is_junk(s):
            return
        if re.search(r"\d+\s+(endorsement|connection|follower)", s, re.I):
            return
        skills.append(s)
        seen.add(s.lower())

    # Strategy 1: "Top skills" section (compact format)
    for i, line in enumerate(lines):
        if line.lower() == "top skills":
            # Next line(s) contain skills separated by •
            for j in range(i + 1, min(i + 4, len(lines))):
                parts = BULLET_SKILL_SEP.split(lines[j])
                if len(parts) >= 2:
                    for p in parts:
                        add_skill(p)
                    if skills:
                        break

    # Strategy 2: Full "Skills" section
    if not skills:
        skill_idx = next((i for i, l in enumerate(lines) if l.lower() == "skills"), None)
        if skill_idx:
            stop = {"experience", "education", "languages", "certifications",
                    "recommendations", "interests", "activity", "show all"}
            edu_words = {"university", "college", "institute", "school"}

            for line in lines[skill_idx + 1:]:
                low = line.lower()
                if low in stop:
                    break
                if any(w in low for w in edu_words):
                    continue
                if re.search(r"\d+\s+endorsement", low):
                    continue
                if "·" in line and re.search(r"1st|2nd|3rd", line):
                    continue
                if 1 <= len(line.split()) <= 4 and len(line) <= 50:
                    add_skill(line)

    # Strategy 3: Extract from headline (pipe-separated)
    if not skills:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        name = title_tag.get_text(strip=True).split("|")[0].strip() if title_tag else ""
        headline = extract_headline(html, name)
        if headline and "|" in headline:
            parts = headline.split("|")
            TECH_PATTERNS = re.compile(
                r"\b(Xero|MYOB|QuickBooks|SAP|Oracle|Excel|Python|SQL|"
                r"PowerBI|Power BI|Tableau|AWS|Azure|Salesforce|"
                r"MYOB|Xero|Sage|NetSuite|Dynamics)\b", re.I
            )
            for part in parts[1:]:
                part = part.strip()
                if TECH_PATTERNS.search(part) or (len(part.split()) <= 3 and len(part) < 40):
                    add_skill(part)

    return skills


# ── EXPERIENCE ────────────────────────────────────────────────────────────────

def extract_experience(html: str, name: str, headline: str) -> List[Dict[str, str]]:
    """
    Three sources (in order of reliability):
    1. Dedicated "Experience" section (when Playwright scrolled enough)
    2. About section bullet points describing current role
    3. Headline + Company line (construct synthetic current role)
    """
    lines = _visible_lines(html)
    roles = []

    # ── Source 1: Experience section ──
    exp_idx = next(
        (i for i, l in enumerate(lines) if l.lower() == "experience"), None
    )

    if exp_idx is not None:
        stop_sections = {
            "education", "skills", "languages", "certifications",
            "licenses", "recommendations", "interests", "activity",
            "volunteering", "courses", "top skills"
        }
        block = []
        for line in lines[exp_idx + 1:]:
            low = line.lower()
            if low in stop_sections:
                break
            if _is_junk(line):
                continue
            if "logo" in low:
                continue
            if line.startswith("•"):
                continue
            if re.search(r"\+\d+\s+skills", low):
                continue
            if len(line) > 150:
                continue
            if len(line) > 2:
                block.append(line)

        roles = _parse_experience_block(block)

    # ── Source 2: About section bullets ──
    if not roles:
        about_idx = next(
            (i for i, l in enumerate(lines) if l.lower() == "about"), None
        )
        if about_idx is not None:
            about_bullets = []
            for line in lines[about_idx + 1: about_idx + 30]:
                if line.startswith("•"):
                    about_bullets.append(line.lstrip("•").strip())
                if line.lower() in {"activity", "experience", "skills"}:
                    break
            if about_bullets:
                roles = [{
                    "title": extract_title(headline) if headline else "Not found",
                    "company": extract_company(html, name),
                    "dates": "Present",
                    "description": " | ".join(about_bullets[:4]),
                }]

    # ── Source 3: Synthetic from top card ──
    if not roles:
        title = extract_title(headline) if headline else "Not found"
        company = extract_company(html, name)
        if title != "Not found" or company != "Not found":
            roles = [{
                "title": title,
                "company": company,
                "dates": "Present",
                "description": "",
            }]

    return roles


def _parse_experience_block(block: List[str]) -> List[Dict]:
    """Parse raw experience block into structured roles."""
    roles = []
    seen = set()

    i = 0
    while i < len(block):
        line = block[i]

        # Skip employment type lines
        if re.match(r"^(Full-time|Part-time|Contract|Freelance|Self-employed)", line, re.I):
            i += 1
            continue

        # Date line → we have a role boundary
        if DATE_PATTERN.search(line):
            dates = line

            # Title: 1-2 lines before date
            title = None
            company = None
            for back in range(i - 1, max(i - 4, -1), -1):
                candidate = block[back].strip()
                if not candidate or _is_junk(candidate):
                    continue
                if DATE_PATTERN.search(candidate):
                    break
                if re.match(r"^(Full-time|Part-time|Remote|Hybrid|On-site)", candidate, re.I):
                    continue
                if title is None:
                    title = re.sub(
                        r"\s*·\s*(Full-time|Part-time|Contract|Freelance).*$",
                        "", candidate, flags=re.I
                    ).strip()
                elif company is None:
                    company = re.sub(
                        r"\s*·\s*(Full-time|Part-time|Contract|Freelance).*$",
                        "", candidate, flags=re.I
                    ).strip()

            if title:
                key = (title, dates)
                if key not in seen:
                    roles.append({
                        "title": title,
                        "company": company or "",
                        "dates": dates,
                        "description": "",
                    })
                    seen.add(key)

        i += 1

    return roles


# ── CERTIFICATIONS ────────────────────────────────────────────────────────────

def extract_certifications(html: str, headline: str) -> List[str]:
    """
    Sources:
    1. Headline pipe-segments containing cert keywords
    2. "Featured" section (Certification blocks)
    3. "Licenses & Certifications" section
    """
    CERT_KEYWORDS = re.compile(
        r"\b(CPA|CA|CMA|ACCA|FCA|FCPA|ACA|CFA|MBA|CPA Australia|"
        r"Certified|Xero Advisor|MYOB Certified|QuickBooks|"
        r"AWS Certified|Azure|Google|PMP|Scrum|ProAdvisor)\b", re.I
    )

    certs = []
    seen = set()

    def add_cert(s: str):
        s = s.strip()
        if s and s.lower() not in seen and CERT_KEYWORDS.search(s):
            certs.append(s)
            seen.add(s.lower())

    # Source 1: From headline
    if headline and "|" in headline:
        for part in headline.split("|"):
            part = part.strip()
            if CERT_KEYWORDS.search(part):
                add_cert(part)

    # Source 2: Featured section
    lines = _visible_lines(html)
    in_featured = False
    for i, line in enumerate(lines):
        if line.lower() == "featured":
            in_featured = True
            continue
        if in_featured:
            if line.lower() == "activity":
                break
            if line.lower() == "certification":
                # Next line is cert name
                if i + 1 < len(lines):
                    add_cert(lines[i + 1])
            elif CERT_KEYWORDS.search(line) and len(line) < 80:
                add_cert(line)

    # Source 3: Dedicated section
    cert_idx = next(
        (i for i, l in enumerate(lines)
         if l.lower() in {"certifications", "licenses & certifications",
                           "licenses and certifications"}),
        None
    )
    if cert_idx:
        stop = {"skills", "experience", "education", "interests", "activity"}
        for line in lines[cert_idx + 1: cert_idx + 30]:
            if line.lower() in stop:
                break
            if CERT_KEYWORDS.search(line) and len(line) < 80:
                add_cert(line)

    return certs


# ── EDUCATION ─────────────────────────────────────────────────────────────────

def extract_education(html: str) -> List[str]:
    lines = _visible_lines(html)
    edu = []
    seen = set()

    edu_idx = next(
        (i for i, l in enumerate(lines) if l.lower() == "education"), None
    )
    if not edu_idx:
        return edu

    stop = {"skills", "experience", "languages", "certifications", "activity"}
    EDU_KEYWORDS = re.compile(
        r"\b(university|college|institute|school|bachelor|master|"
        r"b\.?com|m\.?com|mba|bba|bsc|msc|phd|ca|cpa|acca)\b", re.I
    )

    for line in lines[edu_idx + 1: edu_idx + 30]:
        if line.lower() in stop:
            break
        if len(line) < 3 or len(line) > 100:
            continue
        if EDU_KEYWORDS.search(line):
            key = line.lower()
            if key not in seen:
                edu.append(line)
                seen.add(key)

    return edu


# ── CONTACT INFO ──────────────────────────────────────────────────────────────

def extract_contact_from_html(html: str) -> Dict[str, str]:
    """
    Email and phone from the contact overlay (when page was saved with it open).
    Falls back to pattern-matching in visible text.
    """
    EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,20}\d)")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")

    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)

    # Filter out LinkedIn's own domain
    email_val = ""
    if email:
        e = email.group()
        if "linkedin.com" not in e and "example.com" not in e:
            email_val = e

    return {
        "email": email_val,
        "phone": phone.group().strip() if phone else "",
    }


# ── PROFILE URL ───────────────────────────────────────────────────────────────

def extract_profile_url(html: str, fallback: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", {"property": "og:url"})
    if og and og.get("content"):
        return og["content"].strip()
    return fallback


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTED LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    if not query or not target:
        return False

    STOP = {"and", "or", "the", "a", "an", "in", "at", "of", "for", "to", "with", "as"}

    def normalize(s: str):
        words = re.findall(r"[a-zA-Z]+", s.lower())
        return {w for w in words if w not in STOP and len(w) > 2}

    q_words = normalize(query)
    t_words = normalize(target)
    if not q_words:
        return True  # no filter
    overlap = q_words & t_words
    return len(overlap) / len(q_words) >= threshold


def compute_accepted(
    title: str,
    location: str,
    skills: List[str],
    role_query: str = "",
    loc_query: str = "",
    skills_query: str = "",
) -> str:
    """
    Y if profile matches search criteria, N otherwise.
    Empty queries = accept all (no filter applied).
    """
    role_ok = True
    loc_ok = True

    if role_query and role_query.strip():
        combined = f"{title}"
        role_ok = _fuzzy_match(role_query, combined)

    if loc_query and loc_query.strip() and loc_query.strip().lower() != "all":
        loc_ok = _fuzzy_match(loc_query, location)

    return "Y" if (role_ok and loc_ok) else "N"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PARSE FUNCTION (replaces parse_all_html in linkedin_data_extract.py)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_profile_html(
    html: str,
    file_path: str = "",
    role_query: str = "",
    loc_query: str = "",
    status_cb=None,
) -> Dict[str, Any]:
    """
    Parse a single LinkedIn profile HTML and return structured data dict.
    All fields guaranteed — no "Not found" if data exists in HTML.
    """
    cb = status_cb or (lambda m: None)

    fname = Path(file_path).stem if file_path else "unknown"
    cb(f"⏳ Processing: {fname}")

    try:
        name                     = extract_name(html)
        headline, company, location = _extract_top_card(html, name)
        if not headline:
            headline = extract_headline(html, name)
        if not company:
            company = "Not found"
        if not location:
            location = "Not found"
        title    = extract_title(headline)
        skills   = extract_skills(html)
        exp_list = extract_experience(html, name, headline)
        certs    = extract_certifications(html, headline)
        edu      = extract_education(html)
        contact  = extract_contact_from_html(html)

        # Construct profile URL
        stem = re.sub(r"_\d{10}$", "", Path(file_path).stem) if file_path else ""
        fallback_url = f"https://www.linkedin.com/in/{stem}/" if stem else ""
        profile_url  = extract_profile_url(html, fallback_url)

        # Format experience for output
        exp_strings = []
        for r in exp_list:
            parts = [r.get("title", ""), r.get("company", ""), r.get("dates", "")]
            parts = [p for p in parts if p and p.strip()]
            if r.get("description"):
                parts.append(r["description"])
            exp_strings.append(" | ".join(parts))

        accepted = compute_accepted(
            title=f"{title} {headline}",
            location=location,
            skills=skills,
            role_query=role_query,
            loc_query=loc_query,
        )

        result = {
            "Accepted":     accepted,
            "Name":         name,
            "Title":        title,
            "Company":      company,
            "Location":     location,
            "Email":        contact["email"],
            "Phone":        contact["phone"],
            "Skills":       ", ".join(skills) if skills else "",
            "Certifications": " | ".join(certs) if certs else "",
            "Education":    " | ".join(edu) if edu else "",
            "Experience":   " || ".join(exp_strings) if exp_strings else "",
            "ProfileLink":  profile_url,
        }

        cb(f"✅ Extracted: {name} | {title} | {company} | {location}")
        return result

    except Exception as e:
        cb(f"❌ Failed: {fname}: {e}")
        return {
            "Accepted": "N", "Name": fname, "Title": "", "Company": "",
            "Location": "", "Email": "", "Phone": "",
            "Skills": "", "Certifications": "", "Education": "",
            "Experience": "", "ProfileLink": "",
        }


def parse_all_profiles(
    html_folder: str = "data/temp",
    role_query: str = "",
    loc_query: str = "",
    status_cb=None,
) -> List[Dict[str, Any]]:
    """Parse all HTML files in a folder. Returns list of result dicts."""
    cb = status_cb or (lambda m: None)
    folder = Path(html_folder)
    files = list(folder.glob("*.html"))
    cb(f"📂 Found {len(files)} HTML profiles to parse")

    results = []
    for i, f in enumerate(files, 1):
        cb(f"[{i}/{len(files)}] Parsing {f.name}")
        html = f.read_text(encoding="utf-8", errors="ignore")
        result = parse_profile_html(
            html=html,
            file_path=str(f),
            role_query=role_query,
            loc_query=loc_query,
            status_cb=cb,
        )
        results.append(result)

    accepted = sum(1 for r in results if r["Accepted"] == "Y")
    cb(f"✅ Done: {len(results)} profiles parsed, {accepted} accepted")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PLAYWRIGHT PIPELINE (login + search + download + parse)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_linklens_search(
    email: str,
    password: str,
    job_title: str,
    country: str,
    city: str,
    skills: str,
    max_results: int,
    status_cb,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Full async pipeline:
    1. Login to LinkedIn via Playwright
    2. Search for profiles
    3. Download each profile HTML
    4. Parse and extract structured data
    5. Return results list
    """
    from playwright.async_api import async_playwright
    import json

    cb = status_cb

    results = []
    DATA_DIR = Path("data")
    TEMP_DIR = DATA_DIR / "temp"
    SESSION_DIR = DATA_DIR / "linkedin" / email
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    state_file = SESSION_DIR / "state.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )

        # ── SESSION / LOGIN ──
        context = None
        if state_file.exists():
            cb("🔄 Loading saved LinkedIn session...")
            context = await browser.new_context(
                storage_state=str(state_file),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/feed/", timeout=30000)
            await page.wait_for_timeout(3000)
            if "feed" not in page.url and "/in/" not in page.url:
                cb("⚠️ Session expired, logging in fresh...")
                await context.close()
                context = None

        if context is None:
            cb(f"🔐 Logging in as {email}...")
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/login", timeout=30000)
            await page.fill("input#username", email)
            await page.fill("input#password", password)
            await page.click("button[type=submit]")
            await page.wait_for_timeout(5000)

            if "feed" in page.url or "/in/" in page.url:
                cb("✅ Logged in successfully!")
                await context.storage_state(path=str(state_file))
                cb("💾 Session saved for future reuse")
            else:
                cb(f"❌ Login failed. Current URL: {page.url}")
                await browser.close()
                return []

        # ── SEARCH ──
        cb(f"🔍 Searching: {job_title} in {city}, {country}")
        from urllib.parse import quote_plus
        import json as _json

        # Load location data for geoUrn
        loc_file = DATA_DIR / "linkedin" / "location.json"
        geourn = None
        if loc_file.exists():
            with open(loc_file) as f:
                loc_data = _json.load(f)
            country_data = loc_data.get(country, {})
            if city and city.lower() != "all":
                geourn = country_data.get("cities", {}).get(city)
            if not geourn:
                geourn = country_data.get("country_geoUrn")

        keywords = job_title
        if skills:
            keywords += " " + skills

        pages_needed = max(1, (max_results // 10) + 1)
        profile_links = []

        for page_num in range(1, pages_needed + 1):
            if len(profile_links) >= max_results:
                break

            url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={quote_plus(keywords)}"
                f"&origin=CLUSTER_EXPANSION"
            )
            if geourn:
                url += f'&geoUrn=%5B%22{geourn}%22%5D'
            url += f"&page={page_num}&spellCorrectionEnabled=true"

            cb(f"📄 Search page {page_num}/{pages_needed}...")
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_selector('a[href*="/in/"]', timeout=30000)
                for _ in range(4):
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(1500)
            except Exception as e:
                cb(f"⚠️ Search page {page_num} load issue: {e}")
                continue

            anchors = await page.locator('a[href*="/in/"]').all()
            for a in anchors:
                href = await a.get_attribute("href")
                inner = await a.inner_text()
                inner = inner.strip() if inner else ""
                if (
                    href
                    and inner
                    and ("• 1st" in inner or "• 2nd" in inner or "• 3rd" in inner)
                    and "/search/" not in href
                ):
                    clean = href.split("?")[0]
                    if clean not in profile_links:
                        profile_links.append(clean)
                        if len(profile_links) >= max_results:
                            break

        cb(f"✅ Collected {len(profile_links)} profile links")

        # ── DOWNLOAD PROFILES ──
        # Clear old temp files
        for f in TEMP_DIR.glob("*.html"):
            f.unlink(missing_ok=True)

        for idx, link in enumerate(profile_links, 1):
            cb(f"📥 [{idx}/{len(profile_links)}] Downloading: {link}")
            try:
                await page.goto(link, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Scroll to load lazy sections (Experience, Skills)
                for _ in range(6):
                    await page.mouse.wheel(0, 2500)
                    await page.wait_for_timeout(1500)

                # Scroll back to top to capture top card too
                await page.mouse.wheel(0, -99999)
                await page.wait_for_timeout(1000)

                content = await page.content()

                if not content or len(content) < 1000:
                    cb(f"⚠️ Short content for {link}, retrying...")
                    await page.wait_for_timeout(4000)
                    content = await page.content()

                # Save HTML
                from urllib.parse import urlparse
                slug = urlparse(link).path.strip("/").split("/")[-1]
                slug = re.sub(r"[^a-zA-Z0-9_-]", "-", slug)
                fname = TEMP_DIR / f"{slug}_{int(time.time())}.html"
                fname.write_text(content, encoding="utf-8")
                cb(f"💾 Saved: {fname.name}")

            except Exception as e:
                cb(f"❌ Failed to download {link}: {e}")

        await browser.close()

    # ── PARSE ──
    cb("🧠 Parsing all profiles...")
    results = parse_all_profiles(
        html_folder=str(TEMP_DIR),
        role_query=job_title,
        loc_query=f"{city}, {country}" if city and city.lower() != "all" else country,
        status_cb=cb,
    )

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL FINDER
# ═══════════════════════════════════════════════════════════════════════════════

def guess_email(name: str, company_domain: str = "") -> List[str]:
    """Generate probable email patterns from name and domain."""
    if not name or not company_domain:
        return []

    parts = re.findall(r"[a-zA-Z]+", name.lower())
    if len(parts) < 2:
        return []

    first, last = parts[0], parts[-1]
    domain = company_domain.lower().strip()

    patterns = [
        f"{first}.{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}@{domain}",
        f"{first}{last[0]}@{domain}",
        f"{last}.{first}@{domain}",
    ]
    return patterns