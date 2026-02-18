"""
配置管理模块
管理 API Key 和 LLM 配置
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv()


# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """
    获取配置好的 LLM 实例

    Args:
        temperature: 生成温度，控制随机性

    Returns:
        ChatOpenAI 实例
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置")

    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        temperature=temperature,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


# 预置知识库路径
KNOWLEDGE_BASE_PATH = os.path.join(
    os.path.dirname(__file__), "knowledge", "knowledge_base.json"
)

# Prompt 模板路径
PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts")
