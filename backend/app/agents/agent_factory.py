import asyncio
from typing import Dict, Optional, List
import structlog
from datetime import datetime, timedelta

from .worker_agent import WorkerAgent
from ..redis_client import get_agent_status
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class AgentFactory:
    """
    Manages dynamic agent spawning by name (not by number).
    """
    
    def __init__(self):
        self.active_agents: Dict[str, WorkerAgent] = {}
        self.max_agents = settings.max_agents
        self.agent_timeout = timedelta(seconds=settings.agent_timeout)
        self.logger = logger.bind(component="AgentFactory")
    
    async def ensure_agents(self, required_names: List[str]) -> int:
        """
        Ensure all agents with given names are running.
        Returns number of newly spawned agents.
        """
        spawned = 0
        
        for name in required_names:
            if name in self.active_agents:
                self.logger.debug(f"Agent {name} already active")
                continue
            
            if len(self.active_agents) >= self.max_agents:
                self.logger.warning(f"Max agents reached ({self.max_agents}), cannot spawn '{name}'")
                break
            
            agent = await self._spawn_agent(name)
            if agent:
                spawned += 1
        
        return spawned
    
    async def _spawn_agent(self, agent_name: str) -> Optional[WorkerAgent]:
        """
        Spawn a single agent with specific name.
        """
        try:
            agent = WorkerAgent(agent_name)
            self.active_agents[agent.agent_id] = agent
            
            # Start agent in background
            asyncio.create_task(agent.start())
            
            self.logger.info(f"Spawned agent: {agent_name}")
            return agent
            
        except Exception as e:
            self.logger.error(f"Failed to spawn agent {agent_name}: {e}")
            return None
    
    async def shrink_idle(self) -> int:
        """
        Remove idle agents that exceeded timeout.
        Returns number of agents removed.
        """
        removed = 0
        
        for agent_id in list(self.active_agents.keys()):
            status = await get_agent_status(agent_id)
            
            if status == "idle":
                # Keep at least 1 agent
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
        self.logger.info("All agents shut down")
    
    def get_active_count(self) -> int:
        """
        Get number of currently active agents.
        """
        return len(self.active_agents)
    
    def get_active_names(self) -> List[str]:
        """
        Get list of active agent names.
        """
        return list(self.active_agents.keys())