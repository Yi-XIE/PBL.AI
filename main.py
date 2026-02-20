"""
AI+PBL Agent MVP - CLI

Usage:
  python main.py "Design a PBL lesson on AI image recognition for grade 8, 45 minutes"
  python main.py --topic "Image Recognition" --grade "初中" --duration 45
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
1
from graph.workflow import run_workflow_step, print_course_design
from state.agent_state import create_initial_state, is_design_complete


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI+PBL Agent - Generate PBL course design"
    )
    entry_mode = parser.add_mutually_exclusive_group()
    entry_mode.add_argument(
        "--ui",
        nargs="?",
        const="web",
        choices=["web", "streamlit"],
        help="Launch UI (default: web). Use --ui streamlit for legacy UI.",
    )
    entry_mode.add_argument(
        "--cli",
        action="store_true",
        help="Force CLI mode (prompt in terminal if no input is provided)",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="User input describing the course",
    )
    parser.add_argument(
        "--topic", "-t",
        help="Course topic",
    )
    parser.add_argument(
        "--grade", "-g",
        choices=["小学", "初中", "高中"],
        help="Target grade level",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=80,
        help="Duration in minutes (default 80)",
    )
    parser.add_argument(
        "--classroom-mode",
        choices=["normal", "no_device", "computer_lab"],
        default="normal",
        help="Classroom mode: normal/no_device/computer_lab",
    )
    parser.add_argument(
        "--classroom-context",
        default="",
        help="Classroom context description",
    )
    parser.add_argument(
        "--start-from",
        choices=["topic", "scenario", "activity", "experiment"],
        default=None,
        help="Start from: topic/scenario/activity/experiment",
    )
    parser.add_argument(
        "--scenario-text",
        help="Existing scenario text (required if start-from scenario)",
    )
    parser.add_argument(
        "--activity-text",
        help="Existing activity text (required if start-from activity)",
    )
    parser.add_argument(
        "--experiment-text",
        help="Existing experiment text (required if start-from experiment)",
    )
    parser.add_argument(
        "--no-cascade",
        action="store_true",
        help="Do not cascade downstream on regeneration",
    )
    parser.add_argument(
        "--no-hitl",
        action="store_true",
        help="Disable HITL (auto-accept all outputs)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode",
    )
    return parser.parse_args()


def launch_streamlit_ui() -> None:
    ui_entry = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "ui",
        "app_streamlit.py",
    )
    if not os.path.exists(ui_entry):
        raise FileNotFoundError(f"Streamlit UI entry not found: {ui_entry}")

    cmd = [sys.executable, "-m", "streamlit", "run", ui_entry]
    raise SystemExit(subprocess.call(cmd))


def launch_web_ui() -> None:
    from server.app import app
    import uvicorn

    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, "web", "dist")
    if not os.path.isdir(dist_dir):
        print("[WARN] web/dist not found. Build the UI with:")
        print("       cd web && npm install && npm run build")
        print("       or run the dev server: npm run dev")

    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    raise SystemExit(uvicorn.run(app, host=host, port=port, log_level="info"))


def save_result(state: dict, output_path: str) -> None:
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "topic": state.get("topic", ""),
            "grade_level": state.get("grade_level", ""),
            "duration": state.get("duration", 0),
        },
        "course_design": state.get("course_design", {}),
    }
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Result saved to: {output_path}")


def prompt_yes_no(message: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        resp = input(f"{message}{suffix} ").strip().lower()
        if not resp:
            return default
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False


def prompt_text(message: str, required: bool = True) -> str:
    while True:
        resp = input(message).strip()
        if resp or not required:
            return resp


def choose_start_from(args, interactive: bool) -> str:
    if args.start_from:
        return args.start_from
    if not interactive:
        return "topic"
    print("\nChoose start point: 1) topic  2) scenario  3) activity  4) experiment (default 1)")
    choice = input("Start point: ").strip()
    mapping = {"1": "topic", "2": "scenario", "3": "activity", "4": "experiment"}
    return mapping.get(choice, "topic")


def collect_seed_components(start_from: str, args, interactive: bool) -> tuple[dict, str]:
    seeds = {}
    if args.scenario_text:
        seeds["scenario"] = args.scenario_text
    if args.activity_text:
        seeds["activity"] = args.activity_text
    if args.experiment_text:
        seeds["experiment"] = args.experiment_text

    if start_from in ("scenario", "activity", "experiment") and not seeds.get(start_from):
        if not interactive:
            raise ValueError(f"Start from {start_from} requires corresponding content.")
        print(f"\nStart from {start_from} requires at least one sentence of existing content.")
        while True:
            content = prompt_text(f"Paste existing {start_from} content: ", required=False)
            if content:
                seeds[start_from] = content
                break
            fallback = prompt_yes_no("Fallback to full generation (topic)?", default=True)
            if fallback:
                start_from = "topic"
                break
    return seeds, start_from


def render_preview(state: dict) -> None:
    preview = state.get("pending_preview", {}) or {}
    title = preview.get("title", "Preview")
    print("\n" + "-" * 60)
    print(title)
    print("-" * 60)
    text = preview.get("text", "")
    if text:
        print(text)
    if "question_chain" in preview:
        print("\nQuestion Chain:")
        for i, q in enumerate(preview.get("question_chain", []), 1):
            print(f"{i}. {q}")
    print("-" * 60)


def main():
    args = parse_args()

    # For double-click / `python main.py` convenience:
    # If the user didn't provide any generation input, launch the UI by default.
    has_generation_input = bool(args.input) or bool(args.topic)
    if args.ui or (not args.cli and not has_generation_input):
        if args.ui == "streamlit":
            launch_streamlit_ui()
        else:
            launch_web_ui()

    if args.input:
        user_input = args.input
    elif args.topic:
        grade_label = args.grade or "middle school"
        user_input = (
            f"Design a PBL course on '{args.topic}' for grade {grade_label}, "
            f"{args.duration} minutes."
        )
    else:
        print("AI+PBL Agent - PBL Course Generator")
        print("-" * 50)
        user_input = input("Enter course request:\n").strip()
        if not user_input:
            print("Error: missing input")
            sys.exit(1)

    if not args.quiet:
        print("\nStarting generation...")
        print(f"Request: {user_input}")
        print("-" * 60)

    try:
        interactive = sys.stdin.isatty()
        start_from = choose_start_from(args, interactive)
        seeds, start_from = collect_seed_components(start_from, args, interactive)

        state = create_initial_state(
            user_input=user_input,
            topic=args.topic or "",
            grade_level=args.grade or "",
            duration=args.duration,
            classroom_context=args.classroom_context,
            classroom_mode=args.classroom_mode,
            start_from=start_from,
            provided_components=seeds,
            hitl_enabled=not args.no_hitl,
            cascade_default=not args.no_cascade,
            interactive=interactive,
        )

        if args.no_hitl:
            state = run_workflow_step(state)
        else:
            while True:
                state = run_workflow_step(state)
                if state.get("await_user") and state.get("pending_component"):
                    render_preview(state)
                    if prompt_yes_no("Accept this output?", default=True):
                        state["user_decision"] = "accept"
                        state["user_feedback"] = None
                        state["feedback_target"] = None
                    else:
                        default_target = state.get("pending_component") or "scenario"
                        target = prompt_text(
                            f"Which component to edit? (scenario/driving_question/activity/experiment, default {default_target}): ",
                            required=False,
                        ).strip() or default_target
                        feedback = prompt_text("Feedback: ", required=True)
                        state["user_decision"] = "regenerate"
                        state["feedback_target"] = target
                        state["user_feedback"] = {target: feedback}
                    continue

                if is_design_complete(state):
                    break

                if not state.get("await_user"):
                    # Safety: avoid infinite loop if no actions remain
                    if not state.get("action_sequence"):
                        break

        if not args.quiet:
            print_course_design(state)

        if args.output:
            save_result(state, args.output)

        return state

    except Exception as e:
        print(f"\nGeneration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
