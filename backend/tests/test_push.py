"""Web Push: subscription API, alert hook, dead-subscription cleanup (tilt_ui-91a)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pywebpush import WebPushException
from sqlalchemy import select

from backend.models import Batch, PushSubscription
from backend.services import alert_service, push


@pytest.mark.asyncio
async def test_subscribe_upserts_and_unsubscribe_deletes(client, test_db):
    body = {"endpoint": "https://push.example/abc", "p256dh": "k1", "auth": "a1"}
    assert (await client.post("/api/push/subscribe", json=body)).status_code == 200
    body["p256dh"] = "k2"
    assert (await client.post("/api/push/subscribe", json=body)).status_code == 200
    rows = (await test_db.execute(select(PushSubscription))).scalars().all()
    assert len(rows) == 1 and rows[0].p256dh == "k2"

    await client.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]})
    await test_db.rollback()
    assert (await test_db.execute(select(PushSubscription))).scalars().all() == []


@pytest.mark.asyncio
async def test_vapid_public_key_is_stable(client):
    a = (await client.get("/api/push/vapid-public-key")).json()["public_key"]
    b = (await client.get("/api/push/vapid-public-key")).json()["public_key"]
    assert a and a == b


@pytest.mark.asyncio
async def test_upsert_alert_notifies_only_for_new_alert(test_db):
    batch = Batch(name="IPA", status="fermenting")
    test_db.add(batch)
    await test_db.commit()
    now = datetime.now(timezone.utc)
    args = dict(db=test_db, batch_id=batch.id, device_id="d", alert_type="dry_hop_due",
                severity="warning", message="m", context=None, trigger_reading_id=None, now=now)
    with patch.object(push, "notify", new=AsyncMock()) as notify:
        await alert_service._upsert_alert(**args)
        await test_db.commit()
        await alert_service._upsert_alert(**args)  # refresh of the active alert
        await push.asyncio.sleep(0)
        notify.assert_awaited_once_with("Dry hop now: IPA", "m", f"/batches/{batch.id}")

        await alert_service._upsert_alert(**{**args, "alert_type": "rest_started", "severity": "info"})
        await push.asyncio.sleep(0)
        assert notify.await_count == 1  # informational: no push


@pytest.mark.asyncio
async def test_notify_deletes_subscription_on_410(test_db):
    test_db.add(PushSubscription(endpoint="https://push.example/gone", p256dh="k", auth="a"))
    await test_db.commit()
    resp = MagicMock(status_code=410)
    err = WebPushException("gone", response=resp)

    class Factory:  # notify opens its own session; hand it the test one
        def __call__(self):
            return self

        async def __aenter__(self):
            return test_db

        async def __aexit__(self, *a):
            return False

    with patch.object(push.database, "async_session_factory", Factory()), \
         patch.object(push, "webpush", side_effect=err):
        assert await push.notify("t", "b", "/") == 0
    assert (await test_db.execute(select(PushSubscription))).scalars().all() == []
