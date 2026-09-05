"""CLI for the ACP seller process. Reads a requirement JSON on stdin."""

from __future__ import annotations

import json
import sys

from prior.contract import build_contract
from prior.domain import JobSpec, Lesson
from prior.job_spec import parse_job
from prior.research import run_research


def spec_from_requirement(payload: dict) -> JobSpec:
    raw = str(payload.get("raw") or payload.get("goal") or payload.get("title") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    domain = str(payload.get("domain") or "").strip()
    deliverables = list(payload.get("deliverables") or [])
    count = payload.get("count")

    if (not subject or not domain or not deliverables) and raw and raw.lower() != "research":
        parsed = parse_job(raw)
        if not subject:
            subject = parsed.subject
        if not domain:
            domain = parsed.domain
        if not deliverables:
            deliverables = parsed.deliverables
        if count is None:
            count = parsed.count

    return JobSpec(
        job_type=str(payload.get("job_type") or "research"),
        goal=str(payload.get("goal") or payload.get("title") or raw or "Research"),
        subject=subject,
        domain=domain,
        count=count,
        deliverables=deliverables,
        explicit_requirements=list(payload.get("explicit_requirements") or []),
        time_sensitive=bool(payload.get("time_sensitive")),
        raw=raw,
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
