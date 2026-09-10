# PRIOR Owner UAT

Status: UAT READY

This is the owner acceptance test for the real production UI. It requires no terminal, curl, database access, private API, or manual memory edit. Use a browser profile that has not used PRIOR before so Job 1 starts with no lesson. Do not clear cookies between Job 1 and Job 2.

Production URL: <https://prior.103-195-188-198.sslip.io>

**Money warning (read first):** production hires real Virtuals ACP agents and spends real USDC from the shared buyer wallet. Each paid hire in this script costs a few cents (typical: 0.03 USDC). Fund promptly after hiring: ACP sessions expire about 5 minutes after creation, and an expired job cannot be funded. Never confirm a hire or funding you did not mean.

## 1. Open PRIOR

**What to click:** Open the production URL, then open `/app`.

**What you should see:** The request screen headed "What do you need done?", a shortened `ws:` workspace badge, a "Describe the job" field, and suggestion chips.

**What to verify:** The page identifies a job-hiring product. The workspace badge is shortened and contains no secret.

**Success means:** The product opens over HTTPS and the primary action is visible.

## 2. Start Job 1

**What to click:** Click the `Top five AI wallet companies` chip, then click `Set up this job`.

**What you should see:** A contract review screen ("The contract the agent will receive") with a memory note saying no past lesson matched, standard baseline requirements, an Agent note saying work is delivered by a registered Virtuals ACP agent, and a `Find the right agent` button.

**What to verify:** No learned requirement appears yet. The provider path is Virtuals ACP, not Local.

**Success means:** Job 1 begins from a real clean baseline in the controlled workspace.

## 3. Review The Match

**What to click:** Click `Find the right agent`. Do not confirm yet.

**What you should see:** A hire confirmation panel showing Agent, Offering, Network (Virtuals ACP), and Price, plus why it matched and what will be sent. A hint states confirming creates a real paid ACP job and nothing has been hired yet.

**What to verify:** The agent, offering, and price are concrete and the cost is explicit before any money moves.

**Success means:** Explicit confirmation is required; nothing is purchased by discovery alone.

## 4. Hire Job 1

**What to click:** Click `Confirm hire` and stay on the page.

**What you should see:** The work screen ("The agent is working") with the ACP job id. Within seconds it updates on its own to show a `Fund X USDC` button once the seller posts its budget. No reload needed.

**What to verify:** The update arrives automatically; the budget amount matches the confirmed price.

**Success means:** A real ACP job was created from the frozen plan.

## 5. Fund Job 1

**What to click:** Click `Fund X USDC`, review the funding confirmation (agent, offering, amount, currency), then confirm funding.

**What to verify:** The panel shows the exact amount and currency before you confirm. Funding respects the public limits (0.50 USDC per job).

**Success means:** The seller budget is escrowed by your explicit confirmation only.

## 6. Reject With A Real Reason

**What to click:** When the result arrives, click `Reject and teach PRIOR`. Enter a real reason (for example: `Material factual claims must include identifiable source links.`) and submit.

**What you should see:** A proposed reusable lesson derived from the rejection, waiting for your decision. The page never claims the marketplace accepted your verdict unless it did.

**What to verify:** The proposed requirement matches the reason and is waiting, not auto-stored.

**Success means:** User feedback becomes a proposed lesson, not an automatic policy.

## 7. Approve The Lesson

**What to click:** Click `Add to my memory` (you may edit the wording first, or choose not this time).

**What you should see:** A confirmation that the requirement is active, with a note that matching contracts will include it from now on.

**What to verify:** The lesson is described as active and user-approved.

**Success means:** The user explicitly approves the rule before it controls future work.

## 8. Confirm Memory

**What to click:** Click `Memory` in the top navigation.

**What you should see:** The new active lesson in the workspace memory list.

**Success means:** The lesson is visible as persistent workspace memory.

## 9. Start Job 2 Without Clearing Cookies

**What to click:** Click `Start a new job`, enter a related request (for example the `Top five decentralized exchanges` chip), and click `Set up this job`.

**What you should see:** A "Memory applied" banner saying PRIOR remembered the lesson from the earlier job, with the requirement listed as coming from your own approved feedback. The contract is no longer baseline.

**What to verify:** The workspace badge is unchanged and the remembered requirement is quoted verbatim.

**Success means:** The same workspace recalls the approved lesson for a related job.

## 10. Hire Job 2 And Check Propagation

**What to click:** Click `Find the right agent`, confirm the hire, and fund as in steps 4-5.

**What you should see:** The frozen hire plan carries the learned requirement, and the worker brief sent to the agent contains it.

**What to verify:** The remembered requirement reached the external worker input, not just the screen.

**Success means:** Memory causally changed the second job's contract and worker payload.

## 11. Inspect Proof

**What to click:** Click `Memory`, then the proof/system view, and run the Base check.

**What you should see:** The active lesson remains in Memory. System Proof displays a live Base read result.

**What to verify:** The page shows live read results and never claims registration, payment, transfer, or settlement it did not perform.

**Success means:** The consumer loop and the separate Base proof are both visible in the production UI.

## UAT Result

Record `UAT PASS` only if every step above succeeds in the production browser. A failed step should include the visible screen, the action taken, and the browser time. Do not edit memory or database state to make a step pass. Note the ACP job ids and amounts for every paid step.

Local provider note: a local research agent exists only as a development fallback (`Network: Local`, explicitly labelled as not Virtuals ACP). It is not the production path and must not be presented as one.
