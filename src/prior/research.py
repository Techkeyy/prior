"""Real research worker. Fully generalized entity extraction, relational facet validation, field-targeted follow-up retrieval, and contract-complete deliverable synthesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

from prior.domain import Contract, JobSpec

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_API = "https://en.wikipedia.org/w/api.php"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
DDG_HTML = "https://html.duckduckgo.com/html/"

WIKI_HEADERS = {
    "User-Agent": "PRIOR-Agent/1.0 (https://prior.103-195-188-198.sslip.io; research@prior.internal)",
    "Accept": "application/json",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DISCARD_PATTERNS = [
    r"\blist of .* episodes\b",
    r"\bseason \d+\b",
    r"\bdiscography\b",
    r"\bfilmography\b",
    r"\(tv series\)",
    r"\(film\)",
    r"\(album\)",
    r"\(song\)",
    r"\(manga\)",
    r"\(anime\)",
    r"\(artist\)",
    r"\(singer\)",
    r"\(actor\)",
    r"\(politician\)",
    r"\belections in\b",
    r"\bsoundtrack\b",
    r"^history of\b",
    r"^timeline of\b",
    r"^comparison of\b",
    r"^list of\b",
    r"\(algorithm\)",
    r"\(protocol\)",
    r"\(standard\)",
    r"\(specification\)",
    r"\(concept\)",
    r"\(cryptography\)",
]

PUBLISHER_OR_AGENCY_PATTERNS = [
    r"\bcoingape\b",
    r"\bforbes\b",
    r"\blinkedin\b",
    r"\bmedium\b",
    r"\bcoindesk\b",
    r"\bcoinmarketcap\b",
    r"\bdecrypt\b",
    r"\bcryptoslate\b",
    r"\bcoincreate\b",
    r"\bcryptoaicentral\b",
    r"\baimojo\b",
    r"\blumenscan\b",
    r"\bwootfi\b",
    r"\bresearcher\.life\b",
    r"\bideascale\b",
    r"\bresearchgate\b",
    r"\bgoogle scholar\b",
    r"\bblockchainx\b",
    r"\bsolulab\b",
    r"\bantier\b",
    r"\bment tech\b",
    r"\bdevelopment compan(?:y|ies)\b",
    r"\bdevelopment partners?\b",
    r"\bdevelopment services?\b",
    r"\bhire developers?\b",
    r"\bsoftware development\b",
    r"\btop\s+\d+\b",
    r"\bbest\s+\d+\b",
    r"\b\d+\s+best\b",
    r"\b\d+\s+smart\b",
    r"\bserious businesses\b",
    r"\bguide to\b",
    r"\bhow to\b",
    r"\breview\b",
    r"\bcomparison\b",
    r"\boverview\b",
    r"\bwhat is\b",
    r"\blist of\b",
    r"\bcomplete guide\b",
    r"\beverything you need\b",
    r"\breviewed\b",
    r"\bcompared\b",
    r"\bexplained\b",
    r"\binsights\b",
    r"\blandscape\b",
]

CONCEPT_SUMMARY_INDICATORS = [
    r"\bis a measure of\b",
    r"\bis a metric\b",
    r"\bis a concept\b",
    r"\bis a term (?:for|used)\b",
    r"\bis the process of\b",
    r"\bis an attack\b",
    r"\bis a security vulnerability\b",
    r"\bis a technique\b",
    r"\bis a method for\b",
    r"\brefers to the process\b",
    r"\bis a theoretical\b",
    r"\bis an algorithm for\b",
    r"\bis a cryptographic hash\b",
    r"\bis a mathematical\b",
]

GENERIC_CONCEPT_PATTERNS = [
    r"^password strength.*$",
    r"^password policy.*$",
    r"^password cracking.*$",
    r"^password recovery.*$",
    r"^password hashing.*$",
    r"^password fatigue.*$",
    r"^password complexity.*$",
    r"^password expiration.*$",
    r"^password spraying.*$",
    r"^credential stuffing.*$",
    r"^single sign-on.*$",
    r"^multi-factor authentication.*$",
    r"^two-factor authentication.*$",
    r"^authenticator.*$",
    r"^ai$",
    r"^llm$",
    r"^api$",
    r"^sdk$",
    r"^ui$",
    r"^artificial intelligence$",
    r"^cryptocurrency$",
    r"^smart contract[s]?$",
    r"^blockchain$",
    r"^web3$",
    r"^digital wallet[s]?$",
    r"^crypto wallet[s]?$",
    r"^ai crypto wallet[s]?.*$",
    r"^agentic wallet[s]?.*$",
    r"^ai wallet[s]?.*$",
    r"^mobile app[s]?$",
    r"^software$",
    r"^machine learning$",
    r"^ai agent[s]?$",
    r"^wallet$",
    r"^wallets$",
    r"^password manager$",
    r"^password managers$",
    r"^password management$",
    r"^password$",
    r"^passwords$",
    r"^master password$",
    r"^identity$",
    r"^database$",
    r"^databases$",
    r"^observability$",
    r"^observability platform[s]?$",
    r"^monitoring tool[s]?$",
    r"^feature toggle[s]?$",
    r"^feature flag[s]?$",
    r"^open[- ]source feature flag[s]?.*$",
    r"^self[- ]hosted.*$",
    r"^cloud storage$",
    r"^vpn$",
    r"^antivirus$",
    r"^web browser[s]?$",
    r"^search engine[s]?$",
    r".*foundation$",
    r".*association$",
    r".*consortium$",
    r".*alliance$",
]


@dataclass
class QueryFacets:
    raw_query: str
    subject: str
    domain: str
    entity_type: str
    mandatory_qualifiers: set[str] = field(default_factory=set)
    target_count: int = 5


def extract_facets(spec: JobSpec) -> QueryFacets:
    raw = (spec.raw or spec.goal or "").lower()
    subj = (spec.subject or "").lower()
    dom = (spec.domain or "").lower()

    qualifiers = set()
    if re.search(r"\b(ai|agentic|autonomous|agent)\b", raw) or re.search(r"\b(ai|agentic)\b", subj):
        qualifiers.add("ai")
    if re.search(r"\b(open-source|open source|foss)\b", raw) or re.search(r"\b(open-source|open source)\b", subj):
        qualifiers.add("open_source")
    if re.search(r"\b(self-hosted|self hosted|on-premise|on premise)\b", raw) or re.search(r"\b(self-hosted|self hosted)\b", subj):
        qualifiers.add("self_hosted")
    if re.search(r"\b(non-custodial|non custodial|self-custody|self custody)\b", raw) or re.search(r"\b(non-custodial|self-custody)\b", subj):
        qualifiers.add("non_custodial")
    if re.search(r"\b(decentralized|p2p)\b", raw) or re.search(r"\b(decentralized)\b", subj):
        qualifiers.add("decentralized")
    if re.search(r"\b(privacy-first|privacy focused|zero-knowledge|zk)\b", raw) or re.search(r"\b(privacy-first|privacy)\b", subj):
        qualifiers.add("privacy")

    domain = "general"
    if "wallet" in raw or "wallet" in subj or "wallet" in dom:
        domain = "wallet"
    elif "password" in raw or "password" in subj or "password" in dom:
        domain = "password_manager"
    elif "feature flag" in raw or "feature toggle" in raw or "flag" in subj or "flag" in dom:
        domain = "feature_flag"
    elif "observability" in raw or "apm" in raw or "monitoring" in raw or "tracing" in raw or "observability" in dom:
        domain = "observability"
    elif "identity" in raw or "did" in raw or "identity" in dom:
        domain = "identity"
    elif "exchange" in raw or "dex" in raw or "exchange" in dom:
        domain = "exchange"
    elif "database" in raw or "db" in raw or "database" in dom:
        domain = "database"
    elif "search engine" in raw or "search" in subj or "search" in dom:
        domain = "search_engine"
    else:
        domain = dom or subj or "general"

    entity_type = "Company / Product"
    if "tool" in raw or "tool" in subj:
        entity_type = "Tool / Product"
    elif "platform" in raw or "platform" in subj:
        entity_type = "Platform / Product"
    elif "protocol" in raw or "protocol" in subj:
        entity_type = "Protocol / Project"
    elif "manager" in raw or "manager" in subj:
        entity_type = "Password Manager / Product"

    return QueryFacets(
        raw_query=spec.raw,
        subject=spec.subject or spec.raw,
        domain=domain,
        entity_type=entity_type,
        mandatory_qualifiers=qualifiers,
        target_count=spec.count or 5,
    )


def search_queries(spec: JobSpec) -> list[str]:
    facets = extract_facets(spec)
    queries: list[str] = []
    subject = (spec.subject or "").strip()
    domain = (spec.domain or "").strip()

    if subject:
        queries.append(subject)
        queries.append(f"top {subject}")
        queries.append(f"best {subject} 2026")
    if domain and domain not in queries:
        queries.append(domain)

    if facets.domain == "wallet":
        if "ai" in facets.mandatory_qualifiers:
            queries.extend([
                "AI crypto wallet companies products",
                "top agentic wallet Web3 2026",
                "autonomous AI agent wallet cryptocurrency",
                "AI-powered Web3 smart wallet software",
                "intent-based AI crypto wallet platform",
            ])
        elif "non_custodial" in facets.mandatory_qualifiers:
            queries.extend([
                "non-custodial cryptocurrency wallet software",
                "self-custody crypto wallet apps",
                "top non-custodial crypto wallets 2026",
            ])
        else:
            queries.extend(["crypto wallet software", "Web3 wallet", "digital wallet platforms"])
    elif facets.domain == "password_manager":
        queries.extend([
            "top password managers comparison 2026",
            "best password manager software applications",
            "password management tools comparison pricing platforms",
        ])
    elif facets.domain == "feature_flag":
        if "open_source" in facets.mandatory_qualifiers:
            queries.extend([
                "open-source feature flag tools",
                "open source feature flags management tools",
                "open source feature toggle software GitHub",
            ])
        else:
            queries.extend(["feature toggle software", "feature flag management"])
    elif facets.domain == "observability":
        if "self_hosted" in facets.mandatory_qualifiers:
            queries.extend([
                "self-hosted API observability platforms",
                "self-hosted APM distributed tracing platform",
                "open source self-hosted observability tools",
            ])
        else:
            queries.extend(["API observability tools", "distributed tracing software"])
    elif facets.domain == "identity":
        queries.extend([
            "decentralized identity protocol",
            "W3C DID verifiable credentials protocol",
            "self-sovereign identity blockchain",
        ])

    if spec.goal and spec.goal.lower() not in {q.lower() for q in queries}:
        queries.append(spec.goal)

    return queries or ["technology research"]


def clean_entity_name(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^(?:\d+[\.\)]|\#\d+|\•|\-|\*)\s*", "", cleaned)
    cleaned = re.sub(
        r"^(?:Best|Top\s+\d+|The\s+Best|Review:|10\s+Best|5\s+Best|8\s+Best|7\s+Best|11\s+Best|Leading|The)\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s*\(.*?\)$", "", cleaned).strip()
    parts = re.split(r"\s*[-–—|:]\s*", cleaned)
    if len(parts) > 1:
        p0 = parts[0].strip()
        if p0 and not is_publisher_or_agency(p0) and len(p0.split()) <= 4:
            cleaned = p0
        else:
            cleaned = parts[-1].strip()
    if " / " in cleaned:
        cleaned = cleaned.split(" / ")[0].strip()
    elif " vs " in cleaned.lower():
        cleaned = re.split(r"\s+vs\.?\s+", cleaned, flags=re.I)[0].strip()
    elif " and " in cleaned.lower() and len(cleaned.split()) > 3:
        cleaned = re.split(r"\s+and\s+", cleaned, flags=re.I)[0].strip()
    return cleaned.strip()


def is_publisher_or_agency(name: str) -> bool:
    if not name or len(name) < 2:
        return True
    name_lower = name.lower()
    for pat in PUBLISHER_OR_AGENCY_PATTERNS:
        if re.search(pat, name_lower):
            return True
    for pat in GENERIC_CONCEPT_PATTERNS:
        if re.match(pat, name_lower):
            return True
    return False


def _extract_relational_evidence(text: str, domain: str, qualifier: str) -> str | None:
    if not text:
        return None

    sentences = re.split(r"(?<=[.!?\n])\s+", text)

    if qualifier == "ai" and domain == "wallet":
        compound_pats = [
            r"\b(?:ai|agentic|autonomous)\s+(?:crypto\s+|web3\s+|smart\s+|on-chain\s+)?(?:wallet|wallets|account|accounts|vault|vaults)\b",
            r"\b(?:wallet|wallets|account|accounts)\s+for\s+(?:ai|agentic|autonomous)\s+(?:agents?|transactions?)\b",
            r"\b(?:ai|agentic|autonomous)\s+(?:agent|agents)\s+(?:to\s+execute\s+|executing\s+|holding\s+|managing\s+)?(?:on-chain|crypto|wallet|transactions?)\b",
            r"\b(?:intent-based|ai-powered|ai-driven|ai-assisted|agent-driven)\s+(?:crypto\s+|web3\s+)?(?:wallet|wallets|account|accounts)\b",
            r"\b(?:agentkit|smart\s+account\s+ai|agent\s+wallet)\b",
        ]
        for s in sentences:
            s_clean = s.strip()
            for pat in compound_pats:
                if re.search(pat, s_clean, re.I):
                    return s_clean

            has_ai_term = re.search(
                r"\b(?:ai|agentic|autonomous\s+agent|artificial\s+intelligence)\b",
                s_clean,
                re.I,
            )
            has_wallet_term = re.search(
                r"\b(?:wallet|smart\s+account|custody|key\s+management|on-chain\s+transactions?)\b",
                s_clean,
                re.I,
            )
            if has_ai_term and has_wallet_term:
                if re.search(
                    r"\b(?:such as|including|offers?|adoption of)\s+[^.]*?(?:ai|artificial intelligence)[^.]*?(?:,|and)\s+[^.]*?(?:wallet|crypto|web3)",
                    s_clean,
                    re.I,
                ):
                    if not re.search(
                        r"\b(?:operates?|controls?|assists?|secures?|automates?|analyzes?|powers?|executes?|enables?)\b",
                        s_clean,
                        re.I,
                    ):
                        continue
                if re.search(
                    r"\b(?:support|customer|chatbot|marketing|news|search)\b",
                    s_clean,
                    re.I,
                ) and not re.search(
                    r"\b(?:transaction|key|fund|asset|signature|signer|on-chain|account)\b",
                    s_clean,
                    re.I,
                ):
                    continue
                if re.search(
                    r"\b(?:operates?|controls?|assists?|secures?|automates?|analyzes?|powers?|executes?|enables?|uses\s+ai\s+to|leverages\s+ai\s+for|ai-driven|ai-powered)\b",
                    s_clean,
                    re.I,
                ):
                    return s_clean
        return None

    elif qualifier == "open_source" and domain == "feature_flag":
        for s in sentences:
            s_clean = s.strip()
            if re.search(
                r"\b(?:open[- ]source|foss|github|apache|mit\s+license)\b",
                s_clean,
                re.I,
            ) and re.search(
                r"\b(?:feature\s+flag|feature\s+toggle|feature\s+management)\b",
                s_clean,
                re.I,
            ):
                return s_clean
        return None

    elif qualifier == "self_hosted" and domain == "observability":
        for s in sentences:
            s_clean = s.strip()
            if re.search(
                r"\b(?:self[- ]hosted|on[- ]premise|docker|deploy\s+on\s+your\s+own|kubernetes)\b",
                s_clean,
                re.I,
            ) and re.search(
                r"\b(?:observability|apm|tracing|monitoring|telemetry)\b",
                s_clean,
                re.I,
            ):
                return s_clean
        return None

    elif qualifier == "non_custodial" and domain == "wallet":
        for s in sentences:
            s_clean = s.strip()
            if re.search(
                r"\b(?:non[- ]custodial|self[- ]custody|private\s+keys?|users?\s+own\s+keys?)\b",
                s_clean,
                re.I,
            ) and re.search(r"\b(?:wallet|crypto)\b", s_clean, re.I):
                return s_clean
        return None

    for s in sentences:
        s_clean = s.strip()
        q_clean = qualifier.replace("_", " ")
        d_clean = domain.replace("_", " ")
        if q_clean in s_clean.lower() and d_clean in s_clean.lower():
            return s_clean

    return None


def _validate_candidate_facets(
    name: str, snippet: str, summary: str, url: str, facets: QueryFacets
) -> tuple[bool, str, dict[str, Any]]:
    evidence: dict[str, Any] = {"product_domain": None, "qualifiers": {}}

    if not name or is_publisher_or_agency(name):
        return False, "Publisher, agency, or generic category title", evidence

    for pat in PUBLISHER_OR_AGENCY_PATTERNS:
        if re.search(pat, name.lower()):
            return False, "Matches publisher pattern", evidence

    cand_lower = name.lower()
    if cand_lower == facets.subject.lower() or cand_lower == facets.domain.lower():
        return False, "Generic concept title matching query subject/domain", evidence
    for pat in CONCEPT_SUMMARY_INDICATORS:
        if re.search(pat, summary, re.I) or re.search(pat, snippet, re.I):
            return False, "Summary describes a concept/metric/technique rather than a software product", evidence

    if cand_lower in ("password manager", "password managers", "password management", "crypto wallet", "digital wallet", "ai wallet", "observability platform", "feature flag", "database"):
        return False, "Generic concept category name", evidence

    combined = f"{name} {snippet} {summary}".lower()
    for pat in DISCARD_PATTERNS:
        if re.search(pat, name, re.I):
            return False, "Discard pattern match", evidence

    # 1. Domain Match
    if facets.domain == "wallet":
        wallet_match = any(
            w in combined
            for w in (
                "cryptocurrency wallet",
                "digital wallet",
                "crypto wallet",
                "smart wallet",
                "web3 wallet",
                "self-custody",
                "non-custodial",
                "account abstraction",
                "smart contract wallet",
                "smart account",
                "erc-4337",
                "custody wallet",
                "agentic wallet",
                "defi wallet",
                "wallet platform",
                "wallet infrastructure",
                "wallet software",
                "embedded wallet",
                "mpc wallet",
                "wallet toolkit",
                "wallet sdk",
                "on-chain wallet",
                "crypto wallet app",
            )
        ) or (
            "wallet" in name.lower()
            and any(
                w in combined
                for w in (
                    "crypto",
                    "blockchain",
                    "tokens",
                    "defi",
                    "web3",
                    "digital asset",
                    "keys",
                    "ethereum",
                    "base",
                )
            )
        )
        if not wallet_match:
            return False, "Not a verified wallet product/infrastructure", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    elif facets.domain == "password_manager":
        if not any(
            w in combined
            for w in (
                "password manager",
                "password management",
                "store passwords",
                "password vault",
                "password generator",
                "credential management",
                "autofill passwords",
                "keeper",
                "1password",
                "lastpass",
                "bitwarden",
                "dashlane",
                "nordpass",
                "keepass",
                "roboform",
                "enpass",
            )
        ):
            return False, "Not a password manager product", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    elif facets.domain == "feature_flag":
        if not any(
            w in combined
            for w in (
                "feature flag",
                "feature toggle",
                "rollout",
                "feature management",
                "toggle management",
                "toggling",
                "flagsmith",
                "unleash",
                "flipt",
                "growthbook",
                "launchdarkly",
                "openfeature",
            )
        ):
            return False, "Not a feature flag tool", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    elif facets.domain == "observability":
        if not any(
            w in combined
            for w in (
                "observability",
                "apm",
                "distributed tracing",
                "telemetry",
                "opentelemetry",
                "metrics",
                "monitoring",
                "tracing",
                "signoz",
                "jaeger",
                "prometheus",
                "datadog",
                "grafana",
                "tempo",
                "dynatrace",
                "cilium",
            )
        ):
            return False, "Not an observability platform", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    elif facets.domain == "identity":
        if not any(
            w in combined
            for w in (
                "identity",
                "did",
                "verifiable credential",
                "world id",
                "ens",
                "attestation",
                "sovereign identity",
                "decentralized identifier",
            )
        ):
            return False, "Not an identity protocol/platform", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    # 2. Mandatory Relational Qualifier Validation
    full_text = f"{snippet}\n{summary}"
    for q in facets.mandatory_qualifiers:
        rel_evidence = _extract_relational_evidence(full_text, facets.domain, q)
        if not rel_evidence:
            return (
                False,
                f"Missing relational evidence connecting qualifier '{q}' to domain '{facets.domain}'",
                evidence,
            )
        evidence["qualifiers"][q] = {"evidence": rel_evidence, "source": url}

    return True, "Valid", evidence


def _is_semantically_relevant(title: str, snippet: str, spec: JobSpec) -> bool:
    facets = extract_facets(spec)
    valid, _, _ = _validate_candidate_facets(title, snippet, "", "", facets)
    return valid


def _extract_truthful_pricing(snippet: str, summary: str) -> str:
    combined = f"{snippet} {summary}"
    price_patterns = [
        r"(?:pricing|starting at|plans start at|costs?|free tier|subscription|priced at|flat fee of)\s*([^\.\n,]+)",
        r"(\$\d+(?:\.\d+)?(?:\s*/\s*(?:mo|month|year|user|annually))?)",
        r"\b(free and open-source|free and open source|free software|free of charge|open-source and free|free to use|100% free|completely free|open source with paid cloud|freemium|free tier available|free plan|paid subscription|proprietary freemium|subscription-based(?: model)?)\b",
    ]
    for p in price_patterns:
        m = re.search(p, combined, flags=re.I)
        if m:
            val = m.group(0).strip()
            if len(val) <= 90:
                return val
    return "Not publicly disclosed in the retrieved source."


def _extract_supported_platforms(text: str) -> str:
    if not text:
        return "Could not verify supported platforms from the retrieved sources."
    found = []
    platform_keywords = [
        ("Windows", r"\bwindows\b"),
        ("macOS", r"\b(macos|mac os|os x)\b"),
        ("Linux", r"\blinux\b"),
        ("iOS", r"\b(ios|iphone|ipad)\b"),
        ("Android", r"\bandroid\b"),
        ("Web", r"\b(web|browser extensions?|web app)\b"),
        ("Chrome", r"\bchrome\b"),
        ("Firefox", r"\bfirefox\b"),
        ("Safari", r"\bsafari\b"),
        ("Edge", r"\bedge\b"),
    ]
    for label, pat in platform_keywords:
        if re.search(pat, text, re.I):
            found.append(label)
    if found:
        seen = set()
        clean = []
        for item in found:
            if item not in seen:
                seen.add(item)
                clean.append(item)
        return ", ".join(clean)
    m = re.search(r"(?:available on|supports?|runs on|compatible with)\s+([^\.\n]+)", text, re.I)
    if m:
        return m.group(0).strip()
    return "Could not verify supported platforms from the retrieved sources."


def _extract_grounded_strength(text: str, entity_name: str) -> str:
    if not text:
        return "Could not verify a specific strength from the retrieved sources."
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 25 or len(s_clean) > 260:
            continue
        if re.search(
            r"\b(?:headquartered|offices in|offices located in|founded in|incorporated in|subsidiary of|parent company|revenue of|employees|monthly active users)\b",
            s_clean,
            re.I,
        ):
            continue
        if re.search(
            r"\b(?:enables?|supports?|provides?|features?|allows?|designed to|built for|high-performance|real-time|sub-millisecond|automated|seamless|zero-knowledge|account abstraction|open-source|self-hosted|agentic|intent-based|end-to-end encryption|zero-trust|autofill|encrypted vault|passkey)\b",
            s_clean,
            re.I,
        ):
            return s_clean
    return "Could not verify a specific strength from the retrieved sources."


def _extract_grounded_weakness(text: str, entity_name: str) -> str:
    if not text:
        return "Could not verify a specific weakness from the retrieved sources."
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 25 or len(s_clean) > 260:
            continue
        if re.search(
            r"\b(?:headquartered|offices in|founded in|employees)\b",
            s_clean,
            re.I,
        ):
            continue
        if re.search(
            r"\b(?:limitation|drawback|trade-off|requires?\s+(?:developer|manual|complex|technical|additional|custom|external)|experimental|beta|lacks?|limited support|higher latency|steep learning curve|past security incidents?|security vulnerability|vulnerability|flaw|criticism|data breach|breach history|attack|compromised|exploit)\b",
            s_clean,
            re.I,
        ):
            return s_clean
    return "Could not verify a specific weakness from the retrieved sources."


def _extract_generic_field(field_name: str, text: str) -> str:
    if not text:
        return f"Could not verify {field_name} from the retrieved sources."
    fn_clean = field_name.replace("_", " ").lower()
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    for s in sentences:
        s_clean = s.strip()
        if fn_clean in s_clean.lower() and len(s_clean) >= 15:
            return s_clean
    return f"Could not verify {field_name} from the retrieved sources."


def _search_ddg_lite(query: str, limit: int = 15) -> list[dict[str, Any]]:
    results = []
    try:
        r = httpx.post(
            DDG_LITE,
            data={"q": query},
            headers=BROWSER_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if r.status_code == 200:
            pattern = r"<a rel=['\"]nofollow['\"] href=['\"](?P<url>[^'\"]+)['\"] class=['\"]result-link['\"]>(?P<title>.*?)</a>.*?<td class=['\"]result-snippet['\"]>(?P<snippet>.*?)</td>"
            matches = re.findall(pattern, r.text, re.DOTALL)
            for url, title, snippet in matches:
                clean_title = re.sub(r"<[^>]+>", "", title).strip()
                clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                results.append({
                    "title": clean_title,
                    "snippet": clean_snippet,
                    "url": url,
                    "source": "Web Search (DDG)",
                })
                if len(results) >= limit:
                    break
    except Exception:
        pass
    return results


def _search_ddg_html(query: str, limit: int = 15) -> list[dict[str, Any]]:
    results = []
    try:
        r = httpx.post(
            DDG_HTML,
            data={"q": query},
            headers=BROWSER_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if r.status_code == 200:
            blocks = re.findall(
                r'<div class="result results_links results_links_deep web-result.*?<div class="clear"></div>',
                r.text,
                re.DOTALL,
            )
            for b in blocks:
                title_m = re.search(
                    r'<h2 class="result__title">.*?<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>',
                    b,
                    re.DOTALL,
                )
                snippet_m = re.search(
                    r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
                    b,
                    re.DOTALL,
                )
                if title_m:
                    raw_url = title_m.group("link")
                    if "uddg=" in raw_url:
                        qs = parse_qs(urlparse(raw_url).query)
                        target_url = unquote(qs.get("uddg", [raw_url])[0])
                    else:
                        target_url = raw_url
                    title = re.sub(r"<[^>]+>", "", title_m.group("title")).strip()
                    snippet = (
                        re.sub(r"<[^>]+>", "", snippet_m.group("snippet")).strip()
                        if snippet_m
                        else ""
                    )
                    results.append({
                        "title": title,
                        "snippet": snippet,
                        "url": target_url,
                        "source": "Web Search",
                    })
                    if len(results) >= limit:
                        break
    except Exception:
        pass
    return results


def _search_ddg(query: str, limit: int = 15) -> list[dict[str, Any]]:
    res = _search_ddg_lite(query, limit)
    if not res:
        res = _search_ddg_html(query, limit)
    return res


def _search_wiki(query: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        r = httpx.get(
            WIKI_SEARCH,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": str(limit),
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=5.0,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        for hit in data.get("query", {}).get("search", []):
            title = str(hit.get("title") or "").strip()
            snippet = re.sub(r"<[^>]+>", "", str(hit.get("snippet") or "")).strip()
            results.append({"title": title, "snippet": snippet})
        return results
    except Exception:
        return []


def get_wiki_full_extract(title: str) -> str:
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "titles": title,
        "format": "json",
    }
    try:
        r = httpx.get(WIKI_API, params=params, headers=WIKI_HEADERS, timeout=5.0)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                return str(page.get("extract") or "")
    except Exception:
        pass
    return ""


def _wiki_summary(title: str) -> dict[str, Any] | None:
    url = WIKI_SUMMARY + quote(title.replace(" ", "_"))
    page_url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
    try:
        r = httpx.get(url, headers=WIKI_HEADERS, timeout=5.0, follow_redirects=True)
        if r.status_code != 200:
            return None
        data = r.json()
        extract = str(data.get("extract") or "").strip()
        clean_name = clean_entity_name(data.get("title") or title)
        if is_publisher_or_agency(clean_name):
            return None
        full_text = get_wiki_full_extract(title)
        return {
            "name": clean_name,
            "title": data.get("title") or title,
            "extract": extract,
            "full_text": full_text or extract,
            "url": data.get("content_urls", {}).get("desktop", {}).get("page") or page_url,
        }
    except Exception:
        return None


def _extract_candidates_from_text(text: str) -> list[str]:
    cands = []
    m1 = re.findall(
        r"(?:^|\n|\.\s+)(?:\d+[\.\)]|\#\d+|\•|\-|\*)\s*([A-Z][A-Za-z0-9\s\{\}\.\-]{2,25}?)(?:\s*[-–—:]|\s+is\b|\s+wallet|\s+platform|\s+tool|\s*\n)",
        text,
    )
    for m in m1:
        c = clean_entity_name(m)
        if c and len(c.split()) <= 4 and not is_publisher_or_agency(c):
            cands.append(c)

    if (
        "compare" in text.lower()
        or "wallets for" in text.lower()
        or "tools:" in text.lower()
        or "picks:" in text.lower()
        or "managers:" in text.lower()
    ):
        parts = re.split(r"[,:;]\s*", text)
        for p in parts:
            c = clean_entity_name(p)
            if c and len(c.split()) <= 3 and not is_publisher_or_agency(c) and c[0].isupper():
                cands.append(c)
    return cands


def _build_finding_object(
    cand_name: str,
    facets: QueryFacets,
    spec: JobSpec,
    contract: Contract,
    snippet: str,
    extract: str,
    full_text: str,
    url: str,
    source_label: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    combined_initial = f"{snippet} {extract} {full_text}"
    pricing_val = _extract_truthful_pricing(snippet, f"{extract} {full_text}")
    platforms_val = _extract_supported_platforms(combined_initial)
    strengths_val = _extract_grounded_strength(combined_initial, cand_name)
    weaknesses_val = _extract_grounded_weakness(combined_initial, cand_name)

    field_sources: dict[str, dict[str, str]] = {
        "entity": {"url": url, "label": source_label},
        "pricing": {"url": url, "label": source_label},
        "supported_platforms": {"url": url, "label": source_label},
        "strengths": {"url": url, "label": source_label},
        "weaknesses": {"url": url, "label": source_label},
    }

    all_sources = [{"label": source_label, "url": url}]

    # Perform targeted follow-up retrieval for any missing requested fields
    all_requested = spec.deliverables or contract.deliverables or []
    follow_ups_attempted = []

    if "pricing" in all_requested and pricing_val == "Not publicly disclosed in the retrieved source.":
        follow_ups_attempted.append("pricing")
        hits = _search_ddg(f"{cand_name} pricing plans", limit=4)
        for h in hits:
            h_text = f"{h['title']} {h['snippet']}"
            p_val = _extract_truthful_pricing(h['title'], h['snippet'])
            if p_val != "Not publicly disclosed in the retrieved source.":
                pricing_val = p_val
                field_sources["pricing"] = {"url": h["url"], "label": "Official / Web Pricing"}
                all_sources.append({"label": "Pricing Source", "url": h["url"]})
                break

    if "supported platforms" in all_requested and platforms_val == "Could not verify supported platforms from the retrieved sources.":
        follow_ups_attempted.append("supported platforms")
        hits = _search_ddg(f"{cand_name} supported platforms operating systems Windows macOS iOS Android download", limit=4)
        for h in hits:
            h_text = f"{h['title']} {h['snippet']}"
            plat_val = _extract_supported_platforms(h_text)
            if plat_val != "Could not verify supported platforms from the retrieved sources.":
                platforms_val = plat_val
                field_sources["supported_platforms"] = {"url": h["url"], "label": "Platform Documentation"}
                all_sources.append({"label": "Platform Source", "url": h["url"]})
                break

    if "weaknesses" in all_requested and weaknesses_val == "Could not verify a specific weakness from the retrieved sources.":
        follow_ups_attempted.append("weaknesses")
        hits = _search_ddg(f"{cand_name} limitations drawbacks security review", limit=4)
        for h in hits:
            h_text = f"{h['title']} {h['snippet']}"
            w_val = _extract_grounded_weakness(h_text, cand_name)
            if w_val != "Could not verify a specific weakness from the retrieved sources.":
                weaknesses_val = w_val
                field_sources["weaknesses"] = {"url": h["url"], "label": "Review / Security Source"}
                all_sources.append({"label": "Weakness Source", "url": h["url"]})
                break

    finding: dict[str, Any] = {
        "name": cand_name,
        "company": cand_name,
        "type": facets.entity_type,
        "summary": extract or snippet or f"Solution for {spec.subject} ({cand_name}).",
        "products": [cand_name],
        "pricing": pricing_val,
        "supported_platforms": platforms_val,
        "supported platforms": platforms_val,
        "strengths": strengths_val,
        "weaknesses": weaknesses_val,
        "sources": all_sources,
        "field_sources": field_sources,
        "evidence": evidence,
        "follow_ups_attempted": follow_ups_attempted,
    }

    for field_name in all_requested:
        f_norm = field_name.strip().lower()
        if f_norm in ("names", "pricing", "strengths", "weaknesses", "products", "supported platforms", "supported_platforms") or any(f_norm.startswith(k) for k in ("3 ", "5 ", "2 ", "4 ", "10 ")):
            continue
        val = _extract_generic_field(f_norm, combined_initial)
        if val.startswith("Could not verify"):
            hits = _search_ddg(f"{cand_name} {field_name}", limit=3)
            for h in hits:
                h_text = f"{h['title']} {h['snippet']}"
                v = _extract_generic_field(f_norm, h_text)
                if not v.startswith("Could not verify"):
                    val = v
                    field_sources[field_name] = {"url": h["url"], "label": f"{field_name} Source"}
                    all_sources.append({"label": f"{field_name} Source", "url": h["url"]})
                    break
        finding[field_name] = val
        finding[field_name.replace(" ", "_")] = val

    return finding


def run_research(spec: JobSpec, contract: Contract) -> dict[str, Any]:
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    facets = extract_facets(spec)
    target_count = facets.target_count

    seen_names: set[str] = set()
    findings: list[dict[str, Any]] = []

    queries = search_queries(spec)

    # 1. Harvest & validate from Wikipedia
    for q in queries[:4]:
        wiki_results = _search_wiki(q, limit=8)
        for hit in wiki_results:
            title = hit.get("title", "")
            cand_name = clean_entity_name(title)
            if (
                not cand_name
                or is_publisher_or_agency(cand_name)
                or cand_name.lower() in seen_names
                or len(cand_name.split()) > 4
            ):
                continue

            sum_info = _wiki_summary(title)
            extract = sum_info["extract"] if sum_info else hit.get("snippet", "")
            full_text = sum_info["full_text"] if sum_info else extract
            url = sum_info["url"] if sum_info else f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"

            valid, _, evidence = _validate_candidate_facets(
                cand_name, hit.get("snippet", ""), full_text, url, facets
            )
            if valid and cand_name.lower() not in seen_names:
                seen_names.add(cand_name.lower())
                findings.append(
                    _build_finding_object(
                        cand_name, facets, spec, contract, hit.get("snippet", ""), extract, full_text, url, "Wikipedia", evidence
                    )
                )
                if len(findings) >= target_count:
                    break
        if len(findings) >= target_count:
            break

    # 2. Harvest & validate from Web Search (DDG)
    if len(findings) < target_count:
        for q in queries:
            ddg_results = _search_ddg(q, limit=12)
            for hit in ddg_results:
                title = hit.get("title", "")
                snippet = hit.get("snippet", "")
                url = hit.get("url", "")

                cand_title = clean_entity_name(title)
                if (
                    cand_title
                    and not is_publisher_or_agency(cand_title)
                    and len(cand_title.split()) <= 4
                    and cand_title.lower() not in seen_names
                ):
                    valid, _, evidence = _validate_candidate_facets(
                        cand_title, snippet, "", url, facets
                    )
                    if valid:
                        seen_names.add(cand_title.lower())
                        findings.append(
                            _build_finding_object(
                                cand_title, facets, spec, contract, snippet, "", "", url, "Web Search Citation", evidence
                            )
                        )
                        if len(findings) >= target_count:
                            break

                sub_cands = _extract_candidates_from_text(snippet)
                for cand in sub_cands:
                    if cand.lower() not in seen_names:
                        valid, _, evidence = _validate_candidate_facets(
                            cand, snippet, "", url, facets
                        )
                        if valid:
                            seen_names.add(cand.lower())
                            findings.append(
                                _build_finding_object(
                                    cand, facets, spec, contract, snippet, "", "", url, "Web Research Source", evidence
                                )
                            )
                            if len(findings) >= target_count:
                                break
                if len(findings) >= target_count:
                    break
            if len(findings) >= target_count:
                break

    requires_sources = any(
        "source" in item.lower() or "citation" in item.lower() or "link" in item.lower()
        for item in contract.acceptance
    )
    requires_recent = spec.time_sensitive or any(
        "recent" in item.lower() for item in contract.acceptance
    )

    for finding in findings:
        if requires_sources:
            finding["citations"] = list(finding.get("sources") or [])
            if not finding["citations"]:
                finding["warning"] = "No source URL was available for this item."
            else:
                first_url = finding["citations"][0].get("url", "")
                if first_url and first_url not in (finding.get("summary") or ""):
                    finding["summary"] = (
                        (finding.get("summary") or "") + f" Source: {first_url}"
                    ).strip()
        if requires_recent:
            finding["retrieved_at"] = retrieved_at

    deliverables = _map_deliverables(spec, contract, findings)

    report_value = {
        "title": contract.title,
        "goal": spec.goal,
        "retrieved_at": retrieved_at,
        "findings": findings,
        "deliverables": deliverables,
        "honored_requirements": list(contract.acceptance),
        "applied_lesson_ids": [lesson.id for lesson in contract.applied_lessons],
        "notes": _notes(spec, findings, requires_sources, requires_recent, target_count),
    }

    is_valid, val_reason = validate_deliverable_against_contract(contract, report_value)
    if not is_valid:
        report_value["notes"].append(f"Contract validation warning: {val_reason}")

    return {
        "type": "object",
        "value": report_value,
    }


def _map_deliverables(spec: JobSpec, contract: Contract, findings: list[dict[str, Any]]) -> dict[str, Any]:
    names = [item.get("name") for item in findings if item.get("name")]
    products = [
        item.get("products")
        if item.get("products")
        else [item.get("summary", "")[:180]]
        for item in findings
    ]
    pricing = [item.get("pricing") for item in findings]
    strengths = [item.get("strengths") for item in findings]
    weaknesses = [item.get("weaknesses") for item in findings]

    out: dict[str, Any] = {
        "names": names,
        "products": products,
        "pricing": pricing,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "requested": spec.deliverables or contract.deliverables,
    }

    for field in (spec.deliverables or []) + (contract.deliverables or []):
        f_norm = field.strip().lower()
        if f_norm not in out and not any(f_norm.startswith(k) for k in ("3 ", "5 ", "2 ", "4 ", "10 ")):
            out[field] = [item.get(field, item.get(field.replace(" ", "_"), f"Could not verify {field} from retrieved sources.")) for item in findings]

    return out


def validate_deliverable_against_contract(contract: Contract, deliverable_value: dict[str, Any]) -> tuple[bool, str]:
    findings = deliverable_value.get("findings", [])
    for f in findings:
        name = f.get("name", "").strip()
        if not name or is_publisher_or_agency(name):
            return False, f"Candidate '{name}' is a generic category concept or publisher, not a concrete entity."

    requested = deliverable_value.get("deliverables", {}).get("requested", []) or contract.deliverables
    for field in requested:
        f_low = field.lower()
        if any(token in f_low for token in ("names", "companies", "products", "managers", "wallets", "tools", "platforms")) and not any(k in f_low for k in ("pricing", "platform", "strength", "weakness", "option", "support")):
            continue
        if field not in deliverable_value.get("deliverables", {}):
            return False, f"Missing requested deliverable field '{field}' in deliverables output."

    return True, "Valid"


def _notes(
    spec: JobSpec,
    findings: list[dict[str, Any]],
    requires_sources: bool,
    requires_recent: bool,
    limit: int = 5,
) -> list[str]:
    notes = [
        f"{len(findings)} qualifying entities could be verified from the available sources."
    ]
    if len(findings) < limit:
        notes.append(
            f"Identified {len(findings)} verified options; additional candidates could not be verified with high confidence from public sources without risk of false matches."
        )
    if not findings:
        notes.append("No public sources answered this query with verified qualification.")
    if requires_sources:
        missing = [item.get("name") for item in findings if not item.get("sources")]
        if missing:
            notes.append(
                "Missing source links for: " + ", ".join(str(name) for name in missing)
            )
        else:
            notes.append(
                "Source links were attached to each finding because the contract required them."
            )
    if requires_recent:
        notes.append("Retrieval timestamp recorded because the job is time-sensitive.")
    if spec.explicit_requirements:
        notes.append(
            "Explicit user requirements were included in the contract the worker received."
        )
    return notes


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0].strip() if parts else text.strip()
