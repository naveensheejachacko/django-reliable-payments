from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Q


class PaymentOrder(models.Model):
    """One attempt to pay for one thing. `kind` picks the handler from the registry."""

    class Status(models.TextChoices):
        CREATED = "created"
        PAID = "paid"
        FAILED = "failed"
        REFUNDED = "refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_orders")
    kind = models.CharField(max_length=32)
    object_id = models.PositiveBigIntegerField(help_text="Primary key of the thing being paid for.")
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    gateway_order_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    paid_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.kind}#{self.object_id} {self.gateway_order_id} [{self.status}]"


class WebhookEvent(models.Model):
    """Every webhook we've accepted, keyed by the gateway's event id, so a redelivery is a no-op."""

    event_id = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        CONFIRMED = "confirmed"
        CANCELLED = "cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    slot = models.CharField(max_length=64, help_text='e.g. "room-12@2026-10-20T22:00"')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        constraints = [
            # The database, not application code, guarantees a slot is sold once.
            models.UniqueConstraint(
                fields=["slot"], condition=Q(status="confirmed"), name="one_confirmed_booking_per_slot"
            )
        ]


class Subscription(models.Model):
    PLAN_DAYS = {"monthly": 30, "yearly": 365}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.CharField(max_length=16, choices=[(p, p) for p in PLAN_DAYS])
    active_until = models.DateField(null=True, blank=True)

    def is_active(self, on: date) -> bool:
        return self.active_until is not None and self.active_until >= on
