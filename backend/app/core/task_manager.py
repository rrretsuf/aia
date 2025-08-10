import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog
import uuid
from app.models.task import task_type

from ..database import (
    create_task,
    get_task, 
    update_task,
    save_findings,
    get_findings
)
from ..redis_client import (
    push_task,
    pop_task,
    set_agent_status
)

logger = structlog.get_logger()

async def submit_task(human_request: str, priority: int = 5) -> str:
    """Submit a new task from human request"""
    task_id = str(uuid.uuid4())
    task_data = {
        'id': task_id,
        'human_request': human_request,
        'status': 'pending',
        'priority': priority,
        'task_type': task_type,
        'created_at': datetime.utcnow().isoformat()
    }
    
    # Save to database
    await create_task(task_data)

    queue_name = "planner_queue" if task_type == "human_requst" else "research_queue"
    await push_task({"task_id": task_id}, priority, queue_name)
    
    # Add to queue
    await push_task({'task_id': task_id}, priority)
    
    logger.info(f"Task {task_id} submitted to {queue_name}")
    return task_id

async def claim_task(agent_id: str) -> Optional[Dict[str, Any]]:
    """Agent claims next available task"""
    task_data = await pop_task()
    if not task_data:
        return None
    
    task = await get_task(task_data['task_id'])
    if task:
        # Update task assignment
        await update_task(task['id'], {
            'status': 'in_progress',
            'assigned_agents': [agent_id]
        })
        
        # Update agent status
        await set_agent_status(agent_id, 'working')
        
        logger.info(f"Task {task['id']} claimed by {agent_id}")
        return task
    
    return None

async def complete_task(task_id: str, agent_id: str, results: Dict[str, Any]) -> bool:
    """Mark task as complete with results"""
    # Update task
    await update_task(task_id, {
        'status': 'completed',
        'results': json.dumps(results),
        'completed_at': datetime.utcnow().isoformat(),
        'progress': 1.0
    })
    
    # Save findings
    await save_findings(task_id, agent_id, results)
    
    # Update agent status
    await set_agent_status(agent_id, 'idle')
    
    logger.info(f"Task {task_id} completed by {agent_id}")

    task = await get_task(task_id)
    if task and task.get("parent_task_id"):
        parent_id = task["parent_task_id"]
        logger.info(f"Checking if parent task {parent_id} is complete")

        if await check_all_subtasks_complete(parent_id):
            logger.info(f"All subtasks complete for {parent_id}, triggering synthesis")
            await trigger_final_synthesis(parent_id)

    return True

async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get current task status and results"""
    task = await get_task(task_id)
    if not task:
        return {'status': 'not_found'}
    
    findings = await get_findings(task_id)
    
    return {
        'task_id': task_id,
        'status': task['status'],
        'progress': task.get('progress', 0),
        'results': json.loads(task['results']) if task.get('results') else None,
        'findings': findings,
        'created_at': task['created_at'],
        'completed_at': task.get('completed_at')
    }

async def decompose_task(task_id: str, subtasks: List[str]) -> bool:
    """Break task into subtasks"""
    # Update parent task with subtask IDs
    subtask_ids = []
    
    for subtask_description in subtasks:
        subtask_id = await submit_task(
            human_request=subtask_description,
            priority=5,
            task_type="research_subtask"
        )
        subtask_ids.append(subtask_id)
        
        # Link to parent
        await update_task(subtask_id, {'parent_task_id': task_id})
    
    # Update parent task
    await update_task(task_id, {'subtasks': subtask_ids})
    
    return True

async def check_all_subtasks_complete(parent_task_id: str) -> bool:
    """
    Check if all subtasks of parent are complete.
    """
    parent_task = await get_task(parent_task_id)
    if not parent_task or not parent_task.get("subtasks"):
        return False
    
    for subtask_id in parent_task["subtasks"]:
        subtask = await get_task(subtask_id)
        if not subtask or subtask["status"] != "completed":
            return False
        
    return True

async def trigger_final_synthesis(parent_task_id: str):
    """
    Trigger planner to synthesize all findings.
    """
    synthesis_task_id = str(uuid.uuid4())
    synthesis_task = {
        "id": parent_task_id + "_synthesis", 
        "human_request": f"SYNTHESIZE: {parent_task_id}",
        "task_type": "synthesis",
        "status": "pending",
        "priority": 10,
        "created_at": datetime.utcnow().isoformat()
    }

    await create_task(synthesis_task)
    await push_task({"task_id": synthesis_task_id}, priority=10, queue_name="planner_queue")

    logger.info(f"Synthesis task triggered for parent task {parent_task_id}")

async def claim_task(agent_id: str, agent_type: str = "research") -> Optional[Dict[str, Any]]:
    """
    Agent claims next available task from appropriate queue.
    """
    queue_name = "planner_queue" if agent_type == "planner" else "research_queue"

    task_data = await pop_task(queue_name)
    if not task_data:
        return None

    task = await get_task(task_data["task_id"])
    if task:
        await update_task(task['id'], {
            'status': 'in_progress',
            'assigned_agents': [agent_id]
        })

        await set_agent_status(agent_id, "working")

        logger.info(f"Task {task["id"]} claimed by {agent_id} from {queue_name}")

    return None