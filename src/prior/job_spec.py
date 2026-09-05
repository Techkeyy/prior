from __future__ import annotations

import re

from prior.domain import SUPPORTED_JOB_TYPE, UNSUPPORTED_JOB_TYPE, JobSpec

RESEARCH_CUES = (
    "research",
    "compare",
    "comparison",
    "landscape",
    "find suppliers",
    "find supplier",
    "market",
    "pricing",
    "competitor",
    "competitors",
    "overview",
    "survey",
    "who are",
    "what are",
    "top ",
)

UNSUPPORTED_CUES = (
    "write code",
    "implement",
    "deploy a contract",
    "mint nft",
    "send usdc",
    "transfer tokens",
    "trade",
    "open a position",
    "generate an image",
    "make a video",
    "send email",
    "tweet",
    "post on x",
)

WORD_COUNTS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

DOMAIN_HINTS = {
    "wallet": "ai wallets",
    "wallets": "ai wallets",
    "password manager": "password managers",
    "password managers": "password managers",
    "exchange": "decentralized exchanges",
    "exchanges": "decentralized exchanges",
    "dex": "decentralized exchanges",
    "supplier": "suppliers",
    "suppliers": "suppliers",
    "pricing": "product pricing",
    "price": "product pricing",
}

DEFAULT_DELIVERABLES = [
    "names",
    "products",
    "pricing",
    "strengths",
    "weaknesses",
]

REFUSAL = (
    "This build currently supports research and information-gathering jobs, "
    "such as competitor research, product comparisons, market landscapes, "
    "supplier finding, and pricing surveys."
)


def parse_job(raw: str) -> JobSpec:
    text = (raw or "").strip()
    if not text:
        return JobSpec(
            job_type=UNSUPPORTED_JOB_TYPE,
            goal="",
            subject="",
            domain="",
            count=None,
            deliverables=[],
            explicit_requirements=[],
            time_sensitive=False,
            raw=text,
            refusal_reason="Describe the research you need done.",
            keywords=[],
        )

    lowered = text.lower()
    if _is_unsupported(lowered) and not _looks_like_research(lowered):
        return JobSpec(
            job_type=UNSUPPORTED_JOB_TYPE,
            goal=text,
            subject="",
            domain="",
            count=None,
            deliverables=[],
            explicit_requirements=[],
            time_sensitive=_is_time_sensitive(lowered),
            raw=text,
            refusal_reason=REFUSAL,
            keywords=_keywords(lowered),
        )

    if not _looks_like_research(lowered):
        return JobSpec(
            job_type=UNSUPPORTED_JOB_TYPE,
            goal=text,
            subject="",
            domain="",
            count=None,
            deliverables=[],
            explicit_requirements=[],
            time_sensitive=_is_time_sensitive(lowered),
            raw=text,
            refusal_reason=REFUSAL,
            keywords=_keywords(lowered),
        )

    count = _extract_count(lowered)
    subject = _extract_subject(text, count)
    domain = _domain_for(lowered, subject)
    deliverables = _deliverables(text, count, subject)
    requirements = _explicit_requirements(text)
    keywords = _keywords(lowered)
    if domain:
        keywords.append(domain)
    goal = _goal(text, subject, count)

    return JobSpec(
        job_type=SUPPORTED_JOB_TYPE,
        goal=goal,
        subject=subject,
        domain=domain,
        count=count,
        deliverables=deliverables,
        explicit_requirements=requirements,
        time_sensitive=_is_time_sensitive(lowered),
        raw=text,
        keywords=_unique(keywords),
    )


def _looks_like_research(lowered: str) -> bool:
    return any(cue in lowered for cue in RESEARCH_CUES)


def _is_unsupported(lowered: str) -> bool:
    return any(cue in lowered for cue in UNSUPPORTED_CUES)


def _extract_count(lowered: str) -> int | None:
    match = re.search(r"\btop\s+(\d{1,2})\b", lowered)
    if match:
        return int(match.group(1))
    match = re.search(
        r"\b(?:research|compare|find|list|survey|top)?\s*(\d{1,2})\s+(?:[a-z0-9_-]+\s+)*(?:companies|products|exchanges|wallets|managers|password managers|suppliers|competitors|protocols|tools|frameworks|projects|dapps|options|services|solutions|platforms|networks)\b",
        lowered,
    )
    if match:
        return int(match.group(1))
    for word, value in WORD_COUNTS.items():
        if re.search(rf"\b{word}\b", lowered):
            return value
    match_num = re.search(r"\b(\d{1,2})\s+[a-z0-9_-]+\b", lowered)
    if match_num and int(match_num.group(1)) <= 50:
        return int(match_num.group(1))
    return None


def _extract_subject(text: str, count: int | None) -> str:
    cleaned = re.sub(r"^(please\s+)?", "", text.strip(), flags=re.I)
    cleaned = re.sub(
        r"^(research|compare|find|produce|survey|map|list)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"^(the\s+)?(top\s+)?(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return text.strip()
    split_match = re.split(
        r"\s+(?:and\s+(?:compare|summarize|evaluate|analyze|list|provide|show|break down|examine)|by\s+|focusing on\s+|based on\s+|with their\s+)\b",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )
    core = split_match[0].strip(" .,")
    return core or cleaned


def _domain_for(lowered: str, subject: str) -> str:
    for hint, label in DOMAIN_HINTS.items():
        if re.search(rf"\b{re.escape(hint)}\b", lowered):
            return label
    return subject.lower()[:80]


def _extract_comparison_fields(text: str) -> list[str]:
    # Match comparison clause:
    # "compare their pricing, supported platforms, strengths, and weaknesses"
    # "compare deployment options, API support, and pricing for 3 observability platforms"
    m = re.search(
        r"\b(?:compare|evaluating|evaluate|examine|examining|focusing on|with their|and their|including)\s+(?:their\s+|the\s+)?(.+?)(?:\.|$)",
        text,
        re.I,
    )
    if not m:
        return []
    raw_clause = m.group(1).strip()
    raw_clause = re.sub(r"\s+(?:for|across|among|in|of)\s+(?:\d+|the|all|each|leading|top)?\s*[a-z0-9_\-\s]+$", "", raw_clause, flags=re.I).strip()
    
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+|\s+&\s+", raw_clause, flags=re.I)
    cleaned_fields = []
    for p in parts:
        c = p.strip(" .,/()").lower()
        if not c or len(c) < 2 or c in ("them", "their", "it", "each", "all", "more", "others"):
            continue
        if c in ("price", "cost", "costs", "pricing", "pricing plans", "subscription"):
            cleaned_fields.append("pricing")
        elif c in ("platform", "platforms", "supported platform", "supported platforms", "os support", "os", "supported os", "operating systems"):
            cleaned_fields.append("supported platforms")
        elif c in ("strength", "strengths", "pros", "advantages", "benefits"):
            cleaned_fields.append("strengths")
        elif c in ("weakness", "weaknesses", "cons", "disadvantages", "limitations", "drawbacks", "caveats"):
            cleaned_fields.append("weaknesses")
        elif c in ("feature", "features", "product", "products", "offerings", "capabilities"):
            cleaned_fields.append("products")
        else:
            cleaned_fields.append(c)
    return cleaned_fields


def _deliverables(text: str, count: int | None, subject: str = "") -> list[str]:
    explicit_fields = _extract_comparison_fields(text)
    entity_label = f"{count} {subject}" if count and subject else (f"{count} product names" if count else "names")
    if explicit_fields:
        fields = [entity_label]
        for f in explicit_fields:
            if f not in fields:
                fields.append(f)
        return fields

    items = list(DEFAULT_DELIVERABLES)
    if "supplier" in text.lower():
        items = ["supplier names", "what they sell", "pricing signals", "fit notes", "risks"]
    elif "landscape" in text.lower() or "market" in text.lower():
        items = ["category map", "notable products", "positioning", "pricing if public", "gaps"]
    if count:
        items = [f"{count} {items[0]}" if i == 0 else item for i, item in enumerate(items)]
    return items


def _explicit_requirements(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    if "source" in lowered or "citation" in lowered or "link" in lowered:
        found.append("Material factual claims must include source links.")
    if "pricing" in lowered or "price" in lowered:
        found.append("Include current public pricing when available.")
    musts = re.findall(r"must(?: include| have| cover)? ([^.]+)", text, flags=re.I)
    for item in musts:
        found.append(item.strip().rstrip("."))
    return _unique(found)


def _is_time_sensitive(lowered: str) -> bool:
    return any(token in lowered for token in ("current", "latest", "today", "this year", "2026", "now"))


def _goal(text: str, subject: str, count: int | None) -> str:
    if count:
        return f"Research {count} {subject}".strip()
    return text.strip().rstrip(".")


def _keywords(lowered: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", lowered)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "need",
        "done",
        "please",
        "research",
        "compare",
        "find",
        "produce",
        "top",
        "five",
        "companies",
    }
    return [token for token in tokens if token not in stop][:12]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out
