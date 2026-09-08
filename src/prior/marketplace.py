"""Live Virtuals ACP marketplace discovery and provider selection (READ-ONLY).

Boundary: this module searches the live Virtuals registry, normalizes real
agents and real offerings, filters incompatible ones, ranks the rest
deterministically, and builds the exact requirement payload that WOULD be
sent to the selected provider. It never creates an ACP job, never funds,
and never falls back to a fixed seller disguised as discovery.

Read-only gate: no function here calls create-job, fund, complete, or
reject. The only bridge command used is ``discover`` (browseAgents).
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
# Capability query: derived ONLY from the user's request and PRIOR contract.
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "the a an and or of to in on for with by from that this these those "
    "what which who whom whose when where how why not no yes our your their "
    "its his her him her them they are was were been being have has had do "
    "does did will would can could should shall may might must about into "
    "over under again once here there all any both each few more most other "
    "some such only own same than too very just also compare compared versus "
    "research top best leading list get give show tell find include using use "
    "used make made need needs needed please".split()
)


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in str(text or "").lower().replace("_", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) >= 3 and word not in _STOPWORDS and word not in out:
            out.append(word)
    return out


@dataclass
class CapabilityQuery:
    """Marketplace search intent derived from a PRIOR job, nothing invented."""

    primary_keyword: str
    required_terms: list[str] = field(default_factory=list)
    useful_terms: list[str] = field(default_factory=list)
    job_type: str = "research"
    deliverable_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_keyword": self.primary_keyword,
            "required_terms": list(self.required_terms),
            "useful_terms": list(self.useful_terms),
            "job_type": self.job_type,
            "deliverable_hints": list(self.deliverable_hints),
        }


def build_capability_query(spec: JobSpec, contract: Contract | None = None) -> CapabilityQuery:
    """Derive marketplace search terms from the request, spec, and contract.

    Every term comes from user text or PRIOR-derived fields. Nothing is
    invented: no capability is added that the request does not imply.
    """
    required: list[str] = []
    for token in _tokens(spec.subject) + _tokens(spec.domain) + _tokens(" ".join(spec.keywords or [])):
        if token not in required:
            required.append(token)
    useful: list[str] = []
    pools = list(spec.deliverables or []) + list(spec.explicit_requirements or [])
    if contract is not None:
        pools += list(contract.acceptance or [])
        pools += [lesson.requirement for lesson in (contract.applied_lessons or [])]
    for token in _tokens(" ".join(pools)):
        if token not in required and token not in useful:
            useful.append(token)
    primary = (spec.domain or spec.subject or "research").strip().lower()
    if not primary:
        primary = "research"
    return CapabilityQuery(
        primary_keyword=primary,
        required_terms=required[:12],
        useful_terms=useful[:16],
        job_type=spec.job_type or "research",
        deliverable_hints=list(spec.deliverables or [])[:8],
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
                if cid is not None:
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
# Compatibility filter: hard constraints only.
# ---------------------------------------------------------------------------

def requirement_supply_keys() -> set[str]:
    """Keys PRIOR's outgoing requirement payload can always supply."""
    return {
        "goal", "title", "deliverables", "acceptance", "applied_lessons",
        "learned_requirements", "raw", "subject", "domain",
        "time_sensitive", "job_type", "count", "keywords",
        "explicit_requirements", "job_description",
    }


def schema_required_fields(schema: Any) -> list[str]:
    """Required input fields of an offering requirements schema.

    Handles dict JSON-schema, JSON-encoded strings, and absent schemas.
    A schema that cannot be understood conservatively yields no required
    fields here; semantic fit is judged separately.
    """
    if schema is None or schema == "":
        return []
    if isinstance(schema, str):
        text = schema.strip()
        if not text:
            return []
        try:
            import json as _json
            parsed = _json.loads(text)
        except ValueError:
            return []
        return schema_required_fields(parsed)
    if isinstance(schema, dict):
        required = schema.get("required")
        if isinstance(required, list):
            return [str(item) for item in required if str(item).strip()]
        return []
    return []


def candidate_text(candidate: MarketplaceCandidate) -> str:
    return " ".join([
        candidate.offering_name or "",
        candidate.offering_description,
        candidate.agent_name,
        candidate.agent_description,
    ])


def semantic_overlap(candidate: MarketplaceCandidate, query: CapabilityQuery) -> int:
    text_tokens = set(_tokens(candidate_text(candidate)))
    return len([term for term in query.required_terms if term in text_tokens])


def check_compatibility(candidate: MarketplaceCandidate,
                        query: CapabilityQuery) -> tuple[bool, str]:
    """Hard compatibility gate. Returns (compatible, reason)."""
    if candidate.agent_hidden:
        return False, "agent is hidden on the registry"
    if candidate.offering_hidden or candidate.offering_private:
        return False, "offering is hidden or private"
    if not candidate.offering_name:
        return False, "offering has no name to create a job from"
    missing = [key for key in schema_required_fields(candidate.requirements_schema)
               if key not in requirement_supply_keys()]
    if missing:
        return False, f"offering requires fields PRIOR cannot supply: {', '.join(missing)}"
    if semantic_overlap(candidate, query) < 1 and query.required_terms:
        return False, "no capability overlap with the requested job"
    return True, "compatible"


# ---------------------------------------------------------------------------
# Ranker: deterministic, documented weights, no invented signals.
# ---------------------------------------------------------------------------

# Documented scoring weights. The registry does not return per-agent success
# counts, success rates, or buyer counts on AcpAgentDetail, so the ranker
# does NOT use them. Server-side ordering (AgentSort) can be requested at
# browse time instead; ranking here uses only fields actually returned.
WEIGHT_SEMANTIC_OVERLAP = 3.0
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
        age = datetime.now(timezone.utc) - seen
        if age <= timedelta(days=7):
            return BONUS_ACTIVE_7D, "active within 7 days"
        if age <= timedelta(days=30):
            return BONUS_ACTIVE_30D, "active within 30 days"
        return 0.0, "inactive over 30 days"
    except ValueError:
        return 0.0, "unparseable activity timestamp"


def score_candidate(candidate: MarketplaceCandidate,
                    query: CapabilityQuery) -> tuple[float, dict[str, Any]]:
    """Deterministic score plus a human-readable breakdown."""
    overlap = semantic_overlap(candidate, query)
    offering_terms = set(_tokens(candidate.offering_name or ""))
    name_hit = any(term in offering_terms for term in query.required_terms)
    rating_value = candidate.rating if candidate.rating is not None else 0.0
    recency, recency_note = _recency_bonus(candidate.last_active_at)
    score = (overlap * WEIGHT_SEMANTIC_OVERLAP
             + (BONUS_OFFERING_NAME_TERM if name_hit else 0.0)
             + rating_value * WEIGHT_RATING
             + recency)
    breakdown = {
        "semantic_overlap": overlap,
        "offering_name_term_hit": name_hit,
        "rating": candidate.rating,
        "recency_note": recency_note,
        "score": round(score, 3),
    }
    return score, breakdown


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
# Requirement payload: the exact payload that WOULD be sent.
# ---------------------------------------------------------------------------

def build_provider_payload(candidate: MarketplaceCandidate, contract: Contract,
                           spec: JobSpec) -> dict[str, Any]:
    """Outgoing payload for the selected provider.

    Wraps the standard PRIOR requirement payload (which already carries
    every applied learned requirement) with the selected offering context.
    Memory stays provider-independent: the same contract produces the same
    learned_requirements for any selected provider.
    """
    payload = requirement_payload(contract, spec)
    payload["selected_offering"] = {
        "agent_name": candidate.agent_name,
        "offering_name": candidate.offering_name,
        "provider_wallet": candidate.wallet_address,
    }
    return payload


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
    """READ-ONLY live marketplace lookup. Never creates, funds, or hires."""
    from prior.providers.virtuals import _bridge

    args = ["discover", keyword or "research", str(top_k)]
    if extra_params:
        import json as _json
        args.append(_json.dumps(extra_params))
    try:
        raw = _bridge(args)
    except ProviderError as exc:
        raise DiscoveryError(f"Live marketplace discovery failed: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("ok") is not True:
        raise DiscoveryError(f"Live marketplace discovery failed: unexpected bridge response.")
    agents = raw.get("agents")
    if not isinstance(agents, list):
        raise DiscoveryError("Live marketplace discovery failed: malformed agents list.")
    return agents


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
    try:
        raw_agents = lookup(query.primary_keyword)
    except NoCompatibleProvider:
        raise
    except MarketplaceError:
        raise
    except Exception as exc:  # noqa: BLE001 - discovery must fail explicitly
        raise DiscoveryError(f"Live marketplace discovery failed: {exc}") from exc
    if not isinstance(raw_agents, list):
        raise DiscoveryError("Live marketplace discovery failed: malformed agents list.")
    candidates, agents_seen, skipped = normalize_agents(raw_agents)
    compatible: list[MarketplaceCandidate] = []
    rejections: list[tuple[str, str]] = []
    for candidate in candidates:
        ok, reason = check_compatibility(candidate, query)
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
    winner, score, breakdown = ranked[0]
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
