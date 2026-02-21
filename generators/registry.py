from __future__ import annotations

from typing import Dict

from core.types import StageType
from generators.stages.activity import ActivityGenerator
from generators.stages.driving_question import DrivingQuestionGenerator
from generators.stages.experiment import ExperimentGenerator
from generators.stages.question_chain import QuestionChainGenerator
from generators.stages.scenario import ScenarioGenerator


GENERATOR_BY_STAGE: Dict[StageType, object] = {
    StageType.scenario: ScenarioGenerator(),
    StageType.driving_question: DrivingQuestionGenerator(),
    StageType.question_chain: QuestionChainGenerator(),
    StageType.activity: ActivityGenerator(),
    StageType.experiment: ExperimentGenerator(),
}
