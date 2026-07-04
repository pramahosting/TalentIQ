"""
One-time migration: fix columns that were created as PostgreSQL ENUMs.
Converts them to plain VARCHAR so we can use string values directly.
Run once on startup via main.py lifespan.
"""
import asyncio
import sys
import os
import hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import engine
from sqlalchemy import text

MIGRATIONS = [
    # Client: location -> address rename; partnership_from removed from the
    # model (left as an orphaned column in the DB — no destructive DROP)
    "ALTER TABLE tiq_clients RENAME COLUMN location TO address",

    # Vendor: location -> address, area_of_coverage -> coverage_region
    "ALTER TABLE tiq_vendors RENAME COLUMN location TO address",
    "ALTER TABLE tiq_vendors RENAME COLUMN area_of_coverage TO coverage_region",

    # JD: uploaded JD document (Word/PDF), alongside the existing description text
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS jd_file_blob BYTEA",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS jd_file_filename VARCHAR(300)",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS jd_file_mimetype VARCHAR(100)",

    # Candidate: address + work permission status
    "ALTER TABLE tiq_tracked_candidates ADD COLUMN IF NOT EXISTS address VARCHAR(300)",
    "ALTER TABLE tiq_tracked_candidates ADD COLUMN IF NOT EXISTS work_permission VARCHAR(50)",

    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS essential_skills JSON DEFAULT '[]'",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS good_to_have_skills JSON DEFAULT '[]'",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS optional_skills JSON DEFAULT '[]'",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS min_years_experience INTEGER DEFAULT 0",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS education_requirement VARCHAR(300)",

    "ALTER TABLE tiq_job_matches ADD COLUMN IF NOT EXISTS strengths_breakdown JSON",
    "ALTER TABLE tiq_job_matches ADD COLUMN IF NOT EXISTS jd_requirements JSON",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS strengths_breakdown JSON",

    # Per-user sequential numbering (session numbers isolated per user)
    "ALTER TABLE tiq_job_searches ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_jobintel_runs ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_linklens_searches ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_cvanalysis_records ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS sequence_number INTEGER",
    "ALTER TABLE tiq_vendors ADD COLUMN IF NOT EXISTS sequence_number INTEGER",

    # Vendor Management: new profile fields
    "ALTER TABLE tiq_vendors ADD COLUMN IF NOT EXISTS location VARCHAR(300)",
    "ALTER TABLE tiq_vendors ADD COLUMN IF NOT EXISTS area_of_coverage VARCHAR(300)",
    "ALTER TABLE tiq_vendors ADD COLUMN IF NOT EXISTS technical_area VARCHAR(300)",

    # JD Management: proper Client link (company_name kept as legacy fallback)
    "ALTER TABLE tiq_jd_records ADD COLUMN IF NOT EXISTS client_id INTEGER",

    # CandidateLens: optional link to a JD Management record, categorized
    # requirements, and denormalized client name for the summary panel
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_record_id INTEGER",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_client_name VARCHAR(300)",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_essential_skills JSON DEFAULT '[]'",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_good_to_have_skills JSON DEFAULT '[]'",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_optional_skills JSON DEFAULT '[]'",

    # CandidateLens: candidate sourced from Vendor Management instead of a
    # raw manual CV upload
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS source_vendor_id INTEGER",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS source_vendor_name VARCHAR(300)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS source_tracked_candidate_id INTEGER",

    "ALTER TABLE tiq_user_api_keys ADD COLUMN IF NOT EXISTS is_global BOOLEAN DEFAULT FALSE NOT NULL",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS resume_file_blob BYTEA",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS resume_file_mimetype VARCHAR(100)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS video_blob BYTEA",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS video_mimetype VARCHAR(50) DEFAULT 'video/webm'",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS video_transcript TEXT",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS video_analysis JSON",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS video_analysis_status VARCHAR(20) DEFAULT 'Pending'",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_role VARCHAR(300)",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_location VARCHAR(300)",
    "ALTER TABLE tiq_joblens_sessions ADD COLUMN IF NOT EXISTS jd_company VARCHAR(300)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS experience_years VARCHAR(20)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS summary TEXT",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS resume_summary JSON DEFAULT '[]'",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS interview_token VARCHAR(64)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS contacted BOOLEAN DEFAULT FALSE",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS job_type VARCHAR(50)",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS contract_duration VARCHAR(50)",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS organisational_context TEXT",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS required_qualifications JSON DEFAULT '[]'",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS preferred_qualifications JSON DEFAULT '[]'",
    "ALTER TABLE tiq_jd_documents ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(20)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_tiq_joblens_candidates_interview_token ON tiq_joblens_candidates (interview_token)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS emotion_disgust INTEGER DEFAULT 0",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS emotion_surprise INTEGER DEFAULT 0",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS dominant_emotion VARCHAR(20) DEFAULT 'Neutral'",
    "ALTER TABLE tiq_jobintel_records ADD COLUMN IF NOT EXISTS job_group VARCHAR(200)",
    "ALTER TABLE tiq_jobintel_records ADD COLUMN IF NOT EXISTS company_type VARCHAR(200)",
    # Create JobLens tables if they don't exist (added after initial deployment)
    """CREATE TABLE IF NOT EXISTS tiq_joblens_sessions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES tiq_users(id) ON DELETE CASCADE,
        jd_text TEXT,
        jd_skills JSON DEFAULT '[]',
        low_threshold INTEGER DEFAULT 40,
        high_threshold INTEGER DEFAULT 70,
        cv_count INTEGER DEFAULT 0,
        status VARCHAR(50) DEFAULT 'completed',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS tiq_joblens_candidates (
        id SERIAL PRIMARY KEY,
        session_id INTEGER REFERENCES tiq_joblens_sessions(id) ON DELETE CASCADE,
        name VARCHAR(200),
        email VARCHAR(200),
        phone VARCHAR(100),
        filename VARCHAR(300),
        ats_score FLOAT DEFAULT 0.0,
        status VARCHAR(50) DEFAULT 'Not Qualified',
        matched_skills JSON DEFAULT '[]',
        missing_skills JSON DEFAULT '[]',
        bonus INTEGER DEFAULT 0,
        bonus_reasons TEXT,
        interview_questions JSON DEFAULT '[]',
        video_status VARCHAR(50) DEFAULT 'Pending',
        emotion_happy INTEGER DEFAULT 0,
        emotion_neutral INTEGER DEFAULT 0,
        emotion_sad INTEGER DEFAULT 0,
        emotion_angry INTEGER DEFAULT 0,
        shortlisted BOOLEAN DEFAULT FALSE
    )""",
    # Fix tiq_linklens_searches.status - was ENUM agentstatus, now VARCHAR
    """ALTER TABLE tiq_linklens_searches
       ALTER COLUMN status TYPE VARCHAR(50)
       USING status::text""",

    # Fix tiq_jobintel_runs.status - same problem
    """ALTER TABLE tiq_jobintel_runs
       ALTER COLUMN status TYPE VARCHAR(50)
       USING status::text""",

    # Fix tiq_users.role if it was created as userenum
    """ALTER TABLE tiq_users
       ALTER COLUMN role TYPE VARCHAR(50)
       USING role::text""",

    # Add any missing columns
    "ALTER TABLE tiq_linklens_searches ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
    "ALTER TABLE tiq_jobintel_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
]

async def run():
    # The real cost here isn't any one statement — it's that `--reload`
    # re-runs this ENTIRE ~65-statement pass on every single file save
    # during development, even when nothing schema-related changed at all.
    # We fingerprint the MIGRATIONS list itself; if it's identical to the
    # last successful run, skip straight past the whole thing (one fast
    # query) instead of re-checking every statement again.
    migrations_fingerprint = hashlib.sha256("\n".join(MIGRATIONS).encode()).hexdigest()

    async with engine.connect() as conn:
        autocommit_conn = await conn.execution_options(isolation_level="AUTOCOMMIT")

        await autocommit_conn.execute(text(
            "CREATE TABLE IF NOT EXISTS tiq_migration_state (id INTEGER PRIMARY KEY, fingerprint VARCHAR(64))"
        ))
        existing = (await autocommit_conn.execute(
            text("SELECT fingerprint FROM tiq_migration_state WHERE id = 1")
        )).scalar_one_or_none()

        if existing == migrations_fingerprint:
            print(f"  Migrations unchanged since last run ({len(MIGRATIONS)} statements) — skipping.")
            return

        for sql in MIGRATIONS:
            try:
                await autocommit_conn.execute(text(sql))
                print(f"  OK: {sql[:60]}")
            except Exception as e:
                err = str(e)
                if "does not exist" in err or "already exists" in err or "cannot alter" in err.lower():
                    print(f"  SKIP (already ok): {sql[:60]}")
                else:
                    print(f"  WARN: {err[:100]}")

        await autocommit_conn.execute(
            text("INSERT INTO tiq_migration_state (id, fingerprint) VALUES (1, :fp) "
                 "ON CONFLICT (id) DO UPDATE SET fingerprint = :fp"),
            {"fp": migrations_fingerprint},
        )
    print("  Migration complete.")

if __name__ == "__main__":
    asyncio.run(run())