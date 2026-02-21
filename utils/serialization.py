from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        converted = {}
        for k, v in value.items():
            key = k.value if hasattr(k, "value") else k
            if not isinstance(key, str):
                key = str(key)
            converted[key] = to_jsonable(v)
        return converted
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, default=str)
