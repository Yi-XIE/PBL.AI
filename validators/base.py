from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from core.models import Conflict


class ValidationResult(BaseModel):
    warnings: List[str] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    recommendation: Optional[str] = None
