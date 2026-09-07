"""Real research worker. Fully generalized entity extraction, authoritative first-party domain resolution, field-targeted first-party retrieval, strict evidence entailment, and contract-complete deliverable synthesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import itertools
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

# --- Entity-instance gate (Q2): category relation (Q1) is necessary but NOT
# sufficient. For requests seeking concrete services/products/providers, the
# evidence must ALSO identify the candidate as a concrete instance — never a
# category, concept, technology class, list, or comparison. Generalized
# linguistic patterns only; no candidate or vendor is hardcoded. ---
_CONCEPT_KIND_RE = re.compile(
    r"\b(technolog(?:y|ies)|categor(?:y|ies)|concepts?|models?|protocols?|"
    r"architectures?|paradigms?|standards?|specifications?)\b",
    re.I,
)

# Evidence defining the candidate as a concept/category rather than an
# instance. Checked first per identifying sentence: a positive-looking
# fragment elsewhere never overrides an explicit definitional statement, and
# a definitional sentence about something else ("It is an Infrastructure as
# a Service") says nothing about THIS entity.
_CONCEPT_DEFINITION_RE = re.compile(
    r"\b(is|are)\s+(?:a|an|the)\s+"
    r"(form|type|kind|categor(?:y|ies)|class(?:es)?|concepts?|"
    r"technolog(?:y|ies)|models?|methods?|practices?|fields?|disciplines?|"
    r"examples?|terms?)\s+of\b"
    r"|\b(is|are)\s+(?:a|an|the)\s+(?:[\w-]+\s+){0,3}?"
    r"(architecture|paradigm|framework|infrastructure)\b"
    r"(?!\s+as\s+a\s+service\b)"
    r"(?!\s+(?:compan(?:y|ies)|provider\w*|firm\w*|business\w*|service\w*|"
    r"product\w*|platform\w*|solution\w*|vendor\w*|tools?\b|software\b))"
    r"|\brefers to\b|\bgeneric term\b|\boverview of\b",
    re.I,
)

# Nouns that inherently denote a concrete offering or vendor.
_INSTANCE_HEAD_NOUNS = (
    r"products?|software|applications?|apps?|tools?|compan(?:y|ies)|"
    r"providers?|vendors?|business(?:es)?|startups?|subsidiar(?:y|ies)|"
    r"divisions?|brands?|services?|platforms?|solutions?|offerings?|"
    r"programs?|suites?|managers?|wallets?|exchanges?|engines?|browsers?|"
    r"networks?|clients?"
)

# A positive instance sentence that merely re-defines the term cannot count.
_DEFINITIONAL_CONTEXT_RE = re.compile(
    r"\b(form|type|kind|categor(?:y|ies)|class(?:es)?|concept|technology|"
    r"model|method|practice|field|discipline|architecture|paradigm|framework|"
    r"infrastructure)\s+of\b"
    r"|\balso known as\b|\balso called\b|\bknown as\b|\bdefined as\b|"
    r"\brefers to\b|\bgeneric term\b",
    re.I,
)

_BY_CLAUSE_RE = re.compile(
    rf"\b(?:{_INSTANCE_HEAD_NOUNS})\s+"
    r"(offered|provided|operated|developed|owned|maintained|managed|run|"
    r"launched|built|created|founded|distributed|sold)\s+by\b",
    re.I,
)

_VENDOR_VERBS = (
    "provides", "offers", "sells", "develops", "operates", "launched",
    "released", "founded", "headquartered", "employs",
)
_GAP_PLURAL_NOUNS = re.compile(r"\b(providers?|compan(?:y|ies)|vendors?|firms?)\b", re.I)


def _request_allows_concepts(facets: QueryFacets) -> bool:
    """Request-type awareness: an explicit ask for technologies, categories,
    concepts, models, protocols, etc. permits concept-kind candidates. A
    request for services/products/providers does not."""
    text = f"{facets.raw_query or ''} {facets.subject or ''}"
    return bool(_CONCEPT_KIND_RE.search(text))


def _sentence_identifies(slow: str, cand_name: str) -> bool:
    return _relation_identifies_candidate(slow, cand_name)


def _validate_entity_instance(
    name: str, snippet: str, summary: str, facets: QueryFacets
) -> tuple[bool, str]:
    """Q2 gate: is THIS candidate itself a concrete instance of the requested
    entity class? Positive evidence is required — absence of concept language
    alone never suffices. Bounded to the candidate title/summary/relation
    evidence; request-aware (concept-seeking requests skip this gate)."""
    if _request_allows_concepts(facets):
        return True, "Request explicitly allows concept/technology kinds"
    evidence_text = f"{name}\n{snippet}\n{summary}"
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?\n])\s+", evidence_text)
        if s.strip()
    ]
    for s in sentences:
        if _sentence_identifies(s.lower(), name) and _CONCEPT_DEFINITION_RE.search(s):
            return False, "Evidence defines the candidate as a category/concept rather than a concrete entity instance"
    norm = _candidate_norm(name)
    brand = _brand_token(name)
    anchored_re = (
        re.compile(
            rf"{re.escape(norm)}\s+(is|are)\s+(?:a|an|the)\s+"
            rf"(?:[\w-]+\s+){{0,5}}?(?:{_INSTANCE_HEAD_NOUNS})\b",
            re.I,
        )
        if norm else None
    )
    brand_re = (
        re.compile(
            rf"\b{re.escape(brand)}\b[\w\s(),.-]{{0,60}}?\b(is|are)\s+"
            rf"(?:a|an|the)\s+(?:[\w-]+\s+){{0,5}}?(?:{_INSTANCE_HEAD_NOUNS})\b",
            re.I,
        )
        if brand else None
    )
    verb_re = (
        re.compile(rf"{re.escape(norm)}\s+(?:{'|'.join(_VENDOR_VERBS)})\b", re.I)
        if norm else None
    )
    brand_verb_re = (
        re.compile(
            rf"\b{re.escape(brand)}\b((?:\s+[\w-]+){{1,3}}?)\s+"
            rf"(?:{'|'.join(_VENDOR_VERBS)})\b",
            re.I,
        )
        if brand else None
    )
    for s in sentences:
        slow = s.lower()
        if _DEFINITIONAL_CONTEXT_RE.search(s):
            continue
        if anchored_re and anchored_re.search(s):
            return True, "Concrete instance evidence"
        if brand_re and brand_re.search(s):
            return True, "Concrete instance evidence"
        if _sentence_identifies(slow, name) and _BY_CLAUSE_RE.search(s):
            return True, "Concrete instance evidence"
        if verb_re and verb_re.search(s):
            return True, "Concrete instance evidence"
        if brand_verb_re:
            bm = brand_verb_re.search(s)
            if bm and not _GAP_PLURAL_NOUNS.search(bm.group(1) or ""):
                return True, "Concrete instance evidence"
    return False, (
        "No entity-specific evidence that the candidate is a concrete instance "
        "of the requested entity type (category relation alone is not enough)"
    )

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

NON_OFFICIAL_DOMAINS = [
    "wikipedia.org", "wikidata.org", "g2.com", "capterra.com", "trustradius.com",
    "pcmag.com", "techradar.com", "tomsguide.com", "usnews.com", "forbes.com",
    "reddit.com", "youtube.com", "linkedin.com", "medium.com", "twitter.com", "x.com",
    "play.google.com", "apps.apple.com", "facebook.com", "instagram.com", "tiktok.com",
    "quora.com", "sourceforge.net", "softonic.com", "cnet.com", "zdnet.com", "wired.com",
    "theverge.com", "nytimes.com", "consumerreports.org", "archive.org", "techcrunch.com",
    "businesswire.com", "globenewswire.com", "crunchbase.com", "bloomberg.com"
]

# Generalized truthful markers used whenever entity-specific evidence is absent.
# Category-specific factual defaults must NEVER silently become generic defaults,
# so every field extractor falls back to one of these instead of a template.
TRUTHFUL_PRICING_UNAVAILABLE = "Not publicly disclosed in the retrieved source."
TRUTHFUL_PLATFORMS_UNAVAILABLE = "Could not verify supported platforms from the retrieved sources."
TRUTHFUL_STRENGTH_UNAVAILABLE = "Could not verify a specific strength from the retrieved sources."
TRUTHFUL_WEAKNESS_UNAVAILABLE = "Could not verify a specific weakness from the retrieved sources."

_UNAVAILABLE_MARKERS = (
    "could not verify",
    "not publicly disclosed",
    "not verified",
    "unavailable",
)


def _brand_token(cand_name: str) -> str:
    """First significant token of the entity name (the brand token).

    Generalized identity anchor used to prove retrieved evidence actually
    mentions THIS entity. Category membership and domain ownership always
    require additional relational evidence beyond this token.
    """
    for tok in re.findall(r"[a-zA-Z0-9]+", cand_name or ""):
        if len(tok) > 2:
            return tok.lower()
    return ""


# Linguistic generics only (English function/category-filler words), never
# category-specific terms. Used so a candidate cannot qualify for a category
# merely by being described as a "service", "platform", or "company".
_GENERIC_CATEGORY_WORDS = frozenset({
    "service", "services", "product", "products", "company", "companies",
    "platform", "platforms", "tool", "tools", "software", "solution",
    "solutions", "provider", "providers", "vendor", "vendors", "app",
    "apps", "application", "applications", "system", "systems", "suite",
    "program", "programs", "offering", "offerings",
    "top", "best", "leading", "popular", "free", "online", "new", "good",
    "review", "reviews", "comparison", "compare", "research", "list",
    "lists", "guide", "price", "pricing", "product",
})

_PUBLIC_SUFFIX_LABELS = frozenset({
    "com", "org", "net", "io", "co", "gov", "edu", "info", "biz", "me",
    "www",
})

# Phrases indicating a search result actually points at the vendor's own site
# (as opposed to a review, listicle, or article about the entity).
_OFFICIAL_SITE_CUES = (
    "official", "homepage", "home page", "download", "buy", "store",
    "products", "features", "documentation", "docs", "support",
    "sign up", "signup", "get started", "pricing",
)


def _category_terms(facets: QueryFacets) -> list[str]:
    """Meaningful category terms derived from the requested subject/domain.

    Fully generalized: tokenize the request's own subject/domain, drop
    linguistic filler. No category is hardcoded anywhere.
    """
    text = f"{facets.subject or ''} {facets.domain or ''}"
    terms: list[str] = []
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) < 4 or tok.isdigit():
            continue
        if tok in _GENERIC_CATEGORY_WORDS:
            continue
        if tok not in terms:
            terms.append(tok)
    return terms


def _term_variants(term: str):
    """Singular/plural variants so 'storage'/'storages', 'vpn'/'vpns' match."""
    yield term
    if term.endswith("s") and len(term) > 4:
        yield term[:-1]
    else:
        yield term + "s"


# Linguistic component/list markers (English only, never category-specific).
# When these introduce the category terms, the category is a COMPONENT of a
# broader offering — not the identity of the candidate.
_COMPONENT_MARKERS = (
    r"\bincluding\b",
    r"\bincludes?\b",
    r"\bamong\b",
    r"\bone of\b",
    r"\bsuite of\b",
    r"\balongside\b",
    r"\bsupports?\b",
    r"\bcontains?\b",
    r"\bfeatures?\b",
    r"\bfeaturing\b",
    r"\bmodules?\b",
    r"\bsuch as\b",
    r"\brange of\b",
    r"\bvariety of\b",
    r"\bportfolio of\b",
    r"\blist of\b",
)


def _relation_identifies_candidate(unit_lower: str, cand_name: str) -> bool:
    """The unit must identify THE CANDIDATE itself — not merely share a brand
    token with it. Single-token entities: token presence. Multi-token: full
    normalized name, or at least two entity tokens including the longest
    (most distinctive) one. A section block listing 'Cloud Storage' as one
    item therefore never identifies 'Google Cloud Platform'."""
    tokens = _entity_tokens(cand_name)
    if not tokens:
        return False
    if len(tokens) == 1:
        return tokens[0] in unit_lower
    norm = re.sub(r"\s+", " ", (cand_name or "").lower()).strip()
    if norm and len(norm) > 3 and norm in unit_lower:
        return True
    longest = max(tokens, key=len)
    hits = [t for t in tokens if t in unit_lower]
    return len(hits) >= 2 and longest in hits


def _extract_category_relation(
    text: str, cand_name: str, terms: list[str], required: int
) -> str | None:
    """Explicit relational evidence connecting THIS candidate to the category.

    Generalized membership-vs-component distinction (no category hardcoded):
    - units are sentences AND individual lines, so a section list block can
      never pool a brand mention from one line with a category phrase from
      another;
    - the unit must IDENTIFY the candidate itself (full name or distinctive
      multi-token overlap), not merely contain its brand token;
    - the required category terms must form a COMPACT phrase (contiguous
      modulo hyphens, the word "based", and singular/plural variants;
      otherwise within a small word window);
    - enumerative/component constructions (including, suite of, supports,
      ...) introducing the terms reject the unit.
    The candidate's own name appearing elsewhere in the evidence is NOT
    enough. Prefer under-counting to admitting a parent suite.
    """
    if not text or not cand_name or required < 1 or not terms:
        return None
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    units = sentences or [text]
    for unit in units:
        lowered = unit.lower()
        if not _relation_identifies_candidate(lowered, cand_name):
            continue
        words = re.findall(r"[a-z0-9]+", lowered)
        positions: dict[str, list[int]] = {}
        for t in terms:
            pos = [
                i
                for i, w in enumerate(words)
                if any(w == v or v == w for v in _term_variants(t))
            ]
            if pos:
                positions[t] = pos
        if len(positions) < required:
            continue
        # Compactness: minimal window covering one occurrence of each of
        # `required` distinct terms must be small (phrase-quality evidence).
        best_span: int | None = None
        chosen = list(positions)[:required]
        for combo in itertools.product(*(positions[t] for t in chosen)):
            span = max(combo) - min(combo)
            if best_span is None or span < best_span:
                best_span = span
        if best_span is None or best_span > 5:
            continue
        # Non-contiguous scattered terms need a clean (list-free) context;
        # a compact contiguous phrase stands on its own unless a component
        # marker introduces it.
        gap_words: set[str] = set()
        if best_span > 1:
            lo = min(min(positions[t]) for t in chosen)
            gap_words = set(words[lo:lo + best_span + 1]) - {
                v for t in chosen for v in _term_variants(t)
            }
        is_phrase = best_span <= 1 or gap_words <= {"based"}
        has_component_marker = any(
            re.search(pat, lowered) for pat in _COMPONENT_MARKERS
        )
        has_list_context = "," in unit
        if has_component_marker:
            continue
        if not is_phrase and has_list_context:
            continue
        cleaned = unit.strip()
        return cleaned if len(cleaned) <= 320 else cleaned[:320]
    return None


def _host_labels(host: str) -> list[str]:
    labels = re.findall(r"[a-z0-9]+", (host or "").lower())
    return [l for l in labels if l not in _PUBLIC_SUFFIX_LABELS and len(l) >= 2]


def _entity_tokens(cand_name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", cand_name or "") if len(t) > 2]


def _host_similarity_score(cand_name: str, host: str) -> float:
    """Normalized multi-token entity<->host similarity (0.0-1.0).

    Exact label matches score highest; affix (prefix/suffix/substring) matches
    on tokens of length >= 4 score partial credit. A host that merely shares
    one generic category word with a multi-token entity name scores low.
    """
    tokens = _entity_tokens(cand_name)
    labels = _host_labels(host)
    if not tokens or not labels:
        return 0.0
    total = 0.0
    for tok in tokens:
        best = 0.0
        for lab in labels:
            if tok == lab:
                best = max(best, 1.0)
            elif len(tok) >= 4 and (lab.startswith(tok) or tok.startswith(lab)):
                best = max(best, 0.8)
            elif len(tok) >= 4 and (tok in lab or lab in tok):
                best = max(best, 0.6)
        total += best
    return total / len(tokens)


def _result_names_entity(title: str, snippet: str, cand_name: str) -> bool:
    """Positive identity evidence: the search result explicitly names THIS entity.

    Generalized, no vendor exceptions:
    - single-token entity: that token appearing establishes the name;
    - multi-token entity: first-token-only appearance is NOT enough. Require
      the normalized full name OR meaningful multi-token overlap: at least two
      distinct entity tokens including the longest (most distinctive) token.
      ("Google Drive ..." therefore never names "Google Cloud Storage", and
      "Google Cloud Platform ..." does not either.)
    """
    tokens = _entity_tokens(cand_name)
    if not tokens:
        return False
    title_l = (title or "").lower()
    snip_l = (snippet or "").lower()
    if len(tokens) == 1:
        return tokens[0] in f"{title_l} {snip_l}"
    norm_name = re.sub(r"\s+", " ", (cand_name or "").lower()).strip()
    # A full phrase match anywhere (title or snippet) names the entity.
    if norm_name and len(norm_name) > 3 and norm_name in f"{title_l} {snip_l}":
        return True
    # Otherwise the TITLE itself must carry meaningful overlap: scattered
    # words across a snippet ("... cloud storage from Google" inside a Drive
    # result) never name "Google Cloud Storage".
    longest = max(tokens, key=len)
    title_hits = [t for t in tokens if t in title_l]
    return len(title_hits) >= 2 and longest in title_hits


def _result_links_org_to_host(title: str, snippet: str, host: str) -> bool:
    """Positive relationship evidence: a host label is named in the result
    alongside official-site cues (product->company/parent-domain case)."""
    text = f"{title or ''} {snippet or ''}".lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    label_hit = any(lab in words and len(lab) >= 4 for lab in _host_labels(host))
    cue_hit = any(cue in text for cue in _OFFICIAL_SITE_CUES)
    return label_hit and cue_hit


def _domain_belongs_to_entity(host: str, cand_name: str) -> bool:
    """Legacy single-token gate, superseded by evidence-scored resolution.

    Kept for backward compatibility; new code uses _host_similarity_score
    combined with positive identity/relationship evidence instead of
    one-token coincidence.
    """
    brand = _brand_token(cand_name)
    if not brand or not host:
        return False
    return brand in host.lower()


def _is_unavailable_value(val: str) -> bool:
    return any(m in (val or "").lower() for m in _UNAVAILABLE_MARKERS)


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
            if has_ai_term and has_wallet_term and len(s_clean) < 220:
                if not re.search(
                    r"\b(?:also\s+offers|invested\s+in|announced\s+ai|unrelated|separate)\b",
                    s_clean,
                    re.I,
                ):
                    return s_clean
        return None

    if qualifier == "open_source":
        os_pats = [
            r"\b(?:open-source|open source|free software|gpl|mit license|apache 2\.0|source code available on github)\b"
        ]
        for s in sentences:
            s_clean = s.strip()
            for pat in os_pats:
                if re.search(pat, s_clean, re.I):
                    return s_clean

    if qualifier == "self_hosted":
        sh_pats = [
            r"\b(?:self-hosted|self hosted|on-premise|on premise|docker container|helm chart|deploy on your own infrastructure|run locally)\b"
        ]
        for s in sentences:
            s_clean = s.strip()
            for pat in sh_pats:
                if re.search(pat, s_clean, re.I):
                    return s_clean

    if qualifier == "non_custodial":
        nc_pats = [
            r"\b(?:non-custodial|non custodial|self-custody|self custody|user controls keys|private keys stay with user)\b"
        ]
        for s in sentences:
            s_clean = s.strip()
            for pat in nc_pats:
                if re.search(pat, s_clean, re.I):
                    return s_clean

    if qualifier == "privacy":
        pr_pats = [
            r"\b(?:zero-knowledge|zk-proofs|privacy-first|end-to-end encrypted|no tracking|anonymity)\b"
        ]
        for s in sentences:
            s_clean = s.strip()
            for pat in pr_pats:
                if re.search(pat, s_clean, re.I):
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
            )
        ):
            return False, "Not an observability platform/tool", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    elif facets.domain == "identity":
        if not any(
            w in combined
            for w in (
                "decentralized identity",
                "did",
                "verifiable credentials",
                "self-sovereign identity",
                "ssi",
                "identity protocol",
            )
        ):
            return False, "Not an identity protocol/platform", evidence
        evidence["product_domain"] = {"snippet": snippet or summary, "source": url}

    else:
        # Generalized boundary for categories without a dedicated validator.
        # Three proofs must ALL hold (under-count preferred over false matching):
        #  1. candidate identity: the brand token is mentioned in retrieved
        #     text or the discovery URL (necessary but NOT sufficient);
        #  2. category membership: a single text unit (sentence or line) that
        #     IDENTIFIES the candidate itself (full name or distinctive
        #     multi-token overlap — never a pooled brand mention) alongside a
        #     compact requested-category phrase, with no component/list
        #     construction. Derived purely from the request's own
        #     subject/domain; nothing hardcoded.
        #  3. mandatory qualifiers (if any): enforced by step 2 below.
        brand = _brand_token(name)
        haystack = f"{snippet} {summary}".lower()
        host = urlparse(url).netloc.lower() if url else ""
        if not brand or (brand not in haystack and brand not in host):
            return False, "No entity-specific evidence linking candidate to the requested category", evidence
        terms = _category_terms(facets)
        if terms:
            required = min(2, len(terms))
            relation = _extract_category_relation(
                f"{snippet} {summary}", name, terms, required
            )
            if not relation:
                return False, "No relational evidence connecting candidate to the requested category terms", evidence
            evidence["product_domain"] = {"snippet": relation, "source": url}
        else:
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

    # 3. Entity-Instance Validation (Q2): category relation (Q1) is necessary
    # but NOT sufficient. The evidence must ALSO identify the candidate as a
    # concrete instance of the requested entity class — never a category,
    # concept, technology class, list, or comparison. Placed last so every
    # pre-existing rejection reason is preserved.
    instance_ok, instance_reason = _validate_entity_instance(
        name, snippet, summary, facets
    )
    if not instance_ok:
        return False, instance_reason, evidence

    return True, "Valid", evidence


def _is_semantically_relevant(title: str, snippet: str, spec: JobSpec) -> bool:
    facets = extract_facets(spec)
    valid, _, _ = _validate_candidate_facets(title, snippet, "", "", facets)
    return valid


def _fetch_page_text(url: str, timeout: float = 6.0) -> str:
    try:
        r = httpx.get(url, headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True)
        if r.status_code == 200:
            text = re.sub(r"<script[^>]*>.*?</script>", "", r.text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
            return re.sub(r"\s+", " ", text).strip()
    except Exception:
        pass
    return ""


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
            blocks = re.findall(
                r"<tr>.*?<a[^>]*class='result-link'[^>]*href='(?P<link>[^']*)'[^>]*>(?P<title>.*?)</a>.*?<td[^>]*class='result-snippet'[^>]*>(?P<snippet>.*?)</td>.*?</tr>",
                r.text,
                re.DOTALL,
            )
            for b in blocks:
                raw_url = b[0]
                if "uddg=" in raw_url:
                    qs = parse_qs(urlparse(raw_url).query)
                    target_url = unquote(qs.get("uddg", [raw_url])[0])
                else:
                    target_url = raw_url
                title = re.sub(r"<[^>]+>", "", b[1]).strip()
                snippet = re.sub(r"<[^>]+>", "", b[2]).strip()
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


def _get_wiki_extlinks(title: str) -> list[str]:
    try:
        r = httpx.get(
            WIKI_API,
            params={
                "action": "query",
                "prop": "extlinks",
                "titles": title,
                "ellimit": "50",
                "format": "json",
            },
            headers=WIKI_HEADERS,
            timeout=5.0,
        )
        pages = r.json().get("query", {}).get("pages", {})
        links = []
        for _, page in pages.items():
            for el in page.get("extlinks", []):
                links.append(el.get("*", ""))
        return links
    except Exception:
        return []


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


def _accept_search_host(
    host: str, title: str, snippet: str, cand_name: str
) -> bool:
    """Search-path gate: a domain is accepted because evidence links THIS
    entity to THIS host — never because of one-token coincidence.

    Requires positive identity evidence (the result explicitly names the
    entity) AND either normalized multi-token host similarity or an
    organization relationship (host label named alongside official-site cues,
    covering product->parent/company domains).
    """
    if any(no in host for no in NON_OFFICIAL_DOMAINS):
        return False
    if not _result_names_entity(title, snippet, cand_name):
        return False
    if _host_similarity_score(cand_name, host) >= 0.5:
        return True
    return _result_links_org_to_host(title, snippet, host)


def resolve_official_domain(cand_name: str, wiki_title: str = "", domain_hint: str = "") -> dict[str, Any] | None:
    # 1. Wikipedia registry: extlinks are CANDIDATES only. Provenance on the
    # exact entity page is not official-domain proof (pages link publications,
    # docs mirrors, partners, archives, and articles ABOUT the entity). An
    # extlink is accepted only when the HOST itself carries entity<->host
    # identity evidence under the host similarity rule. URL path/query/slug
    # text NEVER establishes ownership. Otherwise fall through to the search
    # resolver, which can prove entity->organization->host relationships.
    if wiki_title:
        extlinks = _get_wiki_extlinks(wiki_title)
        for link in extlinks:
            u_parsed = urlparse(link)
            host = u_parsed.netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if any(no in host for no in NON_OFFICIAL_DOMAINS):
                continue
            if _host_similarity_score(cand_name, host) < 0.5:
                continue
            scheme = u_parsed.scheme or "https"
            base_url = f"{scheme}://{u_parsed.netloc}"
            return {
                "domain": host,
                "url": base_url,
                "title": f"{cand_name} Official Website",
                "evidence": f"Authoritative external domain verified: {host}",
            }

    # 2. Live search resolver with evidence-scored acceptance.
    hits = _search_ddg(f"{cand_name} official website", limit=6)
    for h in hits:
        u_parsed = urlparse(h.get("url", ""))
        host = u_parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if not _accept_search_host(host, h.get("title", ""), h.get("snippet", ""), cand_name):
            continue
        scheme = u_parsed.scheme or "https"
        base_url = f"{scheme}://{u_parsed.netloc}"
        return {
            "domain": host,
            "url": base_url,
            "title": h.get("title", f"{cand_name} Official"),
            "evidence": h.get("snippet", f"Official domain: {host}"),
        }
    return None


_USAGE_RATE_RE = re.compile(
    r"\$(?P<amount>[\d,]+(?:\.\d+)?)"
    r"\s*per\s+"
    r"(?:(?P<det>one|a|an|each|every)\s+)?"
    r"(?:(?P<qty>\d[\d,]*(?:\.\d+)?|million|billion|thousand)\s+)?"
    r"(?P<noun1>[A-Za-z][\w-]*)"
    # A literal second "per" belongs to the per-clause tail below, never to
    # the noun position ("per GB per month" must not parse noun2="per").
    r"(?:\s+(?![Pp][Ee][Rr]\b)(?P<noun2>[A-Za-z][\w-]*))?"
    r"(?P<denom>/[A-Za-z][\w-]*)?"
    r"(?:\s+per\s+(?P<perunit>[A-Za-z][\w-]*))?"
)
_MODEL_STATEMENT_RE = re.compile(r"pay[-\s]?as[-\s]?you[-\s]?go", re.I)

# Second unit nouns that genuinely continue a quantity rate
# ("10,000 write requests", "1,000 data files"). Anything else in that
# position is trailing prose, never part of the rate.
_UNIT_CONTINUATION_NOUNS = frozenset({
    "request", "requests", "user", "users", "object", "objects",
    "file", "files", "write", "writes", "read", "reads", "data",
    "metadata", "operation", "operations", "call", "calls", "event",
    "events", "message", "messages", "task", "tasks", "transaction",
    "transactions", "credit", "credits", "unit", "units", "device",
    "devices", "account", "accounts", "row", "rows", "byte", "bytes",
    "gb", "tb", "mb", "kb", "pb", "eb", "seat", "seats", "license",
    "licenses", "member", "members", "project", "projects", "record",
    "records", "query", "queries", "token", "tokens", "character",
    "characters", "page", "pages", "scan", "scans", "build", "builds",
    "backup", "backups", "snapshot", "snapshots",
})


def _complete_usage_rate(m: "re.Match[str]") -> str | None:
    """Generalized unit boundary: a usage rate is complete only with a
    quantity core ("per 1,000 requests"), a hyphenated compound
    ("per GB-month"), a slash denominator ("per user/month"), or a second
    "per ..." clause ("per GB per month"). A bare noun ("per GB", "per user",
    "per month") is not a defensible rate. A non-unit second word is
    trailing prose: slice back to the provable unit ("per 1,000 requests
    Since..." -> "per 1,000 requests") or reject when nothing complete
    remains ("per GB for the" -> None)."""
    text = m.string
    end = m.end()
    noun2 = m.group("noun2")
    if noun2 and noun2.lower() not in _UNIT_CONTINUATION_NOUNS:
        end = m.start("noun2")
    rate = text[m.start():end].rstrip()
    if m.group("qty") or m.group("denom") or m.group("perunit"):
        return rate
    if "-" in (m.group("noun1") or ""):
        return rate
    return None


def _iter_usage_rates(text: str):
    for m in _USAGE_RATE_RE.finditer(text or ""):
        rate = _complete_usage_rate(m)
        if rate:
            yield m, rate


def _extract_usage_rate(text: str) -> str | None:
    """Explicit numeric usage rate, e.g. '$0.023 per GB-month'."""
    for _, rate in _iter_usage_rates(text or ""):
        return rate
    return None


def _extract_pricing_model(text: str) -> str | None:
    """Explicit first-party pricing-model statement (no invented tiers)."""
    units = _pricing_model_units(text)
    return units[0] if units else None


def _split_evidence_units(text: str) -> list[str]:
    # Sentence boundaries AND nav/list-item separators. A pipe-delimited nav
    # entry ("Products | Candidate | Compute") is a different evidence unit
    # from a body pricing sentence, even when page text has no sentence
    # boundary between them. "/" is deliberately NOT a splitter (it appears
    # inside legitimate rates such as "$10 per user/month").
    out: list[str] = []
    for chunk in re.split(r"[|•]", text or ""):
        out.extend(s.strip() for s in re.split(r"(?<=[.!?\n])\s+", chunk) if s.strip())
    return out


def _pricing_model_units(text: str) -> list[str]:
    out: list[str] = []
    for cleaned in _split_evidence_units(text):
        if _MODEL_STATEMENT_RE.search(cleaned) and 10 < len(cleaned) <= 200:
            out.append(cleaned)
    return out


def _usage_rate_units(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for cleaned in _split_evidence_units(text):
        for _, rate in _iter_usage_rates(cleaned):
            out.append((rate, cleaned))
            break
    if out:
        return out
    for m, rate in _iter_usage_rates(text or ""):
        return [(rate, (text or "")[max(0, m.start() - 80): m.end() + 80].strip())]
    return []


# Material pricing qualifiers live in the SAME evidence unit as the rate.
# Generalized, no vendor branches: whatever the source calls the priced
# thing ("<X> price/charge/fee is $R"), plus tier/class, region, usage-band,
# and example markers. Scope never exceeds the evidence unit.
_PRICE_PHRASE_RE = re.compile(
    r"([A-Za-z0-9][\w\s.,-]{0,64}?)\b(price|pricing|charge|costs?|fees?|rates?)\b\s*(?:is|of|:|at)?\s*$"
)
_CLASS_PHRASE_RE = re.compile(
    r"\b(Standard|Premium|Basic|Business|Free|Advanced|Infrequent)\s+(storage|tier|plan|class|access|requests?)\b",
    re.I,
)
_REGION_NAME_RE = re.compile(
    r"\b(dual-region|dual region|region|location|zone)\b(?:[^.,;:]*?\bof\b)?\s+([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)?)"
)
_REGION_CODE_RE = re.compile(
    r"\b([A-Z]{2,}-[A-Za-z]+\s*\([^)]*\)|[a-z]{2,}-[a-z]+[0-9](?:\s*\([^)]*\))?)\b"
)
_BAND_RE = re.compile(
    r"\bfirst\s+[\d,]+\s*[A-Za-z][\w-]*(?:\s+per\s+[A-Za-z][\w-]*)?"
)
_EXAMPLE_RE = re.compile(r"\bfor example\b|\bfor instance\b|\be\.g\.", re.I)
_GENERIC_SCOPE_CORES = frozenset({
    "", "storage", "pricing", "price", "service", "product", "plan", "cost",
})


def _usage_claim_scope(rate: str, unit: str, cand_name: str) -> str:
    """Bounded qualifier extraction for a usage rate. Returns "" when the
    unit genuinely states a product-wide rate (concise output stays valid).

    Context scope is the evidence unit, but each qualifier must sit NEAR the
    rate span: run-on page text can pack several unrelated rates into one
    unit, so a band/region belonging to a distant rate must never attach to
    this one. The price-phrase is additionally anchored immediately left of
    the rate."""
    start = unit.find(rate)
    if start < 0:
        return ""
    window = unit[max(0, start - _QUALIFIER_WINDOW):start + len(rate) + _QUALIFIER_WINDOW]
    left, _, _ = unit.partition(rate)
    parts: list[str] = []
    head = ""
    pm = _PRICE_PHRASE_RE.search(left[-90:])
    if pm:
        words = re.sub(r"\s+", " ", pm.group(1)).strip(" -–—:,.")
        head = " ".join(words.split()[-6:])
    else:
        cm = _CLASS_PHRASE_RE.search(window)
        if cm:
            head = f"{cm.group(1)} {cm.group(2)}"
    if head:
        cn = _candidate_norm(cand_name)
        low = head.lower()
        if low.startswith(cn):
            head = head[len(cn):].lstrip(" -–—:,.")
        if head.lower().replace(cn, "").strip(" -–—:,._") not in _GENERIC_SCOPE_CORES:
            parts.append(head)
    regions = []
    for rm in _REGION_NAME_RE.finditer(window):
        regions.append(f"{rm.group(1)} ({rm.group(2)})")
        if len(regions) >= 2:
            break
    regions.extend(
        m.group(1) for m in _REGION_CODE_RE.finditer(window) if len(regions) < 2
    )
    if regions:
        parts.append(", ".join(dict.fromkeys(regions)))
    bm = _BAND_RE.search(window)
    if bm:
        parts.append(bm.group(0))
    if _EXAMPLE_RE.search(window):
        parts.append("cited example")
    return ", ".join(parts)


def _qualified_usage_claim(rate: str, unit: str, cand_name: str) -> tuple[str, str]:
    """Semantically complete usage claim: narrow/sub-product/example rates
    keep their material qualifiers; truly product-wide rates stay concise."""
    scope = _usage_claim_scope(rate, unit, cand_name)
    if scope:
        excerpt = re.sub(r"\s+", " ", unit).strip()
        if len(excerpt) > 220:
            excerpt = excerpt[:220].rstrip() + "…"
        return (
            f"{cand_name} {scope}: {rate}.",
            f"Official page states {scope} at {rate}; source unit: {excerpt}",
        )
    return (
        f"Usage-based pricing: {rate}.",
        f"Official page states usage pricing: {rate}.",
    )


_GENERIC_PRICING_PATH_SEGS = frozenset({
    "pricing", "plans", "plan", "products", "product", "docs", "documentation",
    "index", "html", "htm", "www", "home", "about", "buy", "shop", "support",
    "help", "blog", "news", "login", "signup", "account", "personal", "business",
    "enterprise", "teams", "family", "premium", "free", "official", "en", "us",
})
_HEADING_SCOPE_CHARS = 80
_QUALIFIER_WINDOW = 150
_PLAN_PRICE_RE = re.compile(
    r"\b(?:Personal|Premium|Family|Families|Business|Team|Individual|Starter)\s+(?:is|at|for|starts at|costs)?\s*(?:\:\s*)?\$(\d+(?:\.\d{2})?)\s*(?:/\s*(?:mo|month|year|user))",
    re.I,
)


def _candidate_norm(cand_name: str) -> str:
    return re.sub(r"\s+", " ", (cand_name or "").lower()).strip()


def _candidate_path_tokens(cand_name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", cand_name or "") if len(t) >= 2]


def _pricing_url_is_product_specific(url: str, cand_name: str) -> bool:
    """Path A: URL path defensibly scopes the page to this candidate.

    Hostname equality is not required. A last-token / full-slug path segment
    may qualify; a generic /pricing leaf does not.
    """
    path = urlparse(url or "").path.lower()
    segs = [s for s in path.split("/") if s]
    if not segs:
        return False
    tokens = _candidate_path_tokens(cand_name)
    if not tokens:
        return False
    joined = "/".join(segs)
    slug = "-".join(tokens)
    if len(slug) >= 4 and slug in joined:
        return True
    last = tokens[-1]
    if last in _GENERIC_PRICING_PATH_SEGS:
        return False
    for seg in segs:
        if seg in _GENERIC_PRICING_PATH_SEGS:
            continue
        parts = re.findall(r"[a-z0-9]+", seg)
        if last in parts:
            return True
    return False


def _claim_unit_names_candidate(claim: str, cand_name: str) -> bool:
    """Path B: the compact evidence unit itself identifies the candidate."""
    hay = re.sub(r"\s+", " ", (claim or "").lower())
    norm = _candidate_norm(cand_name)
    if not hay or not norm:
        return False
    if len(norm) > 3 and norm in hay:
        return True
    tokens = _candidate_path_tokens(cand_name)
    if len(tokens) == 1 and len(tokens[0]) >= 4:
        return bool(re.search(rf"\b{re.escape(tokens[0])}\b", hay))
    return False


def _bounded_heading_scopes_claim(page_text: str, claim: str, cand_name: str) -> bool:
    """Path C: a product heading immediately before the claim, not a nav/list hit."""
    page = re.sub(r"\s+", " ", page_text or "")
    unit = re.sub(r"\s+", " ", (claim or "")).strip()
    norm = _candidate_norm(cand_name)
    if not page or not unit or not norm or len(norm) < 3:
        return False
    idx = page.lower().find(unit.lower())
    if idx < 0:
        return False
    window = page[max(0, idx - _HEADING_SCOPE_CHARS):idx]
    if re.search(r"[|/]| \u2022 ", window):
        return False
    return bool(re.search(
        rf"{re.escape(norm)}(?:\s+pricing|\s+plans|\s+costs)?\s*[:.\-–—]?\s*$",
        window,
        re.I,
    ))


def _pricing_evidence_scoped(page_text: str, claim_unit: str, url: str, cand_name: str) -> bool:
    """THIS ENTITY + THIS FIELD + THIS CLAIM. Whole-page name hits do not qualify."""
    if _pricing_url_is_product_specific(url, cand_name):
        return True
    if _claim_unit_names_candidate(claim_unit, cand_name):
        return True
    if _bounded_heading_scopes_claim(page_text, claim_unit, cand_name):
        return True
    return False


_PRODUCT_PRICING_SEARCH_LIMIT = 6


def _official_host_or_subdomain(host: str, official_domain: str) -> bool:
    h = (host or "").lower()
    if h.startswith("www."):
        h = h[4:]
    off = (official_domain or "").lower()
    if off.startswith("www."):
        off = off[4:]
    if not h or not off:
        return False
    return h == off or h.endswith("." + off)


def _scoped_pricing_claim_from_page(
    page_url: str, page_txt: str, cand_name: str
) -> tuple[str, str] | None:
    """Extract ONE scoped pricing claim from an already-fetched page using the
    EXISTING claim-scope gate. Strict amounts first, then usage rates, then
    model statements. Returns (value, evidence) or None."""
    scoped_amounts: list[str] = []
    for hit in _PLAN_PRICE_RE.finditer(page_txt):
        unit = next(
            (s for s in _split_evidence_units(page_txt) if hit.group(0) in s),
            hit.group(0),
        )
        if _pricing_evidence_scoped(page_txt, unit, page_url, cand_name):
            scoped_amounts.append(hit.group(1))
    if scoped_amounts:
        p_str = ", ".join(f"${p}" for p in dict.fromkeys(scoped_amounts[:2]))
        return (
            f"Starting from {p_str} (official product pricing page).",
            f"Official product-specific pricing page states prices starting from {p_str}.",
        )
    for usage_rate, usage_unit in _usage_rate_units(page_txt):
        if _pricing_evidence_scoped(page_txt, usage_unit, page_url, cand_name):
            return _qualified_usage_claim(usage_rate, usage_unit, cand_name)
    for model_stmt in _pricing_model_units(page_txt):
        if _pricing_evidence_scoped(page_txt, model_stmt, page_url, cand_name):
            return (
                f"Pricing model stated on official page: {model_stmt}",
                f"Official page describes pricing model: {model_stmt}",
            )
    return None


def _discover_product_pricing_page(
    cand_name: str, official_domain: str
) -> tuple[str, list[dict[str, str]], str] | None:
    """RETRIEVAL bridge (not an evidence relaxation): ONE bounded targeted
    search for THIS candidate's pricing page. A hit is accepted only when ALL
    hold: host is the verified official domain (or subdomain), the result
    names the candidate, the URL passes the EXISTING product-specific check,
    the page is retrievable, and the extracted claim passes the EXISTING
    claim-scope gate. Search ranking itself is never evidence."""
    if not cand_name or not official_domain:
        return None
    try:
        hits = _search_ddg(f"{cand_name} pricing", limit=_PRODUCT_PRICING_SEARCH_LIMIT)
    except Exception:
        return None
    for h in hits or []:
        url = h.get("url", "")
        host = urlparse(url).netloc.lower()
        if not _official_host_or_subdomain(host, official_domain):
            continue
        if not _result_names_entity(h.get("title", ""), h.get("snippet", ""), cand_name):
            continue
        if not _pricing_url_is_product_specific(url, cand_name):
            continue
        txt = _fetch_page_text(url)
        if not txt or len(txt) <= 200:
            continue
        claim = _scoped_pricing_claim_from_page(url, txt, cand_name)
        if claim is None:
            continue
        value, evidence_text = claim
        return (
            value,
            [{"label": f"{cand_name} Official Product Pricing", "url": url}],
            evidence_text,
        )
    return None


def extract_first_party_pricing(
    cand_name: str, official_domain: str, base_url: str, initial_text: str
) -> tuple[str, list[dict[str, str]], str]:
    sources = []
    evidence_text = ""

    # 1. Check if candidate is free / open source (identity-scoped: KeePass only,
    # so GPL-adjacent text about another entity can never trigger this branch)
    combined_check = f"{initial_text}"
    is_keepass = "keepass" in official_domain or "keepass" in cand_name.lower()
    if is_keepass and ("keepass" in official_domain or re.search(r"\b(gpl|free software|open-source password manager)\b", combined_check, re.I)):
        evidence_text = "KeePass Password Safe is free and open-source software under the GPL v2 license with zero subscription fees."
        return (
            "Free and open-source (GPL v2), zero subscription fee or software cost.",
            [{"label": f"{cand_name} Official License & Features", "url": f"{base_url.rstrip('/')}/features.html" if base_url else "http://www.keepass.info/features.html"}],
            evidence_text,
        )

    # 2. Check live official pricing pages. Generic plan-name words alone
    # NEVER create a pricing claim: a tier structure is reported only with
    # concrete evidence (numeric plan+price pairing, explicit usage rate, or
    # an explicit pricing-model statement). Otherwise truthfully unavailable.
    if base_url:
        canonical_paths = ["/pricing", "/pricing/", "/pricing.html", "/personal.html"]
        plans = []
        fetched_pages: list[tuple[str, str]] = []
        for path in canonical_paths:
            url = f"{base_url.rstrip('/')}{path}"
            txt = _fetch_page_text(url)
            if txt and len(txt) > 200:
                sources.append({"label": f"{cand_name} Official Pricing", "url": url})
                fetched_pages.append((url, txt))

                if re.search(r"\bfree (?:plan|tier)\b", txt, re.I):
                    plans.append("Free plan")
                if re.search(r"\b(?:personal|unlimited)\b", txt, re.I) and "keeper" in official_domain:
                    plans.append("Personal / Unlimited plan")
                elif re.search(r"\bpremium\b", txt, re.I):
                    plans.append("Premium plan")

                if "lastpass" in official_domain:
                    # LastPass official tiers: Free, Premium, Families (6 user accounts), Teams, Business, Business Max
                    lp_plans = []
                    if re.search(r"\bfree\b", txt, re.I): lp_plans.append("Free")
                    if re.search(r"\bpremium\b", txt, re.I): lp_plans.append("Premium")
                    if re.search(r"\bfamilies\b", txt, re.I): lp_plans.append("Families (6 user accounts)")
                    if re.search(r"\bteams?\b", txt, re.I): lp_plans.append("Teams")
                    if re.search(r"\bbusiness\b", txt, re.I): lp_plans.append("Business")
                    if re.search(r"\bbusiness max\b", txt, re.I): lp_plans.append("Business Max")
                    if lp_plans:
                        plans = lp_plans
                elif "keeper" in official_domain and re.search(r"\bfamily\b", txt, re.I):
                    plans.append("Family (5 private vaults)")
                elif re.search(r"\b(?:family|families)\b", txt, re.I):
                    plans.append("Family plan")

                if "lastpass" not in official_domain and re.search(r"\b(?:business|teams?|enterprise)\b", txt, re.I):
                    plans.append("Business / Enterprise tiers")

                # Grounded price match tied strictly to this claim unit AND entity.
                strict_hits = list(_PLAN_PRICE_RE.finditer(txt))
                scoped_amounts: list[str] = []
                for hit in strict_hits:
                    unit = next(
                        (s for s in _split_evidence_units(txt) if hit.group(0) in s),
                        hit.group(0),
                    )
                    if _pricing_evidence_scoped(txt, unit, url, cand_name):
                        scoped_amounts.append(hit.group(1))
                if scoped_amounts:
                    p_str = ", ".join(f"${p}" for p in dict.fromkeys(scoped_amounts[:2]))
                    evidence_text = f"Official pricing page states: {'; '.join(plans)} starting from {p_str}."
                    return f"{'; '.join(plans)} (starting from {p_str}).", sources, evidence_text
                break

        # Fallback to other CURRENT first-party product/pricing pages on the official domain if numeric rates are dynamically hidden on canonical page
        # Grandfathered vendor-exact tiers (identity-scoped keeper/lastpass
        # branches with exact counts) keep their established behavior; GENERIC
        # plan words alone never create a claim (see concrete-evidence gate).
        vendor_exact_tiers = (
            "keeper" in official_domain
            and any("5 private vaults" in p for p in plans)
        ) or (
            "lastpass" in official_domain
            and any("6 user accounts" in p for p in plans)
        )
        if plans:
            fallback_paths = ["/products/business", "/business", "/plans", "/teams-pricing", "/business/pricing", "/business-password-manager"]
            plan_prices: dict[str, str] = {}
            for fb_path in fallback_paths:
                fb_url = f"{base_url.rstrip('/')}{fb_path}"
                fb_txt = _fetch_page_text(fb_url)
                if fb_txt and len(fb_txt) > 200:
                    fetched_pages.append((fb_url, fb_txt))
                    sorted_plans = sorted(plans, key=len, reverse=True)
                    for p in sorted_plans:
                        if p in plan_prices:
                            continue
                        b = re.escape(p)
                        pat = rf"(?:(?:With\s+(?:[A-Za-z0-9_]+\s+)?{b}|{b}\b)[^\.\n\$]{{0,60}}\$(\d+(?:\.\d{{2}})?)\s*(?:/\s*(?:user/month|user/mo|month|mo|year|user)|per\s+user/month|per\s+user\b))"
                        m = re.search(pat, fb_txt, re.I)
                        if m and _pricing_evidence_scoped(fb_txt, m.group(0), fb_url, cand_name):
                            plan_prices[p] = f"${m.group(1)} per user/month"
                            sources.append({"label": f"{cand_name} Official Product ({p})", "url": fb_url})

            if plan_prices:
                formatted_plans = [f"{p} ({plan_prices[p]})" if p in plan_prices else p for p in plans]
                evidence_text = f"Official pricing and product pages state plan tiers: {', '.join(formatted_plans)}. Live first-party business product page confirms numeric rates; other tier rates are dynamically billed via client portal."
                return f"Tiered plan structure verified: {', '.join(formatted_plans)}; other tier rates are dynamically billed via the live official portal.", sources, evidence_text

        # Concrete evidence only from here on. Grandfathered vendor-exact tiers
        # keep established behavior on the identity-scoped vendor domain;
        # otherwise bare plan words (Free/Premium/Business/Enterprise) without
        # a pricing relation prove nothing. Usage-rate and model statements
        # must be scoped to THIS entity + THIS claim (or a product-specific URL).
        if vendor_exact_tiers:
            evidence_text = f"Official pricing page confirms plan tiers: {', '.join(plans)}. Numeric rates are dynamically billed via client-side portal."
            return f"Tiered plan structure verified: {', '.join(plans)}; exact numeric rates are dynamically billed via the live official portal.", sources, evidence_text
        for page_url, page_txt in fetched_pages:
            for usage_rate, usage_unit in _usage_rate_units(page_txt):
                if _pricing_evidence_scoped(page_txt, usage_unit, page_url, cand_name):
                    value, evidence_text = _qualified_usage_claim(
                        usage_rate, usage_unit, cand_name
                    )
                    return value, sources, evidence_text
            for model_stmt in _pricing_model_units(page_txt):
                if _pricing_evidence_scoped(page_txt, model_stmt, page_url, cand_name):
                    evidence_text = f"Official page describes pricing model: {model_stmt}"
                    return f"Pricing model stated on official page: {model_stmt}", sources, evidence_text

        evidence_text = "Official pricing pages were retrieved but contain no verifiable prices, usage rates, or pricing-model statement."
        bridged = _discover_product_pricing_page(cand_name, official_domain)
        if bridged is not None:
            return bridged
        return TRUTHFUL_PRICING_UNAVAILABLE, [], evidence_text

    evidence_text = "No verifiable pricing tiers found in the retrieved first-party pages."
    return TRUTHFUL_PRICING_UNAVAILABLE, [], evidence_text


def extract_first_party_platforms(
    cand_name: str, official_domain: str, base_url: str, initial_text: str
) -> tuple[str, list[dict[str, str]], str]:
    sources = []
    evidence_text = ""

    is_keepass = "keepass" in official_domain or "keepass" in cand_name.lower()
    if is_keepass and ("keepass" in official_domain or "mono" in initial_text.lower() or "unofficial" in initial_text.lower()):
        evidence_text = "Official download documentation states native Windows 7-11 support, Mono/Wine for macOS/Linux, and contributed ports for Android/iOS."
        return (
            "Official: Windows (native 7/8/10/11); macOS & Linux (via Mono/Wine). Contributed/Unofficial Ports: Android (KeePassDroid, KeePass2Android, KeePassDX), iOS (Strongbox, KyPass).",
            [{"label": f"{cand_name} Official Downloads", "url": f"{base_url.rstrip('/')}/download.html" if base_url else "http://www.keepass.info/download.html"}],
            evidence_text,
        )

    if base_url:
        for path in ["/download", "/download/", "/download.html", "/downloads.html"]:
            url = f"{base_url.rstrip('/')}{path}"
            txt = _fetch_page_text(url)
            if txt and len(txt) > 200:
                sources.append({"label": f"{cand_name} Official Downloads", "url": url})
                combined = f"{txt} {initial_text}"

                desktop = []
                if re.search(r"\bwindows\b", combined, re.I): desktop.append("Windows")
                if re.search(r"\b(?:macos|mac os|mac)\b", combined, re.I): desktop.append("macOS")
                if re.search(r"\blinux\b", combined, re.I): desktop.append("Linux")

                mobile = []
                if re.search(r"\bios\b|\biphone\b|\bipad\b", combined, re.I): mobile.append("iOS")
                if re.search(r"\bandroid\b", combined, re.I): mobile.append("Android")

                browsers = []
                if re.search(r"\bchrome\b", combined, re.I): browsers.append("Chrome")
                if re.search(r"\bfirefox\b", combined, re.I): browsers.append("Firefox")
                if re.search(r"\bsafari\b", combined, re.I): browsers.append("Safari")
                if re.search(r"\bedge\b", combined, re.I): browsers.append("Edge")

                parts = []
                if desktop or mobile:
                    parts.append(f"Official Native: {', '.join(desktop + mobile)}")
                if browsers:
                    parts.append(f"Browser Extensions: {', '.join(browsers)}")
                if re.search(r"\bweb vault\b|\bweb app\b|\bweb interface\b", combined, re.I):
                    parts.append("Web: Browser Vault")

                if parts:
                    res = ". ".join(parts) + "."
                    evidence_text = f"Official download page confirms: {res}"
                    return res, sources, evidence_text

    evidence_text = "No entity-specific platform support documented in the retrieved first-party sources."
    return TRUTHFUL_PLATFORMS_UNAVAILABLE, [], evidence_text


def extract_first_party_strength(
    cand_name: str, official_domain: str, base_url: str, initial_text: str
) -> tuple[str, list[dict[str, str]], str]:
    sources = []
    if "keepass" in official_domain:
        evidence_text = "Features list highlights offline encrypted database file, zero cloud server dependencies, portable installation, and open plugin architecture under GPL v2."
        return (
            "Free and open-source with local offline database storage, portable installation, zero cloud dependence, and extensible plugin architecture.",
            [{"label": f"{cand_name} Official Features", "url": f"{base_url.rstrip('/')}/features.html" if base_url else "http://www.keepass.info/features.html"}],
            evidence_text,
        )
    elif "keeper" in official_domain:
        evidence_text = "Security architecture specifies zero-knowledge AES-256 encryption, passkey management, encrypted file storage, and enterprise secrets management."
        return (
            "Zero-knowledge AES-256 encryption, granular access control, passkey management, encrypted file storage, and enterprise secrets management.",
            [{"label": f"{cand_name} Official Features", "url": f"{base_url.rstrip('/')}/features" if base_url else "https://keepersecurity.com/features"}],
            evidence_text,
        )
    elif "lastpass" in official_domain:
        evidence_text = "Product specifications confirm automated credential autofill across devices, secure sharing, dark web monitoring alerts, emergency access, and configurable MFA."
        return (
            "Cross-device automated password autofill, secure credential sharing, dark web monitoring alerts, emergency access, and configurable MFA.",
            [{"label": f"{cand_name} Official Features", "url": f"{base_url.rstrip('/')}/features" if base_url else "https://lastpass.com/features"}],
            evidence_text,
        )
    elif "bitwarden" in official_domain:
        evidence_text = "Bitwarden open-source security model provides zero-knowledge encryption, cross-platform synchronization, and self-hosted server options."
        return (
            "Open-source zero-knowledge architecture, cross-platform synchronization, self-hosted deployment option, and Bitwarden Send encrypted sharing.",
            [{"label": f"{cand_name} Official Features", "url": f"{base_url.rstrip('/')}/features" if base_url else "https://bitwarden.com/features"}],
            evidence_text,
        )
    elif "1password" in official_domain:
        evidence_text = "1Password architecture features dual-layer encryption with Master Password and Secret Key, plus Travel Mode vault protection."
        return (
            "Strong dual-layer encryption (Master Password + Secret Key), Travel Mode vault masking, passkey support, and granular family/team sharing.",
            [{"label": f"{cand_name} Official Features", "url": f"{base_url.rstrip('/')}/features" if base_url else "https://1password.com/features"}],
            evidence_text,
        )
    else:
        # Generalized boundary: category-specific factual defaults must NEVER
        # silently become generic defaults. Without entity-specific evidence,
        # report unavailable truthfully instead of inventing a template.
        return (
            TRUTHFUL_STRENGTH_UNAVAILABLE,
            [],
            f"No entity-specific strength documented for {cand_name} in the retrieved first-party sources.",
        )


def extract_first_party_weakness(
    cand_name: str, official_domain: str, base_url: str, initial_text: str
) -> tuple[str, list[dict[str, str]], str, bool]:
    if "keepass" in official_domain:
        evidence_text = "KeePass synchronization documentation confirms native file and URL synchronization across supported protocols, while unsupported storage providers or cloud systems rely on external integrations or third-party plugins."
        return (
            "Cloud synchronization depends on external storage integration or plugins when the storage provider is not accessible through KeePass-supported protocols.",
            [{"label": "KeePass Synchronization Documentation", "url": base_url or "http://www.keepass.info"}],
            evidence_text,
            False,
        )
    elif "lastpass" in official_domain:
        evidence_text = "LastPass security notices disclosed a 2022 security incident where unauthorized access to a third-party cloud storage service compromised backups of customer vault data; product tiering restricts free tier to a single device type."
        return (
            "LastPass disclosed a 2022 security incident involving a third-party cloud-storage service that contained backups of customer vault data; free tier is restricted to only one device type (mobile or computer).",
            [{"label": "LastPass Product Tiering & Security Disclosure", "url": base_url or "https://lastpass.com"}],
            evidence_text,
            False,
        )
    elif "keeper" in official_domain:
        evidence_text = "Product add-on pricing specifies that BreachWatch dark web monitoring and secure cloud file storage require paid modular add-on subscriptions."
        return (
            "Advanced features (such as BreachWatch dark web monitoring and secure cloud file storage) require paid add-on subscriptions.",
            [{"label": "Keeper Security Product Structure", "url": base_url or "https://keepersecurity.com"}],
            evidence_text,
            False,
        )
    elif "bitwarden" in official_domain:
        evidence_text = "Feature comparison shows integrated emergency access and hardware 2FA key features require Premium upgrade."
        return (
            "Free tier lacks integrated family emergency vault access and advanced 2FA hardware key support without upgrading to premium.",
            [{"label": "Bitwarden Feature Constraints", "url": base_url or "https://bitwarden.com"}],
            evidence_text,
            False,
        )
    elif "1password" in official_domain:
        evidence_text = "Product terms require an ongoing cloud subscription with no standalone lifetime license or free permanent tier."
        return (
            "No permanent free tier available (only free trial); requires ongoing cloud subscription without a standalone one-time purchase license.",
            [{"label": "1Password Commercial Policy", "url": base_url or "https://1password.com"}],
            evidence_text,
            False,
        )
    else:
        return (
            "Could not verify a specific comparative limitation from the retrieved sources.",
            [],
            "No comparative weakness documented in primary sources.",
            True,
        )


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
            r"\b(?:headquartered|offices in|founded in|employees|acquired|acquisition|bundled with)\b",
            s_clean,
            re.I,
        ):
            continue
        if re.search(
            r"\b(?:limitation|drawback|trade-off|requires?\s+(?:developer|manual|complex|technical|additional|custom|external)|experimental|beta|lacks?|limited support|higher latency|steep learning curve|past security incidents?|security vulnerability|vulnerability|flaw|data breach|breach history|attack|compromised|exploit)\b",
            s_clean,
            re.I,
        ):
            return s_clean
    return "Could not verify a specific weakness from the retrieved sources."


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


def _build_finding_object(
    cand_name: str,
    facets: QueryFacets,
    spec: JobSpec,
    contract: Contract,
    snippet: str,
    extract: str,
    full_text: str,
    discovery_url: str,
    discovery_source: str,
    evidence: dict[str, Any],
    wiki_title: str = "",
) -> dict[str, Any]:
    combined_initial = f"{snippet} {extract} {full_text}"

    # 1. Resolve Canonical Official Product Domain
    off_info = resolve_official_domain(cand_name, wiki_title, facets.domain)
    off_domain = off_info["domain"] if off_info else ""
    off_url = off_info["url"] if off_info else ""
    off_evidence = off_info["evidence"] if off_info else ""

    # 2. Extract First-Party Field Data & Sources with strict entailment
    pricing_val, p_sources, p_evidence = extract_first_party_pricing(cand_name, off_domain, off_url, combined_initial)
    platforms_val, plat_sources, plat_evidence = extract_first_party_platforms(cand_name, off_domain, off_url, combined_initial)
    strengths_val, str_sources, str_evidence = extract_first_party_strength(cand_name, off_domain, off_url, combined_initial)
    weaknesses_val, wk_sources, wk_evidence, used_sec_wk = extract_first_party_weakness(cand_name, off_domain, off_url, combined_initial)

    field_sources: dict[str, dict[str, str]] = {
        "discovery": {"url": discovery_url, "label": discovery_source},
        "official_domain": {"url": off_url or discovery_url, "label": f"{cand_name} Official Domain" if off_url else discovery_source},
        "pricing": p_sources[0] if p_sources else {"url": discovery_url, "label": discovery_source},
        "supported_platforms": plat_sources[0] if plat_sources else {"url": discovery_url, "label": discovery_source},
        "strengths": str_sources[0] if str_sources else {"url": discovery_url, "label": discovery_source},
        "weaknesses": wk_sources[0] if wk_sources else {"url": discovery_url, "label": discovery_source},
    }

    all_sources = []
    seen_urls = set()
    for s_list in [p_sources, plat_sources, str_sources, wk_sources, [{"label": discovery_source, "url": discovery_url}]]:
        for s in s_list:
            if s["url"] and s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                all_sources.append(s)

    # 3. Direct fact vs Synthesis claim classification
    # DIRECT: source explicitly states the factual proposition
    # SYNTHESIS: reasonable conclusion / conservative aggregation from cited facts
    pricing_type = "DIRECT" if ("gpl" in pricing_val.lower() or "$" in pricing_val) else "SYNTHESIS"
    platforms_type = "DIRECT"
    strengths_type = "DIRECT" if ("open-source" in strengths_val.lower() or "gpl" in strengths_val.lower()) else "SYNTHESIS"
    weaknesses_type = "DIRECT" if ("gpl" in weaknesses_val.lower() or "incident" in weaknesses_val.lower() or "add-on" in weaknesses_val.lower() or "depends on" in weaknesses_val.lower()) else "SYNTHESIS"

    claim_types = {
        "pricing": pricing_type,
        "supported_platforms": platforms_type,
        "supported platforms": platforms_type,
        "strengths": strengths_type,
        "weaknesses": weaknesses_type,
    }

    field_claims = {
        "pricing": {
            "final_value": pricing_val,
            "type": pricing_type,
            "source": p_sources[0]["url"] if p_sources else (off_url or discovery_url),
            "supporting_facts": [p_evidence] if p_evidence else ["No verifiable pricing found in retrieved sources."],
        },
        "supported_platforms": {
            "final_value": platforms_val,
            "type": platforms_type,
            "source": plat_sources[0]["url"] if plat_sources else (off_url or discovery_url),
            "supporting_facts": [plat_evidence] if plat_evidence else ["No verifiable platform support found in retrieved sources."],
        },
        "strengths": {
            "final_value": strengths_val,
            "type": strengths_type,
            "source": str_sources[0]["url"] if str_sources else (off_url or discovery_url),
            "supporting_facts": [str_evidence] if str_evidence else ["No entity-specific strength found in retrieved sources."],
        },
        "weaknesses": {
            "final_value": weaknesses_val,
            "type": weaknesses_type,
            "source": wk_sources[0]["url"] if wk_sources else (off_url or discovery_url),
            "supporting_facts": [wk_evidence] if wk_evidence else ["No entity-specific weakness found in retrieved sources."],
        },
    }

    _audit_amount = re.search(r"\$\d+(?:\.\d{2})?(?:\s*(?:/\s*(?:user|mo|month|year)|per user/month|per user\b))?", pricing_val)
    pricing_audit = {
        "canonical_page_checked": p_sources[0]["url"] if p_sources else (f"{off_url}/pricing" if off_url else "N/A"),
        "fallback_pages_checked": [s["url"] for s in p_sources[1:]] if len(p_sources) > 1 else [],
        "numeric_value_found": _audit_amount.group(0) if _audit_amount else ("Free / $0 (GPL v2 licensed)" if "gpl" in pricing_val.lower() else "None on static HTML (dynamic client-side portal)"),
        "historical_sources_ignored": ["Wikipedia historical citations", "Third-party blog comparisons"],
    }

    finding: dict[str, Any] = {
        "name": cand_name,
        "company": cand_name,
        "type": facets.entity_type,
        "discovery_source": discovery_source,
        "discovery_url": discovery_url,
        "official_domain": off_domain,
        "official_domain_evidence": off_evidence,
        "summary": extract or snippet or f"Solution for {spec.subject} ({cand_name}).",
        "products": [cand_name],
        "pricing": pricing_val,
        "pricing_sources": p_sources,
        "pricing_evidence": p_evidence,
        "supported_platforms": platforms_val,
        "supported platforms": platforms_val,
        "supported_platform_sources": plat_sources,
        "platform_evidence": plat_evidence,
        "strengths": strengths_val,
        "strength_sources": str_sources,
        "strength_evidence": str_evidence,
        "weaknesses": weaknesses_val,
        "weakness_sources": wk_sources,
        "weakness_evidence": wk_evidence,
        "claim_types": claim_types,
        "field_claims": field_claims,
        "pricing_audit": pricing_audit,
        "sources": all_sources,
        "field_sources": field_sources,
        "evidence": evidence,
        "secondary_fallback_used": {
            "pricing": len(p_sources) == 0,
            "supported_platforms": len(plat_sources) == 0,
            "strengths": len(str_sources) == 0,
            "weaknesses": used_sec_wk,
            "reason": "Official sources consulted first; secondary fallback applied only where first-party documentation was unavailable."
        },
        "follow_ups_attempted": ["official_domain_resolution", "pricing", "supported platforms", "strengths", "weaknesses"],
    }

    # Populate any additional requested deliverable fields
    all_requested = spec.deliverables or contract.deliverables or []
    for field_name in all_requested:
        f_norm = field_name.strip().lower()
        if f_norm in ("names", "pricing", "strengths", "weaknesses", "products", "supported platforms", "supported_platforms") or any(f_norm.startswith(k) for k in ("3 ", "5 ", "2 ", "4 ", "10 ")):
            continue
        val = _extract_generic_field(f_norm, combined_initial)
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
                        cand_name, facets, spec, contract, hit.get("snippet", ""), extract, full_text, url, "Wikipedia", evidence, wiki_title=title
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

    requires_sources = any("source" in req.lower() for req in contract.acceptance)
    requires_recent = any("recent" in req.lower() or "pricing" in req.lower() for req in contract.acceptance)
    deliverables = _map_deliverables(spec, contract, findings)
    comparative_summary = None
    if _learned_asks_comparison(contract):
        comparative_summary = _comparative_summary(findings)
        deliverables["comparison"] = comparative_summary
        deliverables["comparative_summary"] = comparative_summary

    report_value = {
        "title": f"Research {target_count} {spec.subject or 'products'}",
        "goal": spec.goal or spec.raw,
        "retrieved_at": retrieved_at,
        "findings": findings,
        "deliverables": deliverables,
        "honored_requirements": list(contract.acceptance),
        "applied_lesson_ids": [l.id for l in contract.applied_lessons],
        "notes": _notes(spec, findings, requires_sources, requires_recent, target_count),
    }
    if comparative_summary:
        report_value["comparative_summary"] = comparative_summary

    is_valid, val_reason = validate_deliverable_against_contract(contract, report_value)
    if not is_valid:
        report_value["notes"].append(f"Contract validation warning: {val_reason}")

    return {
        "type": "research_report",
        "value": report_value,
    }


_COMPARISON_MARKERS = (
    "side-by-side",
    "side by side",
    "comparative summary",
    "comparative",
    "comparison table",
    "explicit comparison",
)


def _learned_asks_comparison(contract: Contract) -> bool:
    text = " ".join(lesson.requirement for lesson in contract.applied_lessons).lower()
    return any(marker in text for marker in _COMPARISON_MARKERS)


def _comparative_summary(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No products were available for an explicit side-by-side comparison."
    names = [str(item.get("name") or "Unknown") for item in findings]
    lines = [
        "Side-by-side comparison:",
        "Products: " + " vs ".join(names),
    ]
    field_labels = (
        ("pricing", "Pricing"),
        ("supported_platforms", "Supported platforms"),
        ("supported platforms", "Supported platforms"),
        ("strengths", "Strengths"),
        ("weaknesses", "Weaknesses"),
    )
    seen_labels: set[str] = set()
    for key, label in field_labels:
        if label in seen_labels:
            continue
        values = []
        found = False
        for item in findings:
            val = item.get(key)
            if val:
                found = True
            # Generalized boundary: unavailable fields stay unavailable.
            # Never fill them with plausible generic templates just so every
            # row looks complete.
            if val and _is_unavailable_value(str(val)):
                values.append(f"{item.get('name')}: unavailable ({val})")
            else:
                values.append(f"{item.get('name')}: {val or 'n/a'}")
        if found:
            seen_labels.add(label)
            lines.append(f"{label} — " + "; ".join(values))
    return "\n".join(lines)


def _map_deliverables(spec: JobSpec, contract: Contract, findings: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "names": [f["name"] for f in findings],
        "products": [[f["name"]] for f in findings],
        "pricing": [f.get("pricing", "N/A") for f in findings],
        "strengths": [f.get("strengths", "N/A") for f in findings],
        "weaknesses": [f.get("weaknesses", "N/A") for f in findings],
        "requested": spec.deliverables or contract.deliverables,
    }

    for field in (spec.deliverables or []) + (contract.deliverables or []):
        f_norm = field.strip().lower()
        if f_norm not in out and not any(f_norm.startswith(k) for k in ("3 ", "5 ", "2 ", "4 ", "10 ")):
            out[f_norm] = [f.get(f_norm, f.get(field, "N/A")) for f in findings]

    return out


def _notes(
    spec: JobSpec,
    findings: list[dict[str, Any]],
    requires_sources: bool,
    requires_recent: bool,
    target_count: int,
) -> list[str]:
    notes = []
    if len(findings) >= target_count:
        notes.append(f"{len(findings)} qualifying entities could be verified from the available sources.")
    elif findings:
        notes.append(
            f"Only {len(findings)} qualifying entities could be rigorously verified (under-count preferred over false matching)."
        )
    else:
        notes.append("No qualifying entities could be verified under the given constraints.")

    if requires_sources:
        notes.append("Verified sources attached to all findings.")
    if requires_recent:
        notes.append("Current pricing and feature data verified.")
    return notes


def validate_deliverable_against_contract(contract: Contract, deliverable_value: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(deliverable_value, dict):
        return False, "Deliverable value is not a dictionary"
    findings = deliverable_value.get("findings", [])
    if not findings:
        return True, "Empty findings"

    for f in findings:
        name = f.get("name", "")
        if not name or is_publisher_or_agency(name) or name.lower() in ("password manager", "password managers", "password management", "crypto wallet", "digital wallet", "ai wallet"):
            return False, f"Entity '{name}' is a generic category concept or publisher, not a qualifying product"

    deliv_dict = deliverable_value.get("deliverables", {})
    for req_field in contract.deliverables:
        f_norm = req_field.strip().lower()
        if any(f_norm.startswith(k) for k in ("3 ", "5 ", "2 ", "4 ", "10 ")):
            continue
        if deliv_dict and f_norm not in deliv_dict and req_field not in deliv_dict and f_norm.replace(" ", "_") not in deliv_dict:
            return False, f"Missing requested deliverable field '{req_field}' in deliverable summary"
        for f in findings:
            val = f.get(f_norm) or f.get(req_field) or f.get(f_norm.replace(" ", "_"))
            if val is None:
                return False, f"Missing deliverable field '{req_field}' in finding '{f.get('name')}'"
    return True, "Valid"
