"""
TalentIQ - Per-user sequential numbering.

Database primary keys (id) are global auto-increment and must stay that way
for FK integrity — but showing raw global IDs to users ("Session #147") is
confusing and leaks how much total activity is on the platform. This gives
every user their own clean 1, 2, 3... sequence per table, fully isolated
from other users' numbering.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


async def next_sequence_number(db: AsyncSession, model, user_id: int) -> int:
    """Returns MAX(sequence_number) + 1 for this user's rows in this table,
    or 1 if they have none yet. Call this when constructing a new row,
    before commit — e.g. MyModel(..., sequence_number=await next_sequence_number(db, MyModel, user_id))."""
    r = await db.execute(
        select(func.max(model.sequence_number)).where(model.user_id == user_id)
    )
    current_max = r.scalar()
    return (current_max or 0) + 1
