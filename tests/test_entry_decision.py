from engine.entry_decision import resolve_entry_decision
from core.types import EntryPoint
from validators.scenario_realism import is_realistic


def test_entry_decision_strong_signal() -> None:
    decision = resolve_entry_decision("从场景开始")
    assert decision.chosen_entry_point == EntryPoint.scenario
    assert decision.confidence >= 0.9


def test_entry_decision_keyword_tool() -> None:
    decision = resolve_entry_decision("我想用 Orange 做实验")
    assert decision.chosen_entry_point == EntryPoint.tool_seed
    assert decision.confidence >= 0.7


def test_scenario_realism_filter() -> None:
    assert not is_realistic("这是一个魔法世界的学习任务")
    assert is_realistic("校园垃圾分类活动与数据记录")
