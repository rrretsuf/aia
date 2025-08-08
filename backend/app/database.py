from supabase import create_client, Client
from typing import Optional, Any, Dict
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

async def create_task(task_data: Dict[str, Any]) -> str:
    """Create a new task and return its ID"""
    response = get_supabase().table('tasks').insert(task_data).execute()
    return response.data[0]['id'] if response.data else None

async def get_task(task_id: str) -> Dict[str, Any]:
    """Get task by ID"""
    response = get_supabase().table('tasks').select("*").eq('id', task_id).execute()
    return response.data[0] if response.data else None

async def update_task(task_id: str, updates: Dict[str, Any]) -> bool:
    """Update task with any fields"""
    response = get_supabase().table('tasks').update(updates).eq('id', task_id).execute()
    return bool(response.data)

async def save_findings(task_id: str, agent_id: str, findings: Dict[str, Any]) -> bool:
    """Save research findings"""
    data = {
        'task_id': task_id,
        'agent_id': agent_id,
        'findings': findings,
        'confidence': findings.get('confidence', 0.5)
    }
    response = get_supabase().table('research_findings').insert(data).execute()
    return bool(response.data)

async def get_findings(task_id: str) -> list:
    """Get all findings for a task"""
    response = get_supabase().table('research_findings').select("*").eq('task_id', task_id).execute()
    return response.data or []

