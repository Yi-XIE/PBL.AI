from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

try:
    from langsmith import Client
except Exception:  # pragma: no cover
    Client = None


def _enabled() -> bool:
    return os.getenv("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes", "on"}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _sanitize_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, str) and len(value) > 200:
            sanitized[key] = f"hash:{_hash_text(value)}"
        else:
            sanitized[key] = value
    return sanitized


class TraceManager:
    def __init__(self) -> None:
        self.enabled = _enabled() and Client is not None
        self.client = Client() if self.enabled else None
        self.project_name = os.getenv("LANGCHAIN_PROJECT")

    def start_root(
        self,
        task_id: str,
        entry_point: str,
        stage: Optional[str] = None,
        action: str = "task_created",
    ) -> Optional[str]:
        if not self.enabled or self.client is None:
            return None
        root_id = uuid4()
        metadata = {"task_id": task_id, "entry_point": entry_point, "action": action}
        if stage:
            metadata["stage"] = stage
        self.client.create_run(
            id=root_id,
            name=task_id,
            run_type="chain",
            inputs={"entry_point": entry_point},
            outputs={},
            start_time=datetime.now(timezone.utc),
            project_name=self.project_name,
            extra={"metadata": metadata},
        )
        return str(root_id)

    def end_root(self, root_run_id: Optional[str], status: str = "completed") -> None:
        if not self.enabled or self.client is None or not root_run_id:
            return
        try:
            self.client.update_run(
                root_run_id,
                end_time=datetime.now(timezone.utc),
                outputs={"status": status},
                extra={"metadata": {"status": status}},
            )
        except Exception:
            return

    def log_child(
        self,
        *,
        root_run_id: Optional[str],
        name: str,
        run_type: str,
        inputs: Dict[str, Any],
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        if not self.enabled or self.client is None:
            return
        run_id = uuid4()
        kwargs: Dict[str, Any] = {
            "id": run_id,
            "name": name,
            "run_type": run_type,
            "inputs": _sanitize_inputs(inputs),
            "outputs": outputs or {},
            "start_time": start_time or datetime.now(timezone.utc),
            "end_time": end_time or datetime.now(timezone.utc),
            "project_name": self.project_name,
            "extra": {"metadata": metadata or {}},
        }
        if root_run_id:
            kwargs["parent_run_id"] = root_run_id
            kwargs["trace_id"] = root_run_id
        if error:
            kwargs["error"] = error
        self.client.create_run(**kwargs)
