# PRIOR &mdash; 3-Minute Video Demo Script

**Target Duration**: 2:45 &ndash; 3:00  
**Live Application**: https://transcription-modern-tobago-dodge.trycloudflare.com  
**GitHub Repository**: https://github.com/Techkeyy/prior  

---

### Act 1: The Problem & The Premise (0:00 &ndash; 0:30)

- **Visual**: PRIOR Homepage (`/`) with clean prompt box and suggestion chips.
- **Narrator**:
  > "Every time we hire an AI agent to do research, we spend time telling it what went wrong. But on the next job, we start from scratch and make the same mistake.
  > 
  > This is PRIOR: a consumer application for hiring AI agents that learns from previous jobs.
  > 
  > PRIOR doesn’t just remember the job; it remembers what the job taught us, storing approved lessons in Sibyl Memory to automatically improve future contracts."

---

### Act 2: Job 1 & Baseline Contract (0:30 &ndash; 1:00)

- **Action**: Click the chip `"Research the top five AI wallet companies."` and click **Find an agent**.
- **Visual**: Contract Review Screen.
  - Show the Memory Banner: *"No relevant lessons found for this domain yet. Starting with standard baseline requirements."*
  - Show deliverables and baseline acceptance requirements.
  - Show truthful provider badge: `PRIOR Local Research Agent (Local Network / Wikipedia API)`.
- **Action**: Click **Hire this agent**.
- **Visual**: Real findings appear with companies (e.g. Privy, Dynamic, Biconomy, etc.) and summaries.
- **Narrator**:
  > "Our baseline contract had standard requirements. The agent executed live research and returned four findings. But notice: some factual claims don’t have citations attached."

---

### Act 3: Rejection & Learning Loop (1:00 &ndash; 1:40)

- **Action**: Click **Reject with Reason**.
- **Action**: In the rejection box, type:
  `Material factual claims must include identifiable source links.`
- **Action**: Click **Submit Rejection & Propose Lesson**.
- **Visual**: PRIOR transitions to the **Sibyl Learning Opportunity** screen.
  - Show proposed lesson text: `"Material factual claims must include identifiable source links."`
  - Show origin: *"Derived from user rejection on Job 1."*
- **Action**: Click **Approve & Write to Sibyl**.
- **Visual**: Toast notification: *"Lesson approved and written to Sibyl Memory."*
- **Action**: Click **Memory** in top nav.
- **Visual**: Show the new WARM entity active in Sibyl with status `active`, domain `ai wallets`, and provenance `user-approved`.
- **Narrator**:
  > "PRIOR formulated a reusable rule from our rejection reason. When we approved it, it was immediately written to our Sibyl Memory tenant as an active WARM entity."

---

### Act 4: Fresh Session & Contract Mutation Proof (1:40 &ndash; 2:25)

- **Action**: Open a fresh incognito window or clear cookies (simulate a brand-new session with this workspace/tenant).
- **Action**: Enter a new research request: `"Research the top five decentralized exchanges."`
- **Action**: Click **Find an agent**.
- **Visual**: Contract Review Screen.
  - **HIGHLIGHT THIS MOMENT**:
    Show the green banner:
    `✓ PRIOR Remembered 1 Lesson From Similar Jobs`
    `• Material factual claims must include identifiable source links.`
  - Show that `baseline` is now `false`, and the learned requirement is in the acceptance criteria.
- **Action**: Click **Hire this agent**.
- **Visual**: Show that the worker received the learned requirement in its payload, and the new deliverable now includes inline source citations for each DEX (Uniswap, Curve, etc.).
- **Narrator**:
  > "This is the magic moment. We did not retype our citation requirement. PRIOR queried Sibyl Memory, matched the research domain, and mutated the new contract before the worker started.
  > 
  > The worker payload received the learned requirement, and our second job deliverable arrived with verified source citations."

---

### Act 5: Base Onchain Proof & Closing (2:25 &ndash; 3:00)

- **Action**: Click **System Proof** in top nav (`/proof`).
- **Action**: Click **Run Base Mainnet Query**.
- **Visual**: Base verification panel displays:
  - Policy Registry: `0x8453000000000000000000000000000000000002` &rarr; `policyExists(0) = true`
  - B20 Factory: `0xB20f000000000000000000000000000000000000` &rarr; `isB20(factory) = false`
  - RPC: `https://mainnet.base.org` via `eth_call`.
- **Narrator**:
  > "Underneath the product, PRIOR connects to Base onchain precompiles for B20 policy registration, and uses isolated Sibyl Memory tenants for persistent learning.
  > 
  > PRIOR: AI agent hiring that gets smarter after every job."
