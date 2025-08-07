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


class RedisManager:
    """Redis operations manager for agent communication"""
    
    def __init__(self):
        self.client = get_redis()
    
    async def health_check(self) -> bool:
        """Check Redis health"""
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    # Agent State Caching
    async def set_agent_state(self, agent_id: str, state: Dict[str, Any], ttl: int = 3600):
        """Cache agent state with TTL"""
        await self.client.hset(
            f"agent:{agent_id}", 
            mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in state.items()}
        )
        await self.client.expire(f"agent:{agent_id}", ttl)
    
    async def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        """Get cached agent state"""
        data = await self.client.hgetall(f"agent:{agent_id}")
        return {k: self._deserialize_value(v) for k, v in data.items()}
    
    async def delete_agent_state(self, agent_id: str):
        """Remove agent state from cache"""
        await self.client.delete(f"agent:{agent_id}")
    
    # Task Queue Management
    async def add_task_to_queue(self, queue_name: str, task_data: Dict[str, Any], priority: int = 5):
        """Add task to priority queue"""
        task_json = json.dumps(task_data)
        await self.client.zadd(f"queue:{queue_name}", {task_json: priority})
    
    async def get_next_task(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """Get highest priority task from queue"""
        result = await self.client.zpopmax(f"queue:{queue_name}")
        if result:
            task_json, priority = result[0]
            return json.loads(task_json)
        return None
    
    async def get_queue_length(self, queue_name: str) -> int:
        """Get number of tasks in queue"""
        return await self.client.zcard(f"queue:{queue_name}")
    
    # Inter-Agent Messaging
    async def publish_message(self, channel: str, message: Dict[str, Any]):
        """Publish message to channel for agent communication"""
        await self.client.publish(channel, json.dumps(message))
    
    async def subscribe_to_channel(self, channel: str):
        """Subscribe to channel for receiving messages"""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
    
    # Shared Data Storage
    async def set_shared_data(self, key: str, data: Any, ttl: Optional[int] = None):
        """Store shared data between agents"""
        value = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
        await self.client.set(f"shared:{key}", value)
        if ttl:
            await self.client.expire(f"shared:{key}", ttl)
    
    async def get_shared_data(self, key: str) -> Any:
        """Get shared data"""
        value = await self.client.get(f"shared:{key}")
        return self._deserialize_value(value) if value else None
    
    async def delete_shared_data(self, key: str):
        """Delete shared data"""
        await self.client.delete(f"shared:{key}")
    
    def _deserialize_value(self, value: str) -> Any:
        """Helper to deserialize JSON values"""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value