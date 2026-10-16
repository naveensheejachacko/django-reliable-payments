import hashlib
import hmac

from payments.signature import verify_webhook_signature

BODY = b'{"event":"payment.captured"}'
SECRET = "s3cret"
GOOD = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()


def test_accepts_a_correct_signature():
    assert verify_webhook_signature(BODY, GOOD, SECRET)


def test_rejects_a_tampered_body():
    assert not verify_webhook_signature(BODY + b" ", GOOD, SECRET)


def test_rejects_a_missing_signature_or_secret():
    assert not verify_webhook_signature(BODY, None, SECRET)
    assert not verify_webhook_signature(BODY, GOOD, "")
