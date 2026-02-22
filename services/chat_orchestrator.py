from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import CreativeContext, EntryDecision, IntentRevision, Message, Task, ToolSeed
from core.types import DialogueState, EntryPoint
from engine.interaction_router import InteractionRouter
from services.intent_clarifier import IntentClarifier
from services.creative_dialogue_manager import CreativeDialogueManager
from services.divergence_detector import DivergenceDetector
from engine.entry_decision import get_entry_threshold, resolve_entry_decision
from validators.scenario_realism import is_realistic
from utils.intake import intake_to_constraints, normalize_intake


ALGORITHM_KEYWORDS = {
    "kmeans",
    "k-means",
    "k means",
    "k均值",
    "k 均值",
    "k-均值",
    "knn",
    "k近邻",
    "最近邻",
    "svm",
    "bayes",
    "naive bayes",
    "decision tree",
    "random forest",
    "xgboost",
    "聚类",
    "分类",
    "回归",
    "监督学习",
    "无监督学习",
    "机器学习",
    "深度学习",
    "算法",
    "知识点",
}

TOOL_KEYWORDS = {
    "orange",
    "橙子",
    "weka",
    "scratch",
    "python",
    "jupyter",
    "colab",
    "excel",
    "power bi",
    "pytorch",
    "tensorflow",
    "sklearn",
    "scikit",
    "matlab",
    "rapidminer",
}

SCENARIO_KEYWORDS = {"场景", "情境", "scenario"}
TOOL_TRIGGER_KEYWORDS = {
    "工具",
    "软件",
    "实验",
    "活动",
    "驱动问题",
    "驱动性问题",
    "driving question",
    "question chain",
    "project",
    "activity",
    "experiment",
}.union(TOOL_KEYWORDS)


def _contains_keyword(text: str, keywords: set[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty LLM response")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _build_entry_question(intake: Dict[str, Any]) -> str:
    prompt = (
        "你是课程助手。用户已填写课程信息，请用一句自然的中文问题询问："
        "他们希望从哪里开始（场景 / 工具 / 实验 / 活动 / 驱动问题）。"
        "不要输出多余内容，只输出一句话。"
    )
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
        return (result.content or "").strip() or "你希望从哪里开始？场景 / 工具 / 实验 / 活动 / 驱动问题"
    except Exception:
        return "你希望从哪里开始？场景 / 工具 / 实验 / 活动 / 驱动问题"


def _build_intake_intro(intake: Dict[str, Any]) -> str:
    knowledge_point = intake.get("knowledge_point") or "the topic"
    lesson_count = intake.get("lesson_count") or 1
    age_group = intake.get("age_group") or ""
    classroom_type = intake.get("classroom_type") or ""
    prompt = (
        "Please explain the knowledge point in 2-4 short sentences in Chinese."
        " Then give 2-3 teaching suggestions tailored to the age group."
        " End with one sentence that transitions to asking where to start.\n\n"
        f"Topic: {knowledge_point}\n"
        f"Lessons: {lesson_count}\n"
        f"Age group: {age_group}\n"
        f"Classroom: {classroom_type}\n"
    )
    try:
        llm = get_llm(purpose="decision")
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
        content = (result.content or "").strip()
        if content:
            return content
    except Exception:
        pass
    advice = " / ".join([t for t in [age_group, classroom_type] if t]) or "current classroom"
    return (
        f"For {knowledge_point}, start from real-life examples and highlight core concepts.\n"
        f"Teaching tips: adapt to {advice}, use visuals, step-by-step explanation, and short practice.\n"
        "Next, I will ask where you want to start."
    )

def _build_tool_seed_prompt(message: str, intake: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> str:
    intake_text = json.dumps(intake, ensure_ascii=False)
    existing_text = json.dumps(existing or {}, ensure_ascii=False)
    return (
        "你是 PBL 课程助手，请从用户输入中抽取 tool_seed。"
        "只输出严格 JSON，不要多余文字：\n"
        "{\n"
        '  "tool_seed": {\n'
        '    "tool_name": "string",\n'
        '    "algorithms": ["..."],\n'
        '    "affordances": ["..."],\n'
        '    "user_intent": "string",\n'
        '    "constraints": {}\n'
        "  },\n"
        '  "question": "string or null"\n'
        "}\n"
        "规则：\n"
        "- 如果信息不足以确定 tool_name 或 user_intent，请给出一个单句追问放在 question。\n"
        "- tool_seed 可以是部分字段，但不要编造不存在的工具。\n"
        f"已有 intake: {intake_text}\n"
        f"已有 tool_seed: {existing_text}\n"
        f"用户输入: {message}\n"
    )


def _build_fallback_prompt(history: str, message: str) -> str:
    return f"""
你是 PBL 任务入口助手。请根据用户输入判断入口并补齐信息。
只输出严格 JSON，禁止输出多余文字：
{{
  "status": "ask" | "ready",
  "entry_point": "scenario" | "tool_seed" | null,
  "scenario": string | null,
  "tool_seed": object | null,
  "question": string | null
}}
规则：
- 需要更多信息时，status=ask，并给出一个明确问题。
- 准备就绪时，status=ready，并提供 entry_point 为 scenario/tool_seed。
- tool_seed 至少包含 tool_name 与 user_intent。

对话历史：
{history}

用户输入：
{message}
""".strip()


def _detect_entry_choice(message: str) -> Optional[EntryPoint]:
    text = message or ""
    if _contains_keyword(text, SCENARIO_KEYWORDS):
        return EntryPoint.scenario
    if _contains_keyword(text, TOOL_TRIGGER_KEYWORDS):
        return EntryPoint.tool_seed
    return None


INTENT_CHANGE_PATTERN = re.compile(r"(修改意图|调整意图|变更意图|意图改为|意图改成)[:：]?\s*(.*)")


def _extract_intent_change(message: str) -> Optional[str]:
    if not message:
        return None
    match = INTENT_CHANGE_PATTERN.search(message)
    if not match:
        return None
    return match.group(2).strip()


def _infer_tool_name(message: str) -> str:
    lower = (message or "").lower()
    for keyword in TOOL_KEYWORDS:
        if keyword in lower:
            return keyword
    return "通用工具"



def _parse_yes_no(message: str) -> Optional[str]:
    if not message:
        return None
    text = message.strip().lower()
    yes_terms = ["?", "?", "??", "??", "??", "?", "??", "???", "????", "???"]
    no_terms = ["?", "?", "??", "???", "??", "????", "????", "????"]
    if any(term in text for term in yes_terms):
        return "yes"
    if any(term in text for term in no_terms):
        return "no"
    return None

def _extract_tool_seed_with_llm(
    message: str,
    intake: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    prompt = _build_tool_seed_prompt(message, intake, existing)
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
    except Exception as exc:
        raise LLMInvocationError("LLM invocation failed for tool_seed extraction") from exc
    data = _extract_json(result.content or "")
    tool_seed = data.get("tool_seed") if isinstance(data.get("tool_seed"), dict) else None
    question = data.get("question") if isinstance(data.get("question"), str) else None
    return tool_seed, question


def _generate_starter_scenario(intake: Dict[str, Any]) -> str:
    prompt = (
        "你是课程设计助手。请基于以下信息生成一个简短教学场景（2-4句）。"
        "只输出严格 JSON：{\"scenario\":\"...\"}\n"
        f"信息：{json.dumps(intake, ensure_ascii=False)}"
    )
    for _ in range(2):
        try:
            llm = get_llm()
            chain = ChatPromptTemplate.from_template("{text}") | llm
            result = chain.invoke({"text": prompt})
            data = _extract_json(result.content or "")
            scenario = data.get("scenario")
            if isinstance(scenario, str) and scenario.strip() and is_realistic(scenario):
                return scenario.strip()
        except Exception:
            continue
    return "以校园垃圾分类与数据记录为主题的真实生活项目式学习场景。"


class ChatSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []
        self.intake: Dict[str, Any] = {}
        self.creative_context: CreativeContext = CreativeContext()
        self.awaiting_entry: bool = False
        self.awaiting_tool_seed: bool = False
        self.awaiting_scenario: bool = False
        self.entry_asked: bool = False
        self.tool_seed_partial: Optional[Dict[str, Any]] = None
        self.tool_seed_ask_count: int = 0
        self.last_entry_decision: Optional[EntryDecision] = None
        self.dialogue_state: DialogueState = DialogueState.exploring

    def append(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, ChatSession] = {}

    def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def create(self) -> ChatSession:
        session = ChatSession(uuid4().hex)
        self._sessions[session.session_id] = session
        return session


def handle_task_chat_message(*, task: Task, message: str) -> Dict[str, Any]:
    text = (message or '').strip()
    router = InteractionRouter()
    task.dialogue_state = router.route(text, task.messages, task.dialogue_state)
    task.working_memory.focus = task.dialogue_state.value

    last_decision = task.decision_history[-1] if task.decision_history else None
    if last_decision and last_decision.get("type") == "clarification_requested" and text:
        task.decision_history.append({"type": "clarification_confirmed", "answer": text})

    if text:
        task.messages.append(
            Message(
                role="user",
                text=text,
                stage=task.current_stage,
                kind="creative_dialogue",
                mode=task.dialogue_state.value,
            )
        )

    if task.pending_cascade and text:
        decision = _parse_yes_no(text)
        if decision == "yes":
            assistant_message = "???????????????????????"
            task.decision_history.append({"type": "cascade_confirmed", "origin": task.pending_cascade.get("origin_stage")})
            task.messages.append(
                Message(
                    role="assistant",
                    text=assistant_message,
                    stage=task.current_stage,
                    kind="cascade",
                    mode=task.dialogue_state.value,
                )
            )
            return {"status": "ask", "assistant_message": assistant_message, "cascade_action": "confirm", "cascade": task.pending_cascade}
        if decision == "no":
            assistant_message = "???????????????????????"
            task.pending_cascade = None
            task.decision_history.append({"type": "cascade_skipped"})
            task.messages.append(
                Message(
                    role="assistant",
                    text=assistant_message,
                    stage=task.current_stage,
                    kind="cascade",
                    mode=task.dialogue_state.value,
                )
            )
            return {"status": "ask", "assistant_message": assistant_message, "cascade_action": "skip"}

    intent_change = _extract_intent_change(text)
    if intent_change is not None:
        if not intent_change:
            question = "???????????"
            task.messages.append(
                Message(
                    role="assistant",
                    text=question,
                    stage=task.current_stage,
                    kind="creative_dialogue",
                    mode=task.dialogue_state.value,
                )
            )
            return {"status": "ask", "assistant_message": question}
        before = task.creative_context.original_intent
        task.creative_context.original_intent = intent_change
        task.creative_context.intent_evolution.append(
            IntentRevision(trigger=text, before=before, after=intent_change, user_confirmed=True)
        )
        if intent_change not in task.creative_context.anchor_concepts:
            task.creative_context.anchor_concepts.append(intent_change)
            task.decision_history.append(
                {"type": "intent_updated", "before": before, "after": intent_change}
            )
        task.decision_history.append(
            {"type": "creative_context_updated", "summary": intent_change}
        )
        task.working_memory.notes.append(f"intent: {intent_change}")
        task.working_memory.notes = task.working_memory.notes[-10:]
        task.working_memory.focus = "exploring"

    if task.dialogue_state == DialogueState.exploring:
        dialogue = CreativeDialogueManager().extract_intent_update(
            task.creative_context,
            text,
            intake=task.entry_data.get("intake") if isinstance(task.entry_data, dict) else None,
            recent_messages=[m.text for m in task.messages[-6:] if isinstance(m, Message)],
        )
        if dialogue.get("needs_confirmation"):
            question = dialogue.get("question") or "?????????????????"
            task.decision_history.append(
                {
                    "type": "clarification_requested",
                    "question": question,
                    "summary": dialogue.get("summary", ""),
                }
            )
            task.working_memory.notes.append(f"clarification: {question}")
            task.working_memory.notes = task.working_memory.notes[-10:]
            task.messages.append(
                Message(
                    role="assistant",
                    text=question,
                    stage=task.current_stage,
                    kind="creative_dialogue",
                    mode=task.dialogue_state.value,
                )
            )
            return {
                "status": "ask",
                "assistant_message": question,
                "dialogue_action": "clarification_requested",
            }

        intent = dialogue.get("intent") or ""
        if intent and intent != task.creative_context.original_intent:
            before = task.creative_context.original_intent
            task.creative_context.original_intent = intent
            task.creative_context.intent_evolution.append(
                IntentRevision(trigger=text, before=before, after=intent, user_confirmed=False)
            )
        key_constraints = dialogue.get("key_constraints") or []
        if key_constraints:
            merged = list(task.creative_context.key_constraints)
            for item in key_constraints:
                if item not in merged:
                    merged.append(item)
            task.creative_context.key_constraints = merged
        anchors = dialogue.get("anchor_concepts") or []
        if anchors:
            merged = list(task.creative_context.anchor_concepts)
            for item in anchors:
                if item not in merged:
                    merged.append(item)
            task.creative_context.anchor_concepts = merged

        summary = dialogue.get("summary") or intent or text
        task.decision_history.append(
            {"type": "creative_context_updated", "summary": summary}
        )
        task.working_memory.notes.append(f"intent: {summary}")
        task.working_memory.notes = task.working_memory.notes[-10:]
        task.working_memory.focus = "exploring"

        assistant_message = "?????????????????????"
        task.messages.append(
            Message(
                role="assistant",
                text=assistant_message,
                stage=task.current_stage,
                kind="creative_dialogue",
                mode=task.dialogue_state.value,
            )
        )
        return {
            "status": "ask",
            "assistant_message": assistant_message,
            "dialogue_action": "creative_context_updated",
        }

    task.working_memory.focus = "generating"

    assistant_message = "????????????????????????"
    task.messages.append(
        Message(
            role="assistant",
            text=assistant_message,
            stage=task.current_stage,
            kind="creative_dialogue",
            mode=task.dialogue_state.value,
        )
    )
    return {"status": "ask", "assistant_message": assistant_message}
def _finalize_tool_seed(
    tool_seed: Dict[str, Any],
    intake: Dict[str, Any],
    message: str,
) -> Dict[str, Any]:
    allowed_keys = {"tool_name", "algorithms", "affordances", "constraints", "user_intent"}
    tool_seed = {k: v for k, v in tool_seed.items() if k in allowed_keys}
    constraints = tool_seed.get("constraints") if isinstance(tool_seed.get("constraints"), dict) else {}
    constraints = {**constraints, **intake_to_constraints(intake)}
    constraints.setdefault("context_summary", message.strip())
    tool_seed["constraints"] = constraints
    tool_seed.setdefault("algorithms", [])
    tool_seed.setdefault("affordances", [])
    if not tool_seed.get("tool_name"):
        tool_seed["tool_name"] = _infer_tool_name(message)
    if not tool_seed.get("user_intent"):
        tool_seed["user_intent"] = intake.get("knowledge_point") or "项目式学习"
    return tool_seed


def _handle_tool_seed_entry(
    session: ChatSession,
    message: str,
) -> Dict[str, Any]:
    intake = session.intake
    tool_seed, question = _extract_tool_seed_with_llm(message, intake, session.tool_seed_partial)
    if isinstance(tool_seed, dict):
        session.tool_seed_partial = tool_seed
    if not isinstance(tool_seed, dict):
        tool_seed = session.tool_seed_partial or {}
    tool_seed = _finalize_tool_seed(tool_seed, intake, message)
    missing = not tool_seed.get("tool_name") or not tool_seed.get("user_intent")
    if missing and session.tool_seed_ask_count < 1 and question:
        session.tool_seed_ask_count += 1
        session.awaiting_tool_seed = True
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
        }
    session.awaiting_tool_seed = False
    try:
        ToolSeed(**tool_seed)
    except Exception:
        tool_seed = _finalize_tool_seed(tool_seed, intake, message)
    assistant_message = "已收到信息，开始创建任务并进入场景生成。"
    session.append("assistant", assistant_message)
    return {
        "status": "ready",
        "assistant_message": assistant_message,
        "entry_point": EntryPoint.tool_seed,
        "entry_data": tool_seed,
    }


def _handle_scenario_entry(
    session: ChatSession,
    message: str,
    scenario_override: Optional[str] = None,
) -> Dict[str, Any]:
    intake = session.intake
    scenario_text = scenario_override or ""
    if (
        not scenario_text
        and message
        and len(message.strip()) > 12
        and not _contains_keyword(message, TOOL_TRIGGER_KEYWORDS | SCENARIO_KEYWORDS)
    ):
        scenario_text = message.strip()
    if not scenario_text:
        scenario_text = _generate_starter_scenario(intake)
    if not scenario_text or not is_realistic(scenario_text):
        question = "请提供一个真实生活场景或真实学习任务（避免魔法/科幻/超现实设定）。"
        session.awaiting_scenario = True
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
        }
    session.awaiting_scenario = False
    constraints = intake_to_constraints(intake)
    entry_data = {
        "scenario": scenario_text,
        "constraints": constraints,
        "user_intent": intake.get("knowledge_point") or "",
        "tool_name": intake.get("knowledge_point") or "topic",
        "intake": intake,
    }
    assistant_message = "已收到场景信息，开始创建任务。"
    session.append("assistant", assistant_message)
    return {
        "status": "ready",
        "assistant_message": assistant_message,
        "entry_point": EntryPoint.scenario,
        "entry_data": entry_data,
    }


def handle_chat_message(
    *,
    session: ChatSession,
    message: str,
    intake: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if intake:
        normalized = normalize_intake(intake)
        session.intake = normalized
        knowledge_point = normalized.get("knowledge_point") or ""
        session.creative_context.original_intent = session.creative_context.original_intent or knowledge_point
        constraints = intake_to_constraints(normalized)
        key_constraints: List[str] = []
        for key, value in {
            "topic": constraints.get("topic"),
            "grade": constraints.get("grade"),
            "duration": constraints.get("duration"),
            "classroom": constraints.get("classroom_context") or constraints.get("classroom_mode"),
        }.items():
            if value:
                key_constraints.append(f"{key}:{value}")
        session.creative_context.key_constraints = key_constraints
        if knowledge_point and knowledge_point not in session.creative_context.anchor_concepts:
            session.creative_context.anchor_concepts.append(knowledge_point)
        session.awaiting_entry = True
        session.awaiting_tool_seed = False
        session.awaiting_scenario = False
        session.entry_asked = False
        session.tool_seed_partial = None
        session.tool_seed_ask_count = 0
        intro = _build_intake_intro(normalized)
        question = _build_entry_question(normalized)
        assistant_message = f"{intro}\n\n{question}".strip()
        session.entry_asked = True
        session.append("assistant", assistant_message)
        return {
            "status": "ask",
            "assistant_message": assistant_message,
            "entry_point": None,
            "entry_data": None,
        }

    session.append("user", message or "")
    session.dialogue_state = InteractionRouter().route(
        message,
        session.messages,
        session.dialogue_state,
    )
    if session.awaiting_tool_seed:
        return _handle_tool_seed_entry(session, message)
    if session.awaiting_scenario:
        return _handle_scenario_entry(session, message, scenario_override=message.strip())

    intent_change = _extract_intent_change(message)
    if intent_change is not None:
        if not intent_change:
            question = "请说明新的意图或主题。"
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
        before = session.creative_context.original_intent
        session.creative_context.original_intent = intent_change
        session.creative_context.intent_evolution.append(
            IntentRevision(trigger=message, before=before, after=intent_change, user_confirmed=True)
        )
        if intent_change not in session.creative_context.anchor_concepts:
            session.creative_context.anchor_concepts.append(intent_change)
        if session.awaiting_entry:
            question = _build_entry_question(session.intake)
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
    if session.awaiting_entry:
        decision = resolve_entry_decision(message)
        session.last_entry_decision = decision
        threshold = get_entry_threshold()
        if decision.confidence < threshold:
            clarification = IntentClarifier().build_clarification(message)
            question = clarification or _build_entry_question(session.intake)
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
                "entry_decision": decision.model_dump(),
            }
        divergence_score = DivergenceDetector().detect(session.creative_context, message)
        if (
            divergence_score >= 0.6
            and decision.model_reason != "strong_signal"
            and not _contains_keyword(message, SCENARIO_KEYWORDS | TOOL_TRIGGER_KEYWORDS)
        ):
            question = "看起来你想调整方向，是否需要修改意图后再选择入口？"
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
                "entry_decision": decision.model_dump(),
            }
        session.awaiting_entry = False
        if decision.chosen_entry_point == EntryPoint.tool_seed:
            result = _handle_tool_seed_entry(session, message)
        else:
            result = _handle_scenario_entry(session, message)
        result["entry_decision"] = decision.model_dump()
        return result
    decision = resolve_entry_decision(message)
    threshold = get_entry_threshold()
    if decision.confidence < threshold:
        question = IntentClarifier().build_clarification(message) or _build_entry_question(session.intake)
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
            "entry_decision": decision.model_dump(),
        }
    if decision.chosen_entry_point == EntryPoint.tool_seed:
        result = _handle_tool_seed_entry(session, message)
    else:
        result = _handle_scenario_entry(session, message)
    result["entry_decision"] = decision.model_dump()
    return result


__all__ = ["ChatSessionStore", "handle_chat_message", "handle_task_chat_message"]
