from typing import Dict, Any, List
import json
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..core.task_manager import decompose_task

class PlannerAgent(BaseAgent):

    def __init__(self):
        super().__init__(agent_id="planner001", agent_type=AgentType.PLANNER)

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decompose human request into subtasks
        """
        human_request = task["human_request"] 

        # TODO: use llm to decompose request

        # for now, simple mock decomposition
        subtasks = self._mock_decompose(human_request)

        await decompose_task(task["id"], subtasks)

        return {
            "status": "decomposed",
            "subtasks_count": len(subtasks),
            "subtasks": subtasks
        }
    
    def _mock_decompose(self, request: str) -> List[str]:
        """
        Mock decomposition - TODO: replace with llm
        """
        return [
            f"Research aspect 1 of: {request}",
            f"Research aspect 2 of: {request}",
            f"Research aspect 3 of: {request}",
        ]
