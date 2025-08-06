from pydantic import BaseModel, Field
from typing import List, Dict
from datetime import datetime
from enum import Enum

class HolonType(str, Enum):
    HIVE = "hive"
    RESEARCH = "research"

class HolonStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"

class Holon(BaseModel):
    id: str 
    name: str
    holon_type: HolonType
    status: HolonStatus = HolonStatus.IDLE
    agents_ids: List[str] = Field(default_factory=list)
    max_agents: int = Field(default=10)
    current_tasks: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    performance_metrics: Dict[str, float] = Field(default_factory=dict)

    class Config:
        use_enum_values = True

class HolonMetrics(BaseModel):
    holon_id: str
    active_agents: int
    total_tasks_completed: int
    average_task_time: float
    success_rate: float
    current_load: float
    last_updated: datetime = Field(default_factory=datetime.utcnow)