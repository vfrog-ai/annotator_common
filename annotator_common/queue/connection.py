"""
RabbitMQ connection and queue management with async support.
"""

import json
import asyncio
import aio_pika
from aio_pika import Message, DeliveryMode
from typing import Optional, Callable, Dict, Any
from annotator_common.config import Config
from annotator_common.logging import get_logger


logger = get_logger(__name__)


class AsyncQueueManager:
    """Manages RabbitMQ connections and operations with async support."""

    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self):
        """Establish async connection to RabbitMQ."""
        try:
            uri = Config.get_rabbitmq_uri()

            self.connection = await aio_pika.connect_robust(uri)
            self.channel = await self.connection.channel()

            # Declare exchange
            await self.channel.declare_exchange(
                Config.EXCHANGE_PROJECT, aio_pika.ExchangeType.FANOUT, durable=True
            )

            self._connected = True
            logger.info(f"Connected to RabbitMQ at {Config.RABBITMQ_HOST}")

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def close(self):
        """Close RabbitMQ connection."""
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        self._connected = False
        logger.info("RabbitMQ connection closed")

    async def _ensure_connected(self, retry_count: int = 3):
        """Ensure connection is established with automatic retry."""
        if self._connected and self.connection and not self.connection.is_closed:
            return

        for attempt in range(retry_count):
            try:
                await self.connect()
                return
            except Exception as e:
                logger.warning(
                    f"Connection attempt {attempt + 1}/{retry_count} failed: {e}"
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(
                        f"Failed to establish connection after {retry_count} attempts"
                    )
                    raise

    async def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        priority: bool = False,
        passive: bool = False,
    ):
        """Declare a queue with optional durability and priority support."""
        await self._ensure_connected()

        args = {}
        if priority:
            args["x-max-priority"] = 10

        try:
            await self.channel.declare_queue(
                queue_name, durable=durable, arguments=args, passive=passive
            )
            logger.info(f"Declared queue: {queue_name}")
        except Exception as e:
            if not passive:
                # Queue might already exist, try passive check
                try:
                    await self.channel.declare_queue(queue_name, passive=True)
                    logger.info(
                        f"Queue {queue_name} already exists with different settings, using existing"
                    )
                except:
                    logger.warning(f"Could not declare queue {queue_name}: {e}")
                    raise
            else:
                raise

    async def bind_queue(self, queue_name: str, exchange: str, routing_key: str = ""):
        """Bind a queue to an exchange."""
        await self._ensure_connected()

        exchange_obj = await self.channel.get_exchange(exchange)
        queue = await self.channel.get_queue(queue_name)
        await queue.bind(exchange_obj, routing_key=routing_key)

        logger.info(f"Bound queue {queue_name} to exchange {exchange}")

    async def publish_message(
        self,
        routing_key: str,
        message: Dict[str, Any],
        exchange: str = "",
        priority: Optional[int] = None,
        retry_count: int = 3,
    ):
        """Publish a message to a queue or exchange with automatic retry on connection failure."""
        message_obj = Message(
            json.dumps(message).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=priority,
        )

        for attempt in range(retry_count):
            try:
                await self._ensure_connected()

                exchange_obj = (
                    await self.channel.get_exchange(exchange)
                    if exchange
                    else self.channel.default_exchange
                )
                await exchange_obj.publish(message_obj, routing_key=routing_key)

                logger.info(
                    f"Published message to {routing_key}, queue: {routing_key}, priority: {priority}, message: {message}"
                )
                return  # Success

            except (
                aio_pika.exceptions.ChannelClosed,
                aio_pika.exceptions.ConnectionClosed,
                ConnectionError,
                OSError,
                asyncio.CancelledError,
            ) as e:
                logger.warning(
                    f"Connection error during publish (attempt {attempt + 1}/{retry_count}): {e}"
                )

                if attempt < retry_count - 1:
                    # Force reconnection on next attempt
                    self._connected = False
                    if self.connection:
                        try:
                            await self.connection.close()
                        except:
                            pass
                    self.connection = None
                    self.channel = None
                    # Wait before retry
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    # Last attempt failed
                    logger.error(
                        f"Failed to publish message after {retry_count} attempts: {e}, message: {message}"
                    )
                    raise

    async def consume(
        self,
        queue_name: str,
        callback: Callable,
        auto_ack: bool = False,
        priority: bool = False,
        passive: bool = False,
        prefetch_count: int = 1,
    ):
        """Start consuming messages from a queue."""
        await self._ensure_connected()

        # Only declare the queue if we need to (with specific settings)
        try:
            await self.declare_queue(queue_name, priority=priority, passive=passive)
        except Exception as e:
            # If queue already exists with different settings, skip declaration
            logger.info(
                f"Queue {queue_name} already exists, proceeding without redeclaration"
            )

        await self.channel.set_qos(prefetch_count=prefetch_count)

        queue = await self.channel.get_queue(queue_name)

        async def process_message(message: aio_pika.IncomingMessage):
            try:
                body = message.body.decode()
                data = json.loads(body)
                dataset_image_id = data.get("dataset_image_id")
                product_image_id = data.get("product_image_id")
                logger.info(
                    f"Received message from queue: {queue_name}, message: {data}, dataset_image_id: {dataset_image_id}, product_image_id: {product_image_id}"
                )

                try:
                    result = await callback(data)
                    # If callback returns False, it means the consumer cannot handle this message
                    # Nack and requeue so another consumer can process it
                    if result is False:
                        logger.info(
                            f"Consumer rejected message (returned False), requeuing: dataset_image_id={dataset_image_id}, product_image_id={product_image_id}, event_type={data.get('event_type')}, queue: {queue_name}"
                        )
                        if not auto_ack:
                            try:
                                await message.nack(requeue=True)
                                logger.info(
                                    f"Successfully nacked and requeued message: dataset_image_id={dataset_image_id}, product_image_id={product_image_id}"
                                )
                            except Exception as nack_err:
                                logger.error(
                                    f"Failed to nack message (may already be acked): {nack_err}, dataset_image_id={dataset_image_id}, product_image_id={product_image_id}"
                                )
                        return  # Don't ack or log as successfully processed

                    if not auto_ack:
                        try:
                            await message.ack()
                        except (Exception, asyncio.CancelledError) as ack_err:
                            logger.warning(
                                f"Ack failed (will ignore if channel closed): {ack_err}"
                            )
                    logger.info(
                        f"Successfully processed message, dataset_image_id: {dataset_image_id}, product_image_id: {product_image_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}, message: {data}, dataset_image_id: {dataset_image_id}, product_image_id: {product_image_id}"
                    )
                    if not auto_ack:
                        try:
                            # Increment retry count and requeue
                            retry_count = data.get("retry_count", 0) + 1
                            data["retry_count"] = retry_count

                            # Republish with incremented retry count
                            message_obj = Message(
                                json.dumps(data).encode(),
                                delivery_mode=DeliveryMode.PERSISTENT,
                            )
                            await self.channel.default_exchange.publish(
                                message_obj, routing_key=queue_name
                            )

                            # Ack original message
                            await message.ack()
                            logger.info(
                                f"Republished message with retry_count={retry_count}: dataset_image_id={dataset_image_id}, product_image_id={product_image_id}"
                            )
                        except (Exception, asyncio.CancelledError) as nack_err:
                            logger.warning(
                                f"Republish failed (channel may be closed): {nack_err}"
                            )
                    # Don't re-raise - we've handled it, let consumer continue
            except Exception as e:
                logger.error(f"Error in message wrapper (outer): {e}")
                # Don't re-raise - we've handled it at inner level

        await queue.consume(process_message)
        logger.info(f"Started consuming from queue: {queue_name}")

    async def start_consuming(self):
        """Start consuming messages (for async consumers, this is just a placeholder)."""
        logger.info("Consumer started (async mode)")
        # In async mode, the consume() method already starts consuming
        # This is kept for compatibility


# Singleton instance
_async_queue_manager: Optional[AsyncQueueManager] = None


async def get_async_queue_manager() -> AsyncQueueManager:
    """Get the singleton AsyncQueueManager instance."""
    global _async_queue_manager
    if _async_queue_manager is None:
        _async_queue_manager = AsyncQueueManager()
    return _async_queue_manager


async def init_async_queue_manager() -> AsyncQueueManager:
    """Initialize and connect to RabbitMQ."""
    manager = await get_async_queue_manager()
    await manager.connect()
    return manager

