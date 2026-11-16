"""Web Push subscription endpoints (tilt_ui-91a)."""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import PushSubscription
from ..services import push as push_service

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.get("/vapid-public-key")
async def vapid_public_key(db: AsyncSession = Depends(get_db)):
    _, public = await push_service.get_vapid_keys(db)
    return {"public_key": public}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    sub = (await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )).scalar_one_or_none()
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    sub.p256dh, sub.auth, sub.user_agent = body.p256dh, body.auth, user_agent
    await db.commit()
    return {"status": "ok"}


@router.post("/unsubscribe")
async def unsubscribe(body: UnsubscribeRequest, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    await db.commit()
    return {"status": "ok"}


@router.post("/test")
async def test_push():
    sent = await push_service.notify("BrewSignal", "Test notification: push is working.", "/")
    return {"sent": sent}
