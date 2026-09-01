# Manual verification checklist

## Sibyl

- [ ] Job 1: reject a research deliverable with a real reason.
- [ ] Approve the proposed lesson.
- [ ] Confirm the lesson appears under Memory.
- [ ] Stop the PRIOR process completely.
- [ ] Start a new process.
- [ ] Job 2: a related research request recalls the lesson and the contract lists it.
- [ ] Automated: `python scripts/run_sibyl_kill_test.py`

## Virtuals

- [ ] `ACP_ENABLED=true` with v2 Privy credentials: `BUYER_WALLET_ADDRESS`, `BUYER_WALLET_ID`, `BUYER_SIGNER_PRIVATE_KEY`.
- [ ] `node acp-bridge/run.mjs probe` loads `AcpAgent`.
- [ ] Browse returns a real provider (or our registered PRIOR seller).
- [ ] Create job sends `acceptance` including learned lessons in `service_requirement`.
- [ ] UI phase matches ACP events. No timer-based fake completion.
- [ ] Automated: `python scripts/virtuals_kill_test.py`

## Base

- [ ] RPC probe: `python scripts/base_kill_test.py`
- [ ] When an ACP job is funded, capture the Base explorer URL for the payment/escrow tx.
- [ ] Never display "Payment secured" without that tx.

## Fresh-session demo

1. Session A: research job, reject for missing sources, add lesson, stop server.
2. Session B: new terminal, start server, new request, show recalled lesson and changed contract.
3. Record as one unedited segment with an on-screen clock.
