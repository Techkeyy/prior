# PRIOR — Final Submission Pack

Copy/paste ready. Replace `[PASTE URL]` once the demo is uploaded.

---

## PROJECT NAME

PRIOR

## ONE-LINER

Hire AI agents without repeating the same mistakes: every rejection becomes a memory that rewrites the next contract.

## SHORT DESCRIPTION (~250 characters)

PRIOR is a consumer app for hiring AI agents that learns from failure. Reject bad work with a reason, approve the lesson once, and Sibyl Memory injects it into every future contract and worker brief. Live at https://prior.103-195-188-198.sslip.io

## FULL DESCRIPTION

PRIOR helps people hiring AI agents stop retyping the same corrections. You describe the work, PRIOR checks Sibyl Memory for lessons from your past jobs, writes them into the job contract, and hires a live Virtuals ACP agent against it. When a deliverable disappoints, you reject it with a real reason. PRIOR proposes that reason as a reusable requirement, and only after you approve it is the lesson stored. The next related job, even in a fresh session with no conversation history, recalls the lesson, mutates its contract, and sends the remembered requirement into the worker payload. Paid hires need explicit confirmation at every money step and respect public spend ceilings. Memory is load-bearing: delete it and the second contract cannot change.

## PROBLEM

AI agents forget corrections between jobs. Users retype the same requirements ("cite sources", "use the fields I gave you") on every hire, and marketplaces offer no memory of what went wrong last time.

## SOLUTION

A hiring loop where the contract is the memory surface: reject → propose lesson → explicit approve → Sibyl write → recall on the next job → mutated contract → changed worker input. The verdict on a worker is recorded independently of the marketplace outcome, so even a bad seller teaches the system.

## HOW IT WORKS

1. Request → Sibyl recall (tenant = workspace) → contract built with learned requirements → live marketplace selection with scored evidence → frozen plan → explicit hire confirmation.
2. Seller budget → explicit fund confirmation → escrow → execution → deliverable retrieved → human review.
3. Reject with reason → proposed lesson → approve/edit/ignore → Sibyl write.
4. Fresh session, same workspace → recall → contract mutation → worker brief carries the lesson.

## WHY SIBYL IS LOAD-BEARING

Delete Sibyl Memory and fresh sessions start blind: no recall, no contract mutation, no worker effect. The write path (`MemoryClient.set_entity`), read path (tenant-scoped FTS5 `search_entities`), contract mutation (`baseline=false` + appended acceptance), and worker injection (`learned_requirements` in the payload) are each one function call, each covered by tests, each demonstrated live. Memory is not a log. It is the input to the next hire.

## WHAT IS NOVEL

The contract, not the chat, is the memory surface; verdicts are stored independently of marketplace outcomes so failures teach; semantic-fit selection refuses wrong workers before price is considered; spend policy, idempotency, and concurrency guards make paid agent hiring safe for strangers.

## CURRENT LIVE URL

https://prior.103-195-188-198.sslip.io

## GITHUB URL

https://github.com/Techkeyy/prior

## DEMO VIDEO

[PASTE URL]

## PARTNER STACKS

- **Sibyl (load-bearing):** approved lessons stored as WARM entities and recalled across isolated processes and fresh sessions; proof in `evidence/fresh-session-prior.json` and the live demo recall segment.
- **Virtuals (real exercised integration):** live marketplace selection, real ACP job creation, seller budget, explicit user funding of 0.03 USDC, external execution, retrieved seller deliverable, human review. No transaction hash is claimed beyond what PRIOR captured.
- **Base (live read integration):** live `eth_call` B20 Policy Registry read (`policyExists(0) == true`) on mainnet and Sepolia; proof in `evidence/base-b20-read.json` and the `/proof` UI tab. ACP escrow itself settles on Base.

## TECH STACK

Python (FastAPI), SQLite (Sibyl Memory client), Node.js ACP bridge (`@virtuals-protocol/acp-node-v2`), vanilla JS UI, Caddy + systemd on a VPS. Test suite: pytest plus plain-node frontend harnesses (431 tests collected).

## KEY PROOF / EVIDENCE LINKS

- Live app: https://prior.103-195-188-198.sslip.io
- Repo: https://github.com/Techkeyy/prior
- `evidence/fresh-session-prior.json` — cross-process recall proof
- `evidence/stable-deployment-flow.json` — live production loop proof
- `evidence/base-b20-read.json` — Base B20 read proof
- `evidence/virtuals-acp-live.json` — ACP liveness evidence

## PRIOR WORK DECLARATION

PRIOR was conceived and researched prior to the hackathon build window under exploratory working concepts. All codebase architecture, Sibyl Memory integration, Base B20 onchain caller, ACP v2 bridge, FastAPI backend, test suites, and web frontend were authored and verified during the official hackathon build window (1–10 Sep 2026).

## TWO PUBLIC POST DRAFTS

### POST 1 — launch/demo

PRIOR is live: hire AI agents without repeating the same mistakes.

Reject bad work once, approve the lesson, and Sibyl Memory rewrites your next contract automatically. Real Virtuals ACP hires, real escrow, human review.

Try it: https://prior.103-195-188-198.sslip.io
@sibylcap

### POST 2 — build/technical proof

How PRIOR makes memory load-bearing: rejection → proposed rule → explicit approval → WARM entity → fresh session recalls it → contract mutates → the exact requirement ships inside the worker payload.

431 tests. Full write-up and proofs in the repo.
@sibylcap

## FINAL SUBMISSION CHECKLIST

- [ ] Demo uploaded
- [ ] Demo duration 2–5 min
- [ ] Fresh-session segment unedited
- [ ] Timestamp/commit visible where required
- [ ] Public GitHub
- [ ] MIT license
- [ ] README final
- [ ] Prior Work declaration
- [ ] Post 1 published
- [ ] Post 2 published
- [ ] Correct partner tracks selected
- [ ] Submission marked ready
