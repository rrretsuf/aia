from fastapi import FastAPI
import structlog
from backend.app.config import get_settings
from database import init_supabase, DatabaseManager
from redis_client import init_redis, RedisManager

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
settings = get_settings()

# FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="AI Agency MVP - Multi-Agent Research System",
    version="0.1.0",
    debug=settings.debug
)

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    logger.info("Starting AI Agency MVP...")
    
    try:
        # Initialize Supabase
        await init_supabase()
        logger.info("✅ Supabase connection established")
        
        # Initialize Redis
        await init_redis()
        logger.info("✅ Redis connection established")
        
        logger.info("🚀 AI Agency MVP started successfully!")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down AI Agency MVP...")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Agency MVP is running!",
        "version": "0.1.0",
        "status": "healthy"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database
        db = DatabaseManager()
        db_healthy = await db.health_check()
        
        # Check Redis
        redis_mgr = RedisManager()
        redis_healthy = await redis_mgr.health_check()
        
        return {
            "status": "healthy" if (db_healthy and redis_healthy) else "unhealthy",
            "database": "ok" if db_healthy else "error",
            "redis": "ok" if redis_healthy else "error",
            "timestamp": structlog.processors.TimeStamper(fmt="iso")._stamper()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )