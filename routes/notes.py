from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
import models, schemas
from utils import get_current_user
from typing import List
from dependencies.redis import get_redis
import json
from models import Note, User
from schemas import NoteOut
from redis.asyncio.client import Redis  # ✅ дұрыс импорт
from celery_app import send_mock_email

router = APIRouter(prefix="/notes", tags=["Notes"])

# POST /notes
@router.post("/", response_model=schemas.NoteOut)
async def create_note(
    note: schemas.NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis)  # ✅ міндетті аргумент
):
    new_note = Note(**note.dict(), owner_id=current_user.id)
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)

    # ✅ Кэшті тазарту
    pattern = f"notes:{current_user.id}:*"
    keys = await redis.keys(pattern)
    if keys:
        await redis.delete(*keys)
    return new_note

# GET /notes
@router.get("/")
async def get_notes(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis)
):
    cache_key = f"notes:{current_user.id}:{skip}:{limit}"
    cached_data = await redis.get(cache_key)

    if cached_data:
        return json.loads(cached_data)

    result = await db.execute(
        select(Note).where(Note.owner_id == current_user.id).offset(skip).limit(limit)
    )
    notes = result.scalars().all()
    serialized = [NoteOut.from_orm(note).dict() for note in notes]

    await redis.set(cache_key, json.dumps(serialized), ex=300)
    return serialized

# GET /notes/{note_id}
@router.get("/{note_id}", response_model=schemas.NoteOut)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note or note.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    return note

# PUT /notes/{note_id}
@router.put("/{note_id}", response_model=schemas.NoteOut)
async def update_note(
    note_id: int,
    updated_note: schemas.NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis)
):
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note or note.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    for key, value in updated_note.dict(exclude_unset=True).items():
        setattr(note, key, value)

    await db.commit()
    await db.refresh(note)

    # ✅ Кэшті тазарту
    pattern = f"notes:{current_user.id}:*"
    keys = await redis.keys(pattern)
    if keys:
        await redis.delete(*keys)

    return note

# DELETE /notes/{note_id}
@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis)
):
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note or note.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    await db.delete(note)
    await db.commit()

    # ✅ Кэшті тазарту
    pattern = f"notes:{current_user.id}:*"
    keys = await redis.keys(pattern)
    if keys:
        await redis.delete(*keys)

    return {"detail": "Note deleted successfully"}

