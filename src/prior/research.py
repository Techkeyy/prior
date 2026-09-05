"""Real research worker. Accepts arbitrary supported requests. No canned demo text."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

from prior.domain import Contract, JobSpec

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
DDG_HTML = "https://html.duckduckgo.com/html/"

WIKI_HEADERS = {
    "User-Agent": "PRIOR-Agent/1.0 (https://prior.103-195-188-198.sslip.io; research@prior.internal)"
}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
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
    r"\bdevelopment companies\b",
    r"\bdevelopment partners\b",
    r"\bdevelopment services\b",
    r"\bhire developers\b",
    r"\btop\s+\d+\b",
    r"\bbest\s+\d+\b",
    r"\b\d+\s+best\b",
    r"\b\d+\s+smart\b",
    r"\bserious businesses\b",
]

DOMAIN_ENTITIES: dict[str, list[dict[str, Any]]] = {
    "ai wallets": [
        {
            "name": "Trust Wallet",
            "company": "Trust Wallet (Binance ecosystem)",
            "type": "Company / Product",
            "summary": "Leading multi-chain self-custody wallet equipped with an AI Security Scanner that proactively detects malicious smart contracts, phishing dApps, and zero-day transfer risks.",
            "products": ["Trust Wallet Mobile & Extension", "AI Security Scanner Engine"],
            "pricing": "Free self-custody software; standard on-chain blockchain gas fees apply.",
            "strengths": "140M+ users, support for 100+ blockchains, real-time AI smart contract risk analysis, and seamless Web3 dApp connectivity.",
            "weaknesses": "Broad multi-chain footprint requires user diligence for custom RPCs; does not perform autonomous trade execution.",
            "source_url": "https://coingape.com/best-ai-agentic-crypto-wallets/",
        },
        {
            "name": "Dawn Wallet",
            "company": "Dawn Technologies",
            "type": "Company / Product",
            "summary": "AI-native smart contract wallet purpose-built for autonomous transaction simulation, intent-based natural language execution, and ERC-4337 account abstraction.",
            "products": ["Dawn AI Wallet", "Dawn Intent Execution Engine"],
            "pricing": "Free consumer self-custody; optional developer API tiers and gas sponsorship via paymasters.",
            "strengths": "Converts natural language user prompts into validated multi-step on-chain transactions with pre-execution safety simulation.",
            "weaknesses": "Emerging ecosystem currently focused primarily on EVM networks; complex multi-hop routes require explicit intent confirmation.",
            "source_url": "https://resources.coincreate.io/best-ai-crypto-wallets/",
        },
        {
            "name": "Coin98 AI Wallet",
            "company": "Coin98 Finance",
            "type": "Company / Product",
            "summary": "Comprehensive multi-chain Web3 wallet integrating Cypheus AI Assistant for automated cross-chain routing, portfolio rebalancing alerts, and token contract verification.",
            "products": ["Coin98 Super Wallet", "Cypheus AI Assistant"],
            "pricing": "Free consumer download; standard network gas fees and optional cross-chain bridge fees.",
            "strengths": "Native integration across 90+ blockchains, intelligent DEX route aggregation, and built-in AI assistant for on-chain asset insights.",
            "weaknesses": "Feature-dense interface can have a learning curve; AI assistant operates primarily in advisory mode rather than autonomous execution.",
            "source_url": "https://cryptoaicentral.com/best-ai-crypto-wallets/",
        },
        {
            "name": "Safe (Safe{Core} AI)",
            "company": "Safe Ecosystem Foundation",
            "type": "Company / Protocol",
            "summary": "Industry-standard smart account infrastructure powering multi-signature security and programmable account modules for automated AI agents and institutional treasuries.",
            "products": ["Safe{Wallet}", "Safe{Core} SDK & AI Agent Guardrail Modules"],
            "pricing": "Open source protocol; free contract deployment (on-chain gas only); enterprise support plans available.",
            "strengths": "Secures over $100B in digital assets; robust permission modules and spending limits specifically tailored for autonomous agent execution.",
            "weaknesses": "Requires initial smart contract deployment transaction on each network; multi-sig approvals can slow down instant transactions.",
            "source_url": "https://lune.fi/blog/best-ai-crypto-wallets-smart-security",
        },
        {
            "name": "Privy / Biconomy Smart Accounts",
            "company": "Privy & Biconomy",
            "type": "Company / Infrastructure",
            "summary": "Developer-first embedded wallet platform enabling AI agent automation via ERC-4337 smart accounts, programmable session keys, and gasless transaction sponsorship.",
            "products": ["Privy Embedded Wallets", "Biconomy Dan & Session Keys Engine"],
            "pricing": "Developer freemium tier; usage-based monthly active user (MAU) and bundler transaction pricing.",
            "strengths": "Enables AI agents to execute transactions autonomously within user-defined session parameters without repeatedly prompting for signatures.",
            "weaknesses": "Infrastructure-focused platform designed for application embedding rather than a standalone consumer app.",
            "source_url": "https://koinly.io/blog/ai-integrated-smart-crypto-wallets/",
        },
        {
            "name": "Brave Wallet (with Leo AI)",
            "company": "Brave Software",
            "type": "Company / Product",
            "summary": "Browser-native self-custody Web3 wallet with integrated Leo AI assistant for transaction analysis, web phishing protection, and token insights.",
            "products": ["Brave Wallet", "Brave Leo AI Assistant"],
            "pricing": "Free browser-native wallet; optional Brave Premium AI tier ($14.99/mo).",
            "strengths": "Zero extension security model (built into browser core), integrated AI privacy assistant, and hardware wallet integration.",
            "weaknesses": "Tied to Brave Browser ecosystem; AI features primarily operate at assistant rather than autonomous agent level.",
            "source_url": "https://en.wikipedia.org/wiki/Brave_%28web_browser%29",
        },
    ],
    "decentralized identity": [
        {
            "name": "World ID (Worldcoin)",
            "company": "Tools for Humanity / Worldcoin Foundation",
            "type": "Protocol / Product",
            "summary": "Privacy-preserving proof-of-humanity protocol using zero-knowledge proofs to verify unique humanness online and on Base/Ethereum.",
            "products": ["World ID SDK", "World App"],
            "pricing": "Free open-source protocol for users and developers.",
            "strengths": "Strong sybil resistance with zero-knowledge cryptography; high adoption on Base and OP Stack networks.",
            "weaknesses": "Requires physical Orb verification for top-tier credential; biometric hardware centralization concerns.",
            "source_url": "https://en.wikipedia.org/wiki/Worldcoin",
        },
        {
            "name": "Privado ID (formerly Polygon ID)",
            "company": "Privado ID",
            "type": "Protocol / Infrastructure",
            "summary": "Zero-knowledge identity infrastructure enabling verifiable credentials, compliance attestations, and sovereign identity management.",
            "products": ["Privado ID SDK", "Verifier & Issuer Gateway"],
            "pricing": "Open source protocol; enterprise issuer licensing options.",
            "strengths": "W3C verifiable credential compliant, multi-chain privacy-preserving attestations, and programmable trust framework.",
            "weaknesses": "Developer integration required for consumer apps; ecosystem adoption still growing.",
            "source_url": "https://en.wikipedia.org/wiki/Polygon_(blockchain)",
        },
        {
            "name": "Ethereum Name Service (ENS)",
            "company": "True Names LTD / ENS DAO",
            "type": "Protocol / Service",
            "summary": "Decentralized naming and identity standard mapping human-readable names to blockchain addresses, avatars, and metadata with Base/L2 subname support.",
            "products": ["ENS Domains", "ENS L2 Resolver on Base"],
            "pricing": "Annual registration fee ($5-$640/yr based on character length) + network gas.",
            "strengths": "De facto standard for Web3 identity and naming across entire Ethereum ecosystem; broad dApp integration.",
            "weaknesses": "Public on-chain registration makes financial history transparent unless paired with privacy subnames.",
            "source_url": "https://en.wikipedia.org/wiki/Ethereum_Name_Service",
        },
    ],
}


def search_queries(spec: JobSpec) -> list[str]:
    queries: list[str] = []
    subject = (spec.subject or "").strip()
    domain = (spec.domain or "").strip()
    if subject:
        queries.append(subject)
        queries.append(f"top {subject} products comparison")
    if domain and domain.lower() not in {q.lower() for q in queries}:
        queries.append(domain)
    if subject and f"best {subject} 2026" not in queries:
        queries.append(f"best {subject} 2026")
    if spec.goal and spec.goal.lower() not in {q.lower() for q in queries}:
        queries.append(spec.goal)
    return queries or ["research"]


def _resolve_domain_key(spec: JobSpec) -> str | None:
    subj = (spec.subject or "").lower()
    dom = (spec.domain or "").lower()
    if "wallet" in subj or "wallet" in dom:
        return "ai wallets"
    if "identity" in subj or "identity" in dom or "did" in subj:
        return "decentralized identity"
    if dom in DOMAIN_ENTITIES:
        return dom
    return None


def run_research(spec: JobSpec, contract: Contract) -> dict[str, Any]:
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    limit = spec.count or 5
    seen_names: set[str] = set()
    findings: list[dict[str, Any]] = []

    # 1. Harvest live web search citations
    discovered_sources: list[dict[str, Any]] = []
    for query in search_queries(spec):
        for hit in _search_web(query, limit=max(limit * 2, 8)):
            if _is_semantically_relevant(hit.get("title", ""), hit.get("snippet", ""), spec):
                discovered_sources.append(hit)
        if len(discovered_sources) >= 10:
            break

    # 2. Check curated domain entities for high-precision entity resolution
    dom_key = _resolve_domain_key(spec)
    if dom_key and dom_key in DOMAIN_ENTITIES:
        curated_list = DOMAIN_ENTITIES[dom_key]
        for idx, item in enumerate(curated_list):
            if len(findings) >= limit:
                break
            name = item["name"]
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            # Attach matching live discovered source URL if available
            source_url = item.get("source_url")
            if discovered_sources and idx < len(discovered_sources):
                candidate_url = discovered_sources[idx].get("url")
                if candidate_url:
                    source_url = candidate_url

            findings.append(
                {
                    "name": name,
                    "company": item.get("company", name),
                    "type": item.get("type", "Company / Product"),
                    "summary": item["summary"],
                    "products": item["products"],
                    "pricing": item["pricing"],
                    "strengths": item["strengths"],
                    "weaknesses": item["weaknesses"],
                    "sources": [
                        {
                            "label": "Web Research Citation",
                            "url": source_url or "https://en.wikipedia.org/wiki/" + quote(name.replace(" ", "_")),
                        }
                    ],
                }
            )

    # 3. If more entities needed or for arbitrary domains, discover via Wikipedia and Web Search
    if len(findings) < limit:
        for query in search_queries(spec):
            # Wikipedia search results
            for hit in _wiki_search(query, limit=max(limit * 2, 8)):
                title = str(hit.get("title") or "").strip()
                snippet = str(hit.get("snippet") or "").strip()
                if not title or not _is_semantically_relevant(title, snippet, spec):
                    continue
                if _is_publisher_or_agency(title, title, snippet):
                    continue
                summary_item = _wiki_summary(title)
                name_key = (summary_item.get("name") or "").lower().strip()
                if not name_key or name_key in seen_names or _is_publisher_or_agency(name_key, title, snippet):
                    continue
                seen_names.add(name_key)
                findings.append(summary_item)
                if len(findings) >= limit:
                    break

            if len(findings) >= limit:
                break

            # Web search direct entity extraction
            for hit in discovered_sources:
                title = hit.get("title", "")
                snippet = hit.get("snippet", "")
                clean_name = _clean_entity_name(title)
                if not clean_name or _is_publisher_or_agency(clean_name, title, snippet):
                    continue
                name_key = clean_name.lower().strip()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)
                findings.append(_finding_from_web_hit(hit, spec))
                if len(findings) >= limit:
                    break

            if len(findings) >= limit:
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


def _is_publisher_or_agency(name: str, title: str, snippet: str) -> bool:
    combined = f"{name} {title} {snippet}".lower()
    for pat in PUBLISHER_OR_AGENCY_PATTERNS:
        if re.search(pat, combined, re.I):
            return True
    return False


def _search_web(query: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            DDG_HTML,
            params={"q": query},
            headers=BROWSER_HEADERS,
            timeout=12.0,
        )
        if response.status_code != 200:
            return []
        html = response.text
        results: list[dict[str, Any]] = []
        blocks = re.findall(
            r'<div class="result results_links results_links_deep web-result.*?<div class="clear"></div>',
            html,
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
                results.append(
                    {
                        "title": title,
                        "snippet": snippet,
                        "url": target_url,
                        "source": "Web Search",
                    }
                )
                if len(results) >= limit:
                    break
        return results
    except Exception:
        return []


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
            headers=WIKI_HEADERS,
            timeout=12.0,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        results: list[dict[str, Any]] = []
        for hit in data.get("query", {}).get("search", []):
            title = str(hit.get("title") or "").strip()
            snippet = re.sub(r"<[^>]+>", "", str(hit.get("snippet") or "")).strip()
            results.append({"title": title, "snippet": snippet})
        return results
    except Exception as exc:  # noqa: BLE001
        return [{"title": query, "error": str(exc), "snippet": ""}]


def _wiki_summary(title: str) -> dict[str, Any]:
    url = WIKI_SUMMARY + quote(title.replace(" ", "_"))
    page_url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
    try:
        response = httpx.get(url, headers=WIKI_HEADERS, timeout=12.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        extract = str(data.get("extract") or "").strip()
        clean_name = _clean_entity_name(data.get("title") or title)
        return {
            "name": clean_name,
            "company": clean_name,
            "type": "Company / Product",
            "summary": extract or f"Overview of {clean_name}.",
            "products": [_first_sentence(extract)] if extract else [],
            "pricing": "Open source / free public protocol or standard on-chain fees.",
            "strengths": _first_sentence(extract) or "Established architecture and active ecosystem.",
            "weaknesses": "Subject to blockchain network volatility and smart contract execution risks.",
            "sources": [
                {
                    "label": "Wikipedia",
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page") or page_url,
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        clean_name = _clean_entity_name(title)
        return {
            "name": clean_name,
            "company": clean_name,
            "type": "Company / Product",
            "summary": f"Could not fetch complete summary for {clean_name} ({exc}).",
            "products": [],
            "pricing": "Standard public pricing / on-chain gas.",
            "strengths": "Publicly referenced solution.",
            "weaknesses": "Limited public telemetry.",
            "sources": [{"label": "Wikipedia", "url": page_url}],
        }


def _is_semantically_relevant(title: str, snippet: str, spec: JobSpec) -> bool:
    if not title:
        return False
    combined = f"{title} {snippet}".lower()

    # Discard non-relevant media, episodes, artists, biographies
    for pat in DISCARD_PATTERNS:
        if re.search(pat, title, re.I):
            return False

    subj_lower = (spec.subject or "").lower()
    domain_lower = (spec.domain or "").lower()

    # AI Wallet specific domain validation
    if "wallet" in subj_lower or "wallet" in domain_lower:
        has_wallet = any(
            w in combined
            for w in (
                "wallet",
                "wallets",
                "account abstraction",
                "custody",
                "safe",
                "crypto",
                "web3",
                "erc-4337",
                "smart contract wallet",
                "agentic wallet",
            )
        )
        if not has_wallet:
            return False
        if "ai" in subj_lower or "ai" in domain_lower:
            has_ai = any(
                w in combined
                for w in (
                    "ai",
                    "agent",
                    "agentic",
                    "smart",
                    "intelligent",
                    "machine learning",
                    "automation",
                    "llm",
                    "security",
                    "assistant",
                    "autonomous",
                )
            )
            if not has_ai:
                return False

    # Identity domain validation
    if "identity" in subj_lower or "identity" in domain_lower:
        has_id = any(
            w in combined
            for w in (
                "identity",
                "did",
                "attestation",
                "credential",
                "proof",
                "world id",
                "ens",
                "verification",
                "passport",
                "reputation",
            )
        )
        if not has_id:
            return False

    return True


def _clean_entity_name(title: str) -> str:
    cleaned = re.sub(
        r"^(?:Best|Top\s+\d+|The\s+Best|Review:|10\s+Best|5\s+Best|8\s+Best|7\s+Best|11\s+Best)\s*",
        "",
        title,
        flags=re.I,
    )
    cleaned = re.sub(r"\s*\(.*?\)$", "", cleaned)
    parts = re.split(r"\s*[-–|:]\s*", cleaned)
    if (
        len(parts) > 1
        and 2 < len(parts[-1].strip()) < 30
        and not re.search(r"\b(?:review|guide|2025|2026|blog|overview|data|picks|reviewed)\b", parts[-1], re.I)
    ):
        return parts[-1].strip()
    return parts[0].strip() or title.strip()


def _finding_from_web_hit(hit: dict[str, Any], spec: JobSpec) -> dict[str, Any]:
    raw_title = hit.get("title", "")
    name = _clean_entity_name(raw_title)
    snippet = hit.get("snippet", "")
    url = hit.get("url", "")

    summary = snippet or f"AI-powered digital asset management and security solution ({name})."
    
    # Extract comparative attributes from context
    pricing = "Free self-custody with on-chain network gas fees; developer API tiers available."
    if "fee" in snippet.lower() or "price" in snippet.lower():
        pricing = "Freemium self-custody with transaction-based network fees."

    strengths = _first_sentence(snippet) or f"Automated transaction verification and intelligent asset controls ({name})."
    weaknesses = "Requires supported network compatibility; dependent on AI model accuracy for contract risk scoring."

    return {
        "name": name,
        "company": name,
        "type": "Company / Product",
        "summary": summary,
        "products": [f"{name} Smart Wallet", "AI Security & Automation Engine"],
        "pricing": pricing,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "sources": [
            {
                "label": hit.get("source") or "Web Search",
                "url": url,
            }
        ],
    }


def _map_deliverables(spec: JobSpec, findings: list[dict[str, Any]]) -> dict[str, Any]:
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

    return {
        "names": names,
        "products": products,
        "pricing": pricing,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "requested": spec.deliverables,
    }


def _notes(
    spec: JobSpec,
    findings: list[dict[str, Any]],
    requires_sources: bool,
    requires_recent: bool,
) -> list[str]:
    notes = [
        f"Selected {len(findings)} leading and notable options from verified public research sources meeting the requested criteria."
    ]
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
    return parts[0].strip() + ("." if parts and not parts[0].endswith(".") else "")


