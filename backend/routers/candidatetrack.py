"""
TalentIQ - Candidate Tracker Router
Four linked modules: Client/Company Management, JD Management (lifecycle-
tracked job requisitions linked to a Client), Vendor Management (recruitment
agencies/vendors submitting candidates), and Candidate Tracking (every
candidate's end-to-end journey, independent of any single JD or vendor view).

Data model: Client → many JDs; JD → many TrackedCandidates; Vendor → many
TrackedCandidates; each TrackedCandidate belongs to exactly one JD and one
Vendor, and (via its JD) to exactly one Client. "Vendors involved" per JD is
derived from distinct vendor_id among that JD's candidates, not a separate
join table — it's always consistent with the actual submissions by
construction.
"""
import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, delete as sql_delete
from pydantic import BaseModel

from db.database import get_db
from models.models import (
    User, Client, JDRecord, Vendor, TrackedCandidate, CandidateStatusLog, JDVendorLink,
    JD_STATUSES, JD_IN_PROGRESS_STATUSES, CANDIDATE_STATUSES, WORK_PERMISSION_OPTIONS,
)
from utils.auth_utils import get_current_user
from utils.sequencing import next_sequence_number

router = APIRouter()


class BulkIds(BaseModel):
    ids: List[int]


def _parse_csv(content: bytes) -> List[dict]:
    """Parses CSV bytes into a list of {header: value} dicts, tolerant of a
    UTF-8 BOM (common from Excel exports) and stripping whitespace from
    both headers and values."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if any(clean.values()):
            rows.append(clean)
    return rows


async def _link_jd_vendor(db: AsyncSession, jd_id: int, vendor_id: int) -> None:
    """Ensures a JDVendorLink row exists for this JD+Vendor pair — called
    every time a candidate is submitted. This is the ONLY place this
    relationship table is written to; it's never shown as its own tab or
    CRUD screen, purely backing "vendors involved in a JD" / "JDs a vendor
    is involved in" with a real relationship table rather than a DISTINCT
    scan over candidates on every read."""
    existing = await db.execute(
        select(JDVendorLink).where(JDVendorLink.jd_id == jd_id, JDVendorLink.vendor_id == vendor_id)
    )
    if existing.scalar_one_or_none() is None:
        db.add(JDVendorLink(jd_id=jd_id, vendor_id=vendor_id))


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT / COMPANY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class ClientCreate(BaseModel):
    name: str
    address: str = ""
    abn: str = ""
    area_of_work: str = ""


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    abn: Optional[str] = None
    area_of_work: Optional[str] = None


def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _fmt_client(c: Client, jd_count: int = 0) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "address": c.address or "",
        "abn": c.abn or "",
        "area_of_work": c.area_of_work or "",
        "jd_count": jd_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/clients")
async def create_client(
    payload: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(400, "Client name is required.")
    c = Client(
        user_id=current_user.id,
        name=payload.name.strip(),
        address=payload.address.strip(),
        abn=payload.abn.strip(),
        area_of_work=payload.area_of_work.strip(),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _fmt_client(c)


@router.get("/clients")
async def list_clients(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Client).where(Client.user_id == current_user.id).order_by(Client.created_at.desc()))
    clients = r.scalars().all()
    out = []
    for c in clients:
        jr = await db.execute(select(func.count()).select_from(JDRecord).where(JDRecord.client_id == c.id))
        out.append(_fmt_client(c, jr.scalar() or 0))
    return out


@router.put("/clients/{client_id}")
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Client).where(Client.id == client_id, Client.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Client not found")
    if payload.name is not None:
        c.name = payload.name.strip()
    if payload.address is not None:
        c.address = payload.address.strip()
    if payload.abn is not None:
        c.abn = payload.abn.strip()
    if payload.area_of_work is not None:
        c.area_of_work = payload.area_of_work.strip()
    c.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(c)
    return _fmt_client(c)


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Client).where(Client.id == client_id, Client.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Client not found")
    await db.delete(c)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/clients")
async def bulk_delete_clients(
    payload: BulkIds,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(sql_delete(Client).where(Client.id.in_(payload.ids), Client.user_id == current_user.id))
    await db.commit()
    return {"message": f"Deleted {len(payload.ids)} client(s)"}


@router.post("/clients/import-csv")
async def import_clients_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expected columns: name, address, abn, area_of_work
    (name is the only required column)."""
    rows = _parse_csv(await file.read())
    created, skipped, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = row.get("name", "").strip()
        if not name:
            skipped += 1
            errors.append(f"Row {i}: missing 'name', skipped")
            continue
        db.add(Client(
            user_id=current_user.id,
            name=name,
            address=row.get("address", ""),
            abn=row.get("abn", ""),
            area_of_work=row.get("area_of_work", ""),
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════════════════
# JD MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class JDCreate(BaseModel):
    jd_title: str
    client_id: Optional[int] = None   # sole source of truth for the JD's client — no free-text fallback (3NF)
    status: str = "Open"
    description: str = ""


class JDUpdate(BaseModel):
    jd_title: Optional[str] = None
    client_id: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None


async def _fmt_jd(db: AsyncSession, jd: JDRecord) -> dict:
    cr = await db.execute(
        select(TrackedCandidate).where(TrackedCandidate.jd_id == jd.id)
    )
    candidates = cr.scalars().all()

    vr = await db.execute(select(func.count()).select_from(JDVendorLink).where(JDVendorLink.jd_id == jd.id))
    vendor_count = vr.scalar() or 0

    client_name = ""
    if jd.client_id:
        cr2 = await db.execute(select(Client).where(Client.id == jd.client_id))
        client = cr2.scalar_one_or_none()
        if client:
            client_name = client.name

    return {
        "id": jd.id,
        "sequence_number": jd.sequence_number or jd.id,
        "jd_title": jd.title,
        "client_id": jd.client_id,
        "company_name": client_name,
        "status": jd.status,
        "description": jd.description or "",
        "essential_skills": jd.essential_skills or [],
        "good_to_have_skills": jd.good_to_have_skills or [],
        "optional_skills": jd.optional_skills or [],
        "min_years_experience": jd.min_years_experience or 0,
        "education_requirement": jd.education_requirement or "",
        "candidate_count": len(candidates),
        "vendor_count": vendor_count,
        "has_jd_file": bool(jd.jd_file_blob),
        "jd_file_filename": jd.jd_file_filename or "",
        "created_at": jd.created_at.isoformat() if jd.created_at else None,
        "updated_at": jd.updated_at.isoformat() if jd.updated_at else None,
    }


async def _extract_and_apply_requirements(jd: JDRecord, description: str, current_user: User, db: AsyncSession):
    """Extracts categorized requirements from the JD description (LLM if a
    Groq key is available, heuristic otherwise) and persists them onto the
    JDRecord — called on create and whenever the description changes,
    rather than re-extracted on every read."""
    if not description or not description.strip():
        return
    from utils.credentials import get_credential, get_groq_model
    from utils.llm_extraction import extract_jd_requirements_categorized
    groq_key = await get_credential(db, current_user.id, "groq", "api_key")
    groq_model = await get_groq_model(db, current_user.id)
    req = await extract_jd_requirements_categorized(description, groq_key, groq_model)
    jd.essential_skills = req.get("essential", [])
    jd.good_to_have_skills = req.get("good_to_have", [])
    jd.optional_skills = req.get("optional", [])
    jd.min_years_experience = req.get("min_years_experience", 0)
    jd.education_requirement = req.get("education_requirement", "")


@router.post("/jds")
async def create_jd(
    payload: JDCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.jd_title.strip():
        raise HTTPException(400, "JD Title is required.")
    if payload.status not in JD_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(JD_STATUSES)}")

    if payload.client_id:
        cr = await db.execute(select(Client).where(Client.id == payload.client_id, Client.user_id == current_user.id))
        client = cr.scalar_one_or_none()
        if not client:
            raise HTTPException(404, "Client not found")

    seq_num = await next_sequence_number(db, JDRecord, current_user.id)
    jd = JDRecord(
        user_id=current_user.id,
        sequence_number=seq_num,
        title=payload.jd_title.strip(),
        client_id=payload.client_id,
        status=payload.status,
        description=payload.description,
    )
    db.add(jd)
    await db.commit()
    await db.refresh(jd)

    await _extract_and_apply_requirements(jd, payload.description, current_user, db)
    await db.commit()
    await db.refresh(jd)
    return await _fmt_jd(db, jd)


@router.get("/jds")
async def list_jds(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(JDRecord).where(JDRecord.user_id == current_user.id).order_by(JDRecord.created_at.desc())
    )
    return [await _fmt_jd(db, jd) for jd in r.scalars().all()]


@router.get("/jds/stats")
async def jd_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(JDRecord.status).where(JDRecord.user_id == current_user.id))
    statuses = [s for (s,) in r.all()]
    return {
        "total": len(statuses),
        "open": sum(1 for s in statuses if s == "Open"),
        "in_progress": sum(1 for s in statuses if s in JD_IN_PROGRESS_STATUSES),
        "closed": sum(1 for s in statuses if s == "Closed"),
    }


@router.get("/dashboard/jd-summary")
async def jd_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real-time, per-client JD status breakdown — one grouped SQL query,
    computed fresh on every call (no cached/stored counters to drift out of
    sync). LEFT JOIN so JDs with no client assigned still show up under
    "No Client Assigned" rather than being silently dropped."""
    stmt = (
        select(
            JDRecord.client_id,
            func.coalesce(Client.name, "No Client Assigned").label("client_name"),
            func.count(JDRecord.id).label("total_jds"),
            func.sum(case((JDRecord.status == "Open", 1), else_=0)).label("open_jds"),
            func.sum(case((JDRecord.status.in_(JD_IN_PROGRESS_STATUSES), 1), else_=0)).label("in_progress_jds"),
            func.sum(case((JDRecord.status == "Closed", 1), else_=0)).label("closed_jds"),
        )
        .select_from(JDRecord)
        .outerjoin(Client, JDRecord.client_id == Client.id)
        .where(JDRecord.user_id == current_user.id)
        .group_by(JDRecord.client_id, Client.name)
        .order_by(func.coalesce(Client.name, "\uffff"))
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "client_id": r.client_id,
            "client_name": r.client_name,
            "total_jds": r.total_jds,
            "open_jds": r.open_jds,
            "in_progress_jds": r.in_progress_jds,
            "closed_jds": r.closed_jds,
        }
        for r in rows
    ]


@router.get("/dashboard/vendor-summary")
async def vendor_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real-time, per-vendor candidate breakdown — candidate counts come
    from tracked_candidates (Profile Management submissions); average score
    comes from a separate aggregation over tiq_joblens_candidates (actual
    AI-scored analysis runs), matched by source_vendor_id — the link
    recorded whenever a candidate sourced from Vendor Management is sent
    through New Analysis. A vendor with submissions but no scored analysis
    yet simply shows no average, rather than a misleading zero."""
    from models.models import JobLensCandidate, JobLensSession

    candidate_stmt = (
        select(
            Vendor.id,
            Vendor.name,
            func.count(TrackedCandidate.id).label("total"),
            func.sum(case((TrackedCandidate.status.in_(
                ["Applied", "Shortlisted", "Interview Scheduled", "Interview Completed"]
            ), 1), else_=0)).label("in_consideration"),
            func.sum(case((TrackedCandidate.status.in_(["Selected", "Offered"]), 1), else_=0)).label("successful"),
            func.sum(case((TrackedCandidate.status == "Rejected", 1), else_=0)).label("rejected"),
        )
        .select_from(Vendor)
        .outerjoin(TrackedCandidate, TrackedCandidate.vendor_id == Vendor.id)
        .where(Vendor.user_id == current_user.id)
        .group_by(Vendor.id, Vendor.name)
        .order_by(Vendor.name)
    )
    candidate_rows = (await db.execute(candidate_stmt)).all()

    score_stmt = (
        select(JobLensCandidate.source_vendor_id, func.avg(JobLensCandidate.ats_score))
        .join(JobLensSession, JobLensCandidate.session_id == JobLensSession.id)
        .where(JobLensSession.user_id == current_user.id, JobLensCandidate.source_vendor_id.isnot(None))
        .group_by(JobLensCandidate.source_vendor_id)
    )
    avg_scores = {vendor_id: round(avg, 1) for vendor_id, avg in (await db.execute(score_stmt)).all()}

    return [
        {
            "vendor_id": r.id,
            "vendor_name": r.name,
            "total_candidates": r.total,
            "in_consideration": r.in_consideration,
            "successful": r.successful,
            "rejected": r.rejected,
            "avg_score": avg_scores.get(r.id),
        }
        for r in candidate_rows
    ]


@router.get("/jds/{jd_id}")
async def get_jd(
    jd_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    jd = r.scalar_one_or_none()
    if not jd:
        raise HTTPException(404, "JD not found")
    return await _fmt_jd(db, jd)


@router.put("/jds/{jd_id}")
async def update_jd(
    jd_id: int,
    payload: JDUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    jd = r.scalar_one_or_none()
    if not jd:
        raise HTTPException(404, "JD not found")
    if payload.status is not None and payload.status not in JD_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(JD_STATUSES)}")
    if payload.jd_title is not None:
        jd.title = payload.jd_title.strip()
    if payload.client_id is not None:
        cr = await db.execute(select(Client).where(Client.id == payload.client_id, Client.user_id == current_user.id))
        client = cr.scalar_one_or_none()
        if not client:
            raise HTTPException(404, "Client not found")
        jd.client_id = payload.client_id
    if payload.status is not None:
        jd.status = payload.status
    description_changed = False
    if payload.description is not None:
        jd.description = payload.description
        description_changed = True
    jd.updated_at = datetime.utcnow()
    await db.commit()

    if description_changed:
        await _extract_and_apply_requirements(jd, jd.description, current_user, db)
        await db.commit()
    await db.refresh(jd)
    return await _fmt_jd(db, jd)


@router.delete("/jds/{jd_id}")
async def delete_jd(
    jd_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    jd = r.scalar_one_or_none()
    if not jd:
        raise HTTPException(404, "JD not found")
    await db.delete(jd)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/jds")
async def bulk_delete_jds(
    payload: BulkIds,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(sql_delete(JDRecord).where(JDRecord.id.in_(payload.ids), JDRecord.user_id == current_user.id))
    await db.commit()
    return {"message": f"Deleted {len(payload.ids)} JD(s)"}


@router.post("/jds/{jd_id}/file")
async def upload_jd_file(
    jd_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Uploads the original JD document (Word/PDF) — kept alongside (not
    instead of) the description text used for requirement extraction."""
    r = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    jd = r.scalar_one_or_none()
    if not jd:
        raise HTTPException(404, "JD not found")
    content = await file.read()
    jd.jd_file_blob = content
    jd.jd_file_filename = file.filename
    jd.jd_file_mimetype = file.content_type or "application/octet-stream"
    await db.commit()
    return {"status": "saved", "filename": file.filename}


@router.get("/jds/{jd_id}/file")
async def download_jd_file(
    jd_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    jd = r.scalar_one_or_none()
    if not jd or not jd.jd_file_blob:
        raise HTTPException(404, "No JD file stored for this JD")
    return Response(
        content=jd.jd_file_blob,
        media_type=jd.jd_file_mimetype or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{jd.jd_file_filename or "jd"}"'},
    )


@router.post("/jds/import-csv")
async def import_jds_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expected columns: jd_title, client_name, status, description
    (jd_title required; client_name must match an existing Client's name
    exactly, case-insensitive — create the client first if it doesn't
    exist yet, otherwise that row is skipped rather than guessed at)."""
    rows = _parse_csv(await file.read())
    clients = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalars().all()
    client_by_name = {c.name.strip().lower(): c for c in clients}

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):
        jd_title = row.get("jd_title", "").strip()
        if not jd_title:
            skipped += 1
            errors.append(f"Row {i}: missing 'jd_title', skipped")
            continue
        status = row.get("status", "Open").strip() or "Open"
        if status not in JD_STATUSES:
            status = "Open"
        client_id = None
        client_name = row.get("client_name", "").strip()
        if client_name:
            client = client_by_name.get(client_name.lower())
            if not client:
                skipped += 1
                errors.append(f"Row {i}: client '{client_name}' not found — create it first, skipped")
                continue
            client_id = client.id
        seq_num = await next_sequence_number(db, JDRecord, current_user.id)
        db.add(JDRecord(
            user_id=current_user.id, sequence_number=seq_num, title=jd_title,
            client_id=client_id, status=status, description=row.get("description", ""),
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class VendorCreate(BaseModel):
    name: str
    address: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    coverage_region: str = ""
    technical_area: str = ""
    company_details: str = ""


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    coverage_region: Optional[str] = None
    technical_area: Optional[str] = None
    company_details: Optional[str] = None


async def _fmt_vendor(db: AsyncSession, v: Vendor) -> dict:
    cr = await db.execute(select(func.count()).select_from(TrackedCandidate).where(TrackedCandidate.vendor_id == v.id))
    candidate_count = cr.scalar() or 0
    jr = await db.execute(select(func.count()).select_from(JDVendorLink).where(JDVendorLink.vendor_id == v.id))
    jd_count = jr.scalar() or 0
    return {
        "id": v.id,
        "sequence_number": v.sequence_number or v.id,
        "name": v.name,
        "address": v.address or "",
        "contact_email": v.contact_email or "",
        "contact_phone": v.contact_phone or "",
        "coverage_region": v.coverage_region or "",
        "technical_area": v.technical_area or "",
        "company_details": v.company_details or "",
        "candidate_count": candidate_count,
        "jd_count": jd_count,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.post("/vendors")
async def create_vendor(
    payload: VendorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(400, "Vendor name is required.")
    seq_num = await next_sequence_number(db, Vendor, current_user.id)
    v = Vendor(
        user_id=current_user.id,
        sequence_number=seq_num,
        name=payload.name.strip(),
        address=payload.address.strip(),
        contact_email=payload.contact_email.strip(),
        contact_phone=payload.contact_phone.strip(),
        coverage_region=payload.coverage_region.strip(),
        technical_area=payload.technical_area.strip(),
        company_details=payload.company_details,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return await _fmt_vendor(db, v)


@router.get("/vendors")
async def list_vendors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id).order_by(Vendor.created_at.desc()))
    return [await _fmt_vendor(db, v) for v in r.scalars().all()]


@router.put("/vendors/{vendor_id}")
async def update_vendor(
    vendor_id: int,
    payload: VendorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Vendor).where(Vendor.id == vendor_id, Vendor.user_id == current_user.id))
    v = r.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Vendor not found")
    if payload.name is not None:
        v.name = payload.name.strip()
    if payload.address is not None:
        v.address = payload.address.strip()
    if payload.contact_email is not None:
        v.contact_email = payload.contact_email.strip()
    if payload.contact_phone is not None:
        v.contact_phone = payload.contact_phone.strip()
    if payload.coverage_region is not None:
        v.coverage_region = payload.coverage_region.strip()
    if payload.technical_area is not None:
        v.technical_area = payload.technical_area.strip()
    if payload.company_details is not None:
        v.company_details = payload.company_details
    v.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(v)
    return await _fmt_vendor(db, v)


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(
    vendor_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Vendor).where(Vendor.id == vendor_id, Vendor.user_id == current_user.id))
    v = r.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Vendor not found")
    await db.delete(v)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/vendors")
async def bulk_delete_vendors(
    payload: BulkIds,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(sql_delete(Vendor).where(Vendor.id.in_(payload.ids), Vendor.user_id == current_user.id))
    await db.commit()
    return {"message": f"Deleted {len(payload.ids)} vendor(s)"}


@router.post("/vendors/import-csv")
async def import_vendors_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expected columns: name, address, contact_email, contact_phone,
    coverage_region, technical_area, company_details (name required)."""
    rows = _parse_csv(await file.read())
    created, skipped, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):
        name = row.get("name", "").strip()
        if not name:
            skipped += 1
            errors.append(f"Row {i}: missing 'name', skipped")
            continue
        seq_num = await next_sequence_number(db, Vendor, current_user.id)
        db.add(Vendor(
            user_id=current_user.id, sequence_number=seq_num, name=name,
            address=row.get("address", ""), contact_email=row.get("contact_email", ""),
            contact_phone=row.get("contact_phone", ""), coverage_region=row.get("coverage_region", ""),
            technical_area=row.get("technical_area", ""), company_details=row.get("company_details", ""),
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


# ══════════════════════════════════════════════════════════════════════════════
# CANDIDATE TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _norm_phone(p: str) -> str:
    return "".join(ch for ch in (p or "") if ch.isdigit())


async def _detect_duplicate(db: AsyncSession, jd_id: int, email: str, phone: str):
    """Scoped to a single JD. Returns the id of the earliest-submitted
    non-duplicate candidate that matches by email (preferred) or phone, or
    None if no match. The match stays primary; the new submission (caller's
    responsibility) gets flagged but is never discarded or merged, so every
    vendor's submission stays independently auditable."""
    norm_email = _norm_email(email)
    norm_phone = _norm_phone(phone)
    if not norm_email and not norm_phone:
        return None

    existing_candidates = (await db.execute(
        select(TrackedCandidate)
        .where(TrackedCandidate.jd_id == jd_id, TrackedCandidate.is_duplicate.is_(False))
        .order_by(TrackedCandidate.submitted_at.asc(), TrackedCandidate.id.asc())
    )).scalars().all()

    for existing in existing_candidates:
        if norm_email and _norm_email(existing.email) == norm_email:
            return existing.id
        if norm_phone and _norm_phone(existing.phone) == norm_phone:
            return existing.id
    return None


async def _fmt_candidate(db: AsyncSession, c: TrackedCandidate) -> dict:
    jd = (await db.execute(select(JDRecord).where(JDRecord.id == c.jd_id))).scalar_one_or_none()
    vendor = (await db.execute(select(Vendor).where(Vendor.id == c.vendor_id))).scalar_one_or_none()

    client_name = ""
    if jd and jd.client_id:
        cr = await db.execute(select(Client).where(Client.id == jd.client_id))
        client = cr.scalar_one_or_none()
        if client:
            client_name = client.name

    return {
        "id": c.id,
        "name": c.name,
        "email": c.email or "",
        "phone": c.phone or "",
        "address": c.address or "",
        "work_permission": c.work_permission or "",
        "jd_id": c.jd_id,
        "jd_title": jd.title if jd else "",
        "client_name": client_name,
        "vendor_id": c.vendor_id,
        "vendor_name": vendor.name if vendor else "",     # source vendor
        "status": c.status,
        "is_duplicate": bool(c.is_duplicate),              # tracked internally; not surfaced as its own UI column
        "duplicate_of_id": c.duplicate_of_id,
        "has_resume": bool(c.resume_blob),
        "resume_filename": c.resume_filename or "",
        "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.post("/candidates")
async def create_candidate(
    jd_id: int = Form(...),
    vendor_id: int = Form(...),
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    work_permission: str = Form(""),
    status: str = Form("Applied"),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not name.strip():
        raise HTTPException(400, "Candidate name is required.")
    if status not in CANDIDATE_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(CANDIDATE_STATUSES)}")
    if work_permission and work_permission not in WORK_PERMISSION_OPTIONS:
        raise HTTPException(400, f"Work Permission must be one of: {', '.join(WORK_PERMISSION_OPTIONS)}")

    jd_row = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    if not jd_row.scalar_one_or_none():
        raise HTTPException(404, "JD not found")
    vendor_row = await db.execute(select(Vendor).where(Vendor.id == vendor_id, Vendor.user_id == current_user.id))
    if not vendor_row.scalar_one_or_none():
        raise HTTPException(404, "Vendor not found")

    resume_blob = resume_filename = resume_mimetype = None
    if file and file.filename:
        resume_blob = await file.read()
        resume_filename = file.filename
        resume_mimetype = file.content_type or "application/octet-stream"

    duplicate_of_id = await _detect_duplicate(db, jd_id, email, phone)

    candidate = TrackedCandidate(
        user_id=current_user.id,
        jd_id=jd_id,
        vendor_id=vendor_id,
        name=name.strip(),
        email=email.strip(),
        phone=phone.strip(),
        address=address.strip(),
        work_permission=work_permission or None,
        resume_blob=resume_blob,
        resume_filename=resume_filename,
        resume_mimetype=resume_mimetype,
        status=status,
        is_duplicate=duplicate_of_id is not None,
        duplicate_of_id=duplicate_of_id,
        submitted_at=datetime.utcnow(),
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)

    await _link_jd_vendor(db, jd_id, vendor_id)
    db.add(CandidateStatusLog(candidate_id=candidate.id, old_status=None, new_status=status))
    await db.commit()

    return await _fmt_candidate(db, candidate)


@router.post("/candidates/bulk-upload")
async def bulk_upload_candidates(
    jd_id: int = Form(...),
    vendor_id: int = Form(...),
    status: str = Form("Applied"),
    work_permission: str = Form(""),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk resume upload — one candidate row per file, named from the
    filename (edit afterwards to add email/phone for better duplicate
    matching). Status and Work Permission apply as a batch default to every
    file in this upload (adjustable per-candidate afterwards). Each file
    goes through the same duplicate-detection path as a single submission."""
    if status not in CANDIDATE_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(CANDIDATE_STATUSES)}")
    if work_permission and work_permission not in WORK_PERMISSION_OPTIONS:
        raise HTTPException(400, f"Work Permission must be one of: {', '.join(WORK_PERMISSION_OPTIONS)}")
    jd_row = await db.execute(select(JDRecord).where(JDRecord.id == jd_id, JDRecord.user_id == current_user.id))
    if not jd_row.scalar_one_or_none():
        raise HTTPException(404, "JD not found")
    vendor_row = await db.execute(select(Vendor).where(Vendor.id == vendor_id, Vendor.user_id == current_user.id))
    if not vendor_row.scalar_one_or_none():
        raise HTTPException(404, "Vendor not found")

    created = []
    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        # Derive a display name from the filename (strip extension, tidy separators)
        base = f.filename.rsplit(".", 1)[0]
        display_name = base.replace("_", " ").replace("-", " ").strip().title() or f.filename

        candidate = TrackedCandidate(
            user_id=current_user.id,
            jd_id=jd_id,
            vendor_id=vendor_id,
            name=display_name,
            email="",
            phone="",
            work_permission=work_permission or None,
            resume_blob=content,
            resume_filename=f.filename,
            resume_mimetype=f.content_type or "application/octet-stream",
            status=status,
            is_duplicate=False,
            duplicate_of_id=None,
            submitted_at=datetime.utcnow(),
        )
        db.add(candidate)
        await db.flush()
        db.add(CandidateStatusLog(candidate_id=candidate.id, old_status=None, new_status=status))
        created.append(candidate)

    if created:
        await _link_jd_vendor(db, jd_id, vendor_id)
    await db.commit()
    for c in created:
        await db.refresh(c)
    return {"created": len(created), "candidates": [await _fmt_candidate(db, c) for c in created]}


@router.get("/candidates")
async def list_candidates(
    jd_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(TrackedCandidate).where(TrackedCandidate.user_id == current_user.id)
    if jd_id is not None:
        q = q.where(TrackedCandidate.jd_id == jd_id)
    if vendor_id is not None:
        q = q.where(TrackedCandidate.vendor_id == vendor_id)
    r = await db.execute(q.order_by(TrackedCandidate.created_at.desc()))
    return [await _fmt_candidate(db, c) for c in r.scalars().all()]


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(TrackedCandidate).where(TrackedCandidate.id == candidate_id, TrackedCandidate.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    return await _fmt_candidate(db, c)


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    work_permission: Optional[str] = None
    jd_id: Optional[int] = None
    vendor_id: Optional[int] = None
    status: Optional[str] = None


@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(TrackedCandidate).where(TrackedCandidate.id == candidate_id, TrackedCandidate.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    if payload.status is not None and payload.status not in CANDIDATE_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(CANDIDATE_STATUSES)}")
    if payload.work_permission is not None and payload.work_permission and payload.work_permission not in WORK_PERMISSION_OPTIONS:
        raise HTTPException(400, f"Work Permission must be one of: {', '.join(WORK_PERMISSION_OPTIONS)}")

    if payload.name is not None:
        c.name = payload.name.strip()
    if payload.email is not None:
        c.email = payload.email.strip()
    if payload.phone is not None:
        c.phone = payload.phone.strip()
    if payload.address is not None:
        c.address = payload.address.strip()
    if payload.work_permission is not None:
        c.work_permission = payload.work_permission or None
    if payload.jd_id is not None:
        c.jd_id = payload.jd_id
    if payload.vendor_id is not None:
        c.vendor_id = payload.vendor_id
    if payload.jd_id is not None or payload.vendor_id is not None:
        await _link_jd_vendor(db, c.jd_id, c.vendor_id)

    if payload.status is not None and payload.status != c.status:
        db.add(CandidateStatusLog(candidate_id=c.id, old_status=c.status, new_status=payload.status))
        c.status = payload.status

    c.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(c)
    return await _fmt_candidate(db, c)


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(TrackedCandidate).where(TrackedCandidate.id == candidate_id, TrackedCandidate.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    await db.delete(c)
    await db.commit()
    return {"message": "Deleted"}


@router.delete("/candidates")
async def bulk_delete_candidates(
    payload: BulkIds,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(sql_delete(TrackedCandidate).where(TrackedCandidate.id.in_(payload.ids), TrackedCandidate.user_id == current_user.id))
    await db.commit()
    return {"message": f"Deleted {len(payload.ids)} candidate(s)"}


@router.get("/candidates/{candidate_id}/resume")
async def download_candidate_resume(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(TrackedCandidate).where(TrackedCandidate.id == candidate_id, TrackedCandidate.user_id == current_user.id))
    c = r.scalar_one_or_none()
    if not c or not c.resume_blob:
        raise HTTPException(404, "No resume stored for this candidate")
    return Response(
        content=c.resume_blob,
        media_type=c.resume_mimetype or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{c.resume_filename or "resume"}"'},
    )


@router.get("/candidates/{candidate_id}/status-log")
async def get_candidate_status_log(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.execute(select(TrackedCandidate).where(TrackedCandidate.id == candidate_id, TrackedCandidate.user_id == current_user.id))
    if not owns.scalar_one_or_none():
        raise HTTPException(404, "Candidate not found")
    r = await db.execute(
        select(CandidateStatusLog)
        .where(CandidateStatusLog.candidate_id == candidate_id)
        .order_by(CandidateStatusLog.changed_at.asc())
    )
    return [
        {
            "id": log.id,
            "old_status": log.old_status,
            "new_status": log.new_status,
            "changed_at": log.changed_at.isoformat() if log.changed_at else None,
        }
        for log in r.scalars().all()
    ]


@router.get("/meta")
async def get_meta():
    """Status option lists, for populating dropdowns without hardcoding
    them a second time in the frontend."""
    return {
        "jd_statuses": JD_STATUSES,
        "jd_in_progress_statuses": JD_IN_PROGRESS_STATUSES,
        "candidate_statuses": CANDIDATE_STATUSES,
        "work_permission_options": WORK_PERMISSION_OPTIONS,
    }
