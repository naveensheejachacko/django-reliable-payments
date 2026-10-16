# django-reliable-payments

Payment webhooks that are safe to receive twice, a slot that can't be sold twice, and
background jobs that never message a customer twice. A small Django + Celery project
showing the patterns I use for payments in production, rewritten from scratch as a
standalone example. It contains no employer code.

![tests](https://github.com/naveensheejachacko/django-reliable-payments/actions/workflows/ci.yml/badge.svg)

## The problems it solves

| Problem | What goes wrong | How this handles it |
|---|---|---|
| Razorpay sends `payment.captured` more than once | Two bookings, two receipts | Event ids are stored with a unique constraint, and the order row is locked so a second delivery sees `PAID` and stops |
| Someone forges a webhook | Free bookings | HMAC-SHA256 check on the raw body, constant-time compare, rejected before any database write |
| Two people pay for the last slot at the same moment | Double-sold room | A conditional unique constraint in the database. The loser's payment is refunded automatically |
| A Celery task is retried or queued twice | Duplicate WhatsApp or email | `cache.add` (Redis `SET NX`) claims the send; the claim is released if the send fails, so the retry still works |
| A receipt goes out but the transaction rolls back | Customer told they paid when they didn't | Side effects are queued with `transaction.on_commit` |
| Every new product needs its own payment code | One growing `if kind == ...` view | A handler registry. A new product is one class |
| Redis goes down | The busiest screen goes down with it | Cache reads and writes fall back to the database |

## How a payment flows

```
Razorpay ──POST──▶ /payments/webhooks/razorpay/
                      │ 1. verify signature (400 if bad)
                      │ 2. record event id (duplicate → 200, stop)
                      ▼
               confirm_payment()   ← row lock on the order
                      │ already PAID? → "duplicate"
                      │ mark PAID
                      ▼
          registry["booking" | "subscription"].on_paid()
                      │
          ┌───────────┴────────────┐
     fulfilled                 slot taken (unique constraint)
          │                        │
   on_commit: send_receipt   on_commit: refund_payment
   (once, via SET NX)        (once, via row lock)
```

## Code tour

| File | What's in it |
|---|---|
| [`payments/registry.py`](payments/registry.py) | `@register("kind")` and `get_handler()` |
| [`payments/handlers.py`](payments/handlers.py) | Booking (with the lost-race refund) and subscription handlers |
| [`payments/views.py`](payments/views.py) | The webhook: verify, dedupe, dispatch, answer fast |
| [`payments/services.py`](payments/services.py) | `confirm_payment` and `fail_payment`, both safe to repeat |
| [`payments/tasks.py`](payments/tasks.py) | Celery receipt and refund tasks that run at most once |
| [`payments/subscriptions_cache.py`](payments/subscriptions_cache.py) | Per-user, per-day cache with signal invalidation and a database fallback |
| [`payments/signature.py`](payments/signature.py) | Webhook signature check |

## Adding a payment kind

```python
from payments.registry import PaymentHandler, register

@register("car_wash")
class CarWashHandler(PaymentHandler):
    def on_paid(self, order):
        ...  # runs inside the confirmation transaction
```

The webhook, the confirmation service and the tasks don't change.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

The tests run on SQLite by default. To run them on PostgreSQL, the way CI does:

```bash
POSTGRES_DB=payments POSTGRES_PASSWORD=... pytest
```

Set `REDIS_URL` to use Redis for the cache and the Celery broker. Without it, the project
uses an in-memory cache and runs Celery tasks inline.

## Tests

20 tests, run on both SQLite and PostgreSQL in CI. They cover a forged signature, the
same event delivered twice, the same payment under a new event id, two people racing for
one slot, a receipt task run twice, a failed send that retries, a refund task run twice,
and the cache with Redis down.

## License

MIT
