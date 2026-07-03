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
