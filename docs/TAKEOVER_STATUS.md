# PRIOR Takeover Status

Recorded: 2026-09-02 (Takeover from d835e3b)

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
   - 25/25 unit & integration tests pass with pytest.

## Verified Incomplete
1. **Public Deployment**: App running locally (`127.0.0.1:8787`), no hosted public production deployment yet.
2. **Base UI Verification**: Base B20 proof needs product-visible endpoint and UI panel.
3. **Consumer UI Polish**: Refine layout, typography, empty states, error handling, and visual fidelity per `design-skill`.
4. **Virtuals ACP Live Credentials**: `@virtuals-protocol/acp-node-v2` adapter prepared with Privy v2 credential schema; live execution blocked on registered agent credentials.

## Blockers
- Live ACP onchain execution blocked on registered Privy buyer/seller credentials (`BUYER_*`, `SELLER_*`). Adapter fails honestly without faking.

## Immediate Next Actions
1. Expose Base verification endpoint and add interactive proof drawer in UI.
2. Polish consumer UI flow (Specify -> Contract Review with Sibyl badges -> Deliverable -> Rejection / Lesson Proposal -> Approval -> Sibyl Write).
3. Set up public deployment and run production verification test.
4. Update README and demo documentation per `perfect-readme`.
