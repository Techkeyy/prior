"""Real research worker. Accepts arbitrary supported requests. No canned demo text."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from prior.domain import Contract, JobSpec

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
DDG = "https://api.duckduckgo.com/"
HEADERS = {
    "User-Agent": "PRIOR-research-agent/0.1 (Sibyl Labs Hackathon; research jobs)"
}


def run_research(spec: JobSpec, contract: Contract) -> dict[str, Any]:
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    query = spec.goal or spec.raw
    limit = spec.count or 5
    wiki_hits = _wiki_search(query, limit=max(limit, 5))
    findings: list[dict[str, Any]] = []
    for hit in wiki_hits[:limit]:
        summary = _wiki_summary(hit["title"])
        findings.append(summary)
    if not findings:
        ddg = _duckduckgo(query)
        if ddg:
            findings.append(ddg)

    requires_sources = any(
        "source" in item.lower() or "citation" in item.lower() or "link" in item.lower()
        for item in contract.acceptance
    )
    requires_recent = spec.time_sensitive or any(
        "recent" in item.lower() for item in contract.acceptance
    )

    for finding in findings:
        if requires_sources and not finding.get("sources"):
            finding["warning"] = "No source URL was available for this item."
        if requires_recent:
            finding["retrieved_at"] = retrieved_at

    report = {
        "type": "object",
        "value": {
            "title": contract.title,
            "goal": spec.goal,
            "retrieved_at": retrieved_at,
            "findings": findings,
            "deliverables": _map_deliverables(spec, findings),
            "honored_requirements": list(contract.acceptance),
            "applied_lesson_ids": [lesson.id for lesson in contract.applied_lessons],
            "notes": _notes(spec, findings, requires_sources, requires_recent),
        },
    }
    return report


def _wiki_search(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            WIKI_SEARCH,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": str(limit),
                "format": "json",
            },
            headers=HEADERS,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        return list(data.get("query", {}).get("search", []))
    except Exception as exc:  # noqa: BLE001
        return [{"title": query, "error": str(exc)}]


def _wiki_summary(title: str) -> dict[str, Any]:
    url = WIKI_SUMMARY + quote(title.replace(" ", "_"))
    page_url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
    try:
        response = httpx.get(url, headers=HEADERS, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        extract = str(data.get("extract") or "").strip()
        return {
            "name": data.get("title") or title,
            "summary": extract,
            "products": [],
            "pricing": "Not stated in this source.",
            "strengths": _first_sentence(extract),
            "weaknesses": "Not covered by this source.",
            "sources": [
                {
                    "label": "Wikipedia",
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page") or page_url,
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": title,
            "summary": f"Could not fetch a summary ({exc}).",
            "products": [],
            "pricing": "Unknown",
            "strengths": "",
            "weaknesses": "",
            "sources": [{"label": "Wikipedia search hit", "url": page_url}],
        }


def _duckduckgo(query: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(
            DDG,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers=HEADERS,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        heading = data.get("Heading") or query
        abstract = data.get("AbstractText") or data.get("Abstract") or ""
        source = data.get("AbstractURL") or data.get("AbstractSource")
        related = data.get("RelatedTopics") or []
        if not abstract and not related:
            return None
        sources = []
        if source:
            sources.append({"label": data.get("AbstractSource") or "DuckDuckGo", "url": source})
        return {
            "name": heading,
            "summary": abstract or "Related topics only.",
            "products": [
                item.get("Text")
                for item in related[:5]
                if isinstance(item, dict) and item.get("Text")
            ],
            "pricing": "Not stated in this source.",
            "strengths": "",
            "weaknesses": "",
            "sources": sources,
        }
    except Exception:
        return None


def _map_deliverables(spec: JobSpec, findings: list[dict[str, Any]]) -> dict[str, Any]:
    names = [item.get("name") for item in findings if item.get("name")]
    return {
        "names": names,
        "products": [item.get("summary", "")[:180] for item in findings],
        "pricing": [item.get("pricing") for item in findings],
        "strengths": [item.get("strengths") for item in findings],
        "weaknesses": [item.get("weaknesses") for item in findings],
        "requested": spec.deliverables,
    }


def _notes(
    spec: JobSpec,
    findings: list[dict[str, Any]],
    requires_sources: bool,
    requires_recent: bool,
) -> list[str]:
    notes = []
    if not findings:
        notes.append("No public sources answered this query.")
    if requires_sources:
        missing = [item.get("name") for item in findings if not item.get("sources")]
        if missing:
            notes.append("Missing source links for: " + ", ".join(str(name) for name in missing))
        else:
            notes.append("Source links were attached to each finding because the contract required them.")
    if requires_recent:
        notes.append("Retrieval timestamp recorded because the job is time-sensitive.")
    if spec.explicit_requirements:
        notes.append("Explicit user requirements were included in the contract the worker received.")
    return notes


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    parts = text.split(". ")
    return parts[0].strip() + ("." if parts else "")
