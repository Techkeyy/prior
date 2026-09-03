# PRIOR Takeover Status

Recorded: 2026-09-03 (handoff from b9987dc)

## Verified Working
1. **Sibyl Memory Learning Loop & Cold-Start Isolation**:
   - Write path: Approved lessons stored as WARM entities (`category="lesson"`).
   - Read path: Search / list entities in Sibyl tenant.
   - Contract mutation: `applicable_lessons` appends to `contract.acceptance` and marks `baseline: false`.
   - Worker effect: `learned_requirements` and `acceptance` passed into worker payload.
   - Fresh-session recall verified across separate OS processes (`evidence/fresh-session-prior.json`).
2. **Local Research Worker**:
   - Live Wikipedia REST API lookups with source citations attached and inlined.
   - Truthfully labelled: `PRIOR Local Research Agent`, `Network: Local`.
3. **Base Onchain Integration**:
   - Direct eth_call against official B20 Factory (`0xB20f...0000`) and Policy Registry (`0x8453...0002`).
   - Verified live on both Base mainnet (chain 8453) and Base Sepolia (chain 84532) in `evidence/base-b20-read.json`.
4. **Test Suite**:
   - 30/30 unit & integration tests pass with pytest.

## Verified Since Handoff
1. **Stable Public Deployment**: `https://prior.103-195-188-198.sslip.io` runs behind Caddy on a VPS, with an enabled `systemd` service and Sibyl storage under `/var/lib/prior`.
2. **Production Sibyl Loop**: The public endpoint completed Job 1 rejection, approved lesson write, Job 2 recall, contract mutation, and worker learned requirements in `evidence/stable-deployment-flow.json`.
3. **Workspace Continuity**: `/api/workspace` accepts only generated workspace IDs, and `tests/test_scoping.py` verifies the same cookie maps to the same tenant across separate OS processes.
4. **Base UI Verification**: `/proof` performs and displays live Base B20 Factory and Policy Registry reads.
5. **Consumer UI**: Workspace badge, truthful provider identity, memory states, progress, deliverables, rejection, lesson approval, memory management, and proof states are present.
6. **Virtuals ACP Live Credentials**: `@virtuals-protocol/acp-node-v2` adapter and drop-in verification script are prepared, but live execution remains blocked on registered agent credentials.

## Remaining Blockers
1. Virtuals ACP cannot be marked verified until buyer and seller credentials, registration, an offering, and a real funded job are available.
2. The current public hostname is stable for this VPS but uses `sslip.io`; a custom domain would be a presentation improvement, not a product requirement.
