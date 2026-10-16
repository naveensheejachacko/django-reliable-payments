import hashlib
import hmac
import itertools
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from payments.models import Booking, PaymentOrder, Subscription
from tests.fakes import FakeGateway

WEBHOOK_URL = "/payments/webhooks/razorpay/"
_ids = itertools.count(1)


@pytest.fixture(autouse=True)
def _isolate(settings):
    settings.PAYMENT_GATEWAY = "tests.fakes.FakeGateway"
    settings.RAZORPAY_WEBHOOK_SECRET = "test-secret"
    FakeGateway.refunds.clear()
    cache.clear()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username=f"user{next(_ids)}", password="x")


@pytest.fixture
def make_booking_order(user):
    def make(slot="room-1@2026-10-20T22:00", owner=None):
        booking = Booking.objects.create(user=owner or user, slot=slot)
        n = next(_ids)
        order = PaymentOrder.objects.create(
            user=owner or user, kind="booking", object_id=booking.pk,
            amount_paise=49900, gateway_order_id=f"order_{n}",
        )
        return booking, order

    return make


@pytest.fixture
def make_subscription_order(user):
    def make(plan="monthly", active_until=None):
        sub = Subscription.objects.create(user=user, plan=plan, active_until=active_until)
        order = PaymentOrder.objects.create(
            user=user, kind="subscription", object_id=sub.pk,
            amount_paise=29900, gateway_order_id=f"order_{next(_ids)}",
        )
        return sub, order

    return make


def event(kind, order_id, payment_id="pay_1"):
    return {"event": kind, "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}}}


@pytest.fixture
def post_webhook(client, django_capture_on_commit_callbacks):
    """Sign and send a webhook, running on_commit callbacks the way a real commit would."""

    def send(payload, event_id=None, secret="test-secret", signature=None):
        body = json.dumps(payload).encode()
        sig = signature or hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with django_capture_on_commit_callbacks(execute=True):
            return client.post(
                WEBHOOK_URL, data=body, content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=sig,
                HTTP_X_RAZORPAY_EVENT_ID=event_id or f"evt_{next(_ids)}",
            )

    return send
