from __future__ import annotations

from typing import List

from core.models import Candidate
from validators.base import ValidationResult


def validate_non_empty(candidates: List[Candidate]) -> ValidationResult:
    warnings = []
    if not candidates:
        warnings.append("No candidates generated.")
    return ValidationResult(warnings=warnings)
