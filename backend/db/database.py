"""
TalentIQ - Uses AccFino's Neon 'neondb' database but all tables
are prefixed with 'tiq_' so they never clash with AccFino tables.
"""
import os, re
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_DEFAULT = (
    "postgresql+asyncpg://neondb_owner:npg_XH2QFas3gYDd"
    "@ep-dawn-scene-aqma9lhs.c-8.us-east-1.aws.neon.tech/neondb"
)

DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT).strip()

if DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL = re.sub(r'[?&]sslmode=\S+', '', DATABASE_URL).rstrip('?').strip()

engine = create_async_engine(
    DATABASE_URL, echo=False, future=True,
    pool_size=2, max_overflow=3, pool_timeout=60,
    pool_recycle=300, pool_pre_ping=True,
    connect_args={"ssl": "require"},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession,
    expire_on_commit=False, autoflush=False, autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
