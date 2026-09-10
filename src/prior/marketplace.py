"""Live Virtuals ACP marketplace discovery and provider selection (READ-ONLY).

Boundary: this module searches the live Virtuals registry, normalizes real
agents and real offerings, applies HARD compatibility gates (task fit,
domain fit, fund-flow support, chain support, schema receivability), ranks
only the survivors deterministically, and builds the exact candidate-shaped
requirement payload that WOULD be sent to the selected provider.

Task capability and subject/domain are separate signals. A shared domain
word alone never qualifies a provider: the offering must show it can
perform the requested TASK, must be able to receive the task brief through
its real input schema, and must run on PRIOR's supported path.

Read-only gate: no function here calls create-job, fund, complete, or
reject, nor createJobFromOffering / createJobByOfferingName. The only
bridge command used is ``discover`` (browseAgents).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from prior.domain import Contract, JobSpec
from prior.providers.base import ProviderError, requirement_payload


class MarketplaceError(ProviderError):
    """Base for marketplace-layer failures. Never a silent fallback."""


class DiscoveryError(MarketplaceError):
    """Live marketplace lookup failed (network, credentials, malformed)."""


class SchemaError(MarketplaceError):
    """An offering requirements schema cannot be safely interpreted."""


class NoCompatibleProvider(MarketplaceError):
    """No genuinely compatible live provider exists for this job."""

    def __init__(self, message: str, *, query: "CapabilityQuery | None" = None,
                 candidates_seen: int = 0,
                 rejections: list[tuple[str, str]] | None = None) -> None:
        super().__init__(message)
        self.query = query
        self.candidates_seen = candidates_seen
        self.rejections = list(rejections or [])


# ---------------------------------------------------------------------------
# Task verbs and capability derivation. Task-defining verbs are never
# stripped: they are the primary signal of what work the user wants.
# ---------------------------------------------------------------------------

# stem -> surface forms found in real text (verb inflections only; pure
# nouns such as "analysis" or plural "reports" are deliberately excluded so
# that a data product described with nouns cannot pose as an action).
TASK_VERB_FORMS: dict[str, set[str]] = {
    "research": {"research", "researching"},
    "compare": {"compare", "compares", "compared", "comparing", "comparison",
                "comparisons", "comparative"},
    "analyze": {"analyze", "analyzes", "analyzed", "analyzing"},
    "summarize": {"summarize", "summarizes", "summarized", "summarizing",
                  "summary", "summaries"},
    "monitor": {"monitor", "monitors", "monitored", "monitoring"},
    "track": {"track", "tracks", "tracked", "tracking"},
    "report": {"report", "reports", "reported", "reporting"},
    "generate": {"generate", "generates", "generated", "generating"},
    "audit": {"audit", "audits", "audited", "auditing"},
    "evaluate": {"evaluate", "evaluates", "evaluated", "evaluating"},
    "review": {"review", "reviews", "reviewed", "reviewing"},
    "investigate": {"investigate", "investigates", "investigated",
                    "investigating"},
    "survey": {"survey", "surveys", "surveyed", "surveying"},
    "rank": {"rank", "ranks", "ranked", "ranking", "rankings"},
    "screen": {"screen", "screens", "screened", "screening"},
    "scan": {"scan", "scans", "scanned", "scanning"},
    "detect": {"detect", "detects", "detected", "detecting"},
}

# Research-family tasks require strict verb evidence in the offering.
RESEARCH_TASK_VERBS = frozenset({
    "research", "compare", "analyze", "summarize", "investigate", "survey",
    "evaluate", "review", "audit",
})

# Verbs denoting the same examine-and-judge action. Used symmetrically when
# intersecting requested and evidenced task verbs: an offering evidencing
# "audit" satisfies a requested "review" and vice versa. This never adds
# capabilities, it only recognizes equivalent wording of the same action.
REVIEW_FAMILY = frozenset({"review", "audit", "evaluate"})


def _expand_verbs(verbs: list[str]) -> set[str]:
    expanded = set(verbs)
    if expanded & REVIEW_FAMILY:
        expanded |= REVIEW_FAMILY
    return expanded


# Markers of genuine source-code capability in offering-level text.
# Deliberately excludes generic words ("analysis", "report", "data") that
# describe data products rather than code work.
CODE_CAPABILITY_MARKERS = frozenset({
    "solidity",
    "source code",
    "smart contract",
    "vulnerability",
    "vulnerabilities",
    "code review",
    "code audit",
})

def _offering_has_code_capability(candidate: "MarketplaceCandidate") -> bool:
    blob = _offering_blob(candidate).lower()
    if any(marker in blob for marker in CODE_CAPABILITY_MARKERS):
        return True
    import re as _re

    return bool(_re.search(r"\baudit(s|ed|ing)?\b", blob))


def _request_wants_source_code_review(spec: JobSpec, query: "CapabilityQuery") -> bool:
    text = f"{spec.raw or ''} {' '.join(query.subject_terms)}".lower()
    if "solidity" in text or "source code" in text:
        return "review" in query.task_capabilities or "audit" in query.task_capabilities
    if "smart contract" in text:
        return bool(set(query.task_capabilities) & {"review", "audit", "evaluate", "analyze"})
    return False


# Semantic-fit mirror guard. check_compatibility refuses code-review
# requests for non-code agents; without the inverse, a transaction-review
# request can be won by a source-code-only auditor purely on name overlap
# and marketplace rating. Rating must only rank candidates that are already
# semantically compatible.
TX_REVIEW_CAPABILITY_MARKERS = (
    "transaction", "wallet", "approval", "allowance", "spender", "permit",
    "swap", "bridge", "signing", "sign ", "tx ", " tx", "web3", "on-chain",
    "onchain", "crypto safety",
)
CODE_ONLY_MARKERS = (
    "source code", "codebase", "cvss", "static analysis", "code scan",
    "repository scan", "code audit", "code review", "vulnerability scanner",
    "github repo",
)


def _offering_declares_tx_review_capability(candidate: "MarketplaceCandidate") -> bool:
    blob = _offering_blob(candidate).lower()
    return any(marker in blob for marker in TX_REVIEW_CAPABILITY_MARKERS)


def _offering_is_code_only_auditor(candidate: "MarketplaceCandidate") -> bool:
    blob = _offering_blob(candidate).lower()
    return (any(marker in blob for marker in CODE_ONLY_MARKERS)
            or "vulnerabilit" in blob) and not _offering_declares_tx_review_capability(candidate)

# Monitoring-family tasks accept verb evidence or explicit tracker naming.
MONITOR_TASK_VERBS = frozenset({
    "monitor", "track", "report", "watch", "alert", "scan", "detect",
    "screen",
})
MONITOR_FAMILY_NOUNS = frozenset({
    "monitoring", "tracking", "tracker", "scanner", "screener", "watchlist",
    "ranking", "leaderboard", "movements", "activity",
})

_JOB_TYPE_DEFAULT_TASKS = {
    "research": ["research"],
}

_STOPWORDS = frozenset(
    "the a an and or of to in on for with by from that this these those "
    "what which who whom whose when where how why not no yes our your their "
    "its his her him her them they are was were been being have has had do "
    "does did will would can could should shall may might must about into "
    "over under again once here there all any both each few more most other "
    "some such only own same than too very just also top best leading list "
    "get give show tell find include using use used make made need needs "
    "needed please five three two four six seven eight nine ten".split()
)


def _words(text: str) -> list[str]:
    out: list[str] = []
    for raw in str(text or "").lower().replace("_", " ").replace("-", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) >= 3 and word not in out:
            out.append(word)
    return out


def _tokens(text: str) -> list[str]:
    return [word for word in _words(text) if word not in _STOPWORDS]


def _task_verbs_in(text: str) -> list[str]:
    """Task-verb stems evidenced in text, in lexicon order (deterministic)."""
    present = set(_words(text))
    return [stem for stem, forms in TASK_VERB_FORMS.items() if present & forms]


@dataclass
class CapabilityQuery:
    """Marketplace search intent. Task and subject are separate signals."""

    primary_keyword: str
    task_capabilities: list[str] = field(default_factory=list)
    subject_terms: list[str] = field(default_factory=list)
    deliverable_capabilities: list[str] = field(default_factory=list)
    useful_terms: list[str] = field(default_factory=list)
    job_type: str = "research"
    deliverable_hints: list[str] = field(default_factory=list)
    # Backwards-compatible alias: required_terms == subject + task terms.
    required_terms: list[str] = field(default_factory=list)
    # Ordered discovery queries: subject terms first (specific), then a
    # short domain label, then the job type as a final breadth fallback.
    # The live selector searches ALL of them and merges, so relevant
    # providers outside any single top-N slice stay reachable.
    discovery_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_keyword": self.primary_keyword,
            "task_capabilities": list(self.task_capabilities),
            "subject_terms": list(self.subject_terms),
            "deliverable_capabilities": list(self.deliverable_capabilities),
            "useful_terms": list(self.useful_terms),
            "job_type": self.job_type,
            "deliverable_hints": list(self.deliverable_hints),
            "discovery_queries": list(self.discovery_queries),
        }


def _split_terms(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split tokens into (task verbs, subject terms) via the verb lexicon."""
    verb_forms: dict[str, str] = {}
    for stem, forms in TASK_VERB_FORMS.items():
        for form in forms:
            verb_forms[form] = stem
    tasks: list[str] = []
    subjects: list[str] = []
    for token in tokens:
        stem = verb_forms.get(token)
        if stem is not None and stem not in tasks:
            tasks.append(stem)
        elif stem is None and token not in subjects:
            subjects.append(token)
    return tasks, subjects


def build_capability_query(spec: JobSpec, contract: Contract | None = None) -> CapabilityQuery:
    """Derive task capabilities, subject terms, and deliverable capabilities.

    Every capability stays grounded in user text, the JobSpec, the contract,
    or the PRIOR job_type. Task-defining verbs are preserved, never stripped.
    """
    request_text = " ".join([
        spec.raw or "", spec.subject or "", spec.domain or "",
        " ".join(spec.keywords or []),
    ])
    tasks, subjects = _split_terms(_tokens(request_text))
    if not tasks:
        for default in _JOB_TYPE_DEFAULT_TASKS.get(spec.job_type or "research", []):
            if default not in tasks:
                tasks.append(default)
    deliverable_caps: list[str] = []
    for chunk in list(spec.deliverables or []) + list(spec.explicit_requirements or []):
        for stem in _task_verbs_in(chunk):
            if stem not in tasks and stem not in deliverable_caps:
                deliverable_caps.append(stem)
    useful: list[str] = []
    pools = list(spec.deliverables or [])
    if contract is not None:
        pools += list(contract.acceptance or [])
        pools += [lesson.requirement for lesson in (contract.applied_lessons or [])]
    for token in _tokens(" ".join(pools)):
        if token not in subjects and token not in tasks and token not in useful:
            useful.append(token)
    primary = (spec.domain or spec.subject or "research").strip().lower()
    if not primary:
        primary = "research"
    # Discovery queries, specific first: subject terms carry the request's
    # nouns; a raw domain/subject string is only usable when short (longer
    # strings are sentence fragments that poison registry search); the job
    # type trails as a breadth fallback. Capped and deduplicated.
    queries: list[str] = []
    for term in subjects[:2]:
        if term and term not in queries:
            queries.append(term)
    if primary and len(primary.split()) <= 3 and primary not in queries:
        queries.append(primary)
    for term in subjects[2:12]:
        if term and term not in queries and len(queries) < 3:
            queries.append(term)
    if (spec.job_type or "research") not in queries:
        queries.append(spec.job_type or "research")
    queries = queries[:4]
    if not queries:
        queries = ["research"]
    return CapabilityQuery(
        primary_keyword=queries[0],
        task_capabilities=tasks,
        subject_terms=subjects[:12],
        deliverable_capabilities=deliverable_caps,
        useful_terms=useful[:16],
        job_type=spec.job_type or "research",
        deliverable_hints=list(spec.deliverables or [])[:8],
        required_terms=(subjects[:12] + [t for t in tasks if t not in subjects])[:12],
        discovery_queries=queries,
    )


# ---------------------------------------------------------------------------
# Candidate normalization: real registry fields only, never invented.
# ---------------------------------------------------------------------------

@dataclass
class MarketplaceCandidate:
    agent_id: str
    agent_name: str
    agent_description: str
    wallet_address: str
    last_active_at: str
    rating: float | None
    is_new: bool
    agent_hidden: bool
    offering_name: str | None
    offering_description: str
    requirements_schema: Any
    deliverable_desc: str
    price_type: str
    price_value: float | None
    required_funds: bool
    sla_minutes: int | None
    offering_hidden: bool
    offering_private: bool
    chain_ids: list[int] = field(default_factory=list)
    raw_ref: dict[str, int] = field(default_factory=dict)
    # Filled by the compatibility gate on success, with field provenance:
    task_evidence: list[dict[str, str]] = field(default_factory=list)
    subject_evidence: list[dict[str, str]] = field(default_factory=list)
    requirement_data_preview: dict[str, Any] | None = None
    schema_notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.agent_name} / {self.offering_name or 'no offering'}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_description": self.agent_description,
            "wallet_address": self.wallet_address,
            "last_active_at": self.last_active_at,
            "rating": self.rating,
            "is_new": self.is_new,
            "agent_hidden": self.agent_hidden,
            "offering_name": self.offering_name,
            "offering_description": self.offering_description,
            "requirements_schema": self.requirements_schema,
            "deliverable_desc": self.deliverable_desc,
            "price_type": self.price_type,
            "price_value": self.price_value,
            "required_funds": self.required_funds,
            "sla_minutes": self.sla_minutes,
            "offering_hidden": self.offering_hidden,
            "offering_private": self.offering_private,
            "chain_ids": list(self.chain_ids),
            "task_evidence": [dict(item) for item in self.task_evidence],
            "subject_evidence": [dict(item) for item in self.subject_evidence],
            "requirement_data_preview": self.requirement_data_preview,
            "schema_notes": list(self.schema_notes),
        }


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_agents(raw_agents: Any) -> tuple[list[MarketplaceCandidate], int, int]:
    """Normalize raw browseAgents output.

    Returns (candidates, agents_seen, skipped). Malformed entries are
    skipped and counted, never repaired with invented data. Agents without
    offerings produce no candidate: without an offering there is nothing a
    job could be created from.
    """
    candidates: list[MarketplaceCandidate] = []
    if not isinstance(raw_agents, list):
        return candidates, 0, 0
    agents_seen = len(raw_agents)
    skipped = 0
    for ai, agent in enumerate(raw_agents):
        if not isinstance(agent, dict):
            skipped += 1
            continue
        wallet = str(agent.get("walletAddress") or "").strip()
        if not wallet:
            skipped += 1
            continue
        chains: list[int] = []
        for chain in agent.get("chains") or []:
            if isinstance(chain, dict):
                cid = _as_int(chain.get("chainId"))
                if cid is not None and cid not in chains:
                    chains.append(cid)
        offerings = agent.get("offerings")
        if not isinstance(offerings, list) or not offerings:
            skipped += 1
            continue
        for oi, offering in enumerate(offerings):
            if not isinstance(offering, dict):
                skipped += 1
                continue
            name = offering.get("name")
            candidates.append(MarketplaceCandidate(
                agent_id=str(agent.get("id") or ""),
                agent_name=str(agent.get("name") or "Unnamed ACP agent"),
                agent_description=str(agent.get("description") or ""),
                wallet_address=wallet,
                last_active_at=str(agent.get("lastActiveAt") or ""),
                rating=_as_float(agent.get("rating")),
                is_new=bool(agent.get("isNew", False)),
                agent_hidden=bool(agent.get("isHidden", False)),
                offering_name=str(name) if name else None,
                offering_description=str(offering.get("description") or ""),
                requirements_schema=offering.get("requirements"),
                deliverable_desc=(str(offering.get("deliverable"))
                                  if offering.get("deliverable") not in (None, "") else ""),
                price_type=str(offering.get("priceType") or ""),
                price_value=_as_float(offering.get("priceValue")),
                required_funds=bool(offering.get("requiredFunds", False)),
                sla_minutes=_as_int(offering.get("slaMinutes")),
                offering_hidden=bool(offering.get("isHidden", False)),
                offering_private=bool(offering.get("isPrivate", False)),
                chain_ids=chains,
                raw_ref={"agent_index": ai, "offering_index": oi},
            ))
    return candidates, agents_seen, skipped


# ---------------------------------------------------------------------------
# Compatibility gates. ALL must pass. Order: visibility, fund flow, chain,
# task fit, domain fit, schema receivability.
# ---------------------------------------------------------------------------

# PRIOR's supported execution path. Offerings bound to other chains cannot
# be hired through the current authorized write path.
SUPPORTED_CHAIN_ID = 8453

# Schema property names that can legitimately carry the natural-language
# task brief (normalized: lowercase, alphanumeric only).
BRIEF_SLOTS = frozenset({
    "topic", "query", "prompt", "task", "brief", "requirement",
    "description", "request", "question", "subject", "input", "text",
    "message", "goal", "jobdescription", "taskdescription", "userrequest",
    "instruction", "instructions", "jobbrief",
    # Code-carrying inputs accept the brief because the brief always embeds
    # the pasted artifact alongside the task; the worker receives both.
    "code",
})


def _norm_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def requirement_supply_keys() -> set[str]:
    """Keys PRIOR's outgoing requirement payload can always supply."""
    return {
        "goal", "title", "deliverables", "acceptance", "applied_lessons",
        "learned_requirements", "raw", "subject", "domain",
        "time_sensitive", "job_type", "count", "keywords",
        "explicit_requirements", "job_description",
    }


def schema_required_fields(schema: Any) -> list[str]:
    """Required input fields of an offering requirements schema."""
    parsed = _parse_schema(schema)
    if isinstance(parsed, dict):
        required = parsed.get("required")
        if isinstance(required, list):
            return [str(item) for item in required if str(item).strip()]
    return []


def _parse_schema(schema: Any) -> Any:
    """Parse a requirements schema; raise SchemaError if uninterpretable."""
    if schema is None or schema == "" or schema == {}:
        return None
    if isinstance(schema, str):
        text = schema.strip()
        if not text:
            return None
        try:
            import json as _json
            return _json.loads(text)
        except ValueError as exc:
            raise SchemaError(
                "offering requirement schema could not be safely interpreted") from exc
    if isinstance(schema, dict):
        return schema
    raise SchemaError("offering requirement schema could not be safely interpreted")


def _resolve_refs(node: Any, root: Any) -> Any:
    """Resolve local JSON-schema refs (#/... only). External refs fail."""
    if isinstance(node, dict):
        if set(node.keys()) == {"$ref"} and isinstance(node["$ref"], str):
            ref = node["$ref"]
            if not ref.startswith("#/"):
                raise SchemaError(
                    "offering requirement schema could not be safely interpreted")
            target: Any = root
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    raise SchemaError(
                        "offering requirement schema could not be safely interpreted")
                target = target[part]
            return _resolve_refs(target, root)
        return {key: _resolve_refs(value, root) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, root) for item in node]
    return node


def validate_against_schema(value: Any, schema: Any, path: str = "input") -> list[str]:
    """Read-only JSON-schema validation. Returns a list of violations."""
    if isinstance(schema, bool):
        return [] if schema else [f"{path}: schema forbids all values"]
    if not isinstance(schema, dict):
        return [f"{path}: schema could not be safely interpreted"]
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        kinds = [expected] if isinstance(expected, str) else list(expected)
        ok = False
        for kind in kinds:
            if kind == "string" and isinstance(value, str):
                ok = True
            elif kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                ok = True
            elif kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
                ok = True
            elif kind == "boolean" and isinstance(value, bool):
                ok = True
            elif kind == "object" and isinstance(value, dict):
                ok = True
            elif kind == "array" and isinstance(value, list):
                ok = True
            elif kind == "null" and value is None:
                ok = True
        if not ok:
            return [f"{path}: expected {expected}"]
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"] or 0):
            errors.append(f"{path}: too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"] or 0):
            errors.append(f"{path}: too long")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    if "enum" in schema and isinstance(schema["enum"], list):
        if value not in schema["enum"]:
            errors.append(f"{path}: not an allowed value")
    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if key in value:
                    errors.extend(validate_against_schema(value[key], subschema, f"{path}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(validate_against_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


# Offerings that explicitly declare broad scope are subject-compatible with
# any requested subject. Generalism is read ONLY from explicit broad-scope
# wording in the offering's own fields, never inferred from the parent agent
# description, and never from a bare task name: an offering called
# "research" proves it performs research (task evidence), not that it
# accepts arbitrary subjects.
GENERALIST_MARKERS = frozenset({
    "any topic", "any subject", "all topics", "wide range",
    "various topics", "diverse topics", "any domain", "all domains",
    "general research", "open-ended research", "arbitrary topic",
})


def _offering_blob(candidate: "MarketplaceCandidate") -> str:
    """Offering-level text only: name, description, deliverable."""
    return " ".join([
        candidate.offering_name or "",
        candidate.offering_description,
        candidate.deliverable_desc,
    ])


def offering_generalist_markers(candidate: "MarketplaceCandidate") -> list[str]:
    blob = _offering_blob(candidate).lower()
    return sorted({marker for marker in GENERALIST_MARKERS if marker in blob})


def is_subject_general(candidate: "MarketplaceCandidate") -> bool:
    return bool(offering_generalist_markers(candidate))


def _field_verbs(text: str) -> list[str]:
    present = set(_words(text))
    return [stem for stem, forms in TASK_VERB_FORMS.items() if present & forms]


def _field_snippet(text: str, needle: str, width: int = 64) -> str:
    lowered = str(text or "").lower()
    hit = lowered.find(str(needle or "").lower())
    if hit < 0:
        return str(text or "")[:width]
    start = max(0, hit - width // 2)
    return str(text or "")[start:start + width].strip()


def offering_task_evidence(candidate: MarketplaceCandidate) -> list[dict[str, str]]:
    """Task verbs evidenced by the OFFERING's own fields, with provenance.

    Agent name/description are deliberately excluded: they are context, not
    proof that this specific offering performs the task.
    """
    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for source, text in (("offering_name", candidate.offering_name or ""),
                         ("offering_description", candidate.offering_description),
                         ("deliverable", candidate.deliverable_desc)):
        for stem in _field_verbs(text):
            if stem not in seen:
                seen.add(stem)
                evidence.append({"capability": stem, "source": source,
                                 "text": _field_snippet(text, stem)})
    return evidence


def candidate_task_verbs(candidate: MarketplaceCandidate) -> list[str]:
    """Backwards-compatible verb list (offering-level only)."""
    return [item["capability"] for item in offering_task_evidence(candidate)]


def offering_subject_evidence(candidate: MarketplaceCandidate,
                              query: CapabilityQuery) -> list[dict[str, str]]:
    """Subject terms evidenced by the OFFERING's own fields, with provenance."""
    evidence: list[dict[str, str]] = []
    for source, text in (("offering_name", candidate.offering_name or ""),
                         ("offering_description", candidate.offering_description),
                         ("deliverable", candidate.deliverable_desc)):
        tokens = set(_tokens(text))
        for term in query.subject_terms:
            if term in tokens:
                evidence.append({"term": term, "source": source,
                                 "text": _field_snippet(text, term)})
    return evidence


def subject_overlap(candidate: MarketplaceCandidate, query: CapabilityQuery) -> int:
    """Subject overlap counted on OFFERING-level fields only."""
    return len({item["term"] for item in offering_subject_evidence(candidate, query)})


def semantic_overlap(candidate: MarketplaceCandidate, query: CapabilityQuery) -> int:
    """Backwards-compatible alias: offering-level subject overlap."""
    return subject_overlap(candidate, query)


def check_task_fit(candidate: MarketplaceCandidate,
                   query: CapabilityQuery) -> tuple[bool, str, list[dict[str, str]]]:
    """Hard task-capability gate on OFFERING-level evidence only.

    Agent name/description alone can never satisfy this gate: automatic
    hiring selects a compatible offering, not a generally capable agent.
    Returns (compatible, reason, evidence-with-provenance).
    """
    offered = offering_task_evidence(candidate)
    offered_stems = [item["capability"] for item in offered]
    req_verbs = [verb for verb in query.task_capabilities if verb in RESEARCH_TASK_VERBS]
    monitoring_requested = any(verb in MONITOR_TASK_VERBS for verb in query.task_capabilities)
    if req_verbs and (_expand_verbs(req_verbs) & _expand_verbs(offered_stems)):
        evidence = [item for item in offered if item["capability"] in _expand_verbs(req_verbs)]
        return True, "offering evidences the requested task action", evidence
    if monitoring_requested:
        if any(verb in offered_stems for verb in MONITOR_TASK_VERBS):
            evidence = [item for item in offered if item["capability"] in MONITOR_TASK_VERBS]
            return True, "offering evidences the requested monitoring action", evidence
        name_blob = f"{candidate.offering_name or ''}".lower()
        hits = [noun for noun in MONITOR_FAMILY_NOUNS if noun in name_blob]
        if hits:
            return True, "offering is explicitly a monitoring/tracking product", [
                {"capability": noun, "source": "offering_name",
                 "text": _field_snippet(candidate.offering_name or "", noun)}
                for noun in hits]
    return False, "offering shows no evidence it performs the requested task", []


def check_compatibility(candidate: MarketplaceCandidate,
                        query: CapabilityQuery,
                        contract: Contract, spec: JobSpec) -> tuple[bool, str]:
    """Hard compatibility gate. Returns (compatible, reason)."""
    if candidate.agent_hidden:
        return False, "agent is hidden on the registry"
    if candidate.offering_hidden or candidate.offering_private:
        return False, "offering is hidden or private"
    if not candidate.offering_name:
        return False, "offering has no name to create a job from"
    if candidate.required_funds:
        return False, "offering requires fund-transfer flow not yet supported by PRIOR"
    if not candidate.chain_ids:
        return False, "offering reports no chain information for the execution path"
    if SUPPORTED_CHAIN_ID not in candidate.chain_ids:
        return False, "offering is not usable on PRIOR's supported chain path"
    from prior.job_spec import missing_review_artifact

    missing = missing_review_artifact(spec.raw or "")
    if missing:
        return False, (
            f"request expects a review target (this {missing}) but none was "
            "provided; no provider can perform an empty-reference review")
    if _request_wants_source_code_review(spec, query) \
            and not _offering_has_code_capability(candidate):
        return False, (
            "offering shows no source-code review capability for a "
            "source-code review request")
    from prior.job_spec import transaction_review_request

    if transaction_review_request(spec.raw or "") \
            and _offering_is_code_only_auditor(candidate):
        return False, (
            "offering is a source-code-only auditor with no declared "
            "transaction/wallet/approval review capability for a "
            "transaction-review request")
    task_ok, task_reason, evidence = check_task_fit(candidate, query)
    if not task_ok:
        return False, task_reason
    subject_hits = offering_subject_evidence(candidate, query)
    if query.subject_terms and not subject_hits and not is_subject_general(candidate):
        return False, "offering shows no subject relevance to the requested job"
    try:
        preview, notes = build_requirement_data(candidate, query, contract, spec)
    except (SchemaError, ValueError) as exc:
        return False, str(exc)
    candidate.task_evidence = evidence
    candidate.subject_evidence = subject_hits
    candidate.requirement_data_preview = preview
    candidate.schema_notes = notes
    return True, "compatible"


# ---------------------------------------------------------------------------
# Candidate-specific requirementData: the exact input that WOULD be sent.
# ---------------------------------------------------------------------------

def _brief_text(query: CapabilityQuery, contract: Contract, spec: JobSpec) -> str:
    return requirement_payload(contract, spec)["job_description"]


def build_requirement_data(candidate: MarketplaceCandidate, query: CapabilityQuery,
                           contract: Contract, spec: JobSpec) -> tuple[dict[str, Any], list[str]]:
    """Construct and locally validate the offering-shaped requirementData.

    The full improved brief (task plus learned clauses) is placed into a
    real schema field capable of carrying natural language. Optional fields
    are filled only from schema-declared defaults, never invented. Raises
    SchemaError/ValueError when no legitimate transmission exists.
    """
    raw_schema = candidate.requirements_schema
    if raw_schema is None or raw_schema == "" or raw_schema == {}:
        return requirement_payload(contract, spec), [
            "schemaless offering: full brief travels as the raw requirement message"]
    try:
        schema = _resolve_refs(_parse_schema(raw_schema), _parse_schema(raw_schema))
    except SchemaError:
        raise
    if not isinstance(schema, dict):
        raise SchemaError("offering requirement schema could not be safely interpreted")
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise SchemaError("offering requirement schema could not be safely interpreted")
    properties = properties or {}
    brief = _brief_text(query, contract, spec)
    data: dict[str, Any] = {}
    notes: list[str] = []
    slot: str | None = None
    for name, subschema in properties.items():
        if not isinstance(subschema, dict):
            continue
        if _norm_name(name) in BRIEF_SLOTS and _accepts_text(subschema):
            slot = name
            break
    if slot is None:
        raise ValueError(
            "offering input schema has no field for the task brief; "
            "PRIOR would have to discard the brief and memory")
    data[slot] = brief
    notes.append(f"task brief placed in schema field '{slot}'")
    for name, subschema in properties.items():
        if name in data or not isinstance(subschema, dict):
            continue
        if "default" in subschema:
            candidate_value = subschema["default"]
            problems = validate_against_schema(candidate_value, subschema, name)
            if not problems:
                data[name] = candidate_value
                notes.append(f"optional field '{name}' filled from schema default")
    for name in schema_required_fields(schema):
        if name not in data:
            if _norm_name(name) in BRIEF_SLOTS:
                data[name] = brief
                notes.append(f"required field '{name}' carries the task brief")
            else:
                raise ValueError(
                    f"offering requires fields PRIOR cannot supply: {name}")
    problems = validate_against_schema(data, schema)
    if problems:
        raise ValueError(
            "constructed requirement input fails the offering schema: " + "; ".join(problems[:4]))
    return data, notes


def _accepts_text(subschema: dict[str, Any]) -> bool:
    kind = subschema.get("type")
    if kind is None:
        return True
    kinds = [kind] if isinstance(kind, str) else list(kind)
    return "string" in kinds


# ---------------------------------------------------------------------------
# Ranker: runs ONLY over hard-compatible candidates. Deterministic,
# documented weights, no invented signals.
# ---------------------------------------------------------------------------

# Documented scoring weights. The registry does not return per-agent success
# counts, success rates, or buyer counts on browse results, so the ranker
# does NOT use them. Rating/recency/price/SLA are secondary signals applied
# strictly after hard compatibility gates.
WEIGHT_TASK_HIT = 4.0
WEIGHT_SUBJECT_OVERLAP = 2.0
BONUS_OFFERING_NAME_TERM = 2.0
WEIGHT_RATING = 1.0
BONUS_ACTIVE_7D = 1.0
BONUS_ACTIVE_30D = 0.5


def _recency_bonus(last_active_at: str) -> tuple[float, str]:
    if not last_active_at:
        return 0.0, "no activity timestamp"
    try:
        stamp = str(last_active_at).strip()
        if stamp.endswith("Z"):
            stamp = stamp[:-1] + "+00:00"
        seen = datetime.fromisoformat(stamp)
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if seen - now > timedelta(hours=48):
            return 0.0, "suspicious future timestamp, ignored"
        age = now - seen
        if age <= timedelta(days=7):
            return BONUS_ACTIVE_7D, "active within 7 days"
        if age <= timedelta(days=30):
            return BONUS_ACTIVE_30D, "active within 30 days"
        return 0.0, "inactive over 30 days"
    except ValueError:
        return 0.0, "unparseable activity timestamp"


def score_candidate(candidate: MarketplaceCandidate,
                    query: CapabilityQuery) -> tuple[float, dict[str, Any]]:
    """Deterministic score plus a human-readable breakdown.

    Scores offering-level evidence only. Agent name/description are display
    context and tie-break material (wallet address), never score inputs.
    """
    if candidate.task_evidence:
        task_hits = len(candidate.task_evidence)
    else:
        task_hits = len([verb for verb in query.task_capabilities
                         if verb in candidate_task_verbs(candidate)])
    overlap = subject_overlap(candidate, query)
    offering_terms = set(_tokens(candidate.offering_name or ""))
    name_hit = any(term in offering_terms for term in query.subject_terms)
    rating_value = candidate.rating if candidate.rating is not None else 0.0
    recency, recency_note = _recency_bonus(candidate.last_active_at)
    score = (task_hits * WEIGHT_TASK_HIT
             + overlap * WEIGHT_SUBJECT_OVERLAP
             + (BONUS_OFFERING_NAME_TERM if name_hit else 0.0)
             + rating_value * WEIGHT_RATING
             + recency)
    breakdown = {
        "task_hits": task_hits,
        "task_evidence": [dict(item) for item in candidate.task_evidence] or None,
        "subject_overlap": overlap,
        "subject_evidence": [dict(item) for item in candidate.subject_evidence] or None,
        "offering_name_term_hit": name_hit,
        "rating": candidate.rating,
        "recency_note": recency_note,
        "score": round(score, 3),
    }
    # Backwards-compatible key for earlier evidence readers.
    breakdown["semantic_overlap"] = overlap
    return score, breakdown


def _price_within_cap(candidate: "MarketplaceCandidate", cap: float) -> bool:
    """Price gate applied AFTER semantic compatibility: a candidate that is
    not fixed/USDC-priced, or priced above the public per-job ceiling, can
    never be selected no matter how it ranks. Cheapness never rescues an
    incompatible worker (compatibility already filtered those out)."""
    if str(candidate.price_type or "") != "fixed":
        return False
    value = candidate.price_value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= float(value) <= cap


def _price_text(candidate: "MarketplaceCandidate") -> str:
    value = candidate.price_value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "an unpriced amount"
    return f"{float(value):g}"


def rank_candidates(candidates: list[MarketplaceCandidate],
                    query: CapabilityQuery) -> list[tuple[MarketplaceCandidate, float, dict[str, Any]]]:
    """Rank highest first. Ties break by lower price, then wallet address.

    Fully deterministic: identical input always yields identical order, and
    no currently-known provider receives any preference.
    """
    scored = [(candidate, *score_candidate(candidate, query)) for candidate in candidates]
    scored.sort(key=lambda item: (
        -item[1],
        item[0].price_value if item[0].price_value is not None else float("inf"),
        item[0].wallet_address,
    ))
    return scored


# ---------------------------------------------------------------------------
# Requirement payload preview: exact executable input plus PRIOR context.
# ---------------------------------------------------------------------------

def build_provider_payload(candidate: MarketplaceCandidate, contract: Contract,
                           spec: JobSpec) -> dict[str, Any]:
    """Outgoing payload preview for the selected provider.

    ``requirement_data`` is the exact candidate-shaped input that WOULD be
    supplied to the official job-creation helper (schema-validated). The
    full improved brief, including every applied learned requirement, lives
    inside it, and ``prior_context`` separately preserves the task, the
    full contract, and the learned requirements. Memory stays
    provider-independent: the same contract produces the same clauses for
    any selected provider.
    """
    query = build_capability_query(spec, contract)
    requirement_data = candidate.requirement_data_preview
    if requirement_data is None:
        preview, _ = build_requirement_data(candidate, query, contract, spec)
        requirement_data = preview
    learned = [lesson.requirement for lesson in contract.applied_lessons]
    return {
        "requirement_data": requirement_data,
        "learned_requirements": learned,
        "prior_context": {
            "goal": contract.goal,
            "title": contract.title,
            "deliverables": list(contract.deliverables),
            "acceptance": list(contract.acceptance),
            "applied_lessons": [lesson.to_dict() for lesson in contract.applied_lessons],
            "raw": spec.raw,
        },
        "selected_offering": {
            "agent_name": candidate.agent_name,
            "offering_name": candidate.offering_name,
            "provider_wallet": candidate.wallet_address,
        },
    }


# ---------------------------------------------------------------------------
# Selection: live discovery plus deterministic choice, or truthful no-match.
# ---------------------------------------------------------------------------

@dataclass
class MarketplaceSelection:
    candidate: MarketplaceCandidate
    score: float
    score_breakdown: dict[str, Any]
    requirement_preview: dict[str, Any]
    query: CapabilityQuery
    compatible_total: int
    agents_seen: int
    rejections: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self, *, redact_wallets: bool = False) -> dict[str, Any]:
        candidate = self.candidate.to_dict()
        if redact_wallets and candidate.get("wallet_address"):
            wallet = candidate["wallet_address"]
            candidate["wallet_address"] = wallet[:6] + "..." + wallet[-4:] if len(wallet) > 10 else "..."
        preview = dict(self.requirement_preview)
        selected = dict(preview.get("selected_offering") or {})
        if redact_wallets and selected.get("provider_wallet"):
            wallet = selected["provider_wallet"]
            selected["provider_wallet"] = wallet[:6] + "..." + wallet[-4:] if len(wallet) > 10 else "..."
            preview["selected_offering"] = selected
        return {
            "candidate": candidate,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "requirement_preview": preview,
            "query": self.query.to_dict(),
            "compatible_total": self.compatible_total,
            "agents_seen": self.agents_seen,
            "rejections": [{"candidate": label, "reason": reason} for label, reason in self.rejections],
        }


def discover_live(keyword: str, *, top_k: int = 25,
                  extra_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """READ-ONLY live marketplace lookup. Never creates, funds, or hires.

    Automatic selection requests ONLINE providers (exact ``isOnline`` /
    ``OnlineStatus`` naming from the installed SDK source).
    """
    from prior.providers.virtuals import _bridge

    params: dict[str, Any] = {"isOnline": "online"}
    if extra_params:
        params.update(extra_params)
    args = ["discover", keyword or "research", str(top_k)]
    args.append(__import__("json").dumps(params))
    try:
        raw = _bridge(args)
    except ProviderError as exc:
        raise DiscoveryError(f"Live marketplace discovery failed: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("ok") is not True:
        raise DiscoveryError("Live marketplace discovery failed: unexpected bridge response.")
    agents = raw.get("agents")
    if not isinstance(agents, list):
        raise DiscoveryError("Live marketplace discovery failed: malformed agents list.")
    return agents


def merge_agent_lists(lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge per-query agent lists, deduplicated by wallet address.

    Offerings merge by offering name; scalar agent fields keep the first
    seen value. Deterministic: first-seen query order wins ties. No single
    top-N slice can hide a relevant provider behind another query's slice.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for agents in lists:
        if not isinstance(agents, list):
            continue
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            wallet = str(agent.get("walletAddress") or "").strip().lower()
            if not wallet:
                continue
            if wallet not in merged:
                merged[wallet] = dict(agent)
                merged[wallet]["offerings"] = []
                order.append(wallet)
            seen_offerings = {str(o.get("name")) for o in merged[wallet]["offerings"]
                              if isinstance(o, dict)}
            for offering in agent.get("offerings") or []:
                if not isinstance(offering, dict):
                    continue
                if str(offering.get("name")) not in seen_offerings:
                    merged[wallet]["offerings"].append(offering)
                    seen_offerings.add(str(offering.get("name")))
    return [merged[wallet] for wallet in order]


def select_provider_for_spec(spec: JobSpec, contract: Contract,
                             *, discover: Callable[[str], list[dict[str, Any]]] | None = None,
                             top_k: int = 25) -> MarketplaceSelection:
    """Discover live providers and deterministically select one.

    ``discover`` is injectable for tests (fixture marketplace data). The
    default performs a real read-only registry lookup. Raises
    NoCompatibleProvider when nothing genuinely fits: callers must surface
    that truthfully instead of falling back to a fixed seller.
    """
    query = build_capability_query(spec, contract)
    lookup = discover or (lambda keyword: discover_live(keyword, top_k=top_k))
    raw_lists: list[list[dict[str, Any]]] = []
    try:
        for keyword in query.discovery_queries or [query.primary_keyword]:
            raw_list = lookup(keyword)
            if not isinstance(raw_list, list):
                raise DiscoveryError(
                    "Live marketplace discovery failed: malformed agents list.")
            raw_lists.append(raw_list)
    except NoCompatibleProvider:
        raise
    except MarketplaceError:
        raise
    except Exception as exc:  # noqa: BLE001 - discovery must fail explicitly
        raise DiscoveryError(f"Live marketplace discovery failed: {exc}") from exc
    merged_agents = merge_agent_lists(raw_lists)
    candidates, agents_seen, skipped = normalize_agents(merged_agents)
    compatible: list[MarketplaceCandidate] = []
    rejections: list[tuple[str, str]] = []
    for candidate in candidates:
        ok, reason = check_compatibility(candidate, query, contract, spec)
        if ok:
            compatible.append(candidate)
        else:
            rejections.append((candidate.label, reason))
    if skipped:
        rejections.append((f"{skipped} malformed or offering-less entries", "skipped, never repaired"))
    if not compatible:
        raise NoCompatibleProvider(
            "No compatible Virtuals agent was found for this job.",
            query=query, candidates_seen=agents_seen, rejections=rejections,
        )
    ranked = rank_candidates(compatible, query)
    try:
        from prior import settings as settings_mod

        price_cap = settings_mod.public_max_job_usdc()
    except ValueError as exc:
        raise NoCompatibleProvider(
            f"PRIOR public price policy is misconfigured ({exc}); nothing "
            "was hired and no funds were spent.",
            query=query, candidates_seen=agents_seen, rejections=rejections,
        ) from exc
    within_cap = [item for item in ranked if _price_within_cap(item[0], price_cap)]
    if not within_cap:
        best, _, _ = ranked[0]
        price_text = _price_text(best)
        raise NoCompatibleProvider(
            f"This worker costs {price_text} USDC. PRIOR's public safety limit "
            f"is {price_cap:g} USDC per job, so nothing was hired and no funds "
            "were spent. Try another available agent.",
            query=query, candidates_seen=agents_seen, rejections=rejections,
        )
    winner, score, breakdown = within_cap[0]
    return MarketplaceSelection(
        candidate=winner,
        score=round(score, 3),
        score_breakdown=breakdown,
        requirement_preview=build_provider_payload(winner, contract, spec),
        query=query,
        compatible_total=len(compatible),
        agents_seen=agents_seen,
        rejections=rejections,
    )
