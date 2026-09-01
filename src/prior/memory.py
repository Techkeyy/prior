"""Sibyl Memory adapter.

WRITE path: `write_lesson` -> MemoryClient.set_entity(category="lesson", ...)
READ path:  `recall_lessons` -> MemoryClient.search_entities / list_entities
ACTION:     recalled lessons are passed to `prior.contract.build_contract`
"""

from __future__ import annotations

from typing import Any

from sibyl_memory_client import MemoryClient, NotFoundError, SibylMemoryError

from prior.domain import LESSON_CATEGORY, Lesson
from prior.settings import memory_db_path

MEMORY_UNAVAILABLE = (
    "Memory unavailable. PRIOR cannot safely apply learned requirements."
)


class MemoryUnavailable(RuntimeError):
    def __init__(self, detail: str = MEMORY_UNAVAILABLE) -> None:
        super().__init__(detail)
        self.detail = detail


def open_memory(workspace_id: str) -> MemoryClient:
    if not workspace_id or not workspace_id.strip():
        raise MemoryUnavailable("Workspace id is missing; cannot open Sibyl Memory.")
    try:
        return MemoryClient.local(memory_db_path(), tenant_id=workspace_id.strip())
    except Exception as exc:  # noqa: BLE001 - surface any store failure honestly
        raise MemoryUnavailable(f"{MEMORY_UNAVAILABLE} ({exc})") from exc


def write_lesson(workspace_id: str, lesson: Lesson) -> dict[str, Any]:
    """Persist an approved lesson. This is the Sibyl WRITE path."""
    _validate_lesson(lesson)
    client = open_memory(workspace_id)
    body = lesson.to_dict()
    body.pop("match_reason", None)
    row = client.set_entity(LESSON_CATEGORY, lesson.id, body)
    client.write_event(
        acted=[f"lesson.{lesson.status}"],
        extra={
            "lesson_id": lesson.id,
            "workspace_id": workspace_id,
            "source_job_id": lesson.source_job_id,
            "originating_evaluation": lesson.originating_evaluation,
        },
    )
    return row


def disable_lesson(workspace_id: str, lesson_id: str) -> dict[str, Any]:
    client = open_memory(workspace_id)
    existing = client.get_entity(LESSON_CATEGORY, lesson_id)
    body = dict(existing.get("body") or {})
    body["status"] = "disabled"
    return client.set_entity(LESSON_CATEGORY, lesson_id, body)


def get_lesson(workspace_id: str, lesson_id: str) -> Lesson:
    client = open_memory(workspace_id)
    row = client.get_entity(LESSON_CATEGORY, lesson_id)
    return _row_to_lesson(row)


def list_lessons(workspace_id: str) -> list[Lesson]:
    client = open_memory(workspace_id)
    rows = client.list_entities(LESSON_CATEGORY, limit=100)
    return [_row_to_lesson(row) for row in rows]


def recall_lessons(workspace_id: str, query: str, keywords: list[str]) -> list[Lesson]:
    """Fresh-session READ path. Never consults process memory."""
    client = open_memory(workspace_id)
    found: dict[str, dict[str, Any]] = {}
    terms = [query] + [term for term in keywords if term]
    for term in terms:
        cleaned = (term or "").strip()
        if len(cleaned) < 3:
            continue
        try:
            hits = client.search_entities(cleaned, category=LESSON_CATEGORY, limit=20)
        except SibylMemoryError:
            hits = []
        for row in hits:
            found[row["name"]] = row
    if not found:
        for row in client.list_entities(LESSON_CATEGORY, limit=100):
            found[row["name"]] = row
    lessons = [_row_to_lesson(row) for row in found.values()]
    return [lesson for lesson in lessons if lesson.status == "active"]


def tenant_cannot_see(other_workspace: str, lesson_id: str) -> bool:
    client = open_memory(other_workspace)
    try:
        client.get_entity(LESSON_CATEGORY, lesson_id)
        return False
    except NotFoundError:
        return True


def _row_to_lesson(row: dict[str, Any]) -> Lesson:
    body = dict(row.get("body") or {})
    body.setdefault("id", row.get("name") or "")
    body.setdefault("workspace_id", row.get("tenant_id") or "")
    body.setdefault("created_at", row.get("created_at") or "")
    return Lesson.from_dict(body, fallback_id=str(row.get("name") or ""))


def _validate_lesson(lesson: Lesson) -> None:
    if not lesson.id or ".." in lesson.id or any(ch in lesson.id for ch in '<>|;"`'):
        raise ValueError("Invalid lesson id.")
    if not lesson.requirement or not lesson.requirement.strip():
        raise ValueError("Lesson requirement cannot be empty.")
    if len(lesson.requirement) > 2000:
        raise ValueError("Lesson requirement is too long.")
    if lesson.job_type != "research":
        raise ValueError("This build only stores lessons for research jobs.")
    if lesson.status not in {"active", "disabled", "ignored"}:
        raise ValueError("Unknown lesson status.")
