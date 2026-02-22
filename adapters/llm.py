import os
from typing import Optional

from langchain_openai import ChatOpenAI


class LLMNotConfigured(RuntimeError):
    pass


class LLMInvocationError(RuntimeError):
    pass


def _is_required() -> bool:
    return os.getenv("LLM_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}


def get_llm(purpose: Optional[str] = None) -> ChatOpenAI:
    if purpose == "decision":
        model_name = (
            os.getenv("LLM_DECISION_MODEL")
            or os.getenv("LLM_MODEL")
            or os.getenv("QWEN_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "gpt-4o-mini"
        )
    else:
        model_name = (
            os.getenv("LLM_MODEL")
            or os.getenv("QWEN_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "gpt-4o-mini"
        )
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    openai_api_key: Optional[str] = (
        os.getenv("LLM_API_KEY")
        or os.getenv("QWEN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
    )
    openai_api_base: Optional[str] = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("QWEN_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("DEEPSEEK_BASE_URL")
    )

    if _is_required() and not openai_api_key:
        raise LLMNotConfigured("LLM not configured")

    kwargs = {
        "model_name": model_name,
        "temperature": temperature,
    }
    if openai_api_key:
        kwargs["openai_api_key"] = openai_api_key
    if openai_api_base:
        kwargs["openai_api_base"] = openai_api_base

    return ChatOpenAI(**kwargs)


__all__ = ["get_llm", "LLMNotConfigured", "LLMInvocationError"]
