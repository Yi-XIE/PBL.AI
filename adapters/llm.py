import os
from typing import Optional

from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    model_name = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    openai_api_base: Optional[str] = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("LLM_BASE_URL")
    )

    kwargs = {
        "model_name": model_name,
        "temperature": temperature,
    }
    if openai_api_key:
        kwargs["openai_api_key"] = openai_api_key
    if openai_api_base:
        kwargs["openai_api_base"] = openai_api_base

    return ChatOpenAI(**kwargs)


__all__ = ["get_llm"]
