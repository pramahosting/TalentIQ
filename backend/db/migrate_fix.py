"""
One-time migration: fix columns that were created as PostgreSQL ENUMs.
Converts them to plain VARCHAR so we can use string values directly.
Run once on startup via main.py lifespan.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import engine
from sqlalchemy import text

MIGRATIONS = [
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS experience_years VARCHAR(20)",
    "ALTER TABLE tiq_joblens_candidates ADD COLUMN IF NOT EXISTS summary TEXT",
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
    async with engine.begin() as conn:
        for sql in MIGRATIONS:
            try:
                await conn.execute(text(sql))
                print(f"  OK: {sql[:60]}")
            except Exception as e:
                err = str(e)
                if "does not exist" in err or "already exists" in err or "cannot alter" in err.lower():
                    print(f"  SKIP (already ok): {sql[:60]}")
                else:
                    print(f"  WARN: {err[:100]}")
    print("  Migration complete.")

if __name__ == "__main__":
    asyncio.run(run())