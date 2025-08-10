from typing import Dict, Any, List
import json
import structlog
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..core.task_manager import decompose_task
from ..llm.openrouter_client import get_openrouter_client
from ..llm.prompt_manager import get_prompt_manager

logger = structlog.get_logger()

class PlannerAgent(BaseAgent):

    def __init__(self):
        super().__init__(agent_id="planner001", agent_type=AgentType.PLANNER)

        self.llm_client = get_openrouter_client()
        self.prompt_manager = get_prompt_manager()

        try: 
            self.system_prompt = self.prompt_manager.load_prompt("planner_system_prompt")
            logger.info("Planner agent initialized")
        
        except Exception as e:
            logger.error(f"Failed to load planner prompt: {e}")
            self.system_prompt = self._get_fallback_prompt()

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        WORKFLOW:
        1. Create 3 dynamic roles for the request
        2. Create specific tasks for each role
        3. Send tasks to research agents
        """
        human_request = task["human_request"] 
        task_id = task["id"]

        logger.info(f"PLANNER: Processing request: {human_request}")

        # create dynamic role assignments
        try:
            role_assignments = await self._create_role_assignments(human_request)
            logger.info(f"Created 3 dynamic roles")

        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            role_assignments = self._fallback_assignments(human_request)

        # create subtasks with role context
        subtasks = []
        for assignment in role_assignments:
            subtask = f"[ROLE: {assignment['role']}] {assignment['task']}"
            subtasks.append(subtask)

        # send to research agents
        await decompose_task(task_id, subtasks)
        logger.info("Tasks sent to research agents")

        return {
            "status": "roles_assigned",
            "role_assignments": role_assignments,
            "subtasks": subtasks
        }
    
    async def _create_role_assignments(self, request: str) -> List[Dict[str, str]]:
        """
        Use LLM to create 3 dynamic roles and tasks.
        """
        message = f"""
        Request: {request}
        
        Create 3 distinct roles and specific tasks for research agents.
        Each role should be tailored to this specific request.
        """

        response = await self.llm_client.generate_json_response(
            system_prompt=self.system_prompt,
            human_message=message,
            temperature=0.8
        )

        if isinstance(response, list):
            assignments = response
        elif isinstance(response, dict) and "assignments" in response:
            assignments = response["assignments"]
        else: 
            raise ValueError("Invalid LLM response format")
        
        if len(assignments) != 3:
            raise ValueError(f"Expected 3 assignments, got {len(assignments)}")

        for assignment in assignments:
            if "role" not in assignment or "task" not in assignment:
                raise ValueError("Assignment missing role or task")
            
        return assignments
    
    def _fallback_assignments(self, request: str) -> List[Dict[str, str]]:
        """
        Fallback if LLM fails.
        """
        logger.info("Using fallback role assignments")

        return [
            {
                "role": "Primary Research Specialist",
                "task": f"Research the main overview and key aspects of: {request}"
            },
            {
                "role": "Detailed Analysis Specialist", 
                "task": f"Research specific details and technical aspects of: {request}"
            },
            {
                "role": "Strategic Insights Specialist",
                "task": f"Research implications, trends, and opportunities for: {request}"
            }
        ]
    
    def _get_fallback_prompt(self) -> str:
        """
        Simple fallback prompt
        """
        return """
        You are a research director. Create 3 distinct roles and tasks for research agents.

        Return JSON array:
        [
        {"role": "Role Name 1", "task": "Specific task description"},
        {"role": "Role Name 2", "task": "Specific task description"},
        {"role": "Role Name 3", "task": "Specific task description"}
        ]

        Make roles specific to the request, not generic.
        """
