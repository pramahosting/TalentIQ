"""
TalentIQ Platform - FastAPI Backend
Serves React frontend from /static in production (Docker/Northflank).
"""
import sys
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

print(f"\n  TalentIQ Backend | Python {sys.version.split()[0]}")

from db.database import engine, Base, AsyncSessionLocal
from routers import auth, jobhunt, jobintel, linklens, dashboard
from routers import admin as admin_router
from routers import cvintel as cvintel_router
from routers import joblens as joblens_router
from routers import jdcreator as jdcreator_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("  Running DB migrations...")
    try:
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


app = FastAPI(
    title="TalentIQ API",
    version="1.0.0",
    lifespan=lifespan,
    # Hide docs in production
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ───────────────────────────────────────────────────────
app.include_router(auth.router,           prefix="/api/auth",      tags=["Auth"])
app.include_router(jobhunt.router,        prefix="/api/jobhunt",   tags=["JobHunt"])
app.include_router(jobintel.router,       prefix="/api/jobintel",  tags=["JobIntel"])
app.include_router(linklens.router,       prefix="/api/linklens",  tags=["LinkLens"])
app.include_router(dashboard.router,      prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(admin_router.router,   prefix="/api/admin",     tags=["Admin"])
app.include_router(cvintel_router.router, prefix="/api/cvintel",   tags=["CVIntel"])
app.include_router(joblens_router.router, prefix="/api/joblens",   tags=["JobLens"])
app.include_router(jdcreator_router.router, prefix="/api/jdcreator", tags=["JDCreator"])


@app.get("/health")
async def health():
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        db = "connected"
    except Exception as e:
        db = f"error: {str(e)[:80]}"
    return {"status": "healthy", "database": db}


# ── Serve React frontend (production/Docker only) ────────────────────
# In dev: Vite runs on :5173 and proxies /api → :8000
# In prod: FastAPI serves the built React app from /static
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    # Serve static assets (JS, CSS, images) under /assets
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    # Serve favicon and other root-level static files
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        f = STATIC_DIR / "favicon.ico"
        return FileResponse(str(f)) if f.exists() else FileResponse(str(STATIC_DIR / "index.html"))

    # Catch-all: return index.html for all non-API routes
    # This lets React Router handle /login, /app/jobhunt, etc.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API calls (shouldn't happen but safety net)
        if full_path.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index = STATIC_DIR / "index.html"
        return FileResponse(str(index))
else:
    # Development mode — no static files built yet
    @app.get("/")
    async def root():
        return {"status": "TalentIQ API running (dev mode — frontend on :5173)"}