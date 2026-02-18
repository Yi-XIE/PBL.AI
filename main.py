"""
AI+PBL Agent MVP
基于 LangGraph 的 PBL 课程自动生成系统

使用方法：
    python main.py "为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"

或者：
    python main.py --topic "图像识别" --grade "初中" --duration 45
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph.workflow import run_workflow, print_course_design


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="AI+PBL Agent - 自动生成 PBL 课程方案"
    )

    parser.add_argument(
        "input",
        nargs="?",
        help="用户输入的课程需求描述",
    )

    parser.add_argument(
        "--topic", "-t",
        help="课程主题",
    )

    parser.add_argument(
        "--grade", "-g",
        choices=["小学", "初中", "高中"],
        help="目标年级",
    )

    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=45,
        help="课程时长（分钟），默认 45",
    )

    parser.add_argument(
        "--output", "-o",
        help="输出文件路径（JSON 格式）",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式，只输出结果",
    )

    return parser.parse_args()


def save_result(state: dict, output_path: str) -> None:
    """
    保存结果到 JSON 文件

    Args:
        state: 最终状态
        output_path: 输出文件路径
    """
    # 准备输出数据
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "topic": state.get("topic", ""),
            "grade_level": state.get("grade_level", ""),
            "duration": state.get("duration", 0),
        },
        "course_design": state.get("course_design", {}),
    }

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n📄 结果已保存到：{output_path}")


def main():
    """主函数"""
    args = parse_args()

    # 构建用户输入
    if args.input:
        user_input = args.input
    elif args.topic:
        user_input = f"为{args.grade or '初中'}设计'{args.topic}'PBL课程，{args.duration}分钟"
    else:
        # 交互模式
        print("🎓 AI+PBL Agent - PBL 课程自动生成系统")
        print("-" * 50)
        user_input = input("请输入课程需求（如：为初中二年级设计'AI图像识别'PBL课程，45分钟）：\n").strip()

        if not user_input:
            print("❌ 请提供课程需求描述")
            sys.exit(1)

    if not args.quiet:
        print("\n🚀 开始生成 PBL 课程方案...")
        print(f"📝 需求：{user_input}")
        print("-" * 60)

    try:
        # 运行工作流
        result = run_workflow(
            user_input=user_input,
            topic=args.topic,
            grade_level=args.grade,
            duration=args.duration,
        )

        # 打印结果
        if not args.quiet:
            print_course_design(result)

        # 保存到文件
        if args.output:
            save_result(result, args.output)

        return result

    except Exception as e:
        print(f"\n❌ 生成失败：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
