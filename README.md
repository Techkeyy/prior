# PRIOR

**[Live Public Application](https://transcription-modern-tobago-dodge.trycloudflare.com)** &middot; **[GitHub Repository](https://github.com/Techkeyy/prior)** &middot; **[Fresh-Session Proof](evidence/fresh-session-prior.json)** &middot; **[Base B20 Evidence](evidence/base-b20-read.json)** &middot; **[Deployed Flow Evidence](evidence/deployed-sibyl-flow.json)**

Hire a research agent. When the work is wrong, keep the lesson. The next contract gets stricter.

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
| **FRESH-SESSION PROOF** | [`scripts/fresh_session_prior.py`](scripts/fresh_session_prior.py) | Two isolated OS processes (different PIDs). Verified in [`evidence/fresh-session-prior.json`](evidence/fresh-session-prior.json). |
| **DEPLOYED PROOF** | [`scripts/verify_deployed_loop.py`](scripts/verify_deployed_loop.py) | Live loop against public HTTPS endpoint. Verified in [`evidence/deployed-sibyl-flow.json`](evidence/deployed-sibyl-flow.json). |

---

## Consumer Experience

1. **Natural Request**: User enters a research need (e.g. *"Research the top five decentralized exchanges"*).
2. **Memory Check**: PRIOR queries Sibyl. If prior rejections produced lessons in this domain, PRIOR displays:
   `✓ PRIOR remembered 1 lesson from similar jobs: Material factual claims must include identifiable source links.`
3. **Contract Review**: The user reviews deliverables, baseline requirements, and Sibyl-derived learned requirements.
4. **Execution**: The provider executes research with real Wikipedia API lookups and source citations.
5. **Evaluation**: User accepts or rejects the deliverable.
6. **Reusable Lesson**: If rejected with a reason, PRIOR formulates a reusable rule. The user approves, edits, or ignores it.
7. **Sibyl Persistence**: Approved lessons are saved immediately to Sibyl and enforced in all future jobs.

---

## Partner Integrations

### 1. Sibyl Memory (Core Qualifier)
- **Status**: Verified & load-bearing across fresh OS processes and production deployments.
- **Client**: `sibyl-memory-client==0.8.0`.
- **Mapping**: Each workspace cookie maps to a Sibyl `tenant_id`. Approved lessons are WARM entities (`category="lesson"`). Search uses FTS5 lexical matching across domains and keywords.

### 2. Base (Executed Onchain Read)
- **Status**: Live onchain verification against official Base precompiles.
- **Mechanism**: Direct `eth_call` queries to:
  - Base B20 Policy Registry (`0x8453000000000000000000000000000000000002`): `policyExists(0)` &rarr; `0x000...0001` (`true`).
  - Base B20 Factory (`0xB20f000000000000000000000000000000000000`): `isB20(factory)` &rarr; `0x000...0000` (`false`).
- **Endpoints & UI**: Implemented in [`src/prior/base_action.py`](src/prior/base_action.py) and exposed via `/api/base/verify` and the interactive System Proof UI tab (`/proof`).
- **Evidence**: [`evidence/base-b20-read.json`](evidence/base-b20-read.json).
- *Honest claim*: This is a real Base onchain B20 precompile read. It is not an ACP payment.

### 3. Virtuals Protocol ACP v2
- **Status**: Prepared with `@virtuals-protocol/acp-node-v2` v0.1.12.
- **Adapter**: [`src/prior/providers/virtuals.py`](src/prior/providers/virtuals.py) and [`acp-bridge/lib.mjs`](acp-bridge/lib.mjs) implement `PrivyAlchemyEvmProviderAdapter` with Privy authorization signer keys (`BUYER_WALLET_ADDRESS`, `BUYER_WALLET_ID`, `BUYER_SIGNER_PRIVATE_KEY`).
- *Honest claim*: Live ACP jobs require registered agent registry credentials. When unconfigured, PRIOR fails honestly (`Virtuals credentials are not configured`) and executes development hires through `PRIOR Local Research Agent` (clearly labelled `Network: Local`, never falsely badged as Virtuals).

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

# Run self-check doctor
python -m prior.doctor

# Run test suite (27 tests)
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

```
collected 27 items

tests/test_base_action.py ..                                             [  7%]
tests/test_contract.py ...                                               [ 18%]
tests/test_failures.py ...                                               [ 29%]
tests/test_job_spec.py .....                                             [ 48%]
tests/test_lessons.py ....                                               [ 62%]
tests/test_loop.py ..                                                    [ 70%]
tests/test_memory_persistence.py ....                                    [ 85%]
tests/test_providers.py ...                                              [ 96%]
tests/test_scoping.py .                                                  [100%]

======================== 27 passed in 7.78s ========================
```

---

## Codebase Architecture

```
prior/
├── src/prior/
│   ├── app.py              # FastAPI application (REST API & static routes)
│   ├── memory.py           # Sibyl Memory client wrapper (write_lesson, recall_lessons)
│   ├── contract.py         # Dynamic contract builder with learned rules
│   ├── lessons.py          # Lesson proposer, duplicate check & domain matching
│   ├── job_spec.py         # Natural language job normalization
│   ├── base_action.py      # Base B20 Policy Registry & Factory onchain reads
│   ├── research.py         # Real Wikipedia API research worker
│   ├── service.py          # Core workflow coordinator
│   ├── settings.py         # Environment configuration
│   ├── providers/
│   │   ├── base.py         # Provider interface & requirement payload constructor
│   │   ├── local.py        # Local development provider (truthfully labelled)
│   │   └── virtuals.py     # Virtuals ACP v2 adapter
│   └── static/             # Clean, responsive consumer web UI
├── acp-bridge/             # Node.js ACP v2 integration (@virtuals-protocol/acp-node-v2)
├── evidence/               # Cryptographic and empirical verification files
├── scripts/                # Fresh-session, Base B20, and live loop test scripts
├── tests/                  # 27 unit & integration tests
└── docs/                   # Product specifications, demo scripts & status notes
```

---

## Prior Work Declaration

PRIOR was conceived and researched prior to the hackathon build window under exploratory working concepts. All codebase architecture, Sibyl Memory integration, Base B20 onchain caller, ACP v2 bridge, FastAPI backend, test suites, and web frontend were authored and verified during the official hackathon build window (1–10 Sep 2026).

---

## License

[MIT](LICENSE)
