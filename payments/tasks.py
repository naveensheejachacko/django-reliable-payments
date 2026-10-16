import logging

from celery import shared_task
from django.core.cache import cache
from django.db import transaction

from . import notify
from .gateway import get_gateway
from .models import PaymentOrder

logger = logging.getLogger(__name__)

RECEIPT_KEY = "receipt-sent:{order_id}"
RECEIPT_KEY_TTL = 7 * 24 * 3600


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_receipt(self, order_id: int) -> str:
    """At most one receipt per order, even if the task is retried or queued twice.

    `cache.add` is an atomic set-if-absent (SET NX on Redis): the first run claims
    the key, every later run sees it and skips.
    """
    key = RECEIPT_KEY.format(order_id=order_id)
    if not cache.add(key, 1, timeout=RECEIPT_KEY_TTL):
        return "skipped"
    order = PaymentOrder.objects.get(pk=order_id)
    try:
        notify.send_receipt(order)
    except Exception as exc:
        cache.delete(key)  # release the claim so the retry can send it
        raise self.retry(exc=exc)
    return "sent"


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def refund_payment(self, order_id: int) -> str:
    """Refund once. The row lock stops two retries from refunding in parallel."""
    try:
        with transaction.atomic():
            order = PaymentOrder.objects.select_for_update().get(pk=order_id)
            if order.status == PaymentOrder.Status.REFUNDED:
                return "already_refunded"
            get_gateway().refund(order.gateway_payment_id, order.amount_paise, order.refund_reason)
            order.status = PaymentOrder.Status.REFUNDED
            order.save(update_fields=["status", "updated_at"])
    except PaymentOrder.DoesNotExist:
        logger.error("Refund requested for missing order %s", order_id)
        return "missing"
    except Exception as exc:
        raise self.retry(exc=exc)
    return "refunded"
