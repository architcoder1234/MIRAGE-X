"""Small in-process SSE event bus for the single-process demo deployment."""
import asyncio
import queue
import threading

_subscribers = set()
_lock = threading.Lock()


def publish(event_type, data):
    message = {"event": event_type, "data": data}
    with _lock:
        subscribers = list(_subscribers)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(message)
        except queue.Full:
            continue


def subscribe():
    subscriber = queue.Queue(maxsize=100)
    with _lock:
        _subscribers.add(subscriber)
    return subscriber


def unsubscribe(subscriber):
    with _lock:
        _subscribers.discard(subscriber)


async def stream():
    subscriber = subscribe()
    try:
        yield {"event": "ready", "data": {"status": "connected"}}
        while True:
            try:
                message = await asyncio.to_thread(subscriber.get, True, 15)
                yield message
            except queue.Empty:
                yield ": ping\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        unsubscribe(subscriber)
