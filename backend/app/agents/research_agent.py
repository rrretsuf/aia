from typing import Dict, Any, Optional
import structlog
from .base_agent import BaseAgent
from ..models.agent import AgentType
from ..llm.openrouter_client import get_openrouter_client
import asyncio

logger = structlog.get_logger()

class ResearchAgent(BaseAgent):

    def __init__(self, agent_number: int):
        agent_id = f"research_{agent_number:03d}"
        super().__init__(agent_id=agent_id, agent_type=AgentType.RESEARCH)
        self.agent_number = agent_number
        self.llm_client = get_openrouter_client()

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute research task
        """
        research_query = task["human_request"]

        assigned_role = self._extract_role(research_query)
        clean_query = self._clean_query(research_query)

        logger.info(f"Agent {self.agent_id} is RESEARCHING: {clean_query}")
        if assigned_role:
            logger.info(f"Role: {assigned_role}")

        try:
            findings = await self._web_research(clean_query, assigned_role)
        
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return self._error_response(research_query, str(e))
        
        return {
            "agent_id": self.agent_id,
            "assigned_role": assigned_role or "General Researcher",
            "query": research_query,
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
    
    async def _web_research(self, query: str, role: Optional[str]) -> dict:
        if role: 
            system_prompt = f"You are a {role}. Research the web and analyse fromrole's perspective."
        else:
            system_prompt = f"You are research specialist. Search the web and provide comprehensive analysis."

        search_message = f"Research: {query}\n\nProvide detailed analysis with current information."

        response = await self.llm_client.generate_response(
            system_prompt=system_prompt,
            human_message=search_message,
            web_search=True,
            temperature=0.3
        )

        return {
            "summary": response[:200] + "...",
            "detailed_analysis": response,
            "confidence": 0.8 # placeholder for now
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