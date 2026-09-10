# PRIOR — Final Demo Script (2:45–3:15)

**Live app:** https://prior.103-195-188-198.sslip.io
**Repo:** https://github.com/Techkeyy/prior

Rubric order, not feature order: problem → failure → feedback → memory write → fresh session → recall → causal change → worker propagation → Virtuals → Base → close. Every paid step states its real cost on camera. Nothing is faked: waiting time for the external seller is bridged once, on camera, with an honest narration line.

**Money note:** the demo spends one small paid hire (about 0.03 USDC). Fund promptly: ACP sessions expire about 5 minutes after creation.

---

### 0:00–0:25 — Problem and premise

- **Visual:** `/app`, fresh browser profile, shortened `ws:` badge.
- **Narrator:**
  > "Every time we hire an AI agent, we correct its mistakes. Next job, we start from zero and repeat them. PRIOR hires agents through a contract it writes down. When a job goes badly, PRIOR remembers why in Sibyl Memory and the next contract gets stricter. PRIOR doesn't remember the job. It remembers what the job taught us."

### 0:25–0:55 — Job 1, baseline contract, live hire

- **Action:** type a research request (e.g. "Research the top five AI wallet companies"), click **Set up this job**.
- **Visual:** contract screen, memory note says no past lesson matched, standard requirements. Agent note says work is delivered by a registered Virtuals ACP agent.
- **Action:** click **Find the right agent**. Read the frozen plan on camera: Agent, Offering, Network, Price.
- **Action:** click **Confirm hire**. State the price aloud (about 0.03 USDC, real money).
- **Narrator:**
  > "Nothing was purchased by searching. This confirmation is the purchase."

### 0:55–1:20 — Fund, then bridge the seller wait honestly

- **Action:** when the page updates itself with **Fund 0.03 USDC**, click it, read the confirmation, confirm funding.
- **Narrator:**
  > "Funding is a second explicit confirmation. Now the external agent works, which takes a few minutes. While it works: this is the part PRIOR was built for."
- **Cut (one cut allowed here only, narrated):** "Three minutes later, the result is back."

### 1:20–1:45 — Reject, lesson, approve

- **Visual:** delivered result on screen.
- **Action:** click **Reject and teach PRIOR**, type a real reason (e.g. "Material factual claims must include identifiable source links."), submit.
- **Action:** read the proposed reusable lesson, click **Add to my memory**.
- **Visual:** lesson shows Active.
- **Narrator:**
  > "The rejection became a proposed rule. Nothing was stored until I approved it."

### 1:45–2:30 — Fresh session, unedited (ONE continuous segment)

- **Must be one uncut shot.** On screen together: the browser badge, a terminal, and a clock.
- **Action 1:** show the backend PID and the build commit (`/api/health` → `build_commit`), plus the current time.
- **Action 2:** kill the server process on camera (local demo server), start it again, show the NEW PID and the same commit.
- **Action 3:** same browser, same cookie, no clearing. Click **Start a new job**, submit a related request ("Research the top five decentralized exchanges"), click **Set up this job**.
- **Visual, on camera:** "Memory applied" banner quoting the approved lesson; contract no longer baseline; the frozen hire brief contains the learned requirement verbatim.
- **Narrator:**
  > "Different process, new PID, no in-memory state. The workspace cookie is the same, so Sibyl returned our rule, the contract changed, and the exact words go to the next worker."

### 2:30–2:55 — Virtuals and Base proof

- **Visual:** the live ACP hire: agent name, offering, ACP job id, seller budget, and (for the earlier completed job) the retrieved seller deliverable with the human review beside it. State plainly if a shown seller answer was low quality: the requirement was transmitted, the worker contradicted it, review caught it.
- **Action:** open the proof view, run the Base check on camera: `policyExists(0) = true`, live RPC read.
- **Narrator:**
  > "Real marketplace, real escrow, real deliverable, real Base read. And when the worker was wrong, the lesson still landed."

### 2:55–3:05 — Close

- **Narrator:**
  > "PRIOR doesn't remember the job. It remembers what the job taught us."

---

## Do-not-film list

No architecture diagrams, no settings tour, no old failed jobs, no terminals except the one continuous fresh-session segment, no claims beyond what is on screen (no transaction hashes PRIOR did not capture, no seller quality claims beyond the shown review).
