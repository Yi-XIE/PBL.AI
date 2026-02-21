from core.dependencies import compute_required_deps, topo_sort_missing_chain
from core.types import EntryPoint, StageType


def test_tool_seed_requires_scenario_dep() -> None:
    deps = compute_required_deps(StageType.scenario, EntryPoint.tool_seed)
    assert StageType.tool_seed in deps


def test_activity_requires_question_chain_and_tool_seed() -> None:
    deps = compute_required_deps(StageType.activity, EntryPoint.tool_seed)
    assert StageType.question_chain in deps
    assert StageType.tool_seed in deps


def test_missing_chain_for_activity() -> None:
    chain = topo_sort_missing_chain(StageType.activity, EntryPoint.tool_seed, [])
    assert chain == [
        StageType.tool_seed,
        StageType.scenario,
        StageType.driving_question,
        StageType.question_chain,
        StageType.activity,
    ]
