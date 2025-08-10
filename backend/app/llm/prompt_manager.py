import os
from typing import Dict, Optional
import structlog
from pathlib import Path

logger = structlog.get_logger()

class PromptManager:
    """
    Manages system prompts loaded from markdown files.
    """

    def __init__(self):
        self.prompts_dir = Path(__file__).parent.parent / "prompts"
        self._prompts_cache: Dict[str, str] = {}

        self.prompts_dir.mkdir(exist_ok=True)

        logger.info(f"PromptManager initialized with prompts dir: {self.prompts_dir}")

    def load_prompt(self, prompt_name: str) -> str:
        """
        Load a prompt from file, with caching.
        """
        if prompt_name in self._prompts_cache:
            return self._prompts_cache[prompt_name]
        
        prompt_file = self.prompts_dir / f"{prompt_name}.md"

        if not prompt_file.exists():
            logger.error(f"Prompt file not found: {prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {prompt_name}.md")
        
        try:
            with open(prompt_file, "r", encoding="utf-8") as f: 
                content = f.read()

            processed_content = self._process_prompt_content(content)

            self._prompts_cache[prompt_name] = processed_content

            logger.info(f"Loaded prompt: {prompt_name}")
            return processed_content
        
        except Exception as e:
            logger.error(f"Failed to load prompt {prompt_name}: {e}")
            raise

    def _process_prompt_content(self, content: str) -> str:
        """
        Process markdown content to create clean system prompt.
        """
        lines = content.split("\n")
        processed_lines = []

        for line in lines:
            if line.startswith("#"):
                continue
            if not processed_lines and not line.strip():
                continue
            processed_lines.append(line)

        result = "\n".join(processed_lines).strip()

        while "\n\n\n" in result:
            result = result.replace("\n\n\n", "\n\n")

        return result
    
    def reload_prompts(self):
        """
        Clear cache and reload all prompts.
        """
        self._prompts_cache.clear()
        logger.info("Prompt cache cleared")

_prompt_manager: Optional[PromptManager] = None

def get_prompt_manager() -> PromptManager:
    """
    Get or create prompt manager instance.
    """
    global _prompt_manager

    if _prompt_manager is None:
        _prompt_manager = PromptManager()

    return _prompt_manager
