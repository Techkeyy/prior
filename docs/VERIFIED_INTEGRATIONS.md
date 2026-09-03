# Verified integrations

Claims below were read from current official documentation on 2026-09-01.
Only claims PRIOR is about to rely on. Anything not listed here is unverified.

## Sibyl Labs Hackathon

Source: https://hack.sibyllabs.org/rules

- Build window: 1–10 Sep 2026 (UTC). Judging 11–12 Sep. Winners 13–15 Sep.
- Gate (pass/fail): Sibyl Memory must be load-bearing. Delete it and the core function must fail or materially degrade.
- Demo must show cold-start / fresh-session recall as one unedited segment.
- README must point to where memory is written and read.
- Rubric: memory 40, originality 25, execution 20, pitch 15. PMF bonus up to +10.
- Partner multiplier: first verified stack x1.15, second x1.25 cap. Sibyl is never a multiplier.
- Base stack: deployment is the eligibility floor. Bonus requires an executed onchain action: wallet operation, x402 payment, B20 read, or contract interaction shown in the demo.
- Virtuals stack: an ACP job, a registered or transacting agent, or another Virtuals-native integration exercised in the demo.
- Submission: public GitHub repo, OSI license (MIT or Apache-2.0), real commit history, 2–5 minute demo, README with Prior Work declaration, two public posts tagging @sibylcap and claimed partners.

## Sibyl Memory (custom application path)

Sources:

- https://docs.sibyllabs.org/memory/integrations
- https://docs.sibyllabs.org/memory/concepts
- https://docs.sibyllabs.org/memory/install
- Installed package `sibyl-memory-client==0.8.0` (method names confirmed from the installed source, not from memory)

Relied-on API:

- `MemoryClient.local(path, tenant_id=...)` opens a local SQLite store.
- `set_entity(category, name, body)` / `get_entity(category, name)` — WARM entities. UNIQUE `(tenant_id, category, name)`.
- `search_entities(query, limit=..., category=...)` — FTS5 over entity name + category + body, tenant-scoped.
- `list_entities(category=..., status=..., limit=...)` — tenant-scoped listing.
- `delete_entity(category, name)` — hard delete.
- `archive_entity(kind, name)` — recoverable archive.
- `write_event(acted=..., extra=...)` — COLD journal.
- `set_tenant(tenant_id)` / `get_tenant()` — isolate workspaces.
- Unactivated use is local-first and makes no network calls (official privacy statement).
- Free tier has a local size cap (docs: 2 MB; installed client comments mention 5 MB). Stay well under either figure.

PRIOR mapping implemented in this repository:

- Each consumer workspace is a Sibyl `tenant_id`.
- An approved lesson is a WARM entity: `category="lesson"`, `name=<lesson id>`.
- Lesson recall uses `search_entities` with `category="lesson"`, then applicability filtering. If FTS returns nothing, fall back to `list_entities(category="lesson")` in the same tenant (still Sibyl, still scoped).
- Job operational records are not stored in Sibyl. They live in a separate local jobs file. Sibyl holds learned lessons.

## Virtuals ACP

Sources:

- https://os.virtuals.io/acp/sdk/getting-started (current Node SDK v2)
- https://github.com/Virtual-Protocol/acp-python (official Python SDK, `virtuals-acp`)
- https://whitepaper.virtuals.io/acp/acp-faq
- https://whitepaper.virtuals.io/acp/acp-dev-onboarding-guide/set-up-agent-profile/create-job-offering/job-offering-data-schema-validation

Relied-on facts:

- Official current Node SDK is `@virtuals-protocol/acp-node-v2` (`AcpAgent`, `PrivyAlchemyEvmProviderAdapter`, `browseAgents`, `createJobByOfferingName`, `session.fund` / `submit` / `complete` / `reject`).
- v2 credentials are `*_WALLET_ADDRESS`, `*_WALLET_ID`, `*_SIGNER_PRIVATE_KEY` (Privy authorization key, not an EOA).
- `@virtuals-protocol/acp-node` (v1) is deprecated as of 1 Jun 2026.
- Official Python SDK is `virtuals-acp` and requires Python `<3.13`. This machine is 3.14, so PRIOR does not use it.
- Job phases documented for the Python/v1 mental model: REQUEST → NEGOTIATION → TRANSACTION → EVALUATION → COMPLETED / REJECTED.
- v2 event names: `job.created` → `budget.set` → `job.funded` → `job.submitted` → `job.completed` / `job.rejected`.
- Service requirements can be a dict validated against the seller offering's JSON schema.
- Registration on the ACP registry is required before other agents can discover a provider.
- Official FAQ currently recommends Base mainnet for testing (tiny job prices such as $0.01). Base Sepolia is documented (`BASE_SEPOLIA_CONFIG_V2`) but FAQ says contact DevRel for testnet access.
- ACP jobs settle via the ACP contract (escrow / x402 config `BASE_MAINNET_ACP_X402_CONFIG_V2` in current Python examples). That settlement is a Base onchain action if and when a real job is funded.

PRIOR uses the official Node SDK v2 through `acp-bridge/`. If credentials are missing, the app reports the failure and does not invent a job. See `docs/VIRTUALS_STATUS.md`.

## Base

Sources: hackathon rules (above); https://docs.base.org (network facts); ACP FAQ.

Relied-on facts:

- Base mainnet chain ID 8453, RPC `https://mainnet.base.org`.
- Base Sepolia chain ID 84532, RPC `https://sepolia.base.org`.
- Hackathon Base bonus needs an executed onchain action that serves the product, shown in the demo. Deployment alone is the eligibility floor, not the bonus.
- Preferred PRIOR path: the Virtuals ACP job payment / escrow on Base is the product-native action (hiring an agent). We will not assume that one transaction automatically grants both partner multipliers; we will evidence the ACP job and the Base explorer link separately.
- We will not fabricate a self-transfer or a fake USDC confirmation.

## What is not claimed yet

- A live registered Virtuals buyer/seller pair for this repo (credentials not present at first commit).
- A confirmed Base transaction hash for a PRIOR job (no job has been funded yet).
- Hosted Sibyl (MemoryClient hosted URL is documented as not implemented in v1).
- x402 as a separate PRIOR protocol (only if ACP's x402 config is actually exercised).
