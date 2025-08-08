from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from ..models.task import TaskSubmission
from ..core.task_manager import submit_task, get_task_status
from ..redis_client import get_agent_status

router = APIRouter()

@router.post("/tasks")
async def create_task_endpoint(submission: TaskSubmission) -> Dict[str, Any]:
    """
    Submit a new task.
    """
    task_id = await submit_task(
        human_request=submission.human_request,
        priority=submission.priority
    )
    return {
        "task_id": task_id,
        "status": "submitted"
    }

@router.get("/tasks/{tasks_id}")
async def get_task_endpoint(task_id: str) -> Dict[str, Any]:
    """
    Get task status and results.
    """
    status = await get_task_status(task_id)
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Task not found")
    return status

@router.get("/agents")
async def list_agents_endpoints() -> Dict[str, Any]:
    """
    List all agents and their status,
    """
    agents = [
        {
            "id": "planner:001",
            "type": "planner",
            "status": await get_agent_status("planner_001") or "offline"
        },
        {
            "id": "research_001",
            "type": "research",
            "status": await get_agent_status("research_001") or "offline"
        },
        {
            "id": "research_002",
            "type": "research",
            "status": await get_agent_status("research_002") or "offline"
        },
        {
            "id": "research_003",
            "type": "research",
            "status": await get_agent_status("research_003") or "offline"
        },
    ]
    return {"agents": agents}

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check
    """
    return {"status": "healthy"}