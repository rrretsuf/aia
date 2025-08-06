import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from ..database import get_supabase
from ..redis_client import get_redis
from ..models.agent import Agent, AgentStatus
from ..models.task import Task, TaskStatus
from ..models.communication import A2AMessage, ResearchFinding
from ..models.holon import Holon

logger = structlog.get_logger()

class SharedState: 
    """
    Central communication and state management system for all agents.
    Handles message passing, task coordination, and shared data storage.
    """
        
    def __init__(self):
        self.supabase = get_supabase()
        self.redis = get_redis()
        self.logger = logger.bind(component="shared_state")
        self._message_listeners = {}
        self._running = False

    async def initialize(self):
        """
        Initialize the shared state system.
        """
        self.logger.info("Initializing SharedState")

        # Test Connections
        db_healty = await self._test_database()
        redis_healthy = await self._test_redis()

        if not db_healty or not redis_healthy:
            raise Exception("Failed to initialize SharedState - connection issues")

        # Start message processing loop 
        self._running = True
        asyncio.create_task(self._message_processing_loop())

        self.logger.info("SharedState initialized successfully")

    async def shutdown(self):
        """
        Shutdown the shared state system.
        """
        self._running = False
        self.logger.info("ShareState shutdown")

    # --------- AGENT MANAGEMENT ---------

    async def register_agent(self, agent: Agent):
        """
        Register a new agent in the shared state.
        """
        try: 
            agent_data = {
                "agent_id": agent.id,
                "name": agent.name,
                "agent_type": agent.agent_type,
                "holon_id": agent.holon_id,
                "status": agent.status,
                "capabilities": json.dumps([cap.dict() for cap in agent.capabilities]),
                "max_concurrent_tasks": agent.max_concurrent_tasks,
                "performance_metrics": json.dumps(agent.performance_metrics),
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
            }

            response = self.supabase.table("agent_states").upsert(agent_data).execute()

            await self.redis.hset(
                f"agent:{agent.id}",
                mapping={
                    "status": agent.status,
                    "holon_id": agent.holon_id,
                    "last_seen": datetime.utcnow().isoformat(),
                }
            )
            await self.redis.expire(f"agent:{agent.id}", 3600) # 1 hour ttl

            await self._add_agent_to_holon(agent.holon_id, agent.id)

            self.logger.info(f"Agent registered: {agent.id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to register agent {agent.id}: {str(e)}")
            return False
        
    async def update_agent_status(self, agent_id: str, status: AgentStatus):
        """
        Update the status of an existing agent.
        """
        try:
            self.supabase.table("agent_states").update({
                "status": status,
                "last_activity": datetime.utcnow().isoformat()
            }).eq("agent_id", agent_id).execute()

            await self.redis.hset(f"agent:{agent_id}", "status", status)

            self.logger.debug(f"Agent {agent_id} status updated to {status}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to update agent {agent_id} status: {str(e)}")
            return False
        
    async def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """
        Get the current status of an agent.
        """
        try:
            status = await self.redis.hget(f"agent:{agent_id}", "status")
            if status:
                return AgentStatus(status)
            
            response = self.supabase.table("agent_states").select("status").eq("agent_id", agent_id).execute()
            if response.data:
                return AgentStatus(response.data[0]["status"])
                
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get agent {agent_id} status: {str(e)}")
            return None
        
    async def get_agents_by_holon(self, holon_id: str) -> List[str]:
        """
        Get a list of agent IDs belonging to a specific holon.
        """
        try:
            response = self.supabase.table("agent_states").select("agent_id").eq("holon_id", holon_id).execute()
            return [row["agent_id"] for row in response.data]
        except Exception as e:
            self.logger.error(f"Failed to get agents for holon {holon_id}: {str(e)}")
            return []
        
    # --------- TASK MANAGEMENT ---------

    async def create_task(self, task: Task) -> bool:
        """
        Create a new task
        """
        try:
            task_data = {
                "id": task.id,
                "human_request": task.human_request,
                "status": task.status,
                "priority": task.priority,
                "created_at": task.created_at.isoformat(),
                "assigned_agents": task.assigned_agents,
                "subtasks": task.subtasks,
                "parent_task_id": task.parent_task_id,
                "progress": float(task.progress)
            }

            self.supabase.table("tasks").upsert(task_data).execute()

            await self.redis.zadd(
                f"queue:tasks", 
                {json.dumps({"task_id": task.id, "priority": task.priority}): task.priority}
            )

            self.logger.info(f"Task created: {task.id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to create task {task.id}: {str(e)}")
            return False
    
    async def update_task(self, task: Task) -> bool:
        """
        Update an existing task
        """
        try: 
            task_data = {
                "status": task.status,
                "progress": float(task.progress),
                "results": json.dumps(task.results) if task.results else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "assigned_agents": task.assigned_agents,
            }

            self.supabase.table("tasks").update(task_data).eq("id", task.id).execute()

            self.logger.info(f"Task updated: {task.id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to update task {task.id}: {str(e)}")
            return False
        
    async def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by its ID
        """
        try: 
            response = self.supabase.table("tasks").select("*").eq("id", task_id).execute()
            if response.data:
                data = response.data[0]
                return Task(
                    id=data["id"],
                    human_request=data["human_request"],
                    status=TaskStatus(data["status"]),
                    priority=data["priority"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    completed_at=datetime.fromisoformat(data["completed_at"]) if data["completed_at"] else None,
                    results=json.loads(data["results"]) if data["results"] else None,
                    assigned_agents=data["assigned_agents"],
                    subtasks=data["subtasks"] or [],
                    parent_task_id=data["parent_task_id"],
                    progress=float(data["progress"] or 0)
                )
            return None
        
        except Exception as e:
            self.logger.error(f"Failed to get task {task_id}: {str(e)}")
            return None
        
    async def claim_next_task(self, agent_id: str, capabilites: List[str]) -> Optional[Task]:
        """
        Claim the next available task for an agent.
        """
        try:
            result = await self.redis.zpopmax(f"queue:tasks")
            if not result:
                return None
            
            task_info = json.loads(result[0][0])
            task = await self.get_task(task_info["task_id"])

            if task and task.status == TaskStatus.PENDING:
                task.assigned_agents.append(agent_id)
                task.status = TaskStatus.IN_PROGRESS
                await self.update_task(task)

                self.logger.info(f"Task {task.id} claimed by agent {agent_id}")
                return task
            
            return None
        
        except Exception as e:
            self.logger.error(f"Failed to claim next task for agent {agent_id}: {str(e)}")
            return None
        
    # --------- MESSAGE PASSING ---------

    async def send_message(self, message: A2AMessage) -> bool:
        """
        Send a message to another agent.
        """
        try: 
            message_data = {
                "id": message.id,
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "holon_broadcast": message.holon_broadcast,
                "message_type": message.message_type,
                "payload": json.dumps(message.payload),
                "timestamp": message.timestamp.isoformat(),
                "requires_response": message.requires_response,
                "response_to": message.response_to,
                "priority": int(message.priority),
                "ttl": message.ttl,
                "processed": False
            }

            self.supabase.table("agent_messages").insert(message_data).execute()

            queue_key = f"messages:{message.to_agent}" if message.to_agent else f"messages:holon:{message.holon_broadcast}"
            await self.redis.lpush(queue_key, message.id)

            self.logger.info(f"Message sent: {message.id} from {message.from_agent} to {message.to_agent}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to send message {message.id}: {str(e)}")
            return False
        
    async def get_messages_for_agent(self, agent_id: str) -> List[A2AMessage]:
        """
        Get unprocessed messages for a specific agent.
        """
        try: 
            direct_messages = await self._get_direct_messages(agent_id)

            agent_holon = await self._get_agent_holon(agent_id)
            holon_messages = await self._get_holon_messages(agent_holon) if agent_holon else []

            all_messages = direct_messages + holon_messages

            messages = []
            for msg_data in all_messages:
                try: 
                    message = A2AMessage(
                        id=msg_data["id"],
                        from_agent=msg_data["from_agent"],
                        to_agent=msg_data["to_agent"],
                        holon_broadcast=msg_data["holon_broadcast"],
                        message_type=msg_data["message_type"],
                        payload=json.loads(msg_data["payload"]),
                        timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                        requires_response=msg_data["requires_response"],
                        response_to=msg_data["response_to"],
                        priority=msg_data["priority"],
                        ttl=msg_data["ttl"],
                        processed=msg_data["processed"]
                    )
                    messages.append(message)

                except Exception as e:
                    self.logger.error(f"Failed to parse message {msg_data['id']}: {str(e)}")
            
            return messages
        
        except Exception as e:
            self.logger.error(f"Failed to get messages for agent {agent_id}: {str(e)}")
            return []
        
    async def mark_messages_processed(self, message_id: str) -> bool:
        """
        Mark a message as processed.
        """
        try: 
            self.supabase.table("agent_messages").update({
                "processed": True
            }).eq("id", message_id).execute()

            return True
        
        except Exception as e:
            self.logger.error(f"Failed to mark message {message_id} as processed: {str(e)}")
            return False
        
    # --------- RESEARCH FINDINGS ---------

    async def add_findings(self, findings: ResearchFinding) -> bool:
        """
        Add research findings.
        """
        try: 
            finding_data = {
                "id": finding.id,
                "task_id": finding.task_id,
                "agent_id": finding.agent_id,
                "findings": json.dumps(finding.findings),
                "confidence": int(finding.confidence),
                "sources": finding.sources, 
                "created_at": finding.created_at.isoformat(),
                "verified": finding.verified
            }

            self.supabase.table("research_findings").insert(finding_data).execute()

            await self.redis.lpush(f"findings:task:{finding.task_id}", finding.id)

            self.logger.info(f"Research findings added: {finding.id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to add research finding: {e}")
            return False
        
    async def get_findings_for_task(self, task_id: str) -> List[ResearchFinding]:
        """
        Get all research findings for a task.
        """
        try: 
            response = self.supabase.table("research_findings").select("*").eq("task_id", task_id).execute()

            findings = []
            for data in response.data:
                finding = ResearchFinding(
                    id=data["id"],
                    task_id=data["task_id"],
                    agent_id=data["agent_id"],
                    findings=json.loads(data["findings"]),
                    confidence=float(data["confidence"]),
                    sources=data["sources"] or [],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    verified=data["verified"]
                )
                findings.append(finding)

            return findings
        
        except Exception as e: 
            self.logger.error(f"Failed to get findings for task {task_id}: {e}")
            return []

    # --------- PRIVATE HELPER METHODS ---------

    async def _test_database(self) -> bool:
        """
        Test the database connection.
        """
        try: 
            self.supabase.table("tasks").select("count", count="exact").execute()
            return True
        
        except Exception as e:
            self.logger.error(f"Database test failed: {str(e)}")
            return False
        
    async def _test_redis(self) -> bool:
        """
        Test the Redis connection.
        """
        try: 
            await self.redis.ping()
            return True
        
        except Exception as e:
            self.logger.error(f"Redis test failed: {str(e)}")
            return False
        
    async def _add_agent_to_holon(self, holon_id: str, agent_id: str):
        """
        Add an agent to a holon's agent list.
        """
        try:
            response=self.supabase.table("holons").select("agents").eq("id", holon_id).execute()
            if response.data:
                current_agents = response.data[0]["agent_id"] or []
                if agent_id not in current_agents:
                    current_agents.append(agent_id)
                    self.supabase.table("holons").update({
                        "agents": current_agents,
                        "last_activity": datetime.utcnow().isoformat()
                    }).eq("id", holon_id).execute()

        except Exception as e:
            self.logger.error(f"Failed to add agent {agent_id} to holon {holon_id}: {str(e)}")

    async def _get_direct_messages(self, agent_id: str) -> List[Dict]:
        """
        Get direct messages for a specific agent.
        """
        response = self.supabase.table("agent_messages").select("*").eq(
            "to_agent", agent_id
        ).eq("processed", False).execute()
        return response.data or []
    
    async def _get_holon_messages(self, holon_id: str) -> List[Dict]:
        """
        Get messages broadcasted to a holon.
        """
        response = self.supabase.table("agent_messages").select("*").eq(
            "holon_broadcast", holon_id
        ).eq("processed", False).execute()
        return response.data or []
    
    async def _get_agent_holon(self, agent_id: str) -> Optional[str]:
        """
        Get the holon ID for a specific agent.
        """
        try:
            holon_id = await self.redis.hget(f"agent:{agent_id}", "holon_id")
            if holon_id:
                return holon_id
                
            response = self.supabase.table("agent_states").select("holon_id").eq(
                    "agent_id", agent_id
                ).execute()
            if response.data:
                return response.data[0]["holon_id"]
            
            return None
        
        except Exception as e:
            self.logger.error(f"Failed to get holon for agent {agent_id}: {str(e)}")
            return None
        
    async def _message_processing_loop(self):
        """
        Background loop to process expired messages
        """
        try: 
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            self.supabase.table("agent_messages").delete().lt(
                "timestamp", cutoff_time.isoformat()
            ).eq("processed", True).execute()
        
            await asyncio.sleep(300)

        except Exception as e:
            self.logger.error(f"Message processing loop failed: {str(e)}")
            await asyncio.sleep(60)

async def get_shared_state() -> SharedState:
    """
    Get the global ShareState instance.
    """
    global _shared_state
    if _shared_state is None:
        _shared_state = SharedState()
        await _shared_state.initialize()
    return _shared_state