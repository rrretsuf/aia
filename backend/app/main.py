from fastapi import FastAPI
import asyncio
import structlog

from .config import get_settings
from .database import init_supabase
from .redis_client import init_redis
from .api.endpoints import router
from .agents.planner_agent import PlannerAgent
from .agents.research_agent import ResearchAgent

logger = structlog.get_logger()
settings = get_settings()

# FastAPI app
app = FastAPI(
    title="AIA",
    version="0.1.0",
)

app.include_router(router, prefix="/api")

agents = []

@app.on_event("startup")
async def startup_event():
    """
    Initialize connections on startup
    """
    logger.info("Starting AI Agency MVP...")
    
    await init_supabase()
    await init_redis()

    planner = PlannerAgent()
    research_1 = ResearchAgent(1)
    research_2 = ResearchAgent(2)
    research_3 = ResearchAgent(3)

    for agent in [planner, research_1, research_2, research_3]:
        agents.append(agent)
        asyncio.create_task(agent.start())

@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown.
    """
    logger.info("Shutting down AI Agency MVP...")

    for agent in agents:
        await agent.stop()

    logger.info("Shutdown complete")

@app.get("/")
async def root():
    """
    Root endpoint
    """
    return {
        "message": "AI Agency MVP is running!",
        "version": "0.1.0",
    }