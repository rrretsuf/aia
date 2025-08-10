from typing import Optional, Dict, Any
import structlog
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
import json
import re 

from ..config import get_settings

logger = structlog.get_logger()

class OpenRouterClient():
    """
    OpenRouter LLM client using LangChain with OpenAI compatibility
    """
    
    def __init__(self, model_name: Optional[str] = None):
        self.settings = get_settings()
        self.model_name = model_name or self.settings.default_model

        if not self.settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY must be set in environment")
        
        self.llm = ChatOpenAI(
            model=self.model_name,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.7,
            max_tokens=2000, 
            timeout=30,
        )

        logger.info(f"OpenRouter client initialized")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_response(
        self,
        system_prompt: str,
        human_message: str,
        web_search: bool = False,
        **kwargs
    ) -> str:
        """
        Generate response using OpenRouter
        """
        try: 
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_message)
            ]
        
            if web_search:
                web_llm = ChatOpenAI(
                    model=f"{self.model_name}:online",
                    openai_api_key=self.settings.openrouter_api_key,
                    openai_api_base="https://openrouter.ai/api/v1",
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2000),
                    timeout=30,
                )
                response = await web_llm.ainvoke(messages, **kwargs)
            else:
                response = await self.llm.ainvoke(messages, **kwargs)

            return response.content
        
        except Exception as e:
            logger.error(f"OpenRouter API call failed: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_json_response(
        self, 
        system_prompt: str,
        human_message: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate JSON response using OpenRouter.
        """
        try:
            json_system_prompt = f"{system_prompt}\n\nIMPORTANT: Return ONLY valid JSON, no additional text."

            response_text = await self.generate_response(
                system_prompt=json_system_prompt,
                human_message=human_message,
                **kwargs
            )

            try: 
                return json.loads(response_text.strip())
            
            except Exception as e:
                logger.error(f"Failed to parse JSON response: {e}")
                cleaned_response = self._extract_json(response_text)
                return json.loads(cleaned_response)
            
        except Exception as e: 
            logger.error(f"JSON generation failed: {e}")
            raise
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from text response (fallback).
        """   
        # look for json array pattern
        json_pattern = r"\[.*?\]" 
        matches = re.findall(json_pattern, text, re.DOTALL)

        if matches:
            return matches[0]
        
        # if no array found, try object pattern
        json_pattern = r"\{.*?\}"
        matches = re.findall(json_pattern, text, re.DOTALL)

        if matches: 
            return matches[0]
        
        raise ValueError(f"No valid JSON found in response: {text}")
    
_openrouter_client: Optional[OpenRouterClient] = None

def get_openrouter_client(model_name: Optional[str] = None) -> OpenRouterClient:
    """
    Get or create OpenRouter client instance.
    """
    global _openrouter_client

    if _openrouter_client is None or (model_name and _openrouter_client.model_name != model_name):
        _openrouter_client = OpenRouterClient(model_name)

    return _openrouter_client