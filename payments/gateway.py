import base64
import json
import urllib.request
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class PaymentGateway(Protocol):
    def refund(self, payment_id: str, amount_paise: int, reason: str) -> dict: ...


class RazorpayGateway:
    base_url = "https://api.razorpay.com/v1"
    timeout_seconds = 10  # an outbound call without a timeout can hang a worker

    def refund(self, payment_id: str, amount_paise: int, reason: str) -> dict:
        body = json.dumps({"amount": amount_paise, "notes": {"reason": reason}}).encode()
        token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
        request = urllib.request.Request(
            f"{self.base_url}/payments/{payment_id}/refund",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read())


def get_gateway() -> PaymentGateway:
    return import_string(settings.PAYMENT_GATEWAY)()
