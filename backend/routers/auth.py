"""
TalentIQ – Authentication Router
Handles register, login, logout, password reset, profile update, API key management
"""

from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.database import get_db
from models.models import User, UserAPIKey, AuditLog
from schemas.schemas import (
    UserRegister, UserLogin, UserOut, TokenOut,
    PasswordResetRequest, PasswordReset, UserUpdate,
    APIKeyCreate, APIKeyOut,
)
from utils.auth_utils import (
    hash_password, verify_password, create_access_token,
    generate_reset_token, get_current_user, require_admin
)

router = APIRouter()


# ─── REGISTER ────────────────────────────────

@router.post("/register", response_model=TokenOut, status_code=201)
async def register(payload: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    # Check duplicate email
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # First ever user becomes admin
    count_result = await db.execute(select(func.count()).select_from(User))
    is_first = count_result.scalar() == 0

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        company=payload.company,
        phone=payload.phone,
        address=payload.address,
        role='admin' if is_first else 'user',
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id)})

    db.add(AuditLog(
        user_id=user.id,
        action="register",
        resource="user",
        ip_address=request.client.host if request.client else None,
    ))

    return TokenOut(access_token=token, user=UserOut.model_validate(user))


# ─── LOGIN ────────────────────────────────────

@router.post("/login", response_model=TokenOut)
async def login(payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    user.last_login = datetime.utcnow()
    token = create_access_token({"sub": str(user.id)})

    db.add(AuditLog(
        user_id=user.id,
        action="login",
        resource="user",
        ip_address=request.client.host if request.client else None,
    ))

    return TokenOut(access_token=token, user=UserOut.model_validate(user))


# ─── GET PROFILE ──────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


# ─── UPDATE PROFILE ───────────────────────────

@router.put("/me", response_model=UserOut)
async def update_profile(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    current_user.updated_at = datetime.utcnow()
    return UserOut.model_validate(current_user)


# ─── CHANGE PASSWORD ──────────────────────────

@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    current_user.password_hash = hash_password(new_password)
    return {"message": "Password changed successfully"}


# ─── PASSWORD RESET REQUEST ───────────────────

@router.post("/reset-request")
async def reset_request(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user:
        token = generate_reset_token()
        user.reset_token = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        # In production: send email with reset link
        return {"message": "Reset token generated", "token": token}  # Remove token from prod response
    return {"message": "If that email exists, a reset link was sent"}


# ─── PASSWORD RESET ───────────────────────────

@router.post("/reset-password")
async def reset_password(payload: PasswordReset, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(
            User.reset_token == payload.token,
            User.reset_token_expiry > datetime.utcnow(),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.password_hash = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    return {"message": "Password reset successfully"}


# ─── API KEYS MANAGEMENT ──────────────────────

@router.post("/api-keys", response_model=APIKeyOut, status_code=201)
async def save_api_key(
    payload: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Adzuna/Groq/Ollama are admin-managed only now — every other user
    # inherits whatever the admin configures as the global fallback, so
    # there's no legitimate reason for a non-admin to save their own here.
    # (is_global handling below is effectively moot for non-admins once
    # this fires, but is left in place as defense-in-depth.)
    from utils.credentials import SHAREABLE_SERVICES
    if payload.service in SHAREABLE_SERVICES and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"{payload.service.capitalize()} is configured by your administrator. Contact them to update it.",
        )

    # is_global is a privileged flag: only an admin may set it, and only for
    # the services explicitly allowed to be shared (see utils/credentials.py).
    # Any other combination is silently coerced to False rather than
    # rejected outright, so a non-admin's request still succeeds — it just
    # saves as a normal private key instead of a platform-wide one.
    is_global = bool(
        payload.is_global
        and current_user.role == "admin"
        and payload.service in SHAREABLE_SERVICES
    )

    # Replace if same service+key_name exists for THIS user (global keys are
    # still stored under the admin's own user_id — is_global is what makes
    # them visible platform-wide, not a change of ownership).
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == current_user.id,
            UserAPIKey.service == payload.service,
            UserAPIKey.key_name == payload.key_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.key_value = payload.key_value
        existing.is_global = is_global
        return APIKeyOut.model_validate(existing)

    key = UserAPIKey(
        user_id=current_user.id,
        service=payload.service,
        key_name=payload.key_name,
        key_value=payload.key_value,
        is_global=is_global,
    )
    db.add(key)
    await db.flush()
    return APIKeyOut.model_validate(key)


@router.get("/api-keys", response_model=List[APIKeyOut])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == current_user.id)
    )
    return [APIKeyOut.model_validate(k) for k in result.scalars().all()]


@router.get("/global-keys", response_model=List[APIKeyOut])
async def list_global_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Visible to every user (not just admins) so people can see which
    shared services (Groq/Ollama/Adzuna) are already configured platform-
    wide — never returns the actual secret value, same as /api-keys."""
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.is_global.is_(True))
    )
    return [APIKeyOut.model_validate(k) for k in result.scalars().all()]


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(UserAPIKey).where(UserAPIKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    # A global key may be managed by any admin (not just the one who
    # originally saved it); every other key is strictly private to its
    # owner, admins included — an admin cannot delete another user's
    # private LinkedIn/SMTP/MorphCast credentials.
    is_owner = key.user_id == current_user.id
    is_admin_managing_global = key.is_global and current_user.role == "admin"
    if not (is_owner or is_admin_managing_global):
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key)
    return {"message": "Deleted"}


# ─── ADMIN – USER MANAGEMENT ─────────────────

@router.get("/users", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(User))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    return {"message": "User deactivated"}
