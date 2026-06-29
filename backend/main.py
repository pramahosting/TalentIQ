"""
TalentIQ Platform - FastAPI Backend
"""
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text

print(f"\n  TalentIQ Backend | Python {sys.version.split()[0]}")

from db.database import engine, Base, AsyncSessionLocal
from routers import auth, jobhunt, jobintel, linklens, dashboard
from routers import admin as admin_router
from routers import cvintel as cvintel_router
from routers import joblens as joblens_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("  Running DB migrations...")
    try:
        # Fix any ENUM columns from old schema
        from db.migrate_fix import run as run_migrations
        await run_migrations()
    except Exception as e:
        print(f"  [!] Migration warning: {e}")

    print("  Creating TalentIQ tables (tiq_*) in neondb...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("  [OK] Tables ready.")
        from db.seed_admin import seed
        await seed()
    except Exception as e:
        print(f"  [!] DB error: {e}\n")
    yield


app = FastAPI(title="TalentIQ API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,           prefix="/api/auth",      tags=["Auth"])
app.include_router(jobhunt.router,        prefix="/api/jobhunt",   tags=["JobHunt"])
app.include_router(jobintel.router,       prefix="/api/jobintel",  tags=["JobIntel"])
app.include_router(linklens.router,       prefix="/api/linklens",  tags=["LinkLens"])
app.include_router(dashboard.router,      prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(admin_router.router,   prefix="/api/admin",     tags=["Admin"])
app.include_router(cvintel_router.router, prefix="/api/cvintel",   tags=["CVIntel"])
app.include_router(joblens_router.router,  prefix="/api/joblens",   tags=["JobLens"])


@app.get("/")
async def root():
    return {"status": "TalentIQ API running"}


@app.get("/health")
async def health():
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        db = "connected"
    except Exception as e:
        db = f"error: {str(e)[:80]}"
    return {"status": "healthy", "database": db}