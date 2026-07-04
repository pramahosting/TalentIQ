"""
Drops and recreates ONLY the CandidateLens Management tables (Client, JD,
Vendor, Candidate, Candidate Status Log) — use this when those specific
tables are in a stale/inconsistent state from earlier schema iterations
and you want a guaranteed-clean slate, without touching any other module's
data (JobHunter, MarketIntel, LinkExplore, CVAnalysis, JD Creator, users,
API keys — all untouched).

⚠️  DESTRUCTIVE — this permanently deletes all Clients, JDs, Vendors,
    tracked Candidates, and their status history for ALL users. There is
    no undo. Back up first if this data matters.

Usage:
    cd backend
    venv\\Scripts\\python.exe db\\reset_candidatelens_tables.py --yes
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from db.database import engine, Base
# Import models so they're registered on Base.metadata before create_all
import models.models  # noqa: F401

TABLES_IN_DROP_ORDER = [
    # children first (FK dependents), then parents — CASCADE also handles
    # this automatically, but explicit order makes the intent clear
    "tiq_candidate_status_log",
    "tiq_tracked_candidates",
    "tiq_jd_records",
    "tiq_vendors",
    "tiq_clients",
]


async def reset():
    async with engine.begin() as conn:
        print("Dropping CandidateLens management tables (if they exist)...")
        for table in TABLES_IN_DROP_ORDER:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            print(f"  Dropped: {table}")

        print("\nRecreating all tables from current models (only missing ones are created;")
        print("every other module's existing table/data is left untouched)...")
        await conn.run_sync(Base.metadata.create_all)
        print("Done. CandidateLens management tables are now fresh and match the current schema.")
    await engine.dispose()


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        print("This will PERMANENTLY DELETE all Clients, JDs, Vendors, and tracked")
        print("Candidates (all users). Re-run with --yes to confirm:")
        print("  python db/reset_candidatelens_tables.py --yes")
        sys.exit(1)
    asyncio.run(reset())
