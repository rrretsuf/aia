from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from ..models.task import TaskSubmission
from ..core.task_manager import submit_task, get_task_status
from ..redis_client import get_agent_status, list_agents_status

router = APIRouter()

@router.post("/tasks")
async def create_task_endpoint(submission: TaskSubmission) -> Dict[str, Any]:
    """
    Submit a new task.
    """
    task_id = await submit_task(
        human_request=submission.human_request,
        priority=submission.priority,
        task_type="human_request"
    )
    return {
        "task_id": task_id,
        "status": "submitted"
    }

@router.get("/tasks/{task_id}")
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
    agent_statuses = await list_agents_status()

    agents = []
    for agent_id, status in agent_statuses.items():
        agent_type = "brain_hive" if "brain" in agent_id else "research"
        agents.append({
            "id": agent_id,
            "type": agent_type,
            "status": status or "offline"
        })
    
    if not any(a["id"] == "brain_hive_001" for a in agents):
        agents.insert(0, {
            "id": "brain_hive_001",
            "type": "brain_hive",
            "status": await get_agent_status("brain_hive_001") or "offline"
        })

    return {"agents": agents}

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check
    """
    return {"status": "healthy"}