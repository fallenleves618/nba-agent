"""Delivery channels."""

from nba_agent.delivery.console import deliver_to_console
from nba_agent.delivery.webhook import deliver_to_webhooks

__all__ = ["deliver_to_console", "deliver_to_webhooks"]
