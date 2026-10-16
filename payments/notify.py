import logging

logger = logging.getLogger(__name__)


def send_receipt(order) -> None:
    """Stand-in for WhatsApp / email / push. Swap in a real provider here."""
    logger.info("Receipt sent for order %s to user %s", order.gateway_order_id, order.user_id)
