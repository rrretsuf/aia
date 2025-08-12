import asyncio
from typing import Dict, Optional
import structlog
from datetime import datetime, timedelta

from .research_agent import ResearchAgent
from ..redis_client import get_agent_status
from ..config import get_settings

logger = structlog.get_logger()

settings = get_settings()

class AgentFactory:
    """
    Manages dynamic agent spawning and lifecycle.
    """

    def __init__(self):
        self.active_agents: Dict[str, ResearchAgent] = {}
        self.max_counter = 0
        self.max_agents = settings.max_agents
        self.agent_timeout = timedelta(seconds=settings.agent_timeout)
        self.logger = logger.bind(component="AgentFactory")

    async def ensure_capacity(self, required: int) -> int:
        """
        Ensure we have at least 'required' agents running. Returns actual number spawned.
        """
        required = min(required, self.max_agents)
        current_count = len(self.activate_agents)

        if current_count >= required:
            self.logger.info(f"Capacity OK: {current_count}/{required} agents active")
            return 0
        
        to_spawn = required - current_count
        self.logger.info(f"Spawning {to_spawn} new agents (current: {current_count})")

        spawned = 0
        for _ in range(to_spawn):
            if len(self.active_agents) >= self.max_agents:
                self.logger.warning(f"Hit max agent limit {self.max_agents}")
                break

            agent = await self._spawn_agent()
            if agent:
                spawned += 1

        return spawned
    
    async def _spawn_agent(self) -> Optional[ResearchAgent]:
        """
        Spawn a single new agent.
        """
        self.agent_counter += 1
        agent_number = self.agent_counter

        try:
            agent = ResearchAgent(agent_number)
            self.active_agents[agent.agent_id] = agent

            asyncio.create_task(agent.start())

            self.logger.info(f"Spawned agent: {agent.agent_id}")
            return agent
        
        except Exception as e:
            self.logger.error(f"Failed to spawn agent: {e}")
            return None
        
    async def shrink_idle(self) -> int: 
        """
        Remove idle agents that exceeded timeout. Returns number of agents removed.
        """
        removed = 0
        now = datetime.utcnow()

        for agent_id in list(self.active_agents.keys()):
            status = await get_agent_status(agent_id)

            if status == "idle":
                # for now simple approach - remove if idle
                if len(self.active_agents) > 1:
                    agent = self.active_agents.pop(agent_id)
                    await agent.stop()
                    removed += 1 
                    self.logger.info(f"Removed idle agent: {agent_id}")

        return removed
    
    async def shutdown_all(self):
        """
        Stop all active agents.
        """
        self.logger.info(f"Shutting down {len(self.active_agents)} agents")

        for agent in self.active_agents.values():
            await agent.stop()

        self.active_agents.clear()
        self.logger.info("All agents are shut down")

    def get_active_count(self) -> int:
        """
        Get number of currently active agents.
        """
        return len(self.active_agents)
    
    def get_active_ids(self) -> list:
        """
        Get list of active agent IDs.
        """
        return list(self.active_agents.keys())