"""CLI for the ACP seller process. Reads a requirement JSON on stdin."""

from __future__ import annotations

import json
import sys

from prior.contract import build_contract
from prior.domain import JobSpec, Lesson
from prior.research import run_research


def spec_from_requirement(payload: dict) -> JobSpec:
    return JobSpec(
        job_type=str(payload.get("job_type") or "research"),
        goal=str(payload.get("goal") or payload.get("title") or payload.get("raw") or ""),
        subject=str(payload.get("subject") or ""),
        domain=str(payload.get("domain") or ""),
        count=payload.get("count"),
        deliverables=list(payload.get("deliverables") or []),
        explicit_requirements=list(payload.get("explicit_requirements") or []),
        time_sensitive=bool(payload.get("time_sensitive")),
        raw=str(payload.get("raw") or payload.get("goal") or ""),
        keywords=list(payload.get("keywords") or []),
    )


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    spec = spec_from_requirement(payload)
    lessons = [Lesson.from_dict(item) for item in (payload.get("applied_lessons") or [])]
    contract = build_contract(spec, lessons)
    if payload.get("acceptance"):
        contract.acceptance = list(payload["acceptance"])
    report = run_research(spec, contract)
    json.dump(report, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
