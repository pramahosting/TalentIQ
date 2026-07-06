"""
TalentIQ - Shared Groq key pool with adaptive, self-healing routing.

Replaces a fixed per-user quota with something that actually scales with
demand: instead of rationing a single shared key by blocking users once
they hit a ceiling, this spreads load across a POOL of shared keys and
automatically routes around whichever ones are currently rate-limited.
Capacity grows by an admin adding another key to the pool — a one-row
insert via the existing generic admin table editor, not a code change —
rather than by adjusting a limit that only ever rations scarcity.

Health tracking is DB-backed rather than in-process memory, specifically
so this stays correct if the app ever runs as multiple replicas behind a
load balancer — each replica reads/writes the same cooldown state, rather
than every replica independently re-discovering that a key is rate-limited.

Backward compatible with a single legacy global Groq key: if the pool
table is empty, resolution falls back to the existing is_global=True
UserAPIKey row exactly as before this feature existed. An admin only
needs to populate the pool if/when they want the adaptive multi-key
behavior; nothing breaks if they never do.
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from models.models import UserAPIKey, GroqKeyPool

# Cooldown grows with consecutive failures (30s, 60s, 120s, 240s... capped
# at 10 minutes) — a key that's genuinely being rate-limited gets a real
# break instead of being retried every single request, but nothing is ever
# a PERMANENT ban; it's automatically tried again once the cooldown lapses,
# and a single success immediately clears it back to full health.
BASE_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 600


def _mask(key_value: str) -> str:
    """Same masking convention used in the admin pool UI (routers/admin.py)
    — last 4 characters only, safe to log or display, never the real key."""
    if not key_value:
        return ""
    tail = key_value[-4:] if len(key_value) >= 4 else key_value
    return f"...{tail}"


async def resolve_groq_key(db: AsyncSession, user_id: int) -> dict:
    """Resolves the Groq key (and optional per-key model override) to use
    for this request.

    Returns:
    {"groq_key": str | None, "model": str | None,
     "source": "personal" | "pool" | "legacy_global" | "none",
     "pool_id": int | None, "key_preview": str}

    key_preview is a masked identifier (last 4 chars, e.g. "...ab12") —
    safe to log or show in the UI so a specific request can be traced back
    to which key actually served it, without ever exposing the real value.
    This matters directly once there's more than one key in play: "why did
    this analysis fall back" is a very different question to answer when
    you can see it was specifically key "...ab12" that failed, versus
    just knowing "a key failed, somewhere."

    - "personal": the user's own saved key. Always exempt from pool/health
      logic entirely — it's their account, their budget.
    - "pool": the least-recently-used currently-healthy key from
      GroqKeyPool. Call record_key_outcome() after the attempt so future
      requests route around it if it turns out to be struggling.
    - "legacy_global": the pool is empty (or every pool entry is currently
      cooling down) — falls back to the original single shared
      is_global=True key, so existing single-key setups keep working with
      zero migration required.
    - "none": nothing configured at all, personal or shared — callers
      fall through to Ollama/keyword matching exactly as before this
      feature existed.
    """
    r = await db.execute(
        select(UserAPIKey.key_value).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.service == "groq",
            UserAPIKey.key_name == "api_key",
            UserAPIKey.is_global.isnot(True),
        )
    )
    personal_key = r.scalar_one_or_none()
    if personal_key:
        return {"groq_key": personal_key, "model": None, "source": "personal", "pool_id": None, "key_preview": _mask(personal_key)}

    now = datetime.utcnow()
    r = await db.execute(
        select(GroqKeyPool)
        .where(
            GroqKeyPool.is_active.is_(True),
            or_(GroqKeyPool.cooldown_until.is_(None), GroqKeyPool.cooldown_until < now),
        )
        .order_by(GroqKeyPool.last_used_at.asc().nulls_first())
        .limit(1)
    )
    entry = r.scalar_one_or_none()
    if entry:
        entry.last_used_at = now
        await db.commit()
        return {"groq_key": entry.key_value, "model": entry.model or None, "source": "pool", "pool_id": entry.id, "key_preview": _mask(entry.key_value)}

    # Pool is empty, or every entry is currently cooling down — fall back
    # to the legacy single global key so existing deployments with just
    # one shared key are completely unaffected by this feature existing.
    r = await db.execute(
        select(UserAPIKey.key_value).where(
            UserAPIKey.is_global.is_(True),
            UserAPIKey.service == "groq",
            UserAPIKey.key_name == "api_key",
        )
    )
    legacy_key = r.scalar_one_or_none()
    if legacy_key:
        return {"groq_key": legacy_key, "model": None, "source": "legacy_global", "pool_id": None, "key_preview": _mask(legacy_key)}

    return {"groq_key": None, "model": None, "source": "none", "pool_id": None, "key_preview": ""}


async def record_key_outcome(db: AsyncSession, pool_id: Optional[int], success: bool) -> None:
    """Updates a pool key's health after an attempt that used it.

    On success: immediately clears any cooldown and resets the error
    streak — a key that's working again is trusted again right away, no
    gradual "probation" period.

    On failure: applies an exponentially increasing cooldown so a key
    that's genuinely struggling (rate-limited, or a deeper problem) gets
    skipped for a while rather than being retried on every single request
    — but always automatically, never a permanent removal. An admin can
    still hard-disable a key via is_active if it turns out to be
    genuinely bad (e.g. revoked), but that's a deliberate action, not
    something this function does on its own.
    """
    if pool_id is None:
        return
    entry = await db.get(GroqKeyPool, pool_id)
    if not entry:
        return
    if success:
        entry.consecutive_errors = 0
        entry.cooldown_until = None
    else:
        entry.consecutive_errors += 1
        cooldown = min(BASE_COOLDOWN_SECONDS * (2 ** (entry.consecutive_errors - 1)), MAX_COOLDOWN_SECONDS)
        entry.cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown)
    await db.commit()
