from __future__ import annotations

import json
import threading
from prior.domain import JobRecord
from prior.settings import jobs_path

_lock = threading.Lock()


class HireConflictError(RuntimeError):
    """Atomic hire-claim conflict: another execution already claimed the job."""


class FundConflictError(RuntimeError):
    """Atomic fund-claim conflict: another funding already claimed the job."""


def hire_claim(record_id: str, workspace_id: str) -> JobRecord:
    """Atomically claim a prepared job for execution (prepared -> creating).

    Read-modify-write under the store lock with re-read semantics: the
    caller must use the returned record, never a previously read copy.
    Production runs a single uvicorn worker with threaded request handling,
    so this in-process lock serializes claims. A multi-worker deployment
    would require an external lock; documented here, not hidden.
    """
    with _lock:
        records = load_all()
        current = next(
            (item for item in records
             if item.id == record_id and item.workspace_id == workspace_id),
            None,
        )
        if current is None:
            raise KeyError("Job not found in this workspace.")
        if current.hire_state != "prepared" or current.acp_job_id:
            raise HireConflictError(
                f"Job {record_id} is not awaiting execution "
                f"(hire_state={current.hire_state!r}).")
        current.hire_state = "creating"
        current.hire_error = None
        from datetime import datetime, timezone

        current.updated_at = datetime.now(timezone.utc).isoformat()
        by_id = {item.id: item for item in records}
        by_id[current.id] = current
        save_all(list(by_id.values()))
        return current


def fund_claim(record_id: str, workspace_id: str) -> JobRecord:
    """Atomically claim a fund-prepared job for funding (fund_prepared ->
    funding). Same single-worker lock discipline and re-read contract as
    hire_claim: callers must use the returned record.
    """
    with _lock:
        records = load_all()
        current = next(
            (item for item in records
             if item.id == record_id and item.workspace_id == workspace_id),
            None,
        )
        if current is None:
            raise KeyError("Job not found in this workspace.")
        if current.fund_state != "fund_prepared" or not current.fund_intent:
            raise FundConflictError(
                f"Job {record_id} is not awaiting funding "
                f"(fund_state={current.fund_state!r}).")
        current.fund_state = "funding"
        current.fund_error = None
        from datetime import datetime, timezone

        current.updated_at = datetime.now(timezone.utc).isoformat()
        by_id = {item.id: item for item in records}
        by_id[current.id] = current
        save_all(list(by_id.values()))
        return current


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
