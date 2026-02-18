"""
LangGraph 工作流定义
定义 PBL 课程生成 Agent 的状态图
"""

import os
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state.agent_state import AgentState, create_initial_state
from nodes.reasoning_node import reasoning_node
from nodes.action_node import action_node, should_continue


def create_workflow() -> StateGraph:
    """
    创建 PBL 课程生成工作流

    工作流结构：
    START -> reasoning_node -> action_node -> [判断]
                                          ↓
                              未完成 -> 循环回 action_node
                              已完成 -> END

    Returns:
        编译好的 StateGraph
    """
    # 创建状态图
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("action", action_node)

    # 设置入口点
    workflow.set_entry_point("reasoning")

    # 添加边
    # reasoning -> action
    workflow.add_edge("reasoning", "action")

    # action -> 条件判断
    workflow.add_conditional_edges(
        "action",
        should_continue,
        {
            "continue": "action",  # 继续执行下一个动作
            "end": END,            # 所有动作完成，结束
        }
    )

    return workflow


def compile_workflow():
    """
    编译工作流

    Returns:
        可执行的 CompiledGraph
    """
    workflow = create_workflow()
    return workflow.compile()


def run_workflow(
    user_input: str,
    topic: str = None,
    grade_level: str = None,
    duration: int = None,
) -> AgentState:
    """
    运行工作流生成 PBL 课程

    Args:
        user_input: 用户原始输入
        topic: 课程主题（可选，会从 user_input 中解析）
        grade_level: 年级（可选）
        duration: 时长（可选）

    Returns:
        最终的 AgentState，包含完整的课程设计
    """
    # 创建初始状态
    initial_state = create_initial_state(
        user_input=user_input,
        topic=topic or "",
        grade_level=grade_level or "",
        duration=duration or 45,
    )

    # 编译并运行工作流
    app = compile_workflow()
    final_state = app.invoke(initial_state)

    return final_state


# 便捷函数：打印课程设计结果
def print_course_design(state: AgentState) -> None:
    """
    打印课程设计结果

    Args:
        state: 最终状态
    """
    course = state.get("course_design", {})

    print("\n" + "=" * 60)
    print("📚 PBL 课程设计方案")
    print("=" * 60)

    print(f"\n🎯 主题：{state.get('topic', '')}")
    print(f"👥 年级：{state.get('grade_level', '')}")
    print(f"⏱️  时长：{state.get('duration', '')}分钟")

    print("\n" + "-" * 60)
    print("📖 教学场景")
    print("-" * 60)
    print(course.get("scenario", "未生成"))

    print("\n" + "-" * 60)
    print("❓ 驱动问题")
    print("-" * 60)
    print(course.get("driving_question", "未生成"))

    print("\n" + "-" * 60)
    print("🔗 问题链")
    print("-" * 60)
    for i, q in enumerate(course.get("question_chain", []), 1):
        print(f"{i}. {q}")

    print("\n" + "-" * 60)
    print("🎮 活动设计")
    print("-" * 60)
    print(course.get("activity", "未生成"))

    print("\n" + "-" * 60)
    print("🔬 实验设计")
    print("-" * 60)
    print(course.get("experiment", "未生成"))

    print("\n" + "=" * 60)
    print("✅ 课程设计完成！")
    print("=" * 60)


if __name__ == "__main__":
    # 测试运行
    test_input = "为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"

    print("🚀 开始生成 PBL 课程...")
    print(f"📝 输入：{test_input}")
    print("-" * 60)

    result = run_workflow(test_input)
    print_course_design(result)
