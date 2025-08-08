import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
import structlog
from backend.app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Global Redis client instance
redis_client: Optional[redis.Redis] = None


async def init_redis() -> redis.Redis:
    """Initialize Redis client"""
    global redis_client
    
    redis_url = settings.upstash_redis_url or settings.redis_url
    if not redis_url:
        raise ValueError("Redis URL must be set in environment")
    
    try:
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            health_check_interval=30
        )
        
        # Test connection
        await redis_client.ping()
        logger.info("Redis connected successfully")
        
        return redis_client
        
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return redis_client

async def push_task(task_data: Dict[str, Any], priority: int = 5) -> bool:
    """Add task to queue with priority"""
    task_json = json.dumps(task_data)
    await get_redis().zadd("task_queue", {task_json: priority})
    return True

async def pop_task() -> Optional[Dict[str, Any]]:
    """Get highest priority task from queue"""
    result = await get_redis().zpopmax("task_queue")
    if result:
        task_json, _ = result[0]
        return json.loads(task_json)
    return None

async def publish(channel: str, data: Dict[str, Any]) -> bool:
    """Publish message to channel"""
    await get_redis().publish(channel, json.dumps(data))
    return True

async def get_pubsub() -> redis.client.PubSub:
    """Get pubsub instance for subscriptions"""
    return get_redis().pubsub()

async def set_agent_status(agent_id: str, status: str) -> bool:
    """Update agent status in Redis"""
    await get_redis().hset(f"agent:{agent_id}", "status", status)
    await get_redis().expire(f"agent:{agent_id}", 3600)
    return True

async def get_agent_status(agent_id: str) -> Optional[str]:
    """Get agent status from Redis"""
    return await get_redis().hget(f"agent:{agent_id}", "status")