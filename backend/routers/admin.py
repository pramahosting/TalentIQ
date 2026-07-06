"""
TalentIQ - Admin Router
Full database browser, user management, record editing for all tiq_* tables.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, update, delete, inspect, func, bindparam
from sqlalchemy.engine import Row
from pydantic import BaseModel

from db.database import get_db, engine
from models.models import User
from utils.auth_utils import get_current_user, require_admin

router = APIRouter()

# ── TABLE LIST ───────────────────────────────────────────────────────

@router.get("/tables")
async def list_tables(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """List all tiq_* tables with row counts."""
    result = await db.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'tiq_%' ORDER BY tablename"
    ))
    tables = []
    for row in result.fetchall():
        tname = row[0]
        cnt = (await db.execute(text(f'SELECT COUNT(*) FROM "{tname}"'))).scalar()
        tables.append({"table": tname, "rows": cnt})
    return tables


# ── TABLE SCHEMA ─────────────────────────────────────────────────────

@router.get("/tables/{table}/schema")
async def table_schema(table: str, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get column names and types for a table."""
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    result = await db.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_name = :t AND table_schema = 'public' "
        "ORDER BY ordinal_position",
    ), {"t": table})
    return [dict(r._mapping) for r in result.fetchall()]


# ── TABLE ROWS ───────────────────────────────────────────────────────

@router.get("/tables/{table}/rows")
async def table_rows(
    table: str,
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    offset = (page - 1) * page_size
    total = (await db.execute(text(f'SELECT COUNT(*) FROM "{table}"'))).scalar()
    rows = await db.execute(text(f'SELECT * FROM "{table}" ORDER BY id DESC LIMIT :lim OFFSET :off'), {"lim": page_size, "off": offset})
    cols = list(rows.keys())
    data = [dict(zip(cols, r)) for r in rows.fetchall()]
    # Convert non-serialisable types
    for row in data:
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
            elif v is None:
                row[k] = None
            else:
                row[k] = str(v) if not isinstance(v, (int, float, bool, str, dict, list)) else v
    return {"total": total, "page": page, "page_size": page_size, "columns": cols, "rows": data}


# ── UPDATE ROW ───────────────────────────────────────────────────────

class RowUpdate(BaseModel):
    data: Dict[str, Any]

@router.put("/tables/{table}/rows/{row_id}")
async def update_row(
    table: str,
    row_id: int,
    payload: RowUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    # Build SET clause
    safe = {k: v for k, v in payload.data.items() if k != "id"}
    if not safe:
        raise HTTPException(400, "No fields to update")
    sets = ", ".join(f'"{k}" = :{k}' for k in safe)
    safe["_id"] = row_id
    await db.execute(text(f'UPDATE "{table}" SET {sets} WHERE id = :_id'), safe)
    await db.commit()
    return {"message": "Row updated"}


# ── DELETE ROW ───────────────────────────────────────────────────────

@router.delete("/tables/{table}/rows/{row_id}")
async def delete_row(
    table: str,
    row_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    await db.execute(text(f'DELETE FROM "{table}" WHERE id = :id'), {"id": row_id})
    await db.commit()
    return {"message": "Row deleted"}


@router.delete("/tables/{table}/rows")
async def bulk_delete_rows(
    table: str,
    payload: dict,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    ids = payload.get("ids", [])
    if not ids:
        raise HTTPException(400, "No row ids provided")
    # A raw Python list bound to :ids with ANY(:ids) doesn't reliably expand
    # through SQLAlchemy's text() + asyncpg — bindparam(expanding=True) with
    # an IN clause is the correct, driver-safe way to bind a variable-length
    # list of values in a raw SQL statement.
    stmt = text(f'DELETE FROM "{table}" WHERE id IN :ids').bindparams(
        bindparam("ids", expanding=True)
    )
    result = await db.execute(stmt, {"ids": ids})
    await db.commit()
    return {"message": f"Deleted {result.rowcount} row(s)"}


# ── INSERT ROW ───────────────────────────────────────────────────────

@router.post("/tables/{table}/rows")
async def insert_row(
    table: str,
    payload: RowUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not table.startswith("tiq_"):
        raise HTTPException(403, "Only tiq_* tables are accessible")
    safe = {k: v for k, v in payload.data.items() if k != "id" and v is not None and v != ""}
    if not safe:
        raise HTTPException(400, "No data provided")
    cols = ", ".join(f'"{k}"' for k in safe)
    vals = ", ".join(f":{k}" for k in safe)
    result = await db.execute(text(f'INSERT INTO "{table}" ({cols}) VALUES ({vals}) RETURNING id'), safe)
    await db.commit()
    return {"message": "Row inserted", "id": result.scalar()}


# ── USER MANAGEMENT (Registration table) ─────────────────────────────

@router.get("/users")
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id, "name": u.name, "email": u.email,
            "company": u.company, "phone": u.phone, "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if payload.name is not None: user.name = payload.name
    if payload.email is not None: user.email = payload.email
    if payload.company is not None: user.company = payload.company
    if payload.phone is not None: user.phone = payload.phone
    if payload.role is not None: user.role = payload.role
    if payload.is_active is not None: user.is_active = payload.is_active
    if payload.password:
        import bcrypt
        user.password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    await db.commit()
    return {"message": "User updated"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current.id:
        raise HTTPException(400, "Cannot delete your own account")
    await db.execute(text("DELETE FROM tiq_users WHERE id = :id"), {"id": user_id})
    await db.commit()
    return {"message": "User deleted"}


# ── RAW SQL QUERY ────────────────────────────────────────────────────

class SQLQuery(BaseModel):
    sql: str

@router.post("/query")
async def run_query(
    payload: SQLQuery,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Execute a raw SELECT query (read-only)."""
    sql = payload.sql.strip()
    if not sql.lower().startswith("select"):
        raise HTTPException(400, "Only SELECT queries are allowed here. Use table endpoints for writes.")
    try:
        result = await db.execute(text(sql))
        cols = list(result.keys())
        rows = []
        for r in result.fetchall():
            row = {}
            for k, v in zip(cols, r):
                if hasattr(v, 'isoformat'): row[k] = v.isoformat()
                elif isinstance(v, (int, float, bool, str, dict, list, type(None))): row[k] = v
                else: row[k] = str(v)
            rows.append(row)
        return {"columns": cols, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── GROQ KEY POOL ────────────────────────────────────────────────────
# A dedicated, friendlier interface for managing the shared Groq key pool
# (see utils/groq_pool.py) — the same table (tiq_groq_key_pool) is also
# reachable through the generic File Manager, but a purpose-built list/
# add/remove UI beats hand-editing raw rows for something admins will do
# repeatedly. Admin-only: this is a platform-wide shared resource, same
# security tier as the existing global Groq/Ollama/Adzuna keys.

class GroqPoolKeyIn(BaseModel):
    key_value: str
    model: Optional[str] = None

class GroqPoolKeyOut(BaseModel):
    id: int
    key_preview: str   # never the real key — last 4 chars only, enough to tell entries apart
    model: Optional[str] = None
    is_active: bool
    consecutive_errors: int
    cooldown_until: Optional[str] = None
    last_used_at: Optional[str] = None
    added_at: Optional[str] = None


def _mask_key(key_value: str) -> str:
    if not key_value:
        return ""
    tail = key_value[-4:] if len(key_value) >= 4 else key_value
    return f"...{tail}"


class GroqModelsQuery(BaseModel):
    key_value: str


@router.post("/groq-pool/models")
async def list_groq_models_for_key(
    payload: GroqModelsQuery,
    _: User = Depends(require_admin),
):
    """Fetches the REAL, current list of models available to a Groq key,
    directly from Groq's own API (OpenAI-compatible /models endpoint) —
    rather than a hardcoded list in our own code, which is exactly the
    kind of thing that goes stale the moment Groq adds or retires a
    model (we hit this directly, twice, earlier this session). Also
    doubles as a quick validity check for a key before it's added to the
    pool — an invalid/revoked key will fail here with a clear reason
    instead of silently sitting in the pool until it's actually used."""
    import requests as _requests
    key_value = payload.key_value.strip()
    if not key_value:
        raise HTTPException(400, "API key value is required.")
    try:
        resp = _requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key_value}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        models = sorted(
            [m["id"] for m in data.get("data", []) if m.get("id")],
        )
        return {"models": models}
    except _requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status == 401:
            raise HTTPException(400, "This key was rejected by Groq — check it's correct and active.")
        raise HTTPException(400, f"Groq returned an error (status {status}) when listing models for this key.")
    except Exception as e:
        raise HTTPException(400, f"Could not reach Groq to list models: {type(e).__name__}")


@router.get("/groq-pool", response_model=List[GroqPoolKeyOut])
async def list_groq_pool(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from models.models import GroqKeyPool
    result = await db.execute(select(GroqKeyPool).order_by(GroqKeyPool.added_at.desc()))
    entries = result.scalars().all()
    return [
        GroqPoolKeyOut(
            id=e.id, key_preview=_mask_key(e.key_value), model=e.model,
            is_active=e.is_active, consecutive_errors=e.consecutive_errors,
            cooldown_until=e.cooldown_until.isoformat() if e.cooldown_until else None,
            last_used_at=e.last_used_at.isoformat() if e.last_used_at else None,
            added_at=e.added_at.isoformat() if e.added_at else None,
        )
        for e in entries
    ]


@router.post("/groq-pool", response_model=GroqPoolKeyOut, status_code=201)
async def add_groq_pool_key(
    payload: GroqPoolKeyIn,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from models.models import GroqKeyPool
    key_value = payload.key_value.strip()
    if not key_value:
        raise HTTPException(400, "API key value is required.")

    existing = (await db.execute(select(GroqKeyPool).where(GroqKeyPool.key_value == key_value))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "This exact key is already in the pool.")

    entry = GroqKeyPool(key_value=key_value, model=(payload.model or "").strip() or None, is_active=True)
    db.add(entry)
    await db.flush()
    return GroqPoolKeyOut(
        id=entry.id, key_preview=_mask_key(entry.key_value), model=entry.model,
        is_active=entry.is_active, consecutive_errors=entry.consecutive_errors,
        cooldown_until=None, last_used_at=None,
        added_at=entry.added_at.isoformat() if entry.added_at else None,
    )


class GroqPoolKeyPatch(BaseModel):
    is_active: Optional[bool] = None
    model: Optional[str] = None


@router.patch("/groq-pool/{pool_id}", response_model=GroqPoolKeyOut)
async def update_groq_pool_key(
    pool_id: int,
    payload: GroqPoolKeyPatch,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from models.models import GroqKeyPool
    entry = await db.get(GroqKeyPool, pool_id)
    if not entry:
        raise HTTPException(404, "Pool key not found.")
    if payload.is_active is not None:
        entry.is_active = payload.is_active
    if payload.model is not None:
        entry.model = payload.model.strip() or None
    # Reactivating a key clears any lingering cooldown/error streak — an
    # admin flipping it back on is a deliberate "trust this again" signal.
    if payload.is_active is True:
        entry.consecutive_errors = 0
        entry.cooldown_until = None
    await db.flush()
    return GroqPoolKeyOut(
        id=entry.id, key_preview=_mask_key(entry.key_value), model=entry.model,
        is_active=entry.is_active, consecutive_errors=entry.consecutive_errors,
        cooldown_until=entry.cooldown_until.isoformat() if entry.cooldown_until else None,
        last_used_at=entry.last_used_at.isoformat() if entry.last_used_at else None,
        added_at=entry.added_at.isoformat() if entry.added_at else None,
    )


@router.delete("/groq-pool/{pool_id}")
async def delete_groq_pool_key(
    pool_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from models.models import GroqKeyPool
    entry = await db.get(GroqKeyPool, pool_id)
    if not entry:
        raise HTTPException(404, "Pool key not found.")
    await db.delete(entry)
    return {"message": "Deleted"}
