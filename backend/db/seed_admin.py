"""
Seeds the default admin user on first startup.
username: admin  /  email: admin@talentiq.ai  /  password: Talent@1
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, func
from db.database import AsyncSessionLocal, engine, Base
from models.models import User
import bcrypt

async def seed():
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(User))).scalar()
        if count == 0:
            admin = User(
                name="Admin",
                email="admin@talentiq.ai",
                password_hash=bcrypt.hashpw(b"Talent@1", bcrypt.gensalt()).decode(),
                company="TalentIQ",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print("  [OK] Admin user created: admin@talentiq.ai / Talent@1")
        else:
            print(f"  [OK] {count} user(s) exist — skipping admin seed.")

if __name__ == "__main__":
    asyncio.run(seed())
