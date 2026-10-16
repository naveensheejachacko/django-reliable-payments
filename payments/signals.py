from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import subscriptions_cache
from .models import Subscription


@receiver(post_save, sender=Subscription)
@receiver(post_delete, sender=Subscription)
def clear_subscription_cache(sender, instance, **kwargs):
    subscriptions_cache.invalidate(instance.user_id)
