from __future__ import annotations

from langchain_openai import ChatOpenAI

from second_brain.core.config import Settings

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def create_llm(settings: Settings) -> ChatOpenAI:
    """Create a ChatOpenAI instance pointed at OpenRouter.

    The model is configurable via ``config.yaml`` — swapping LLM providers
    is a one-line config change as long as the model is available on
    OpenRouter.
    """
    return ChatOpenAI(
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=_OPENROUTER_BASE_URL,
    )
