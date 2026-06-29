"""
TalentIQ - LinkLens Browser Runner
Uses the EXACT same login/search/download logic as the working LinkLens Agent.
Runs as a separate subprocess so Chrome opens visibly on Windows desktop.
Outputs JSON lines to stdout for the parent process to read.
"""
import sys
import json
import time
import re
import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse


def emit(msg: str):
    print(json.dumps({"kind": "status", "msg": msg}), flush=True)

def emit_result(data):
    print(json.dumps({"kind": "result", "data": data}), flush=True)

def emit_done():
    print(json.dumps({"kind": "done"}), flush=True)


# ── LOCATION RESOLVER (from working linkedin_search.py) ──────────────────────

def load_location_data(data_dir: Path) -> dict:
    loc_file = data_dir / "linkedin" / "location.json"
    if not loc_file.exists():
        return {}
    with open(loc_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        k.strip().lower(): {
            "country_geoUrn": v["country_geoUrn"],
            "cities": {c.strip().lower(): u for c, u in v.get("cities", {}).items()},
        }
        for k, v in raw.items()
    }


def resolve_geourn(location_data: dict, country: str, city: str) -> str | None:
    country_data = location_data.get(country.strip().lower())
    if not country_data:
        return None
    city_key = (city or "").strip().lower()
    if city_key and city_key != "all":
        urn = country_data["cities"].get(city_key)
        if urn:
            return urn
    return country_data.get("country_geoUrn")


def build_search_urls(keywords: str, pages: int, geourn: str | None) -> list:
    encoded = quote_plus(keywords)
    urls = []
    for p in range(1, pages + 1):
        url = (
            "https://www.linkedin.com/search/results/people/"
            f"?keywords={encoded}&origin=CLUSTER_EXPANSION"
        )
        if geourn:
            url += f"&geoUrn=%5B%22{geourn}%22%5D"
        url += f"&page={p}&spellCorrectionEnabled=true"
        urls.append(url)
    return urls


# ── MAIN RUN ─────────────────────────────────────────────────────────────────

def run(params: dict):
    from playwright.sync_api import sync_playwright

    email       = params["email"]
    password    = params["password"]
    job_title   = params["job_title"]
    country     = params.get("country", "Australia")
    city        = params.get("city", "All")
    skills      = params.get("skills", "")
    max_results = int(params.get("max_results", 25))
    headless    = bool(params.get("headless", False))
    data_dir    = Path(params.get("data_dir", "data"))

    TEMP_DIR    = data_dir / "temp"
    SESSION_DIR = data_dir / "linkedin" / email
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    state_file  = SESSION_DIR / "state.json"

    location_data = load_location_data(data_dir)

    emit(f"🌐 Launching {'headless' if headless else 'visible'} Chrome browser...")

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)

    try:
        # ── LOGIN (exact same logic as working linkedin_login.py) ──────────
        context = None
        page = None
        logged_in = False

        # Try saved session first
        if state_file.exists():
            emit(f"🔄 Loading saved session for {email}...")
            context = browser.new_context(storage_state=str(state_file))
            page = context.new_page()
            page.goto("https://www.linkedin.com/feed/")
            time.sleep(3)
            if "feed" in page.url or "/in/" in page.url:
                logged_in = True
                emit("✅ Reused saved session — skipping login")

        # Fresh login if session invalid
        if not logged_in:
            if context:
                context.close()
            emit(f"🔐 Logging in as {email}...")
            context = browser.new_context()
            page = context.new_page()

            page.goto("https://www.linkedin.com/login")
            time.sleep(2)

            page.fill("input#username", email)
            page.fill("input#password", password)
            page.click("button[type=submit]")
            time.sleep(5)

            current_url = page.url
            emit(f"   URL after login: {current_url[:80]}")

            if "feed" in current_url or "/in/" in current_url:
                logged_in = True
                emit("✅ Logged in successfully!")
                context.storage_state(path=str(state_file))
                emit("💾 Session saved for future reuse")
            elif any(x in current_url for x in ["checkpoint", "challenge", "verification"]):
                emit("⚠️ LinkedIn security check — complete it in the browser window!")
                emit("⏳ Waiting up to 3 minutes...")
                for _ in range(90):
                    time.sleep(2)
                    if "feed" in page.url:
                        logged_in = True
                        emit("✅ Verified!")
                        context.storage_state(path=str(state_file))
                        break
                if not logged_in:
                    emit("❌ Verification timed out.")
                    return
            else:
                emit(f"❌ Login failed. URL: {current_url}")
                emit("   Check your LinkedIn credentials in Settings → API Keys → LinkedIn")
                return

        if not logged_in:
            emit("❌ Could not log in. Aborting.")
            return

        # ── SEARCH (exact same logic as working linkedin_search.py) ────────
        keywords = job_title.strip()
        if skills.strip():
            keywords += " " + skills.strip()

        emit(f"🔍 Keywords: {keywords}")

        geourn = resolve_geourn(location_data, country, city)
        if geourn:
            emit(f"📍 Location: {city}, {country} (geoUrn: {geourn})")
        else:
            emit(f"📍 Location: {country} (no geoUrn found, searching globally)")

        pages_needed = max(1, (max_results // 10) + 1)
        search_urls  = build_search_urls(keywords, pages_needed, geourn)

        profile_links = []

        for idx, search_url in enumerate(search_urls, 1):
            if len(profile_links) >= max_results:
                break

            emit(f"➡️ Scraping search page {idx}/{len(search_urls)}")

            # Exact retry logic from working code
            try:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            except Exception:
                emit(f"⚠️ Slow load on page {idx}, retrying...")
                time.sleep(5)
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")

            page.wait_for_selector('a[href*="/in/"]', timeout=45000)

            for _ in range(5):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(2000)

            anchors = page.locator('a[href*="/in/"]').all()
            new_this_page = 0
            for a in anchors:
                href = a.get_attribute("href")
                text = a.inner_text().strip() if a.inner_text() else ""
                if (
                    href and text
                    and ("• 1st" in text or "• 2nd" in text or "• 3rd" in text)
                    and "/search/" not in href
                ):
                    clean = href.split("?")[0]
                    if clean not in profile_links:
                        profile_links.append(clean)
                        new_this_page += 1
                        if len(profile_links) >= max_results:
                            break

            emit(f"   +{new_this_page} links (total: {len(profile_links)})")

        emit(f"✅ Collected {len(profile_links)} profile links")

        # ── DOWNLOAD PROFILES (exact same logic as working linkedin_html.py) ─
        for f in TEMP_DIR.glob("*.html"):
            f.unlink(missing_ok=True)

        saved = []
        for idx, link in enumerate(profile_links, 1):
            emit(f"📥 [{idx}/{len(profile_links)}] {link}")

            content = None
            for attempt in range(2):
                try:
                    page.goto(link, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(2000)
                    content = page.content()
                    if not content or len(content) < 500:
                        raise Exception("Content too short")
                    break
                except Exception as e:
                    if attempt == 0:
                        emit(f"   ⚠️ Slow load, retrying...")
                        time.sleep(5)
                    else:
                        emit(f"   ❌ Failed: {e}")

            if not content:
                continue

            parsed = urlparse(link)
            slug = parsed.path.strip("/").split("/")[-1] or "profile"
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
            fname = TEMP_DIR / f"{slug}_{int(time.time())}.html"
            fname.write_text(content, encoding="utf-8")
            saved.append(fname)
            emit(f"   💾 Saved: {fname.name}")

        emit(f"💾 {len(saved)} HTML files saved")

    finally:
        try:
            browser.close()
            playwright.stop()
        except Exception:
            pass

    emit("🧠 Parsing profiles...")

    # ── PARSE ────────────────────────────────────────────────────────────────
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.linklens_agent import parse_all_profiles

    results = parse_all_profiles(
        html_folder=str(TEMP_DIR),
        role_query=job_title,
        loc_query=f"{city}, {country}" if city and city.lower() != "all" else country,
        status_cb=lambda m: emit(m),
    )

    emit_result(results)
    emit_done()


if __name__ == "__main__":
    params = json.loads(sys.argv[1])
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    run(params)