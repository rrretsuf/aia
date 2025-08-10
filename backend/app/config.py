from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Application
    app_name: str = "AIA"
    debug: bool = True
    
    # API Keys
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None 
    
    # Supabase Database
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_service_key: Optional[str] = None
    
    # Redis/Upstash
    redis_url: Optional[str] = None 
    upstash_redis_url: Optional[str] = None
    
    # Agent Configuration
    max_agents: int = 10
    agent_timeout: int = 300  # 5 minutes
    task_timeout: int = 1800  # 30 minutes

    # LLM Configuration
    default_model: str = "moonshotai/kimi-k2:free"

    # Communication
    websocket_ping_interval: int = 20
    websocket_ping_timeout: int = 10
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security
    secret_key: str = "your-secret-key-change-this"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get application settings"""
    return settings