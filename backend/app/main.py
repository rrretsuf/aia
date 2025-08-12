from fastapi import FastAPI
import asyncio
import structlog

from .config import get_settings
from .database import init_supabase
from .redis_client import init_redis
from .api.endpoints import router
from .agents.brain_hive import BrainHive
from .agents.agent_factory import AgentFactory

logger = structlog.get_logger()
settings = get_settings()

app = FastAPI(
    title="AIA",
    version="0.1.0",
)

app.include_router(router, prefix="/api")

agents = []

@app.on_event("startup")
async def startup_event():
    """
    Initialize system on startup
    """
    logger.info("Starting AI Agency...")
    
    await init_supabase()
    await init_redis()
    
    brain_hive = BrainHive()
    agents.append(brain_hive)
    asyncio.create_task(brain_hive.start())
    
    logger.info("Brain Hive initialized - worker agents will spawn on demand")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown
    """
    logger.info("Shutting down AI Agency...")
    
    for agent in agents:
        await agent.stop()
    
    factory = AgentFactory()
    await factory.shutdown_all()
    
    logger.info("Shutdown complete")

@app.get("/")
async def root():
    """
    Root endpoint
    """
    return {
        "message": "AI Agency is running!",
        "version": "0.1.0",
    }