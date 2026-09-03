# PRIOR &mdash; 3-Minute Video Demo Script

**Target Duration**: 2:45 &ndash; 3:00
**Live Application**: https://prior.103-195-188-198.sslip.io
**GitHub Repository**: https://github.com/Techkeyy/prior  

---

### Act 1: The Problem & The Premise (0:00 &ndash; 0:25)

- **Visual**: PRIOR Homepage (`/`) showing header mark and the shortened workspace badge, for example `ws: 006a…ded5`.
- **Narrator**:
  > "Every time we hire an AI agent to do research, we spend time correcting mistakes. But on the next job, we start from scratch and repeat them.
  >
  > PRIOR helps you hire AI agents without repeating mistakes. When a job goes badly, PRIOR remembers why in Sibyl Memory and automatically improves future job terms.
  >
  > PRIOR doesn't remember the job. It remembers what the job taught us."

---

### Act 2: Job 1 & Baseline Contract (0:25 &ndash; 0:55)

- **Action**: Click prompt chip `"Research the top five AI wallet companies."` and click **Find an agent**.
- **Visual**: Contract Review Screen.
  - Show Memory Banner: *"No relevant lessons found for this domain yet. Starting with standard baseline requirements."*
  - Show deliverables and baseline criteria.
  - Show provider badge: `PRIOR Local Research Agent (Local Network / Wikipedia API)`.
- **Action**: Click **Hire this agent**.
- **Visual**: Real findings appear for Privy, Dynamic, Biconomy, etc.
- **Narrator**:
  > "Our baseline contract had standard requirements. The agent executed live research and returned live findings. But notice: some factual claims lack verifiable source links."

---

### Act 3: Rejection & Sibyl Lesson Write (0:55 &ndash; 1:20)

- **Action**: Click **Reject with Reason**.
- **Action**: Type: `Material factual claims must include identifiable source links.`
- **Action**: Click **Submit Rejection & Propose Lesson**.
- **Visual**: PRIOR presents the proposed lesson.
- **Action**: Click **Approve & Write to Sibyl**.
- **Visual**: Toast notification confirms write to Sibyl Memory.
- **Action**: Click **Memory** in top nav to show the new WARM entity active in Sibyl.
- **Narrator**:
  > "PRIOR extracted a reusable rule from our rejection. When approved, it was stored immediately as an active WARM entity in our workspace's Sibyl Memory tenant."

---

### Act 4: Continuous Unedited Cold-Start Recall (1:20 &ndash; 2:15)

*(THIS SECTION MUST BE FILMED IN ONE UNEDITED CONTINUOUS SEGMENT WITH ON-SCREEN TIMESTAMP/PID)*

- **Action 1**: Point out the shortened workspace identifier in the header, for example `ws: ab12…34ef`.
- **Action 2**: Show the current timestamp and commit hash, then switch to terminal. Show current running server PID (e.g. `PID 10216`).
- **Action 3**: Terminate the server process (`Ctrl+C` or `kill`). Process PID 10216 dies.
- **Action 4**: Start a NEW server process (`python -m uvicorn prior.app:app ...`). Note NEW PID (e.g. `PID 19840`).
- **Action 5**: Switch back to the same browser. Do NOT clear cookies. Click **New job** or refresh.
- **Action 6**: Point out that the workspace identity is identical, using the shortened badge.
- **Action 7**: Submit Job 2: `"Research the top five decentralized exchanges."`
- **Visual**: Contract Review Screen updates:
  - **GREEN BADGE**: `✓ PRIOR Remembered 1 Lesson From Similar Jobs`
  - `• Material factual claims must include identifiable source links.`
  - `baseline` is `false`.
- **Action 8**: Click **Hire this agent**.
- **Visual**: Show that `worker_requirement.learned_requirements` contains the remembered requirement, and the new findings arrive with verified source citations inline.
- **Narrator**:
  > "Notice what happened: Server process A died completely. We started server process B with a new PID. But our browser workspace identity remained constant.
  >
  > Process B queried Sibyl Memory, recalled our source-citation rule, mutated the new contract, and passed the learned requirement into the worker payload.
  >
  > No session state was cached in memory. Memory came directly from Sibyl."

---

### Act 5: Base Onchain Proof & Closing (2:15 &ndash; 3:00)

- **Action**: Click **System Proof** in top nav (`/proof`).
- **Action**: Click **Run Base Mainnet Query**.
- **Visual**: Base verification panel displays live RPC query result:
  - Base Policy Registry: `0x8453000000000000000000000000000000000002` &rarr; `policyExists(0) = true`
  - Base B20 Factory: `0xB20f000000000000000000000000000000000000` &rarr; `isB20(factory) = false`
- **Narrator**:
  > "Here PRIOR performs a live B20 Policy Registry read on Base. The returned policyExists result comes directly from the Base RPC as a real onchain read.
  > 
  > PRIOR: AI agent hiring that gets smarter after every job."
