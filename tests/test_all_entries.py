# -*- coding: utf-8 -*-
"""
测试脚本 - 模拟老师的真实使用场景
从四个不同的入口点测试：
1. 场景优先 - 老师已有教学场景想法
2. 知识/主题优先 - 老师只知道要教什么知识点
3. 活动优先 - 老师想先设计活动
4. 实验/问题链优先 - 老师想从动手实验开始
"""

import os
import sys
import io
import json
from datetime import datetime

# 设置标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 测试结果保存路径
TEST_RESULTS_DIR = os.path.join(PROJECT_ROOT, "test_results")

from dotenv import load_dotenv
load_dotenv()

from state.agent_state import create_initial_state, AgentState
from nodes.reasoning_node import reasoning_node, load_knowledge_base, match_knowledge_snippets, generate_context_summary
from nodes.action_node import action_node
from tools.generate_scenario import generate_scenario
from tools.generate_driving_question import generate_driving_question
from tools.generate_activity import generate_activity
from tools.generate_experiment import generate_experiment
from config import get_llm


def test_1_topic_first():
    """
    测试1: 知识/主题优先入口
    模拟场景：老师只知道要教"图像识别"这个知识点，需要系统帮忙设计完整课程
    """
    print("\n" + "="*60)
    print("测试1: 知识/主题优先入口")
    print("模拟：老师只知道要教'AI图像识别'，需要完整课程设计")
    print("="*60)

    user_input = "为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"

    # 创建初始状态
    state = create_initial_state(
        user_input=user_input,
        topic="AI如何识别交通标志",
        grade_level="初中",
        duration=45,
        start_from="topic",
    )

    print(f"\n输入: {user_input}")

    # 执行推理节点
    print("\n--- 执行推理节点 ---")
    updates = reasoning_node(state)
    state.update(updates)

    print(f"主题: {state['topic']}")
    print(f"年级: {state['grade_level']}")
    print(f"时长: {state['duration']}分钟")
    print(f"上下文摘要: {state['context_summary'][:100]}...")
    print(f"动作序列: {state['action_sequence']}")

    # 执行所有动作
    print("\n--- 执行生成工具 ---")
    for i, action in enumerate(state['action_sequence']):
        state['current_action_index'] = i
        updates = action_node(state)
        state.update(updates)
        print(f"[OK] {action} 完成")

    # 输出结果
    print("\n--- 课程设计结果 ---")
    print(f"场景: {state['course_design']['scenario'][:200]}...")
    print(f"驱动问题: {state['course_design']['driving_question']}")
    print(f"问题链: {state['course_design']['question_chain'][:2]}...")
    print(f"活动: {state['course_design']['activity'][:200]}...")
    print(f"实验: {state['course_design']['experiment'][:200]}...")

    return {
        "entry": "topic",
        "user_input": user_input,
        "topic": state["topic"],
        "grade_level": state["grade_level"],
        "duration": state["duration"],
        "context_summary": state.get("context_summary", ""),
        "course_design": state.get("course_design", {}),
    }


def test_2_scenario_first():
    """
    测试2: 场景优先入口
    模拟场景：老师已经有了教学场景的想法，只需要生成其他组件
    """
    print("\n" + "="*60)
    print("测试2: 场景优先入口")
    print("模拟：老师已有场景想法，只需要生成问题、活动、实验")
    print("="*60)

    # 老师已有的场景
    existing_scenario = """
### 场景名称
智慧果园：AI帮你挑水果

### 场景背景
小明和妈妈去水果店买苹果，但不知道怎么挑选。店主告诉他们，现在有AI摄像头可以自动识别水果的新鲜程度！这是怎么做到的呢？

### 角色设定
学生扮演"智慧果园"的AI助手训练师，需要教会AI识别水果是否新鲜。

### 场景挑战
果园老板希望AI能帮助顾客快速挑选新鲜水果，你需要设计一套规则让AI学会判断。
"""

    # 创建初始状态（场景已完成）
    state = create_initial_state(
        user_input="小学三年级，AI识别水果",
        topic="AI识别水果",
        grade_level="小学",
        duration=40,
        start_from="scenario",
        provided_components={"scenario": existing_scenario},
    )

    print(f"\n已有场景: 智慧果园：AI帮你挑水果")

    # 执行推理节点（会跳过已完成的场景）
    print("\n--- 执行推理节点 ---")
    updates = reasoning_node(state)
    state.update(updates)

    print(f"动作序列（跳过场景）: {state['action_sequence']}")

    # 执行剩余动作
    print("\n--- 执行生成工具 ---")
    for i, action in enumerate(state['action_sequence']):
        state['current_action_index'] = i
        updates = action_node(state)
        state.update(updates)
        print(f"[OK] {action} 完成")

    # 输出结果
    print("\n--- 课程设计结果 ---")
    print(f"驱动问题: {state['course_design']['driving_question']}")
    print(f"问题链: {state['course_design']['question_chain']}")
    print(f"活动: {state['course_design']['activity'][:200]}...")

    return {
        "entry": "scenario",
        "user_input": state["user_input"],
        "topic": state["topic"],
        "grade_level": state["grade_level"],
        "duration": state["duration"],
        "context_summary": state.get("context_summary", ""),
        "seed_scenario": existing_scenario,
        "course_design": state.get("course_design", {}),
    }


def test_3_activity_first():
    """
    测试3: 活动优先入口
    模拟场景：老师已经有了活动设计想法，需要补充场景和问题
    """
    print("\n" + "="*60)
    print("测试3: 活动优先入口")
    print("模拟：老师已有活动想法，需要补充其他组件")
    print("="*60)

    # 创建初始状态
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

    print(f"\n输入: 高中讨论AI伦理问题")

    # 执行推理节点
    print("\n--- 执行推理节点 ---")
    updates = reasoning_node(state)
    state.update(updates)

    print(f"上下文摘要: {state['context_summary'][:100]}...")
    print(f"动作序列: {state['action_sequence']}")

    # 执行所有动作
    print("\n--- 执行生成工具 ---")
    for i, action in enumerate(state['action_sequence']):
        state['current_action_index'] = i
        updates = action_node(state)
        state.update(updates)
        print(f"✓ {action} 完成")

    # 输出结果
    print("\n--- 课程设计结果 ---")
    print(f"场景: {state['course_design']['scenario'][:200]}...")
    print(f"驱动问题: {state['course_design']['driving_question']}")
    print(f"活动（包含辩论环节）: {state['course_design']['activity'][:300]}...")

    return {
        "entry": "activity",
        "user_input": state["user_input"],
        "topic": state["topic"],
        "grade_level": state["grade_level"],
        "duration": state["duration"],
        "context_summary": state.get("context_summary", ""),
        "course_design": state.get("course_design", {}),
    }


def test_4_experiment_first():
    """
    测试4: 实验/问题链优先入口
    模拟场景：老师想从动手实验开始设计课程
    """
    print("\n" + "="*60)
    print("测试4: 实验/问题链优先入口")
    print("模拟：老师想从动手实验开始，逆向设计课程")
    print("="*60)

    # 创建初始状态
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

    print(f"\n输入: 小学五年级语音识别声音实验")

    # 执行推理节点
    print("\n--- 执行推理节点 ---")
    updates = reasoning_node(state)
    state.update(updates)

    print(f"匹配的主题模板: 语音识别相关")
    print(f"动作序列: {state['action_sequence']}")

    # 执行所有动作
    print("\n--- 执行生成工具 ---")
    for i, action in enumerate(state['action_sequence']):
        state['current_action_index'] = i
        updates = action_node(state)
        state.update(updates)
        print(f"✓ {action} 完成")

    # 输出结果（重点关注实验设计）
    print("\n--- 课程设计结果 ---")
    print(f"场景: {state['course_design']['scenario'][:200]}...")
    print(f"实验设计: {state['course_design']['experiment'][:400]}...")

    return {
        "entry": "experiment",
        "user_input": state["user_input"],
        "topic": state["topic"],
        "grade_level": state["grade_level"],
        "duration": state["duration"],
        "context_summary": state.get("context_summary", ""),
        "course_design": state.get("course_design", {}),
    }


def test_knowledge_base():
    """测试知识库加载和匹配"""
    print("\n" + "="*60)
    print("测试: 知识库加载和匹配")
    print("="*60)

    # 加载知识库
    kb = load_knowledge_base()
    print(f"\n知识库包含:")
    print(f"- 年级规则: {list(kb['grade_rules'].keys())}")
    print(f"- 主题模板: {list(kb['topic_templates'].keys())}")
    print(f"- 安全约束: {len(kb['safety_constraints'])}条")

    # 测试匹配
    snippets = match_knowledge_snippets("图像识别", "初中", kb)
    print(f"\n匹配结果（图像识别 + 初中）:")
    print(f"年级规则: {snippets['grade_rules'][:100]}...")
    print(f"主题模板: {snippets['topic_template'][:100]}...")

    return {"entry": "knowledge_base", "summary_only": True}


def test_context_summary():
    """测试上下文摘要生成"""
    print("\n" + "="*60)
    print("测试: 上下文摘要生成")
    print("="*60)

    kb = load_knowledge_base()
    snippets = match_knowledge_snippets("自然语言处理", "高中", kb)

    print(f"\n输入: 自然语言处理 + 高中 + 90分钟")

    summary = generate_context_summary(
        topic="自然语言处理",
        grade_level="高中",
        duration=90,
        knowledge_snippets=snippets
    )

    print(f"生成的上下文摘要:")
    print(summary)

    return {
        "entry": "context_summary",
        "summary_only": True,
        "summary": summary,
    }


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始运行所有测试用例")
    print("="*60)

    tests = [
        ("知识库测试", test_knowledge_base),
        ("上下文摘要测试", test_context_summary),
        ("测试1-主题优先", test_1_topic_first),
        ("测试2-场景优先", test_2_scenario_first),
        ("测试3-活动优先", test_3_activity_first),
        ("测试4-实验优先", test_4_experiment_first),
    ]

    # 记录测试开始时间
    start_time = datetime.now()
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")

    results = []
    all_outputs = []  # 收集所有测试的详细结果
    llm_outputs = []  # 收集四个入口案例的模型产出

    for name, test_func in tests:
        test_result = {
            "name": name,
            "status": "pending",
            "error": None
        }
        try:
            output = test_func()
            results.append((name, "[OK] 通过"))
            test_result["status"] = "passed"
            if isinstance(output, dict) and output.get("entry") in ("topic", "scenario", "activity", "experiment"):
                llm_outputs.append(output)
            print(f"\n{name}: [OK] 通过")
        except Exception as e:
            results.append((name, f"[FAIL] 失败: {str(e)}"))
            test_result["status"] = "failed"
            test_result["error"] = str(e)
            print(f"\n{name}: [FAIL] 失败")
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()

        all_outputs.append(test_result)

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    for name, result in results:
        print(f"{name}: {result}")

    passed = sum(1 for _, r in results if "[OK]" in r)
    print(f"\n总计: {passed}/{len(results)} 通过")

    # 保存模型产出（四个入口案例）
    os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
    llm_output_report = {
        "timestamp": timestamp,
        "cases": llm_outputs
    }
    llm_output_file = os.path.join(TEST_RESULTS_DIR, f"llm_outputs_{timestamp}.json")
    with open(llm_output_file, "w", encoding="utf-8") as f:
        json.dump(llm_output_report, f, ensure_ascii=False, indent=2)
    print(f"\n模型产出已保存到: {llm_output_file}")


if __name__ == "__main__":
    run_all_tests()
