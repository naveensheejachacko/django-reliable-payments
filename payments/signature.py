import hashlib
import hmac


def verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Razorpay signs the raw request body with HMAC-SHA256 using the webhook secret.

    Verify against the exact bytes received (never a re-serialised payload), and
    compare in constant time so the check can't be timed.
    """
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
