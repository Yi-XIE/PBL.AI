"""
生成工具模块
提供 4 个 PBL 课程组件生成工具
"""

from tools.generate_scenario import generate_scenario
from tools.generate_driving_question import generate_driving_question
from tools.generate_activity import generate_activity
from tools.generate_experiment import generate_experiment

__all__ = [
    "generate_scenario",
    "generate_driving_question",
    "generate_activity",
    "generate_experiment",
]

# 工具名称到函数的映射
TOOL_REGISTRY = {
    "generate_scenario": generate_scenario,
    "generate_driving_question": generate_driving_question,
    "generate_activity": generate_activity,
    "generate_experiment": generate_experiment,
}


def get_tool(tool_name: str):
    """
    根据工具名称获取工具函数

    Args:
        tool_name: 工具名称

    Returns:
        对应的工具函数

    Raises:
        ValueError: 工具名称无效
    """
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}. Available tools: {list(TOOL_REGISTRY.keys())}")
    return TOOL_REGISTRY[tool_name]
