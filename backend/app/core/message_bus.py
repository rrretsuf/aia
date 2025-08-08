from typing import Dict, Any, AsyncIterator, List
import json
import asyncio
import structlog
from datetime import datetime

from ..redis_client import get_redis, get_pubsub, publish

logger = structlog.get_logger()

async def broadcast(channel: str, message: Dict[str, Any]) -> bool:
    """Broadcast message to all subscribers"""
    return await publish(channel, message)

async def subscribe(channels: List[str]) -> AsyncIterator[Dict[str, Any]]:
    """Subscribe to channels and yield messages"""
    pubsub = await get_pubsub()
    await pubsub.subscribe(*channels)
    
    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    yield data
                except json.JSONDecodeError:
                    logger.error(f"Invalid message format: {message['data']}")
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()

async def notify_task_complete(task_id: str, agent_id: str) -> bool:
    """Notify that a task is complete"""
    return await broadcast('task_complete', {
        'task_id': task_id,
        'agent_id': agent_id,
        'timestamp': datetime.utcnow().isoformat()
    })

async def notify_agent_status(agent_id: str, status: str) -> bool:
    """Notify agent status change"""
    return await broadcast('agent_status', {
        'agent_id': agent_id,
        'status': status,
        'timestamp': datetime.utcnow().isoformat()
    })