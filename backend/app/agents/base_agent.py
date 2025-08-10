from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import asyncio
import structlog

from ..models.agent import Agent, AgentStatus, AgentType
from ..models.task import Task
from ..core.task_manager import claim_task, complete_task
from ..core.message_bus import notify_agent_status
from ..redis_client import set_agent_status

logger = structlog.get_logger()

class BaseAgent(ABC):
    """
    Base class for all agents in the AI Agency system.
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.status = AgentStatus.IDLE
        self.current_task: Optional[Task] = None
        self.running = False
        self.logger = logger.bind(agent_id=agent_id, agent_type=agent_type.value)

    async def start(self):
        """
        Start the agent's main loop.
        """
        self.running = True
        self.logger.info(f"Agent {self.agent_id} started")
        
        await set_agent_status(self.agent_id, AgentStatus.IDLE.value)
        await notify_agent_status(self.agent_id, AgentStatus.IDLE.value)

        await self._main_loop()
    
    async def stop(self): 
        """
        Stop the agent's main loop and perform cleanup.
        """
        self.running = False
        await set_agent_status(self.agent_id, AgentStatus.OFFLINE.value)
        await notify_agent_status(self.agent_id, AgentStatus.OFFLINE.value)
        self.logger.info(f"Stopping agent {self.agent_id}")

    
    async def _main_loop(self):
        """
        Main loop for the agent. This should be implemented by subclasses.
        """
        while self.running:
            try: 
                if self.status == AgentStatus.IDLE:
                    task = await claim_task(self.agent_id, self.agent_type.value)
                    if task: 
                        self.current_task = task
                        self.status = AgentStatus.WORKING

                        result = await self.process_task(task)

                        await complete_task(
                            task["id"],
                            self.agent_id,
                            result
                        )

                        self.current_task = None
                        self.status = AgentStatus.IDLE
                
                await asyncio.sleep(1)  

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)  

    @abstractmethod
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a task
        """
        pass