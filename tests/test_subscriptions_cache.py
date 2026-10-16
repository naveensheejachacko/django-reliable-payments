from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from payments import subscriptions_cache
from payments.models import Subscription
from tests.conftest import event

pytestmark = pytest.mark.django_db


def test_second_read_comes_from_cache(user, django_assert_num_queries):
    Subscription.objects.create(user=user, plan="monthly", active_until=timezone.localdate() + timedelta(days=5))

    with django_assert_num_queries(1):
        subscriptions_cache.active_subscriptions(user.pk)
    with django_assert_num_queries(0):
        assert len(subscriptions_cache.active_subscriptions(user.pk)) == 1


def test_a_write_clears_the_cache(user):
    sub = Subscription.objects.create(user=user, plan="monthly", active_until=timezone.localdate() + timedelta(days=5))
    assert len(subscriptions_cache.active_subscriptions(user.pk)) == 1

    sub.active_until = timezone.localdate() - timedelta(days=1)  # expired
    sub.save()

    assert subscriptions_cache.active_subscriptions(user.pk) == []


def test_redis_being_down_falls_back_to_the_database(user):
    Subscription.objects.create(user=user, plan="yearly", active_until=timezone.localdate() + timedelta(days=30))
    broken = ConnectionError("redis unavailable")

    with mock.patch.object(subscriptions_cache.cache, "get", side_effect=broken), \
         mock.patch.object(subscriptions_cache.cache, "set", side_effect=broken):
        result = subscriptions_cache.active_subscriptions(user.pk)

    assert [r["plan"] for r in result] == ["yearly"]


def test_paying_for_a_subscription_extends_it_and_refreshes_the_cache(post_webhook, make_subscription_order, user):
    today = timezone.localdate()
    sub, order = make_subscription_order(plan="monthly", active_until=today + timedelta(days=3))
    before = subscriptions_cache.active_subscriptions(user.pk)

    post_webhook(event("payment.captured", order.gateway_order_id))

    sub.refresh_from_db()
    assert sub.active_until == today + timedelta(days=33)  # renewal stacks on the current end date
    after = subscriptions_cache.active_subscriptions(user.pk)
    assert after != before
    assert after[0]["active_until"] == sub.active_until.isoformat()
