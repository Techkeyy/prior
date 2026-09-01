# PRIOR

Hire a research agent. When the work is wrong, keep the lesson. The next contract gets stricter.

> *"I already told the last agent to cite sources. Why am I typing that again?"*

Sibyl Labs Hackathon · 1–10 Sep 2026 · MIT.

## Why memory is load-bearing

PRIOR is not a notepad. A rejected job becomes a user-approved lesson in **Sibyl Memory**. A later, fresh process reads that lesson and **changes the next contract** before another agent is hired.

If you delete the Sibyl calls, Session B cannot recall Session A, and the second contract does not change. That is the product.

```
JOB 1  reject  ->  user approves lesson  ->  Sibyl write
fresh process
JOB 2  Sibyl read  ->  contract mutates  ->  worker receives new requirements
```

### Judges: the three files

| Path | What it does |
| --- | --- |
| **WRITE** [`src/prior/memory.py`](src/prior/memory.py) `write_lesson` | `MemoryClient.set_entity("lesson", id, body)` |
| **READ** [`src/prior/memory.py`](src/prior/memory.py) `recall_lessons` | `search_entities` / `list_entities` in the workspace tenant |
| **ACTION CHANGE** [`src/prior/contract.py`](src/prior/contract.py) `build_contract` | recalled lessons are appended to `acceptance` and sent to the worker |

Fresh-session proof (two OS processes, different PIDs): [`scripts/run_sibyl_kill_test.py`](scripts/run_sibyl_kill_test.py) · evidence in [`evidence/sibyl-kill-test.json`](evidence/sibyl-kill-test.json).

## What it does

1. **Normalizes** a research request into a job spec ([`src/prior/job_spec.py`](src/prior/job_spec.py)).
2. **Recalls** workspace-scoped lessons from Sibyl before hiring.
3. **Writes a contract** whose acceptance list includes those lessons.
4. **Hires** through a `ResearchProvider`. Virtuals ACP v2 when credentials exist. Otherwise LOCAL PROVIDER if explicitly enabled. LOCAL PROVIDER is never labelled as Virtuals.
5. **Shows the real deliverable.** The user accepts or rejects.
6. **Proposes a reusable lesson** from the rejection reason. Nothing becomes policy until the user adds it.
7. **Writes the approved lesson to Sibyl.** A new process can recall it.

MVP domain: research and information-gathering jobs only.

## Quickstart

```bash
cd Desktop/prior
python -m venv .venv
# Windows: .venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
# For a local hire without Virtuals keys:
#   PRIOR_LOCAL_PROVIDER=true
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m prior.doctor
.venv\Scripts\python.exe -m prior.cli
```

Open http://127.0.0.1:8787

### Fresh-session demo

1. Ask PRIOR to research five AI wallet companies.
2. Reject the deliverable: "Important factual claims should include source links."
3. Add the proposed lesson.
4. Stop the server.
5. Start it again.
6. Ask PRIOR to research five decentralized exchanges.
7. The contract now includes the source-link requirement, recalled from Sibyl, not from the browser.

## Architecture

| Module | Job |
| --- | --- |
| `src/prior/job_spec.py` | Turn natural language into a research spec |
| `src/prior/memory.py` | Sibyl read/write for lessons (`tenant_id` = workspace) |
| `src/prior/lessons.py` | Applicability, proposal, payload sanitizer |
| `src/prior/contract.py` | Baseline contract, then mutate from recalled lessons |
| `src/prior/research.py` | Live Wikipedia/DuckDuckGo research worker |
| `src/prior/providers/` | `ResearchProvider`: LOCAL PROVIDER or Virtuals ACP v2 |
| `src/prior/service.py` | The hire / reject / approve loop |
| `src/prior/app.py` | Consumer HTTP API + UI |
| `acp-bridge/run.mjs` | `AcpAgent.browseAgents` / `createJobByOfferingName` / `complete` / `reject` |

Workspace identity is a cookie (`ws_...`) used as the Sibyl tenant. That is isolation, not enterprise multi-tenancy.

## Partner stacks

**Sibyl Memory** is mandatory and load-bearing. See WRITE/READ/ACTION above.

**Virtuals.** `@virtuals-protocol/acp-node-v2` 0.1.12 with `PrivyAlchemyEvmProviderAdapter`. Status: [`docs/VIRTUALS_STATUS.md`](docs/VIRTUALS_STATUS.md). Live jobs need `BUYER_WALLET_ADDRESS`, `BUYER_WALLET_ID`, `BUYER_SIGNER_PRIVATE_KEY`. Missing credentials raise `Virtuals credentials are not configured.` There is no silent ACP success.

**Base.** RPCs for mainnet (8453) and Sepolia (84532) respond ([`scripts/base_kill_test.py`](scripts/base_kill_test.py)). The product-native Base action is the ACP job payment/escrow once a real job is funded. PRIOR will not show a fake USDC confirmation.

## Tests

```bash
.venv\Scripts\python.exe -m pytest -q
```

21 tests covering job normalization, lesson applicability, workspace scoping, contracts with and without memory, approved persistence, fresh-process Sibyl recall, malicious payloads, duplicates, and honest ACP failure.

## Prior Work

Research from an earlier direction (working name Precedent) is not this architecture. The product was redefined before this repository's first build-window commit. No prior application code was reused except a small job-spec sketch written at the start of this window.

## Limitations

- Research jobs only.
- Virtuals live job is blocked until registry credentials are supplied.
- Local provider is development-only and labelled as not Virtuals.
- Workspace cookie is not wallet login.
- Wikipedia/DuckDuckGo research is real and incomplete; it is not a predetermined script.

## License

[MIT](LICENSE)
