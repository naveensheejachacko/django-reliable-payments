"""Per-user cache for "my active subscriptions", a hot read on every app open.

- Keyed by user and by day, so a plan that ends at midnight is never served stale.
- Cleared by signals on every write that changes the answer.
- Redis being down is not an outage: every cache call falls back to the database.
"""

import logging

from django.core.cache import cache
from django.utils import timezone

from .models import Subscription

logger = logging.getLogger(__name__)

TTL_SECONDS = 600  # safety net only; invalidation does the real work


def _key(user_id: int, day) -> str:
    return f"subs:active:v1:{user_id}:{day.isoformat()}"


def active_subscriptions(user_id: int) -> list[dict]:
    today = timezone.localdate()
    key = _key(user_id, today)

    try:
        cached = cache.get(key)
    except Exception:
        logger.warning("Cache read failed for %s; using the database", key, exc_info=True)
        cached = None
    if cached is not None:
        return cached

    data = [
        {"plan": s.plan, "active_until": s.active_until.isoformat()}
        for s in Subscription.objects.filter(user_id=user_id, active_until__gte=today).order_by("active_until")
    ]
    try:
        cache.set(key, data, timeout=TTL_SECONDS)
    except Exception:
        logger.warning("Cache write failed for %s", key, exc_info=True)
    return data


def invalidate(user_id: int) -> None:
    try:
        cache.delete(_key(user_id, timezone.localdate()))
    except Exception:
        logger.warning("Cache delete failed for user %s", user_id, exc_info=True)
