from typing import Dict, Any, Optional
import structlog
import re
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..llm.openrouter_client import get_openrouter_client

logger = structlog.get_logger()

class WorkerAgent(BaseAgent):
    """
    Generic worker agent that executes tasks based on Brain Hive's configuration.
    """
    
    def __init__(self, agent_name: str):
        super().__init__(agent_id=agent_name, agent_type=AgentType.WORKER)
        self.llm_client = get_openrouter_client()

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute task with dynamic configuration from Brain Hive.
        """
        task_description = task["human_request"]
        
        config = self._parse_cfg_header(task_description)
        clean_task = self._clean_task(task_description)
        
        name = config.get('name', self.agent_id)
        role = config.get('role', 'Generic Worker')
        system_prompt = config.get('system_prompt', '')
        model = config.get('model', 'moonshotai/kimi-k2:free')
        
        logger.info(f"Worker {self.agent_id} executing: {clean_task}")
        logger.info(f"Config - Name: {name}, Role: {role}, Model: {model}")
        
        try:
            result = await self._execute_task(clean_task, role, system_prompt, model)
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return self._error_response(clean_task, str(e))
        
        return {
            "agent_id": self.agent_id,
            "agent_name": name,
            "assigned_role": role,
            "task": clean_task,
            "model_used": model,
            "findings": result
        }
    
    def _parse_cfg_header(self, task: str) -> Dict[str, str]:
        """
        Parse [CFG name="..." role="..." model="..." sys="..."] header.
        """
        cfg_pattern = r'\[CFG\s+(.*?)\]'
        match = re.search(cfg_pattern, task)
        
        if not match:
            return {}
        
        cfg_str = match.group(1)
        config = {}
        
        name_match = re.search(r'name="([^"]*)"', cfg_str)
        if name_match:
            config['name'] = name_match.group(1)
        
        role_match = re.search(r'role="([^"]*)"', cfg_str)
        if role_match:
            config['role'] = role_match.group(1)
        
        model_match = re.search(r'model="([^"]*)"', cfg_str)
        if model_match:
            config['model'] = model_match.group(1)
        
        sys_match = re.search(r'sys="((?:[^"\\]|\\.)*)"', cfg_str)
        if sys_match:
            config['system_prompt'] = sys_match.group(1).replace('\\"', '"')
        
        return config
    
    def _clean_task(self, task: str) -> str:
        """
        Remove [CFG ...] header from task description.
        """
        cfg_pattern = r'\[CFG\s+.*?\]\s*'
        return re.sub(cfg_pattern, '', task).strip()
    
    async def _execute_task(self, task: str, role: str, system_prompt: str, model: str) -> dict:
        """
        Execute task with custom configuration from Brain Hive.
        """
        if system_prompt:
            final_system_prompt = system_prompt
        elif role:
            final_system_prompt = f"You are a {role}. Execute this task with expertise and thoroughness."
        else:
            final_system_prompt = "You are a specialized worker. Complete the following task professionally."
        
        task_message = f"Task: {task}\n\nProvide comprehensive analysis with current information."
        
        response = await self.llm_client.generate_response(
            system_prompt=final_system_prompt,
            human_message=task_message,
            web_search=True,
            temperature=0.3,
            model_override=model
        )
        
        return {
            "summary": response[:200] + "..." if len(response) > 200 else response,
            "detailed_analysis": response,
            "confidence": 0.8
        }
    
    def _error_response(self, task: str, error: str) -> dict:
        """
        Return error response structure.
        """
        return {
            "agent_id": self.agent_id,
            "task": task,
            "findings": {
                "summary": f"Task failed: {error}",
                "detailed_analysis": "Unable to complete task",
                "confidence": 0.0
            }
        }