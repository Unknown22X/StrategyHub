import asyncio

from rangebot.engine.events import EngineEventPublisher


def test_event_publisher_delivers_sanitized_sequence() -> None:
    async def scenario() -> None:
        publisher = EngineEventPublisher(queue_size=2)
        subscription = publisher.subscribe()
        pending = asyncio.create_task(anext(subscription))
        await asyncio.sleep(0)

        published = publisher.publish(
            category="order", action="post", resource="/v1/manual-orders"
        )
        received = await pending
        await subscription.aclose()

        assert received == published
        assert received.sequence == 1
        assert received.category == "order"
        assert publisher.status().subscriber_count == 0

    asyncio.run(scenario())


def test_event_publisher_drops_oldest_for_slow_subscriber() -> None:
    async def scenario() -> None:
        publisher = EngineEventPublisher(queue_size=1)
        subscription = publisher.subscribe()
        first_wait = asyncio.create_task(anext(subscription))
        await asyncio.sleep(0)
        publisher.publish(category="engine", action="first", resource="/health")
        first = await first_wait

        publisher.publish(category="engine", action="second", resource="/health")
        latest = publisher.publish(category="engine", action="latest", resource="/health")
        received = await anext(subscription)
        await subscription.aclose()

        assert first.action == "first"
        assert received == latest
        assert received.action == "latest"

    asyncio.run(scenario())
