from unittest import mock

import pytest

from payments import tasks
from payments.models import PaymentOrder
from tests.fakes import FakeGateway

pytestmark = pytest.mark.django_db


def test_receipt_is_sent_once_even_if_the_task_runs_twice(make_booking_order):
    _, order = make_booking_order()
    with mock.patch("payments.notify.send_receipt") as sent:
        assert tasks.send_receipt.apply(args=[order.pk]).get() == "sent"
        assert tasks.send_receipt.apply(args=[order.pk]).get() == "skipped"
    assert sent.call_count == 1


def test_a_failed_send_releases_the_claim_so_the_retry_can_send(make_booking_order):
    _, order = make_booking_order()
    with mock.patch("payments.notify.send_receipt", side_effect=[RuntimeError("provider down"), None]) as sent:
        # In eager mode Celery runs the retry inline: attempt 1 fails, attempt 2 sends.
        tasks.send_receipt.apply(args=[order.pk])
        assert sent.call_count == 2
        # The receipt is now claimed, so a stray duplicate is still skipped.
        assert tasks.send_receipt.apply(args=[order.pk]).get() == "skipped"
    assert sent.call_count == 2


def test_refund_runs_once_even_if_the_task_runs_twice(make_booking_order):
    _, order = make_booking_order()
    PaymentOrder.objects.filter(pk=order.pk).update(
        status=PaymentOrder.Status.PAID, gateway_payment_id="pay_X", refund_reason="test"
    )

    assert tasks.refund_payment.apply(args=[order.pk]).get() == "refunded"
    assert tasks.refund_payment.apply(args=[order.pk]).get() == "already_refunded"
    assert len(FakeGateway.refunds) == 1
