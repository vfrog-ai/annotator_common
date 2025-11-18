"""
RabbitMQ queue utilities.
"""

from .connection import AsyncQueueManager, get_async_queue_manager, init_async_queue_manager
from typing import TYPE_CHECKING

# For backwards compatibility and cleaner imports
if TYPE_CHECKING:
    from typing import Awaitable

__all__ = ["AsyncQueueManager", "get_async_queue_manager", "init_async_queue_manager"]

