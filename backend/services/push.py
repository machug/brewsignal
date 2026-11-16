"""Web Push delivery (tilt_ui-91a). A push failure must never break alert handling or ingest."""
import asyncio
import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from .. import database
from ..config import get_settings
from ..models import PushSubscription
from ..routers.config import get_config_value, set_config_value

logger = logging.getLogger(__name__)

# Apple's push service rejects a "mailto:...@localhost" subject (403 BadJwtToken),
# so default to the project URL; override with the vapid_subject config value.
VAPID_SUBJECT = "https://github.com/machug/brewsignal"

_tasks: set[asyncio.Task] = set()  # keep fire-and-forget tasks alive until done


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def get_vapid_keys(db) -> tuple[str, str]:
    """(private, public) VAPID keys, generated and stored on first use. Caller commits."""
    private = await get_config_value(db, "vapid_private_key")
    public = await get_config_value(db, "vapid_public_key")
    if not (private and public):
        v = Vapid()
        v.generate_keys()
        private = _b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
        public = _b64(v.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        await set_config_value(db, "vapid_private_key", private)
        await set_config_value(db, "vapid_public_key", public)
        await db.commit()
    return private, public


def _send(sub: dict, payload: str, private: str, subject: str) -> None:
    webpush(sub, payload, vapid_private_key=private, vapid_claims={"sub": subject}, ttl=86400, timeout=10)


async def notify(title: str, body: str, url: str = "/") -> int:
    """Send to every subscription. Returns how many were delivered. Never raises."""
    # ponytail: subscriptions have no owner, so push is local (single-user Pi)
    # only; cloud needs a user_id on PushSubscription and a filter here.
    if get_settings().is_cloud:
        return 0
    try:
        async with database.async_session_factory() as db:
            subs = (await db.execute(select(PushSubscription))).scalars().all()
            if not subs:
                return 0  # cheap no-op: also what tests hit
            private, _ = await get_vapid_keys(db)
            subject = await get_config_value(db, "vapid_subject") or VAPID_SUBJECT
            payload = json.dumps({"title": title, "body": body, "url": url})
            sent, dead = 0, []
            for s in subs:
                info = {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}
                try:
                    await asyncio.to_thread(_send, info, payload, private, subject)
                    sent += 1
                except WebPushException as e:
                    status = getattr(e.response, "status_code", None)
                    if status in (404, 410):
                        dead.append(s.endpoint)  # subscription expired or unsubscribed
                    else:
                        logger.warning(f"Web push failed ({status}): {e}")
                except Exception as e:
                    logger.warning(f"Web push failed: {e}")
            if dead:
                await db.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(dead)))
                await db.commit()
            return sent
    except Exception as e:
        logger.error(f"Web push notify failed: {e}")
        return 0


def notify_soon(title: str, body: str, url: str = "/") -> None:
    """Fire and forget notify() from async code."""
    task = asyncio.create_task(notify(title, body, url))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
