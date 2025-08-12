from typing import Dict, Any, List
import structlog
from uuid import uuid4
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..core.task_manager import decompose_task, get_task, get_findings, update_task
from ..llm.openrouter_client import get_openrouter_client
from ..llm.prompt_manager import get_prompt_manager
from datetime import datetime, timezone
from .agent_factory import AgentFactory

logger = structlog.get_logger()

class BrainHive(BaseAgent):
    """
    Central orchestrator that plans and coordinates all worker agents.
    """
    
    def __init__(self):
        super().__init__(agent_id="brain_hive_001", agent_type=AgentType.ORCHESTRATOR)
        
        self.llm_client = get_openrouter_client()
        self.prompt_manager = get_prompt_manager()
        self.agent_factory = AgentFactory()
        
        try:
            self.system_prompt = self.prompt_manager.load_prompt("brain_hive_system_prompt")
            logger.info("Brain Hive initialized successfully")
        except Exception as e:
            logger.error(f"Failed to load brain hive prompt: {e}")
            self.system_prompt = self._get_fallback_prompt()
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming task:
        1. Create dynamic agent plan with names
        2. Spawn required agents by name
        3. Create headerized subtasks
        4. Send to agent queue
        """
        human_request = task["human_request"]
        task_id = task["id"]
        
        logger.info(f"Brain Hive processing: {human_request}")
        
        if human_request.startswith("SYNTHESIZE"):
            parent_task_id = human_request.split(":")[1]
            return await self._synthesize_results(parent_task_id)
        
        try:
            plan = await self._create_agent_plan(human_request)
            logger.info(f"Created plan with {plan['agent_count']} agents")
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            plan = self._fallback_plan(human_request)
        
        agent_names = [assignment['name'] for assignment in plan['assignments']]
        spawned = await self.agent_factory.ensure_agents(agent_names)
        logger.info(f"Ensured {len(agent_names)} agents, spawned {spawned} new")
        
        subtasks = []
        for assignment in plan['assignments']:
            sys_prompt = assignment['system_prompt'].replace('"', '\\"')
            
            header = (
                f'[CFG name="{assignment["name"]}" '
                f'role="{assignment["role"]}" '
                f'model="{assignment["model"]}" '
                f'sys="{sys_prompt}"]'
            )
            subtask = f"{header} {assignment['task']}"
            subtasks.append(subtask)
        
        await decompose_task(task_id, subtasks)
        logger.info(f"Dispatched {len(subtasks)} tasks to agent queue")
        
        return {
            "status": "plan_created",
            "agent_count": plan['agent_count'],
            "agent_names": agent_names,
            "assignments": plan['assignments']
        }
    
    async def _create_agent_plan(self, request: str) -> Dict[str, Any]:
        """
        Use LLM to create dynamic agent plan with names.
        """
        message = f"Request: {request}"
        
        response = await self.llm_client.generate_json_response(
            system_prompt=self.system_prompt,
            human_message=message,
            temperature=0.8
        )
        
        if not isinstance(response, dict):
            raise ValueError("Invalid response format - expected dict")
        
        if "agent_count" not in response or "assignments" not in response:
            raise ValueError("Missing agent_count or assignments")
        
        agent_count = response["agent_count"]
        assignments = response["assignments"]
        
        agent_count = min(agent_count, 5)  
        agent_count = max(1, agent_count)
        
        if len(assignments) != agent_count:
            logger.warning(f"Assignment count mismatch: {len(assignments)} vs {agent_count}")
            assignments = assignments[:agent_count]
        
        for i, assignment in enumerate(assignments):
            if "name" not in assignment or not assignment["name"]:
                assignment["name"] = f"worker_{uuid4().hex[:6]}"
            
            assignment["name"] = assignment["name"].strip().lower().replace(" ", "_").replace("-", "_")
            
            if "system_prompt" not in assignment:
                assignment["system_prompt"] = "You are a specialized worker. Be thorough and accurate."
            if "model" not in assignment:
                assignment["model"] = "moonshotai/kimi-k2:free"
            
            if len(assignment["system_prompt"]) > 800:
                assignment["system_prompt"] = assignment["system_prompt"][:797] + "..."
        
        return {
            "agent_count": agent_count,
            "assignments": assignments
        }
    
    async def _synthesize_results(self, parent_task_id: str) -> Dict[str, Any]:
        """
        Synthesize all worker findings into final output.
        """
        all_findings = []
        parent_task = await get_task(parent_task_id)
        today = datetime.now(timezone.utc).date().isoformat()        
        for subtask_id in parent_task["subtasks"]:
            findings = await get_findings(subtask_id)
            all_findings.extend(findings)
        
        synthesis_prompt = f"You are creating the final output. Today is {today} Synthesize these findings into a comprehensive analysis."
        
        findings_text = "\n\n".join([
            f"Agent {f['agent_id']} ({f.get('assigned_role', 'Worker')}):\n{f['findings']['findings']['detailed_analysis']}"
            for f in all_findings if f.get('findings') and f['findings'].get('findings')
        ])
        
        final_output = await self.llm_client.generate_response(
            system_prompt=synthesis_prompt,
            human_message=f"Original request: {parent_task['human_request']}\n\nFindings:\n{findings_text}",
            temperature=0.6
        )
        
        print("\n" + "="*80)
        print("📋 FINAL OUTPUT") 
        print("="*80)
        print(f"Request: {parent_task['human_request']}")
        print("-"*80)
        print(final_output)
        print("="*80 + "\n")
        
        try:
            await update_task(parent_task_id, {
                "status": "completed",
                "final_report": final_output,
                "completed_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to save final output: {e}")
        
        return {
            "status": "synthesis_complete",
            "final_output": final_output
        }
    
    def _fallback_plan(self, request: str) -> Dict[str, Any]:
        """
        Fallback plan if LLM fails - with proper agent names.
        """
        logger.info("Using fallback agent plan")
        
        return {
            "agent_count": 3,
            "assignments": [
                {
                    "name": "primary_analyst",
                    "role": "Primary Analysis Specialist",
                    "task": f"Analyze the main overview and key aspects of: {request}",
                    "system_prompt": "You are a primary analysis specialist. Focus on core concepts and overview.",
                    "model": "moonshotai/kimi-k2:free"
                },
                {
                    "name": "detail_analyst",
                    "role": "Detailed Analysis Specialist",
                    "task": f"Analyze specific details and technical aspects of: {request}",
                    "system_prompt": "You specialize in detailed analysis. Focus on technical depth.",
                    "model": "moonshotai/kimi-k2:free"
                },
                {
                    "name": "strategy_expert",
                    "role": "Strategic Insights Specialist",
                    "task": f"Analyze implications, trends, and opportunities for: {request}",
                    "system_prompt": "You excel at strategic thinking. Focus on implications and opportunities.",
                    "model": "moonshotai/kimi-k2:free"
                }
            ]
        }
    
    def _get_fallback_prompt(self) -> str:
        """
        Emergency fallback prompt.
        """
        return """
        You are the Brain Hive. Create an agent plan for the request.
        
        Return ONLY a JSON object:
        {
            "agent_count": 1-5,
            "assignments": [
                {"name": "agent_name", "role": "...", "task": "...", "system_prompt": "...", "model": "moonshotai/kimi-k2:free"}
            ]
        }
        
        Names must be lowercase snake_case (e.g., market_analyzer, data_collector).
        """