import json
import os
import sys
from typing import Dict, Any

import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from graph.workflow import run_workflow_step
from state.agent_state import create_initial_state, is_design_complete


def inject_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap');
        :root {
            --ink: #1f1f1f;
            --accent: #0b6b62;
            --accent-2: #d18f33;
            --card: rgba(255,255,255,0.85);
            --shadow: 0 12px 30px rgba(0,0,0,0.08);
        }
        html, body, [class*="css"] {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--ink);
        }
        .stApp {
            background: linear-gradient(135deg, #f6f2e9 0%, #e3f2ff 60%, #f4f7ff 100%);
        }
        .hero {
            padding: 24px 28px;
            background: var(--card);
            border: 1px solid rgba(0,0,0,0.05);
            border-radius: 18px;
            box-shadow: var(--shadow);
        }
        .chip {
            display: inline-block;
            padding: 6px 10px;
            margin-right: 6px;
            border-radius: 999px;
            background: rgba(11,107,98,0.1);
            color: var(--accent);
            font-size: 12px;
            font-weight: 600;
        }
        .card {
            padding: 18px 20px;
            background: var(--card);
            border-radius: 16px;
            border: 1px solid rgba(0,0,0,0.06);
            box-shadow: var(--shadow);
        }
        .mono {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_user_input(raw_input: str, topic: str, grade: str, duration: int) -> str:
    if raw_input.strip():
        return raw_input.strip()
    if topic.strip():
        return f"为{grade}设计'{topic}'PBL课程，{duration}分钟"
    return ""


def init_state(
    user_input: str,
    topic: str,
    grade: str,
    duration: int,
    classroom_context: str,
    classroom_mode: str,
    start_from: str,
    provided_components: Dict[str, Any],
    hitl_enabled: bool,
    cascade_default: bool,
) -> Dict[str, Any]:
    state = create_initial_state(
        user_input=user_input,
        topic=topic,
        grade_level=grade,
        duration=duration,
        classroom_context=classroom_context,
        classroom_mode=classroom_mode,
        start_from=start_from,
        provided_components=provided_components,
        hitl_enabled=hitl_enabled,
        cascade_default=cascade_default,
        interactive=True,
    )
    return run_workflow_step(state)


def render_preview(preview: Dict[str, Any]) -> None:
    st.markdown(f"**{preview.get('title', 'Preview')}**")
    text = preview.get("text", "")
    if text:
        st.write(text)
    if "question_chain" in preview:
        st.markdown("**Question Chain**")
        for i, q in enumerate(preview.get("question_chain", []), 1):
            st.write(f"{i}. {q}")


def main() -> None:
    st.set_page_config(page_title="AI+PBL Agent", layout="wide")
    inject_style()

    st.markdown(
        """
        <div class="hero">
            <div class="chip">AI+PBL</div>
            <div class="chip">HITL</div>
            <div class="chip">Local Test UI</div>
            <h2 style="margin:8px 0 4px 0;">Course Design Studio</h2>
            <div class="mono">Iterate component-by-component with human-in-the-loop control.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "agent_state" not in st.session_state:
        st.session_state.agent_state = None

    col_left, col_right = st.columns([1, 1.2], gap="large")

    with col_left:
        st.markdown("**Inputs**")
        raw_input = st.text_area("Raw request", value="", height=100)
        topic = st.text_input("Topic", value="")
        grade = st.selectbox("Grade", ["小学", "初中", "高中"], index=1)
        duration = st.number_input("Duration (minutes)", min_value=10, max_value=240, value=80, step=5)

        start_from = st.selectbox("Start from", ["topic", "scenario", "activity", "experiment"], index=0)

        st.markdown("**Seed Components (optional)**")
        scenario_text = st.text_area("Scenario seed", value="", height=80)
        activity_text = st.text_area("Activity seed", value="", height=80)
        experiment_text = st.text_area("Experiment seed", value="", height=80)

        st.markdown("**Classroom**")
        classroom_mode = st.selectbox("Classroom mode", ["normal", "no_device", "computer_lab"], index=0)
        classroom_context = st.text_area("Classroom context", value="", height=60)

        st.markdown("**Controls**")
        hitl_enabled = st.checkbox("Enable HITL", value=True)
        cascade_default = st.checkbox("Cascade downstream on regenerate", value=True)

        start_clicked = st.button("Start / Reset", use_container_width=True)

        if start_clicked:
            user_input = build_user_input(raw_input, topic, grade, duration)
            if not user_input:
                st.error("Please provide a raw request or a topic.")
            else:
                provided = {}
                if scenario_text.strip():
                    provided["scenario"] = scenario_text.strip()
                if activity_text.strip():
                    provided["activity"] = activity_text.strip()
                if experiment_text.strip():
                    provided["experiment"] = experiment_text.strip()

                st.session_state.agent_state = init_state(
                    user_input=user_input,
                    topic=topic,
                    grade=grade,
                    duration=duration,
                    classroom_context=classroom_context,
                    classroom_mode=classroom_mode,
                    start_from=start_from,
                    provided_components=provided,
                    hitl_enabled=hitl_enabled,
                    cascade_default=cascade_default,
                )

    with col_right:
        st.markdown("**HITL Panel**")
        state = st.session_state.agent_state
        if not state:
            st.info("Initialize a session to start generating.")
            return

        status_col1, status_col2 = st.columns(2)
        with status_col1:
            st.markdown(f"**Start From**: `{state.get('start_from')}`")
            st.markdown(f"**Current**: `{state.get('pending_component') or state.get('current_component') or '-'}`")
        with status_col2:
            st.markdown(f"**Await User**: `{state.get('await_user')}`")
            st.markdown(f"**Locked**: `{', '.join(state.get('locked_components', [])) or '-'}`")

        if state.get("pending_preview"):
            st.markdown('<div class="card">', unsafe_allow_html=True)
            render_preview(state.get("pending_preview", {}))
            st.markdown("</div>", unsafe_allow_html=True)

        feedback_target = st.selectbox(
            "Feedback target",
            ["scenario", "driving_question", "activity", "experiment"],
            index=0,
        )
        feedback_text = st.text_area("Feedback", value="", height=80)

        action_cols = st.columns(2)
        with action_cols[0]:
            accept_clicked = st.button("Accept", use_container_width=True)
        with action_cols[1]:
            regen_clicked = st.button("Regenerate", use_container_width=True)

        if accept_clicked and state.get("await_user"):
            state["user_decision"] = "accept"
            state["user_feedback"] = None
            state["feedback_target"] = None
            st.session_state.agent_state = run_workflow_step(state)

        if regen_clicked and state.get("await_user"):
            target = feedback_target
            state["user_decision"] = "regenerate"
            state["feedback_target"] = target
            state["user_feedback"] = {target: feedback_text}
            st.session_state.agent_state = run_workflow_step(state)

        if not state.get("await_user") and not is_design_complete(state):
            if st.button("Continue", use_container_width=True):
                st.session_state.agent_state = run_workflow_step(state)

        if is_design_complete(state):
            st.success("Design complete.")
            st.markdown("**Course Design JSON**")
            st.json(state.get("course_design", {}))
            data = json.dumps(
                {
                    "metadata": {
                        "topic": state.get("topic"),
                        "grade_level": state.get("grade_level"),
                        "duration": state.get("duration"),
                    },
                    "course_design": state.get("course_design", {}),
                },
                ensure_ascii=False,
                indent=2,
            )
            st.download_button(
                "Download JSON",
                data=data,
                file_name="course_design.json",
                mime="application/json",
            )


if __name__ == "__main__":
    main()
