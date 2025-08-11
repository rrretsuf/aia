from typing import Dict, Any, List
import structlog
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..core.task_manager import decompose_task, get_task, get_findings, update_task
from ..llm.openrouter_client import get_openrouter_client
from ..llm.prompt_manager import get_prompt_manager
from datetime import datetime

logger = structlog.get_logger()

class PlannerAgent(BaseAgent):

    def __init__(self):
        super().__init__(agent_id="planner_001", agent_type=AgentType.PLANNER)

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

        if human_request.startswith("SYNTHESIZE"):
            parent_task_id = human_request.split(":")[1]
            return await self._synthesize_results(parent_task_id)

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
    
    async def _synthesize_results(self, parent_task_id: str) -> Dict[str, Any]:
        """
        Synthesize all research findings into final report.
        """
        all_findings = []
        parent_task = await get_task(parent_task_id)

        for subtask_id in parent_task["subtasks"]:
            findings = await get_findings(subtask_id)
            all_findings.extend(findings)

        synthesis_prompt = "You are creating a final research report. Synthesize these findings into a comprehensive analysis."

        findings_text = "\n\n".join([
            f"Agent {f['agent_id']} ({f.get('assigned_role', 'Unknown')}):\n{f['findings']['findings']['detailed_analysis']}"
            for f in all_findings if f.get('findings') and f['findings'].get('findings')
        ])

        final_report = await self.llm_client.generate_response(
            system_prompt=synthesis_prompt,
            human_message=f"Original request: {parent_task['human_request']}\n\nFindings:\n{findings_text}",
            temperature=0.6
        )

        print("\n" + "="*80)
        print("📋 FINAL RESEARCH REPORT")
        print("="*80)
        print(f"Request: {parent_task['human_request']}")
        print("-"*80)
        print(final_report)
        print("="*80 + "\n")

        try:
            await update_task(parent_task_id, {
                "status": "completed",
                "final_report": final_report,
                "completed_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to save final report to database: {e}")

        return {
            "status": "synthesis_complete",
            "final_report": final_report
        }
    
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
        You are a research director. Create EXACTLY 3 distinct roles and tasks for research agents.

        Return ONLY a JSON array with this EXACT structure:
        [
        {"role": "Role Name 1", "task": "Specific task description"},
        {"role": "Role Name 2", "task": "Specific task description"},
        {"role": "Role Name 3", "task": "Specific task description"}
        ]

        Rules:
        - Return ONLY the JSON array, no other text
        - Each object MUST have "role" and "task" fields
        - Make roles specific to the request, not generic
        - Tasks should be actionable research directives
        """