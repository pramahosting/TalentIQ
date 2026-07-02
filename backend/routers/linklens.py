"""
TalentIQ - LinkLens Router
Launches Playwright as a SEPARATE SUBPROCESS so Chrome opens visibly on Windows desktop.
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel

from db.database import get_db, AsyncSessionLocal
from models.models import User, UserAPIKey, LinkLensSearch, LinkedInProfile
from utils.auth_utils import get_current_user
from utils.credentials import get_all_credentials
from utils.sequencing import next_sequence_number

router = APIRouter()

_status: dict[int, list[str]] = {}
_running: dict[int, bool] = {}


class SearchRequest(BaseModel):
    job_title: str
    country: str = "Australia"
    city: str = "All"
    skills: str = ""
    max_results: int = 25
    headless: bool = False


@router.post("/search")
async def start_search(
    req: SearchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get LinkedIn credentials — strictly private, never shared or
    # falls back to another user's/admin's key (LinkedIn is not in
    # utils.credentials.SHAREABLE_SERVICES).
    key_map = await get_all_credentials(db, current_user.id, "linkedin")
    li_email    = key_map.get("email", "")
    li_password = key_map.get("password", "")

    if not li_email or not li_password:
        raise HTTPException(
            400,
            "LinkedIn credentials not saved. "
            "Go to Settings → API Keys → LinkedIn and save your email + password."
        )

    # Ensure table columns exist (add completed_at if missing)
    try:
        await db.execute(text(
            "ALTER TABLE tiq_linklens_searches ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP"
        ))
        await db.commit()
    except Exception:
        pass

    # Create DB record
    try:
        seq_num = await next_sequence_number(db, LinkLensSearch, current_user.id)
        search = LinkLensSearch(
            user_id=current_user.id,
            sequence_number=seq_num,
            job_title=req.job_title,
            country=req.country,
            city=req.city,
            skills=req.skills,
            max_results=req.max_results,
            status="running",
            profiles_found=0,
        )
        db.add(search)
        await db.commit()
        await db.refresh(search)
        sid = search.id
    except Exception as e:
        raise HTTPException(500, f"DB error creating search: {str(e)}")

    _status[sid] = []
    _running[sid] = True

    def push(msg: str):
        ts = time.strftime("%H:%M:%S")
        _status[sid].append(f"[{ts}] {msg}")

    background_tasks.add_task(
        _run_subprocess,
        sid=sid,
        li_email=li_email,
        li_password=li_password,
        req=req,
        push=push,
    )

    return {"id": sid, "status": "running", "message": "Search started"}


async def _run_subprocess(sid: int, li_email: str, li_password: str, req: SearchRequest, push):
    """
    Launch linklens_browser.py in a thread using subprocess.Popen.
    asyncio.create_subprocess_exec fails on Windows uvicorn (no ProactorEventLoop).
    """
    import subprocess, threading, queue

    backend_dir = Path(__file__).parent.parent
    script      = backend_dir / "agents" / "linklens_browser.py"
    python_exe  = sys.executable

    params = {
        "email":       li_email,
        "password":    li_password,
        "job_title":   req.job_title,
        "country":     req.country,
        "city":        req.city,
        "skills":      req.skills,
        "max_results": req.max_results,
        "headless":    req.headless,
        "data_dir":    str(backend_dir / "data"),
    }

    push(f"🚀 Starting browser (headless={req.headless})...")
    push(f"🔑 LinkedIn account: {li_email}")

    results = []
    line_queue: queue.Queue = queue.Queue()
    done_event = threading.Event()

    def reader_thread(proc):
        try:
            for raw in proc.stdout:
                line_queue.put(("out", raw.decode("utf-8", errors="ignore").strip()))
            for raw in proc.stderr:
                line_queue.put(("err", raw.decode("utf-8", errors="ignore").strip()))
        finally:
            proc.wait()
            line_queue.put(("exit", str(proc.returncode)))
            done_event.set()

    try:
        import platform
        extra = {}
        if platform.system() == "Windows":
            # CREATE_NEW_CONSOLE = 0x10 — opens a new visible console window
            # This is required so Playwright can show the Chrome window on the desktop
            extra["creationflags"] = 0x00000010  # CREATE_NEW_CONSOLE

        proc = subprocess.Popen(
            [python_exe, str(script), json.dumps(params)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(backend_dir),
            bufsize=1,
            **extra,
        )
        push(f"🖥️ Browser process started (PID {proc.pid})")

        t = threading.Thread(target=reader_thread, args=(proc,), daemon=True)
        t.start()

        # Poll queue in async loop
        while not done_event.is_set() or not line_queue.empty():
            try:
                kind, line = line_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.3)
                continue

            if kind == "exit":
                push(f"🏁 Browser exited (code {line})")
                break
            if kind == "err":
                if line and "DeprecationWarning" not in line and "UserWarning" not in line:
                    push(f"[err] {line}")
                continue
            if not line:
                continue
            try:
                data = json.loads(line)
                k = data.get("kind", "status")
                if k == "status":
                    push(data.get("msg", ""))
                elif k == "result":
                    results = data.get("data", [])
                    push(f"📊 {len(results)} profiles extracted")
                elif k == "done":
                    push("✅ Browser finished")
            except json.JSONDecodeError:
                push(f"[log] {line}")

    except Exception as e:
        push(f"❌ Browser launch error: {e}")
        import traceback
        push(traceback.format_exc()[:400])

    # Save to DB
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LinkLensSearch).where(LinkLensSearch.id == sid)
            )
            search = result.scalar_one_or_none()
            if search:
                search.profiles_found = len(results)
                search.status = "completed" if results else ("failed" if not results else "completed")
                try:
                    from datetime import datetime
                    search.completed_at = datetime.utcnow()
                except Exception:
                    pass

            for r in results:
                skills_val = r.get("Skills", "")
                profile = LinkedInProfile(
                    search_id=sid,
                    profile_url=r.get("ProfileLink", ""),
                    full_name=r.get("Name", ""),
                    headline=r.get("Title", ""),
                    location=r.get("Location", ""),
                    current_title=r.get("Title", ""),
                    current_company=r.get("Company", ""),
                    skills=skills_val.split(", ") if skills_val else [],
                    email=r.get("Email", ""),
                    phone=r.get("Phone", ""),
                    raw_data=r,
                )
                db.add(profile)

            await db.commit()
        push(f"💾 {len(results)} profiles saved to database")
    except Exception as e:
        push(f"❌ DB save error: {e}")
    finally:
        _running[sid] = False


@router.get("/searches/{search_id}/status")
async def stream_status(search_id: int, token: str = ""):
    async def generator():
        sent = 0
        while True:
            msgs = _status.get(search_id, [])
            for msg in msgs[sent:]:
                yield f"data: {json.dumps({'message': msg})}\n\n"
                sent += 1
            if not _running.get(search_id, False) and sent >= len(msgs):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/searches")
async def list_searches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LinkLensSearch)
        .where(LinkLensSearch.user_id == current_user.id)
        .order_by(LinkLensSearch.created_at.desc())
    )
    return [
        {
            "id": s.id, "sequence_number": s.sequence_number or s.id, "job_title": s.job_title, "country": s.country,
            "city": s.city, "skills": s.skills, "max_results": s.max_results,
            "status": s.status, "profiles_found": s.profiles_found,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "completed_at": s.completed_at.isoformat() if getattr(s, "completed_at", None) else None,
        }
        for s in result.scalars().all()
    ]


@router.get("/searches/{search_id}")
async def get_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(LinkLensSearch).where(
            LinkLensSearch.id == search_id,
            LinkLensSearch.user_id == current_user.id,
        )
    )
    search = r.scalar_one_or_none()
    if not search:
        raise HTTPException(404, "Search not found")

    pr = await db.execute(
        select(LinkedInProfile).where(LinkedInProfile.search_id == search_id)
    )
    profiles = pr.scalars().all()

    return {
        "id": search.id, "sequence_number": search.sequence_number or search.id, "job_title": search.job_title,
        "country": search.country, "city": search.city,
        "skills": search.skills, "status": search.status,
        "profiles_found": search.profiles_found,
        "created_at": search.created_at.isoformat() if search.created_at else None,
        "completed_at": getattr(search, "completed_at", None) and search.completed_at.isoformat(),
        "profiles": [
            {
                "id": p.id, "name": p.full_name, "title": p.current_title,
                "company": p.current_company, "location": p.location,
                "email": p.email, "phone": p.phone, "skills": p.skills,
                "profile_url": p.profile_url,
                "accepted": p.raw_data.get("Accepted", "N") if p.raw_data else "N",
            }
            for p in profiles
        ],
    }


@router.get("/searches/{search_id}/export")
async def export_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import io, pandas as pd

    r = await db.execute(
        select(LinkLensSearch).where(
            LinkLensSearch.id == search_id,
            LinkLensSearch.user_id == current_user.id,
        )
    )
    search = r.scalar_one_or_none()
    if not search:
        raise HTTPException(404, "Search not found")

    pr = await db.execute(
        select(LinkedInProfile).where(LinkedInProfile.search_id == search_id)
    )

    rows = []
    for p in pr.scalars().all():
        raw = p.raw_data or {}
        rows.append({
            "Accepted": raw.get("Accepted", "N"),
            "Name": p.full_name, "Title": p.current_title,
            "Company": p.current_company, "Location": p.location,
            "Email": p.email or "", "Phone": p.phone or "",
            "Skills": ", ".join(p.skills) if p.skills else raw.get("Skills", ""),
            "Certifications": raw.get("Certifications", ""),
            "Education": raw.get("Education", ""),
            "Experience": raw.get("Experience", ""),
            "ProfileLink": p.profile_url,
        })

    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=linklens_{search_id}.xlsx"},
    )

@router.delete("/searches/{search_id}")
async def delete_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(LinkLensSearch).where(
            LinkLensSearch.id == search_id,
            LinkLensSearch.user_id == current_user.id,
        )
    )
    search = r.scalar_one_or_none()
    if not search:
        raise HTTPException(404, "Search not found")
    await db.delete(search)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/searches")
async def delete_all_searches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete ALL searches for the current user."""
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(LinkLensSearch).where(LinkLensSearch.user_id == current_user.id)
    )
    await db.commit()
    return {"message": "All searches deleted"}