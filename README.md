# PRIOR

**[LIVE APP](https://prior.103-195-188-198.sslip.io)** &middot; **[GITHUB](https://github.com/Techkeyy/prior)** &middot; **[Fresh-Session Proof](evidence/fresh-session-prior.json)** &middot; **[Base B20 Evidence](evidence/base-b20-read.json)** &middot; **[Stable Deployment Evidence](evidence/stable-deployment-flow.json)**

Hire an AI agent. When the work is wrong, keep the lesson. The next contract gets stricter.

> *"I already told the last agent to cite verifiable sources. Why am I typing that again?"*

PRIOR is a consumer-facing application for hiring AI agents that learns from previous jobs.
**PRIOR doesn't just remember the job. It remembers what the job taught us and applies that lesson to future jobs.**

Submitted to Sibyl Labs Hackathon (1–10 Sep 2026 UTC) &middot; MIT License.

---

## Why Sibyl Memory is Load-Bearing

PRIOR is not a notepad or a chat history. A rejected job outcome becomes a user-approved lesson stored as a WARM entity in **Sibyl Memory**. A fresh, independent session queries Sibyl, discovers applicable lessons, and **mutates the future job contract and worker requirements** before the next agent is hired.

If you delete Sibyl Memory, fresh sessions start blind, cannot recall past mistakes, and the second contract does not change.

```
JOB 1 (AI Wallets) -> Reject ("Material factual claims must include source links") -> User Approves Lesson -> Real Sibyl Write
                                            |
                                  FRESH PROCESS / SESSION
                                            |
JOB 2 (DEXs)       -> Sibyl Query  -> Contract Mutates (baseline=false) -> Worker Payload Receives Learned Requirement
```

### Judges: Critical Path Verification

| Step | Source File | Exact Mechanism |
| --- | --- | --- |
| **WRITE PATH** | [`src/prior/memory.py`](src/prior/memory.py) (`write_lesson`) | Approved lesson written via `MemoryClient.set_entity("lesson", id, body)` with tenant isolation. |
| **READ PATH** | [`src/prior/memory.py`](src/prior/memory.py) (`recall_lessons`) | Fresh query calls `search_entities` (FTS5) and `list_entities` scoped to `tenant_id`. |
| **CONTRACT MUTATION** | [`src/prior/contract.py`](src/prior/contract.py) (`build_contract`) | Recalled lessons are appended to `acceptance` criteria and `baseline` is set to `false`. |
| **WORKER EFFECT** | [`src/prior/providers/base.py`](src/prior/providers/base.py) (`requirement_payload`) | `learned_requirements` are directly injected into the worker payload. |
| **FRESH-SESSION PROOF** | [`scripts/fresh_session_prior.py`](scripts/fresh_session_prior.py) + [`tests/test_scoping.py`](tests/test_scoping.py) | Two isolated OS processes (different PIDs), plus same-cookie workspace continuity across processes. Verified in [`evidence/fresh-session-prior.json`](evidence/fresh-session-prior.json). |
| **STABLE DEPLOYED PROOF** | [`scripts/verify_deployed_loop.py`](scripts/verify_deployed_loop.py) | Live loop against stable public HTTPS endpoint. Verified in [`evidence/stable-deployment-flow.json`](evidence/stable-deployment-flow.json). |

---

## Consumer Experience

1. **Natural Request**: User enters a research or review need (e.g. *"Research the top five decentralized exchanges"*, or a transaction-approval security review).
2. **Memory Check**: PRIOR queries Sibyl. If prior rejections produced lessons in this domain, PRIOR displays them and adds them to the new contract.
3. **Contract Review**: The user reviews what the agent will get and what it must follow, including Sibyl-derived learned requirements.
4. **Agent Match**: PRIOR selects a live Virtuals ACP offering with scored compatibility evidence and freezes the agent, offering, network, and price in a plan the user confirms. Nothing is hired until the user confirms.
5. **Execution**: The hired agent executes against the brief, which carries the full request plus every learned requirement.
6. **Evaluation**: User accepts or rejects the deliverable. Funding a paid job is a separate explicit confirmation (public safety limit: 0.50 USDC per job, 1.00 USDC deployment pool).
7. **Reusable Lesson**: If rejected with a reason, PRIOR formulates a reusable rule. The user approves, edits, or ignores it.
8. **Sibyl Persistence**: Approved lessons are saved immediately to Sibyl and enforced in all future jobs.

---

## Verified Integrations Status

| Partner / Stack | Status | Verification & Evidence |
| --- | --- | --- |
| **Sibyl Memory** | **VERIFIED (Load-Bearing)** | SQLite WARM entities (`category="lesson"`), tenant-scoped search, verified across isolated OS processes in [`evidence/fresh-session-prior.json`](evidence/fresh-session-prior.json). |
| **Base** | **VERIFIED (B20 Read)** | Live `eth_call` read against Base B20 Policy Registry (`policyExists(0) == true`) and Factory, verified on mainnet & Sepolia in [`evidence/base-b20-read.json`](evidence/base-b20-read.json). |
| **Virtuals ACP** | **VERIFIED (Real Paid Lifecycle)** | Live marketplace selection, real ACP job creation, seller budget, explicit user funding (0.03 USDC), external execution, retrieved seller deliverable, and human review, all against production. |

### The honest Virtuals story

PRIOR completed a real paid ACP lifecycle end to end: dynamic selection picked a transaction-review specialist, the frozen plan carried the Sibyl-derived requirement into the worker payload, the seller posted a budget, the owner explicitly funded 0.03 USDC, the seller submitted, and PRIOR retrieved the deliverable for review.

The seller's answer was low quality: it marked supplied transaction fields as unknown, directly contradicting the remembered requirement PRIOR had transmitted. That failure is the point, not a footnote. PRIOR records verdicts independently of the marketplace outcome, proposes a lesson from the rejection reason, and the next contract carries it. Human review and lesson learning exist precisely because external workers can be wrong.

*Honest scope*: funding is observed via the funded ACP session state and the buyer wallet balance movement recorded during UAT; PRIOR does not display a transaction hash it did not capture. Paid jobs require explicit user confirmation and respect the public 0.50 USDC per-job and 1.00 USDC pool ceilings.

### Base Integration Details
- **Mechanism**: PRIOR performs a live B20 Policy Registry read on Base.
- **RPC Calls**: Direct `eth_call` queries to:
  - Base B20 Policy Registry (`0x8453000000000000000000000000000000000002`): `policyExists(0)` &rarr; `0x000...0001` (`true`).
  - Base B20 Factory (`0xB20f000000000000000000000000000000000000`): `isB20(factory)` &rarr; `0x000...0000` (`false`).
- **Endpoints & UI**: Implemented in [`src/prior/base_action.py`](src/prior/base_action.py), exposed via `/api/base/verify` and the interactive System Proof UI tab (`/proof`).
- *Honest claim*: This is a live Base onchain B20 Policy Registry read. It is not an ACP payment.

---

## Stable Deployment

The live app runs on a VPS at [`prior.103-195-188-198.sslip.io`](https://prior.103-195-188-198.sslip.io), with HTTPS terminated by Caddy and the FastAPI process supervised by `systemd` (`deploy/prior.service`). The laptop and its development tunnel are not required. Sibyl's SQLite database persists at `/var/lib/prior`, and the local research provider is explicitly labelled `Network: Local` and is only the development fallback; production hires registered Virtuals ACP agents.

The deployed application revision is exposed by `/api/health` as `build_commit` and recorded in the stable deployment evidence, so judges can compare it with the public repository history.

The production loop was exercised against the public endpoint and recorded in [`evidence/stable-deployment-flow.json`](evidence/stable-deployment-flow.json). That evidence includes a shortened workspace ID, a real rejection and approved lesson, the changed second contract, the worker's learned requirement, and the live Base read.

---

## Local Development & Reproduction

### Prerequisites
- Python 3.10+ (tested on Python 3.14.3)
- Node.js 18+ (for ACP bridge)

### Setup & Run
```bash
# Clone repository
git clone https://github.com/Techkeyy/prior.git
cd prior

# Install Python package and dependencies
python -m pip install -e ".[dev]"

# Install ACP bridge dependencies
cd acp-bridge && npm install && cd ..

# Configure environment
cp .env.example .env
# Set PRIOR_LOCAL_PROVIDER=true in .env for the local research-agent demo.

# Run self-check doctor
python -m prior.doctor

# Run test suite (431 tests collected)
python -m pytest

# Run server
python -m uvicorn prior.app:app --app-dir src --host 127.0.0.1 --port 8787
```

Visit **http://127.0.0.1:8787** in your browser.

---

## Test Suite

```bash
python -m pytest
```

431 tests collected (`pytest --collect-only`); the suite covers the memory loop, contract routing, marketplace semantic-fit selection, the paid hire/fund lifecycle with spend-policy guards, frontend behavior harnesses, auth/scoping isolation, and failure/ambiguity handling.

---

## Codebase Architecture

```
prior/
├── src/prior/
│   ├── app.py              # FastAPI application (REST API & static routes)
│   ├── service.py          # Core workflow coordinator (specify/hire/fund/review/lessons)
│   ├── hiring.py           # Frozen hire/fund intents, preflight, spend policy, idempotency
│   ├── marketplace.py      # Dynamic selection: compatibility gates, scoring, price cap
│   ├── job_spec.py         # Natural language job normalization + review routing
│   ├── contract.py         # Dynamic contract builder with learned rules
│   ├── lessons.py          # Lesson proposer, duplicate check & domain matching
│   ├── memory.py           # Sibyl Memory client wrapper (write_lesson, recall_lessons)
│   ├── auth.py             # Guest workspaces, Google/email identity, handoff tokens
│   ├── handoff.py          # Single-use owner-UAT workspace handoff
│   ├── base_action.py      # Base B20 Policy Registry onchain read
│   ├── research.py         # Real Wikipedia API research worker
│   ├── settings.py         # Environment configuration incl. public spend policy
│   ├── providers/
│   │   ├── base.py         # Provider interface & requirement payload constructor
│   │   ├── local.py        # Local development provider (truthfully labelled)
│   │   └── virtuals.py     # Virtuals ACP v2 adapter (live paid path)
│   └── static/             # Consumer web UI
├── acp-bridge/             # Node.js ACP v2 integration (@virtuals-protocol/acp-node-v2)
├── evidence/               # Empirical verification files
├── scripts/                # Fresh-session, Base B20, Virtuals ACP, and live loop scripts
├── tests/                  # Pytest suite + plain-node frontend harnesses
└── docs/                   # Product specifications, demo script & submission pack
```

---

## How I tried to break it

| Input | Result |
| --- | --- |
| Happy path: reject a deliverable, approve the lesson, submit a related job | New contract carries the approved requirement; worker payload includes it |
| Seller returns content contradicting the transmitted requirement | Human review records the failure independently of the marketplace outcome; lesson proposed from the reason |
| Over-limit worker wins ranking on name/rating | Rejected before hire: compatibility is semantic-first, price-capped at 0.50 USDC per job |
| Source-code-only auditor offered for a transaction review | Refused at selection; transaction specialist selected instead |
| Duplicate hire/fund clicks, concurrent poll vs prepare | Single create, single fund: idempotency keys plus atomic claims; refresh never clobbers prepared intents |
| Expired ACP session with a pending review | Funding refused; UI shows the timeout truthfully; no auto-retry, no fake completion |
| Missing/expired auth, wrong workspace | 404/denied; workspaces never leak across tenants |
| Malformed spend-policy configuration | Fail closed: hires and funding refuse with a plain-language message |

Key invariant: **a transport or timing failure never fabricates a business state, and a placeholder is never presented as a worker's deliverable.**

---

## Platform feedback

PRIOR is built directly on the official `@virtuals-protocol/acp-node-v2` SDK (marketplace discovery, offering jobs, budgets, funding, submission history) and the Sibyl memory client (WARM entities, tenant-scoped FTS5 search). No issues were filed against either platform during the build; integration gaps found (deliverable location in `job.submitted` history events, single-flight UI polling, stale-bundle cache delivery) were fixed in PRIOR's own adapter and UI layers.

---

## Prior Work Declaration

PRIOR was conceived and researched prior to the hackathon build window under exploratory working concepts. All codebase architecture, Sibyl Memory integration, Base B20 onchain caller, ACP v2 bridge, FastAPI backend, test suites, and web frontend were authored and verified during the official hackathon build window (1–10 Sep 2026).

---

## License

[MIT](LICENSE)
