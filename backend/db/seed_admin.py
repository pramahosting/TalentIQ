"""
Seeds/repairs the default admin user on every startup.
username: admin  /  email: admin@talentiq.ai  /  password: Talent@1

Unlike before, this now ALWAYS ensures the admin@talentiq.ai account
exists with the correct password hash and is active — fixing cases
where a stale or incorrectly-hashed admin row exists in the DB from
an earlier deployment.
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, func
from db.database import AsyncSessionLocal, engine, Base
from models.models import User
import bcrypt

ADMIN_EMAIL = "admin@talentiq.ai"
ADMIN_PASSWORD = "Talent@1"


async def seed():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        admin = result.scalar_one_or_none()

        new_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()

        if admin is None:
            admin = User(
                name="Admin",
                email=ADMIN_EMAIL,
                password_hash=new_hash,
                company="TalentIQ",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print(f"  [OK] Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        else:
            # Verify the existing hash actually works; if not, repair it.
            try:
                valid = bcrypt.checkpw(ADMIN_PASSWORD.encode(), admin.password_hash.encode())
            except Exception:
                valid = False

            changed = False
            if not valid:
                admin.password_hash = new_hash
                changed = True
            if admin.role != "admin":
                admin.role = "admin"
                changed = True
            if not admin.is_active:
                admin.is_active = True
                changed = True

            if changed:
                await db.commit()
                print(f"  [OK] Admin user repaired: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
            else:
                print(f"  [OK] Admin user verified OK: {ADMIN_EMAIL}")

        total = (await db.execute(select(func.count()).select_from(User))).scalar()
        print(f"  [OK] {total} user(s) total in database.")


if __name__ == "__main__":
    asyncio.run(seed())
