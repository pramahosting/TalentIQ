"""
Creates a new admin user, or resets an existing user's password and promotes
them to admin — unlike seed_admin.py, this works regardless of how many
users already exist in the database (seed_admin.py only ever runs once,
on a genuinely empty database).

Usage:
    python db/create_admin.py you@example.com "YourNewPassword123"

If a user with that email already exists, their password is reset and
their role is set to "admin". Otherwise a brand-new admin user is created.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from db.database import AsyncSessionLocal
from models.models import User
import bcrypt


async def create_or_promote_admin(email: str, password: str, name: str = "Admin"):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        if user:
            user.password_hash = password_hash
            user.role = "admin"
            user.is_active = True
            await db.commit()
            print(f"  [OK] Existing user updated: {email} is now an active admin with the new password.")
        else:
            user = User(
                name=name,
                email=email,
                password_hash=password_hash,
                company="TalentIQ",
                role="admin",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            print(f"  [OK] New admin user created: {email}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python db/create_admin.py you@example.com "YourNewPassword123" ["Display Name"]')
        sys.exit(1)
    email_arg = sys.argv[1]
    password_arg = sys.argv[2]
    name_arg = sys.argv[3] if len(sys.argv) > 3 else "Admin"
    asyncio.run(create_or_promote_admin(email_arg, password_arg, name_arg))
