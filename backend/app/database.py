from supabase import create_client, Client
from typing import Optional
import structlog
from backend.app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Global Supabase client instance
supabase: Optional[Client] = None

async def init_supabase() -> Client:
    """Initialize Supabase client"""
    global supabase
    
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("Supabase URL and Key must be set in environment")
    
    try:
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key
        )
        
        # Test connection
        response = supabase.table('tasks').select("count", count='exact').execute()
        logger.info("Supabase connected successfully")
        
        return supabase
        
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        raise


def get_supabase() -> Client:
    """Get Supabase client instance"""
    if supabase is None:
        raise RuntimeError("Supabase not initialized. Call init_supabase() first.")
    return supabase


class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self):
        self.client = get_supabase()
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            response = self.client.table('tasks').select("count", count='exact').execute()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def create_task(self, task_data: dict) -> dict:
        """Create a new task"""
        response = self.client.table('tasks').insert(task_data).execute()
        return response.data[0] if response.data else None
    
    async def get_task(self, task_id: str) -> dict:
        """Get task by ID"""
        response = self.client.table('tasks').select("*").eq('id', task_id).execute()
        return response.data[0] if response.data else None
    
    async def update_task_status(self, task_id: str, status: str) -> dict:
        """Update task status"""
        response = self.client.table('tasks').update({
            'status': status
        }).eq('id', task_id).execute()
        return response.data[0] if response.data else None
    
    async def create_agent_state(self, agent_data: dict) -> dict:
        """Create or update agent state"""
        response = self.client.table('agent_states').upsert(agent_data).execute()
        return response.data[0] if response.data else None
    
    async def get_active_agents(self) -> list:
        """Get all active agents"""
        response = self.client.table('agent_states').select("*").neq('status', 'offline').execute()
        return response.data or []
    
    async def get_agent_by_id(self, agent_id: str) -> dict:
        """Get agent by agent_id (not UUID id)"""
        response = self.client.table('agent_states').select("*").eq('agent_id', agent_id).execute()
        return response.data[0] if response.data else None

    async def update_agent_status(self, agent_id: str, status: str) -> dict:
        """Update agent status by agent_id"""
        response = self.client.table('agent_states').update({
            'status': status,
            'last_activity': 'now()'
        }).eq('agent_id', agent_id).execute()
        return response.data[0] if response.data else None