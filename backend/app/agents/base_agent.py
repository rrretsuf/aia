from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio
import structlog
from datetime import datetime

from ..models.agent import Agent, AgentStatus, AgentType, AgentCapability
from ..models.communication import A2AMessage, MessageType
from ..models.task import Task, TaskStatus
from ..communication.shared_state import SharedState

logger = structlog.get_logger()

class BaseAgent(ABC):
    """
    Base class for all agents in the AI Agency system.
    """

    def __init__(
        self,
        agent_id: str,
        name: str, 
        agent_type: AgentType,
        holon_id: str,
        capabilites: List[AgentCapability] = None
    ):
        self.agent_id = agent_id
        self.name = name
        self.agent_type = agent_type
        self.holon_id = holon_id
        self.capabilities = capabilites or []
        self.status = AgentStatus.IDLE
        self.current_task: Optional[Task] = None
        self.shared_state = Optional[SharedState] = None
        self.running = False
        self.logger = logger.bind(agent_id=agent_id, agent_type=agent_type.value)

    async def initialize(self, shared_state: SharedState):
        """
        Initialize the agent with shared state.
        """
        self.shared_state = shared_state
        await self._register_agent()
        self.logger.info("Agent initialized")

    async def start(self):
        """
        Start the agent's main loop.
        """
        self.running = True
        self.logger.info("Agent started")
        
        try: 
            await self._main_loop()

        except Exception as e:
            self.logger.error("Error in agent main loop", error=str(e))
            await self._handle_error(e)
        finally:
            self.running = False
            await self._cleanup()
    
    async def stop(self): 
        """
        Stop the agent's main loop and perform cleanup.
        """
        self.logger.info("Stopping agent")
        self.running = False
        await self._update_status(AgentStatus.OFFLINE)
    
    async def _main_loop(self):
        """
        Main loop for the agent. This should be implemented by subclasses.
        """
        while self.running:
            try: 
                await self._process_messages()

                if self.status == AgentStatus.IDLE:
                    await self._check_for_tasks()

                if self.status == AgentStatus.WORKING and self.current_task:
                    await self._process_current_task()
                
                await asyncio.sleep(1)  

            except Exception as e:
                self.logger.error("Error in main loop", error=str(e))
                await asyncio.sleep(5)  

    async def _process_messages(self):
        """
        Process incoming messages.
        """
        messages = await self.shared_state.get_messages_for_agent(self.agent_id)
        
        for message in messages:
            try: 
                await self._handle_message(message)
                await self.shared_state.mark_messages_processed(message.id)

            except Exception as e:
                self.logger.error("Error processing message", message_id=message.id, error=str(e))

    async def _handle_message(self, message: A2AMessage):
        """
        Handle incoming messages.
        """
        if message.message.type == MessageType.TASK_ASSIGNMENT:
            await self._handle_task_assigment(message)
        elif message.message.type == MessageType.STATUS_UPDATE:
            await self._handle_status_update(message)
        elif message.message.type == MessageType.HEALTH_CHECK:
            await self._handle_health_check(message)
        elif message.message.type == MessageType.RESULT_SHARING:
            await self._handle_result_sharing(message)
        else:
            self.logger.warning("Unknown message type", message_type=message.type)
        
    async def _handle_task_assigment(self, message: A2AMessage):
        """
        Handle task assignment messages.
        """
        task_data = message.payload.get("task")

        if not task_data:
            return
        
        task = Task(**task_data)
        await self._assign_task(task)

    async def _handle_status_update(self, message: A2AMessage):
        """
        Handle status update from other agents.
        """
        self.logger.debug(f"Status update from agent {message.from_agent}: {message.payload}")

    async def handle_result_sharing(self, message: A2AMessage):
        """
        Handle result sharing messages.
        """
        self.logger.debug(f"Result sharing from agent {message.from_agent}: {message.payload}")

    async def _handle_health_check(self, message: A2AMessage):
        """
        Respond to health check messages.
        """
        response = A2AMessage(
            from_agent=self.agent_id,
            to_agent=message.from_agent,
            message_type=MessageType.STATUS_UPDATE,
            payload={
                "status": self.status.value,
                "current_task": self.current_task.id if self.current_task else None,
                "timestamp": datetime.utcnow().isoformat()
            }, 
            response_to=message.id
        )
        await self.send_message(response)

    async def assign_task(self, task: Task):
        """
        Assign a task to this agent.
        """
        if self.status != AgentStatus.IDLE:
            self.logger.warning(f"Agent {self.agent_id} is not idle, cannit assign task.")
            return False
        
        self.current_task = task
        await self._update_status(AgentStatus.WORKING)
        self.logger.info(f"Assigned task: {task.id}")

        asyncio.create_task(self._execute_task(task))
        return True
    
    async def _execute_task(self, task: Task):
        """
        Execute the assigned task.
        """
        try:
            self.logger.info(f"Starting task execution {task.id}")
            result = await self.process_task(task)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.progress = 1.0

            await self._complete_task(task)

        except Exception as e:
            self.logger.error(f"Error executing task {task.id}", error=str(e))
            task.status = TaskStatus.FAILED
            await self._fail_task(task, str(e))

    @abstractmethod
    async def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process the task. This should be implemented by subclasses.
        """
        pass

    async def _complete_task(self, task: Task):
        """
        Handle task completion.
        """
        self.logger.info(f"Task {task.id} completed successfully")

        await self.shared_state.update_task(task)

        await self._broadcast_to_holon({
            "type": "task_completed",
            "task_id": task.id,
            "agent_id": self.agent_id,
            "result": task.result
        })

        self.current_task = None
        await self._update_status(AgentStatus.IDLE)

    async def _fail_task(self, task: Task, error: str):
        """
        Handle task failure.
        """
        self.logger.error(f"Task {task.id} failed", error=error)

        await self.shared_state.update_task(task)

        await self._broadcast_to_holon({
            "type": "task_failed",
            "task_id": task.id,
            "agent_id": self.agent_id,
            "error": error
        })

        self.current_task = None
        await self._update_status(AgentStatus.IDLE)

    async def send_message(self, message: A2AMessage):
        """
        Send a message to another agent.
        """
        if not self.shared_state:
            raise RuntimeError("Shared state not initialized")
        
        await self.shared_state.send_message(message)
        self.logger.debug("Message sent", message_id=message.id, to_agent=message.to_agent)

    async def broadcast_to_holon(self, payload: Dict[str, Any]):
        """
        Broadcast a message to all agents in the holon.
        """
        message = A2AMessage(
            from_agent=self.agent_id,
            holon_broadcast=self.holon_id,
            message_type=MessageType.STATUS_UPDATE,
            payload=payload
        )
        await self.send_message(message)
        
    async def _update_status(self, status: AgentStatus):
        """
        Update the agent's status.
        """
        old_status = self.status
        self.status = status
        
        if self.shared_state:
            await self.shared_state.update_agent_status(self.agent_id, status)

        self.logger.info(f"Status updated: {old_status.value} -> {status.value}")

    async def _register_agent(self):
        """
        Register the agent in the shared state.
        """
        agent_data = Agent(
            id=self.agent_id,
            name=self.name,
            agent_type=self.agent_type,
            holon_id=self.holon_id,
            capabilities=self.capabilities,
            status=self.status
        )

        success = await self.shared_state.register_agent(agent_data)
        if success: 
            self.logger.info("Agent registered")
        else:
            self.logger.error("Failed to register agent")
        
    async def _check_for_tasks(self):
        """
        Check for new tasks assigned to this agent.
        """
        if not self.shared_state:
            return
        
        tasks = await self.shared_state.get_tasks_for_agent(
            self.agent_id,
            self.get_capabilities()
        )
        
        if tasks:
            await self.assign_task(tasks)

    async def _process_current_task(self):
        """
        Process the current task if it exists.
        """
        # Override in subclasses if needed for periodic task processing
        pass 

    async def _handle_error(self, error: Exception):
        """
        Handle errors that occur during the agent's operation.
        """
        await self._update_status(AgentStatus.ERROR)
        
        error_message =A2AMessage(
            from_agent=self.agent_id,
            holon_broadcast=self.holon_id,
            message_type=MessageType.ERRO_REPORT,
            payload={
                "error": str(error),
                "timestamp": datetime.utcnow().isoformat(),
                "current_task": self.current_task.id if self.current_task else None
            }
        )
        await self.send_message(error_message)

    async def _cleanup(self):
        """
        Cleanup when agent stops.
        """
        await self._update_status(AgentStatus.OFFLINE)
        self.logger.info("Agent cleanup completed")

    def get_capabilities(self) -> List[str]:
        """
        Get the list of agent capabilities.
        """
        return [cap.name for cap in self.capabilities]

    def has_capability(self, capability: str) -> bool:
        """
        Check if agent has specific capability.
        """
        return capability in self.get_capabilities()

    def get_performance_metrics(self) -> Dict[str, float]:
        """
        Get performance metrics for the agent.
        """
        return {
            'uptime': 0.0,
            'tasks_completed': 0.0,
            'success_rate': 0.0,
            'average_task_time': 0.0
        }