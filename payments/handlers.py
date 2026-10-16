from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Booking, Subscription
from .registry import PaymentHandler, register


class SlotTaken(Exception):
    """Payment succeeded, but someone else confirmed the same slot first."""

    def __init__(self, slot: str):
        super().__init__(slot)
        self.slot = slot


@register("booking")
class BookingHandler(PaymentHandler):
    def on_paid(self, order) -> None:
        booking = Booking.objects.select_for_update().get(pk=order.object_id)
        if booking.status == Booking.Status.CONFIRMED:
            return
        booking.status = Booking.Status.CONFIRMED
        try:
            # Savepoint: if the unique constraint fires, only this write rolls back,
            # and the payment record in the outer transaction survives.
            with transaction.atomic():
                booking.save(update_fields=["status"])
        except IntegrityError:
            Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.CANCELLED)
            raise SlotTaken(booking.slot) from None

    def on_failed(self, order) -> None:
        Booking.objects.filter(pk=order.object_id, status=Booking.Status.PENDING).update(
            status=Booking.Status.CANCELLED
        )


@register("subscription")
class SubscriptionHandler(PaymentHandler):
    def on_paid(self, order) -> None:
        sub = Subscription.objects.select_for_update().get(pk=order.object_id)
        today = timezone.localdate()
        # Renewing early extends from the current end date, not from today.
        start = max(today, sub.active_until) if sub.active_until else today
        sub.active_until = start + timedelta(days=Subscription.PLAN_DAYS[sub.plan])
        sub.save(update_fields=["active_until"])  # post_save clears the cached view
