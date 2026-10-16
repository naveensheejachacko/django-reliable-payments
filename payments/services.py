"""Payment state changes. Every function here is safe to call more than once."""

import logging

from django.db import transaction
from django.utils import timezone

from .handlers import SlotTaken
from .models import PaymentOrder
from .registry import get_handler

logger = logging.getLogger(__name__)


@transaction.atomic
def confirm_payment(gateway_order_id: str, gateway_payment_id: str) -> str:
    """Mark an order paid and fulfil it, exactly once.

    The row lock serialises concurrent deliveries of the same payment (Razorpay can
    send `payment.captured` more than once, and the client may also call back), so
    the second caller sees PAID and does nothing.
    """
    order = PaymentOrder.objects.select_for_update().get(gateway_order_id=gateway_order_id)
    if order.status in (PaymentOrder.Status.PAID, PaymentOrder.Status.REFUNDED):
        return "duplicate"

    order.status = PaymentOrder.Status.PAID
    order.gateway_payment_id = gateway_payment_id
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "gateway_payment_id", "paid_at", "updated_at"])

    try:
        get_handler(order.kind).on_paid(order)
    except SlotTaken as exc:
        # The money arrived but the slot is gone. Refund automatically instead of
        # leaving it for a support ticket.
        order.refund_reason = f"slot {exc.slot} was taken before this payment completed"
        order.save(update_fields=["refund_reason", "updated_at"])
        transaction.on_commit(lambda: _tasks().refund_payment.delay(order.pk))
        logger.warning("Order %s lost the race for %s; refund queued", order.gateway_order_id, exc.slot)
        return "refund_queued"

    # Side effects only after the commit, so a rollback never sends a receipt.
    transaction.on_commit(lambda: _tasks().send_receipt.delay(order.pk))
    return "confirmed"


@transaction.atomic
def fail_payment(gateway_order_id: str) -> str:
    order = PaymentOrder.objects.select_for_update().get(gateway_order_id=gateway_order_id)
    if order.status != PaymentOrder.Status.CREATED:
        return "ignored"
    order.status = PaymentOrder.Status.FAILED
    order.save(update_fields=["status", "updated_at"])
    get_handler(order.kind).on_failed(order)
    return "failed"


def _tasks():
    from . import tasks  # avoid a circular import at module load

    return tasks
