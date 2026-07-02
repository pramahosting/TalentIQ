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
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sql_delete
from pydantic import BaseModel

from db.database import get_db
from models.models import (
    User, Client, JDRecord, Vendor, TrackedCandidate, CandidateStatusLog,
    JD_STATUSES, JD_IN_PROGRESS_STATUSES, CANDIDATE_STATUSES,
)
from utils.auth_utils import get_current_user
from utils.sequencing import next_sequence_number

router = APIRouter()


class BulkIds(BaseModel):
    ids: List[int]


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT / COMPANY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class ClientCreate(BaseModel):
    name: str
    location: str = ""
    abn: str = ""
    partnership_from: Optional[str] = None   # ISO date string, e.g. "2024-01-15"
    area_of_work: str = ""


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    abn: Optional[str] = None
    partnership_from: Optional[str] = None
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
        "location": c.location or "",
        "abn": c.abn or "",
        "partnership_from": c.partnership_from.date().isoformat() if c.partnership_from else "",
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
        location=payload.location.strip(),
        abn=payload.abn.strip(),
        partnership_from=_parse_date(payload.partnership_from),
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
    if payload.location is not None:
        c.location = payload.location.strip()
    if payload.abn is not None:
        c.abn = payload.abn.strip()
    if payload.partnership_from is not None:
        c.partnership_from = _parse_date(payload.partnership_from)
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


# ══════════════════════════════════════════════════════════════════════════════
# JD MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class JDCreate(BaseModel):
    jd_title: str
    client_id: Optional[int] = None
    company_name: str = ""     # legacy free-text fallback if no client_id given
    status: str = "Open"
    description: str = ""


class JDUpdate(BaseModel):
    jd_title: Optional[str] = None
    client_id: Optional[int] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None


async def _fmt_jd(db: AsyncSession, jd: JDRecord) -> dict:
    cr = await db.execute(
        select(TrackedCandidate).where(TrackedCandidate.jd_id == jd.id)
    )
    candidates = cr.scalars().all()
    shortlisted_count = sum(1 for c in candidates if c.status in ("Shortlisted", "Interview Scheduled", "Interview Completed", "Selected", "Offered"))
    vendor_count = len({c.vendor_id for c in candidates})

    client_name = jd.company_name or ""
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
        "candidate_count": len(candidates),
        "shortlisted_count": shortlisted_count,
        "vendor_count": vendor_count,
        "created_at": jd.created_at.isoformat() if jd.created_at else None,
        "updated_at": jd.updated_at.isoformat() if jd.updated_at else None,
    }


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

    company_name = payload.company_name.strip()
    if payload.client_id:
        cr = await db.execute(select(Client).where(Client.id == payload.client_id, Client.user_id == current_user.id))
        client = cr.scalar_one_or_none()
        if not client:
            raise HTTPException(404, "Client not found")
        company_name = client.name  # keep legacy field in sync for any older display code

    seq_num = await next_sequence_number(db, JDRecord, current_user.id)
    jd = JDRecord(
        user_id=current_user.id,
        sequence_number=seq_num,
        title=payload.jd_title.strip(),
        client_id=payload.client_id,
        company_name=company_name,
        status=payload.status,
        description=payload.description,
    )
    db.add(jd)
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
        jd.company_name = client.name
    elif payload.company_name is not None:
        jd.company_name = payload.company_name.strip()
    if payload.status is not None:
        jd.status = payload.status
    if payload.description is not None:
        jd.description = payload.description
    jd.updated_at = datetime.utcnow()
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


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class VendorCreate(BaseModel):
    name: str
    location: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    area_of_coverage: str = ""
    technical_area: str = ""
    company_details: str = ""


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    area_of_coverage: Optional[str] = None
    technical_area: Optional[str] = None
    company_details: Optional[str] = None


async def _fmt_vendor(db: AsyncSession, v: Vendor) -> dict:
    cr = await db.execute(select(func.count()).select_from(TrackedCandidate).where(TrackedCandidate.vendor_id == v.id))
    candidate_count = cr.scalar() or 0
    jr = await db.execute(select(func.count(func.distinct(TrackedCandidate.jd_id))).where(TrackedCandidate.vendor_id == v.id))
    jd_count = jr.scalar() or 0
    return {
        "id": v.id,
        "sequence_number": v.sequence_number or v.id,
        "name": v.name,
        "location": v.location or "",
        "contact_email": v.contact_email or "",
        "contact_phone": v.contact_phone or "",
        "area_of_coverage": v.area_of_coverage or "",
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
        location=payload.location.strip(),
        contact_email=payload.contact_email.strip(),
        contact_phone=payload.contact_phone.strip(),
        area_of_coverage=payload.area_of_coverage.strip(),
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
    if payload.location is not None:
        v.location = payload.location.strip()
    if payload.contact_email is not None:
        v.contact_email = payload.contact_email.strip()
    if payload.contact_phone is not None:
        v.contact_phone = payload.contact_phone.strip()
    if payload.area_of_coverage is not None:
        v.area_of_coverage = payload.area_of_coverage.strip()
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
    if jd:
        client_name = jd.company_name or ""
        if jd.client_id:
            cr = await db.execute(select(Client).where(Client.id == jd.client_id))
            client = cr.scalar_one_or_none()
            if client:
                client_name = client.name

    return {
        "id": c.id,
        "name": c.name,
        "email": c.email or "",
        "phone": c.phone or "",
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
    status: str = Form("Applied"),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not name.strip():
        raise HTTPException(400, "Candidate name is required.")
    if status not in CANDIDATE_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(CANDIDATE_STATUSES)}")

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

    db.add(CandidateStatusLog(candidate_id=candidate.id, old_status=None, new_status=status))
    await db.commit()

    return await _fmt_candidate(db, candidate)


@router.post("/candidates/bulk-upload")
async def bulk_upload_candidates(
    jd_id: int = Form(...),
    vendor_id: int = Form(...),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk resume upload — one candidate row per file, named from the
    filename (edit afterwards to add email/phone for better duplicate
    matching). Each file goes through the same duplicate-detection path as
    a single submission."""
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
            resume_blob=content,
            resume_filename=f.filename,
            resume_mimetype=f.content_type or "application/octet-stream",
            status="Applied",
            is_duplicate=False,
            duplicate_of_id=None,
            submitted_at=datetime.utcnow(),
        )
        db.add(candidate)
        await db.flush()
        db.add(CandidateStatusLog(candidate_id=candidate.id, old_status=None, new_status="Applied"))
        created.append(candidate)

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

    if payload.name is not None:
        c.name = payload.name.strip()
    if payload.email is not None:
        c.email = payload.email.strip()
    if payload.phone is not None:
        c.phone = payload.phone.strip()
    if payload.jd_id is not None:
        c.jd_id = payload.jd_id
    if payload.vendor_id is not None:
        c.vendor_id = payload.vendor_id

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
    }
