from typing import Dict, Any, Optional
import structlog
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..llm.openrouter_client import get_openrouter_client
import re

logger = structlog.get_logger()

class ResearchAgent(BaseAgent):

    def __init__(self, agent_number: int):
        agent_id = f"research_{agent_number:03d}"
        super().__init__(agent_id=agent_id, agent_type=AgentType.RESEARCH)
        self.agent_number = agent_number
        self.llm_client = get_openrouter_client()

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute research task with dynamic configuration.
        """
        research_query = task["human_request"]
        
        # Parse configuration header
        config = self._parse_cfg_header(research_query)
        clean_query = self._clean_query(research_query)
        
        # Extract or use defaults
        role = config.get('role', 'General Researcher')
        system_prompt = config.get('system_prompt', '')
        model = config.get('model', 'moonshotai/kimi-k2:free')
        
        logger.info(f"Agent {self.agent_id} researching: {clean_query}")
        logger.info(f"Role: {role}, Model: {model}")
        
        try:
            findings = await self._web_research(clean_query, role, system_prompt, model)
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return self._error_response(research_query, str(e))
        
        return {
            "agent_id": self.agent_id,
            "assigned_role": role,
            "query": clean_query,
            "model_used": model,
            "findings": findings
        }
    
    def _extract_role(self, task: str) -> Optional[str]:
        if task.startswith("[ROLE:"):
            end = task.find("]")
            if end != -1:
                return task[6:end].strip()
        return None
    
    def _clean_query(self, task: str) -> str:
        if task.startswith("[ROLE:"):
            end = task.find("]")
            if end != -1:
                return task[end + 1].strip()
        return task
    
    async def _web_research(self, query: str, role: str, system_prompt: str, model: str) -> dict:
        """
        Perform web research with custom configuration.
        """
        # Use provided system prompt or fall back to role-based
        if system_prompt:
            final_system_prompt = system_prompt
        elif role:
            final_system_prompt = f"You are a {role}. Research the web and analyze from this role's perspective."
        else:
            final_system_prompt = "You are a research specialist. Search the web and provide comprehensive analysis."
        
        search_message = f"Research: {query}\n\nProvide detailed analysis with current information."
        
        # pass model override
        response = await self.llm_client.generate_response(
            system_prompt=final_system_prompt,
            human_message=search_message,
            web_search=True,
            temperature=0.3,
            model_override=model
        )
        
        return {
            "summary": response[:200] + "..." if len(response) > 200 else response,
            "detailed_analysis": response,
            "confidence": 0.8
        }
    
    def _error_response(self, query: str, error: str) -> dict:
        return {
            "agent_id": self.agent_id,
            "query": query,
            "findings": {
                "summary": f"Research failed: {error}",
                "detailed_analysis": "Unable to complete research",
                "confidence": 0.0
            }
        }
    
    def _parse_cfg_header(self, task: str) -> Dict[str, str]:
        """
        Parse [CFG role="..." model="..." sys="..."] header.
        """
        cfg_pattern = r'\[CFG\s+(.*?)\]'
        match = re.search(cfg_pattern, task)
        
        if not match:
            return {}
        
        cfg_str = match.group(1)
        config = {}

        # parse role
        role_match = re.search(r'role="([^"]*)"', cfg_str)
        if role_match:
            config["role"] = role_match.group(1)

        # parse model
        model_match = re.search(r'model="([^"]*)"', cfg_str)
        if model_match:
            config["model"] = model_match.group(1)

        # parse system prompt
        sys_match = re.search(r'sys="((?:[^"\\]|\\.)*)"', cfg_str)
        if sys_match:
            config['system_prompt'] = sys_match.group(1).replace('\\"', '"')

        return config
    
    def _clean_query(self, task: str) -> str:
        """
        Remove [CFG ...] header from task.
        """
        cfg_pattern = r'\[CFG\s+.*?\]\s*'
        return re.sub(cfg_pattern, ", task").strip()

