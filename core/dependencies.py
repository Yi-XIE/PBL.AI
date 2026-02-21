from __future__ import annotations

from typing import Dict, List, Set

from core.types import EntryPoint, StageType


STAGE_DEPENDENCIES: Dict[StageType, List[StageType]] = {
    StageType.driving_question: [StageType.scenario],
    StageType.question_chain: [StageType.driving_question],
    StageType.activity: [StageType.question_chain],
    StageType.experiment: [StageType.activity],
}

TOOL_SEED_DEPENDENCIES: Dict[StageType, List[StageType]] = {
    StageType.scenario: [StageType.tool_seed],
    StageType.activity: [StageType.tool_seed],
}


STAGE_SEQUENCE: List[StageType] = [
    StageType.scenario,
    StageType.driving_question,
    StageType.question_chain,
    StageType.activity,
    StageType.experiment,
]


def compute_required_deps(stage: StageType, entry_point: EntryPoint) -> List[StageType]:
    deps: List[StageType] = []
    deps.extend(STAGE_DEPENDENCIES.get(stage, []))
    if entry_point == EntryPoint.tool_seed:
        deps = TOOL_SEED_DEPENDENCIES.get(stage, []) + deps
    seen: Set[StageType] = set()
    ordered: List[StageType] = []
    for item in deps:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def compute_missing_deps(
    stage: StageType,
    entry_point: EntryPoint,
    completed_stages: List[StageType],
) -> List[StageType]:
    required = compute_required_deps(stage, entry_point)
    return [dep for dep in required if dep not in completed_stages]


def topo_sort_missing_chain(
    target_stage: StageType,
    entry_point: EntryPoint,
    completed_stages: List[StageType],
) -> List[StageType]:
    chain: List[StageType] = []
    visited: Set[StageType] = set()
    visiting: Set[StageType] = set()

    def visit(stage: StageType) -> None:
        if stage in visiting:
            raise ValueError("Dependency cycle detected")
        if stage in visited:
            return
        visiting.add(stage)
        visited.add(stage)
        for dep in compute_required_deps(stage, entry_point):
            if dep not in completed_stages:
                visit(dep)
        visiting.remove(stage)
        if stage not in completed_stages and stage not in chain:
            chain.append(stage)

    visit(target_stage)
    return chain
