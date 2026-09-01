from __future__ import annotations

import json
import threading
from prior.domain import JobRecord
from prior.settings import jobs_path

_lock = threading.Lock()


def load_all() -> list[JobRecord]:
    path = jobs_path()
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [JobRecord.from_dict(item) for item in raw]


def save_all(records: list[JobRecord]) -> None:
    path = jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = [record.to_dict() for record in records]
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def put(record: JobRecord) -> JobRecord:
    with _lock:
        records = load_all()
        by_id = {item.id: item for item in records}
        by_id[record.id] = record
        save_all(list(by_id.values()))
        return record


def get(job_id: str, workspace_id: str) -> JobRecord | None:
    for record in load_all():
        if record.id == job_id and record.workspace_id == workspace_id:
            return record
    return None


def list_for(workspace_id: str) -> list[JobRecord]:
    items = [record for record in load_all() if record.workspace_id == workspace_id]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items
