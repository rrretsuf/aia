from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio
import structlog
from datetime import datetime

from ..models.holon import Holon, HolonStatus, HolonType
from ..models.agent import Agent, AgentStatus
from ..models.task import Task
from ..models.communication import A2AMessage, MessageType
from ..communication.shared_state import SharedState

logger = structlog.get_logger()

class BaseHolon(ABC):
    """
    Base class for all holons (agent groups) in the system
    """

    def __init__(
        self,
        holon_id: str,
        name: str,
        holon_type: HolonType,
        max_agents: int= 10
    ):
        self.holon_id = holon_id
        self.name = name
        self.holon_type = holon_type
        self.max_agents = max_agents
        self.status = HolonStatus.IDLE
        self.agent_ids: List[str] = []
        self.current_tasks: List[str] = []
        self.capabilities: List[str] = []
        self.shared_state: Optional[SharedState] = None
        self.running = False
        self.logger = logger.bind(holon_id=holon_id, holon_type=holon_type.value)

    async def initialize(self, shared_state: SharedState):
        """
        Initialize holon with shared state.
        """
        self.shared_state = shared_state
        await self._register_holon()
        self.logger.info("Holon initialized")

    async def start(self):
        """
        Start the holon's coordination loop.
        """
        if self.running:
            return
        
        self.running = True
        self.logger.info("Starting holon coordination")

        try: 
            await self._coordination_loop()
        
        except Exception as e: 
            self.logger.error(f"Holon coordination crashed: {e}")
        
        finally:
            self.running = False
            await self.cleanup()

    async def stop(self):
        """
        Stop the holon
        """
        self.logger.info("Stopping holon")
        self.running = False
        await self._update_status(HolonStatus.OFFLINE)

    async def _coordination_loop(self):
        """
        Main coordination loop for managing agents and tasks
        """
        while self.running: 
            try: 
                await self._refresh_agents() # update agent list
                await self._monitor_agents() # monitor agent health
                await self._coordinate_tasks() # coordinate tasks
                await self._update_holon_status() # update holon status
                await asyncio.sleep(5) 
            
            except Exception as e:
                self.logger.error(f"Error in coordination loop: {e}")
                await asyncio.sleep(10)
        
    async def add_agent(self, agent_id: str) -> bool:
        """
        Add an agent to this holon.
        """
        if len(self.agent_ids) >= self.max_agents:
            self.logger.warning(f"Cannot add agent {agent_id}: holon at capacity")
            return False
        if agent_id not in self.agent_ids:
            self.agent_ids.append(agent_id)
            await self._update_holon_data()
            self.logger.info(f"Agent {agent_id} added to holon")
            return True
        
        return True
    
    async def remove_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from this holon.
        """
        if agent_id in self.agent_ids:
            self.agent_ids.remove(agent_id)
            await self._update_holon_data()
            self.logger.info(f"Agent {agent_id} removed from holon")
            return True
        
        return False
    
    async def get_active_agents(self) -> List[str]:
        """
        Get list of current active agents
        """
        if not self.shared_state:
            return []
        
        active_agents = []
        for agent_id in self.agent_ids:
            status = await self.shared_state.get_agent_status(agent_id)
            if status and status != AgentStatus.OFFLINE:
                active_agents.append(agent_id)
        
        return active_agents

    async def get_idle_agents(self) -> List[str]:
        """
        Get list of idle agents that can take new tasks.
        """
        if not self.shared_state:
            return []
        
        idle_agents = []
        for agent_id in self.agent_ids:
            status = await self.shared_state.get_agent_status(agent_id)
            if status == AgentStatus.IDLE:
                idle_agents.append(agent_id)
        
        return idle_agents

    async def broadcast_message(self, message_type: MessageType, payload: Dict[str, Any]):
        """
        Broadcast a message to all agents in the holon.
        """
        if not self.shared_state:
            return
        
        message = A2AMessage(
            from_agent=f"holon_{self.holon_id}",
            holon_broadcast=self.holon_id,
            message_type=message_type,
            payload=payload
        )

        await self.shared_state.send_message(message)
        self.logger.debug(f"Broadcast {message_type} to holon agents")

    async def assign_task_to_agent(self, task: Task, agent_id: str) -> bool:
        """
        Assign a task to a specific agent.
        """
        if not self.shared_state:
            return False
        
        if agent_id not in self.agent_ids:
            self.logger.warning(f"Cannot assign task {task.task_id} to agent {agent_id}: not in holon")
            return False

        status = await self.shared_state.get_agent_status(agent_id)
        if status != AgentStatus.IDLE:
            self.logger.warning(f"Cannot assign task {task.task_id} to agent {agent_id}: not idle")
            return False
        
        messsage = A2AMessage(
            from_agent=f"holon_{self.holon_id}",
            to_agent=agent_id,
            message_type=MessageType.TASK_ASSIGNMENT,
            payload={
                "task": task.dict(),
                "assigned_by": self.holon_id
            }
        )

        success = await self.shared_state.send_message(messsage)
        if success: 
            if task.id not in self.current_tasks:
                self.current_tasks.append(task.id)
            self.logger.info(f"Task {task.task_id} assigned to agent {agent_id}")
        
        return success
    
    @abstractmethod
    async def coordinate_tasks(self) -> None:
        """
        Coordinate tasks among agents in the holon.
        """
        pass

    @abstractmethod
    async def handle_agent_message(self, message: A2AMessage) -> None:
        """
        Handle incoming messages from agents.
        """
        pass

    async def _register_holon(self):
        """
        Register this holon in the shared state.
        """
        if not self.shared_state:
            return
        
        try: 
            holon_data = {
                "id": self.holon_id,
                "name": self.name,
                "holon_type": self.holon_type.value,
                "status": self.status.value,
                "agent_ids": self.agent_ids,
                "max_agents": self.max_agents,
                "current_tasks": self.current_tasks,
                "capabilities": self.capabilities,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "perfomance_metrics": {}
            }

            self.shared_state.supabase.table("holons").insert(holon_data).execute()
            self.logger.info(f"Holon {self.holon_id} registered successfully")

        except Exception as e:
            self.logger.error(f"Failed to register holon: {e}")
    
    async def _refresh_agents(self):
        """
        Refresh the list of agents in this holon.
        """
        if not self.shared_state:
            return
        
        try:
            db_agents = await self.shared_state.get_agents_by_holon(self.holon_id)

            if set(db_agents) != set(self.agent_ids):
                self.agent_ids = db_agents
                await self._update_holon_data()
                self.logger.info(f"Refreshed agents in holon {self.holon_id}: {self.agent_ids}")
        
        except Exception as e:
            self.logger.error(f"Error refreshing agents: {e}")


    async def _monitor_agents(self):     
        """
        Monitor the health of agents in this holon.
        """
        if not self.shared_state:
            return
        
        for agent_id in self.agent_ids.copy():
            try: 
                status = await self.shared_state.get_agent_status(agent_id)

                if status == AgentStatus.ERROR:
                    self.logger.warning(f"Agent {agent_id} in error state")
                    await self._handle_agent_error(agent_id)
                elif status == AgentStatus.OFFLINE:
                    self.logger.warning(f"Agent {agent_id} is offline")
                
            except Exception as e:
                self.logger.error(f"Error monitoring agent {agent_id}: {e}")

    async def _coordinate_tasks(self):
        """
        Coordinate tasks among agents in the holon.
        """
        try:
            await self.coordinate_tasks()

        except Exception as e:
            self.logger.error(f"Error coordinating tasks: {e}")

    async def _update_holon_status(self):
        """
        Update the holon's status in the shared state.
        """
        if not self.shared_state:
            new_status = HolonStatus.IDLE
        
        else:
            active_agents = await self.get_active_agents()
            if not active_agents:
                new_status = HolonStatus.OFFLINE
            elif len(self.current_tasks) > 0:
                new_status = HolonStatus.BUSY
            else: 
                new_status = HolonStatus.ACTIVE
        
        if new_status != self.status:
            await self._update_status(new_status)

    async def _update_status(self, new_status: HolonStatus):
        """
        Update the holon's status.
        """
        if not self.shared_state:
            return

        try: 
            update_data = {
                "status": new_status.value,
                "agent_ids": self.agent_ids,
                "current_tasks": self.current_tasks,
                "last_activity": datetime.utcnow().isoformat()
            }
            self.shared_state.supabase.table("holons").update(update_data).eq(
                "id", 
                self.holon_id
            ).execute()
        
        except Exception as e:
            self.logger.error(f"Failed to update holon status: {e}")
    
    async def _handle_agent_error(self, agent_id: str):
        """
        Handle an agent that is in error state.
        """
        self.logger.warning(f"Handling error for agent {agent_id}")


    async def _cleanup(self):
        """
        Cleanup resources when holon is stopped.
        """
        await self._update_status(HolonStatus.OFFLINE)
        self.logger.info("Holon cleanup complete")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this holon.
        """
        return {
            "active_tasks": len(self.current_tasks),
            "status": self.status.value,
            "total_agents": len(self.agent_ids),
            "last_activity": datetime.utcnow().isoformat()
        }