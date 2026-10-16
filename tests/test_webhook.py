from unittest import mock

import pytest

from payments.models import Booking, PaymentOrder, WebhookEvent
from tests.conftest import event
from tests.fakes import FakeGateway

pytestmark = pytest.mark.django_db


@pytest.fixture
def receipts():
    with mock.patch("payments.notify.send_receipt") as sent:
        yield sent


def test_bad_signature_is_rejected_before_any_write(post_webhook, make_booking_order):
    booking, order = make_booking_order()
    response = post_webhook(event("payment.captured", order.gateway_order_id), signature="0" * 64)

    assert response.status_code == 400
    assert WebhookEvent.objects.count() == 0
    order.refresh_from_db()
    assert order.status == PaymentOrder.Status.CREATED


def test_captured_payment_confirms_the_booking_and_sends_one_receipt(post_webhook, make_booking_order, receipts):
    booking, order = make_booking_order()
    response = post_webhook(event("payment.captured", order.gateway_order_id, "pay_A"))

    assert response.json() == {"status": "confirmed"}
    order.refresh_from_db()
    booking.refresh_from_db()
    assert order.status == PaymentOrder.Status.PAID
    assert order.gateway_payment_id == "pay_A"
    assert booking.status == Booking.Status.CONFIRMED
    assert receipts.call_count == 1


def test_same_event_delivered_twice_is_processed_once(post_webhook, make_booking_order, receipts):
    _, order = make_booking_order()
    payload = event("payment.captured", order.gateway_order_id)

    first = post_webhook(payload, event_id="evt_same")
    second = post_webhook(payload, event_id="evt_same")

    assert first.json() == {"status": "confirmed"}
    assert second.json() == {"status": "duplicate"}
    assert receipts.call_count == 1


def test_same_payment_under_a_new_event_id_is_still_a_no_op(post_webhook, make_booking_order, receipts):
    _, order = make_booking_order()
    payload = event("payment.captured", order.gateway_order_id)

    post_webhook(payload, event_id="evt_1")
    second = post_webhook(payload, event_id="evt_2")

    assert second.json() == {"status": "duplicate"}
    assert receipts.call_count == 1


def test_losing_the_race_for_a_slot_refunds_automatically(post_webhook, make_booking_order, user, receipts):
    slot = "room-7@2026-10-21T22:00"
    winner_booking, winner = make_booking_order(slot=slot)
    loser_booking, loser = make_booking_order(slot=slot)

    post_webhook(event("payment.captured", winner.gateway_order_id, "pay_W"))
    response = post_webhook(event("payment.captured", loser.gateway_order_id, "pay_L"))

    assert response.json() == {"status": "refund_queued"}
    winner_booking.refresh_from_db()
    loser_booking.refresh_from_db()
    loser.refresh_from_db()
    assert winner_booking.status == Booking.Status.CONFIRMED
    assert loser_booking.status == Booking.Status.CANCELLED
    assert loser.status == PaymentOrder.Status.REFUNDED
    assert FakeGateway.refunds == [{"payment_id": "pay_L", "amount": 49900, "reason": loser.refund_reason}]
    assert receipts.call_count == 1  # only the winner gets a receipt


def test_failed_payment_cancels_the_pending_booking(post_webhook, make_booking_order):
    booking, order = make_booking_order()
    response = post_webhook(event("payment.failed", order.gateway_order_id))

    assert response.json() == {"status": "failed"}
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_unknown_order_is_acknowledged_so_the_gateway_stops_retrying(post_webhook):
    response = post_webhook(event("payment.captured", "order_not_ours"))

    assert response.status_code == 200
    assert response.json() == {"status": "unknown_order"}
