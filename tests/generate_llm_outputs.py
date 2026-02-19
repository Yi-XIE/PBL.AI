# -*- coding: utf-8 -*-
"""
生成四个入口案例的大模型完整产出，并保存到 test_results/llm_outputs_<timestamp>.json
支持按单个 case 执行，避免一次性运行过久。
"""

import argparse
import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from state.agent_state import create_initial_state
from nodes.reasoning_node import reasoning_node
from nodes.action_node import action_node

TEST_RESULTS_DIR = os.path.join(PROJECT_ROOT, "test_result")


def run_case(case_name: str) -> dict:
    if case_name == "topic":
        user_input = "为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"
        state = create_initial_state(
            user_input=user_input,
            topic="AI如何识别交通标志",
            grade_level="初中",
            duration=45,
            start_from="topic",
        )
    elif case_name == "scenario":
        existing_scenario = """
### 场景名称
智慧果园：AI帮你挑水果
### 场景背景
小明和妈妈去水果店买苹果，但不知道怎么挑选。店主告诉他们，现在有AI摄像头可以自动识别水果的新鲜程度！这是怎么做到的呢？
### 角色设定
学生扮演“智慧果园”的AI助手训练师，需要教会AI识别水果是否新鲜。
### 场景挑战
果园老板希望AI能帮助顾客快速挑选新鲜水果，你需要设计一套规则让AI学会判断。
"""
        state = create_initial_state(
            user_input="小学三年级，AI识别水果",
            topic="AI识别水果",
            grade_level="小学",
            duration=40,
            start_from="scenario",
            provided_components={"scenario": existing_scenario},
        )
    elif case_name == "activity":
        existing_activity = """
### 活动标题
推荐算法辩论会

### 活动流程
学生分组，模拟平台与用户，讨论推荐算法的利弊，并形成辩论观点。
"""
        state = create_initial_state(
            user_input="高中，讨论AI伦理问题，想让学生辩论推荐算法的利弊",
            topic="AI伦理与推荐算法",
            grade_level="高中",
            duration=90,
            start_from="activity",
            provided_components={"activity": existing_activity},
        )
    elif case_name == "experiment":
        existing_experiment = """
### 实验名称
声音特征实验

### 实验描述
学生录制不同音色的声音，观察波形差异并尝试分类。
"""
        state = create_initial_state(
            user_input="小学五年级，语音识别，想做声音实验",
            topic="语音识别",
            grade_level="小学",
            duration=45,
            start_from="experiment",
            provided_components={"experiment": existing_experiment},
        )
    else:
        raise ValueError(f"Unknown case: {case_name}")

    updates = reasoning_node(state)
    state.update(updates)

    for i, action in enumerate(state["action_sequence"]):
        state["current_action_index"] = i
        updates = action_node(state)
        state.update(updates)

    return {
        "entry": case_name,
        "user_input": state["user_input"],
        "topic": state["topic"],
        "grade_level": state["grade_level"],
        "duration": state["duration"],
        "context_summary": state.get("context_summary", ""),
        "course_design": state.get("course_design", {}),
    }


def load_or_init_output(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"timestamp": os.path.basename(path).split("_", 2)[-1].replace(".json", ""), "cases": []}


def upsert_case(report: dict, case_output: dict) -> dict:
    cases = report.get("cases", [])
    cases = [c for c in cases if c.get("entry") != case_output.get("entry")]
    cases.append(case_output)
    report["cases"] = cases
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["topic", "scenario", "activity", "experiment", "all"], default="all")
    parser.add_argument("--output", help="输出文件路径（JSON）")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
    output_path = args.output or os.path.join(TEST_RESULTS_DIR, f"llm_outputs_{timestamp}.json")

    cases = ["topic", "scenario", "activity", "experiment"] if args.case == "all" else [args.case]
    report = load_or_init_output(output_path)

    for case_name in cases:
        case_output = run_case(case_name)
        report = upsert_case(report, case_output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[OK] {case_name} -> {output_path}")


if __name__ == "__main__":
    main()
