import json
import logging

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .models import PaymentOrder, WebhookEvent
from .signature import verify_webhook_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    # 1. Authenticate before touching the database.
    if not verify_webhook_signature(
        request.body, request.headers.get("X-Razorpay-Signature"), settings.RAZORPAY_WEBHOOK_SECRET
    ):
        return JsonResponse({"error": "invalid signature"}, status=400)

    event_id = request.headers.get("X-Razorpay-Event-Id")
    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "invalid json"}, status=400)
    if not event_id:
        return JsonResponse({"error": "missing event id"}, status=400)

    # 2. Record the event; a redelivered event id stops here.
    with transaction.atomic():
        event, _ = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={"event_type": payload.get("event", ""), "payload": payload},
        )
        if event.processed_at:
            return JsonResponse({"status": "duplicate"})

        result = _dispatch(payload)
        event.processed_at = timezone.now()
        event.save(update_fields=["processed_at"])

    # 3. Answer fast. Receipts and refunds run in Celery after the commit.
    return JsonResponse({"status": result})


def _dispatch(payload: dict) -> str:
    event = payload.get("event")
    try:
        entity = payload["payload"]["payment"]["entity"]
    except (KeyError, TypeError):
        return "ignored"

    try:
        if event == "payment.captured":
            return services.confirm_payment(entity["order_id"], entity["id"])
        if event == "payment.failed":
            return services.fail_payment(entity["order_id"])
    except PaymentOrder.DoesNotExist:
        # Not ours (or created elsewhere). Return 200 so the gateway stops retrying.
        logger.warning("Webhook for unknown order %s", entity.get("order_id"))
        return "unknown_order"
    return "ignored"
