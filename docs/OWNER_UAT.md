# PRIOR Owner UAT

Status: UAT READY

This is the owner acceptance test for the real production UI. It requires no terminal, curl, database access, private API, or manual memory edit. Use a browser profile that has not used PRIOR before so Job 1 starts with no lesson. Do not clear cookies between Job 1 and Job 2.

Production URL: <https://prior.103-195-188-198.sslip.io>

## 1. Open PRIOR

**What to click:** Open the production URL.

**What you should see:** The PRIOR request screen, a shortened `ws:` workspace badge, a research request field, and suggestion chips.

**What to verify:** The page identifies PRIOR as a research-agent hiring product. The workspace badge is shortened and contains no secret.

**Success means:** The product opens over HTTPS and the primary action is visible.

## 2. Start Job 1

**What to click:** Click `Top AI wallet companies`, then click `Find an agent`.

**What you should see:** A contract review screen with a memory message saying no relevant lesson was found and standard baseline requirements are being used.

**What to verify:** The contract shows `baseline` behavior through the baseline requirements. No learned citation rule should appear yet.

**Success means:** Job 1 begins from a real clean baseline in the controlled workspace.

## 3. Review The Provider

**What to click:** Do not hire yet. Read the provider line on the contract screen.

**What you should see:** `PRIOR Local Research Agent`, `Local`, and `Wikipedia API`.

**What to verify:** The provider is not labelled Virtuals ACP and no payment or transaction is claimed.

**Success means:** The active development provider is truthfully identified.

## 4. Hire Job 1

**What to click:** Click `Hire this agent` and wait for the result.

**What you should see:** A real research deliverable with findings and source links where available.

**What to verify:** The result is not an instant placeholder. Findings have retrieved content and source links.

**Success means:** A real local research job returns a deliverable.

## 5. Reject With A Real Reason

**What to click:** Click `Reject with Reason`. Enter `Material factual claims must include identifiable source links.` and submit.

**What you should see:** A proposed reusable lesson derived from the rejection.

**What to verify:** The proposed requirement matches the reason and is waiting for your decision.

**Success means:** User feedback becomes a proposed lesson, not an automatic policy.

## 6. Approve The Lesson

**What to click:** Click `Approve & Write to Sibyl`.

**What you should see:** A confirmation that the lesson was written to Sibyl Memory.

**What to verify:** The lesson is described as active and user-approved.

**Success means:** The user explicitly approves the rule before it controls future work.

## 7. Confirm Memory

**What to click:** Click `Memory` in the top navigation.

**What you should see:** The new active lesson in the workspace memory list.

**What to verify:** The requirement is `Material factual claims must include identifiable source links.`

**Success means:** The lesson is visible as persistent workspace memory.

## 8. Start Job 2 Without Clearing Cookies

**What to click:** Click `New Job`, choose `Top decentralized exchanges`, and click `Find an agent`.

**What you should see:** A green memory banner saying PRIOR remembered a lesson from similar jobs.

**What to verify:** The contract includes the source-link requirement and is no longer baseline. The workspace badge is unchanged.

**Success means:** The same workspace recalls the approved lesson for a related research job.

## 9. Hire Job 2

**What to click:** Click `Hire this agent` and wait for the result.

**What you should see:** A second research deliverable with source citations and a `Requirements Passed to Worker Payload` section.

**What to verify:** `Sibyl-derived requirements` contains the approved source-link rule.

**Success means:** The learned requirement changed the contract and reached the worker input.

## 10. Inspect Memory And Base Proof

**What to click:** Click `Memory`, then `System Proof`, then `Run Base Mainnet Query`.

**What you should see:** The active lesson remains in Memory. System Proof displays a live Base B20 Policy Registry result.

**What to verify:** `policyExists(0) = true` is shown as a live read. The page does not claim B20 registration, payment, transfer, settlement, or an ACP transaction.

**Success means:** The consumer loop and the separate Base proof are both visible in the production UI.

## UAT Result

Record `UAT PASS` only if every step above succeeds in the production browser. A failed step should include the visible screen, the action taken, and the browser time. Do not edit memory or database state to make a step pass.

The fresh-process hackathon proof is separate from this normal consumer UAT. Use `docs/DEMO_SCRIPT.md` for the operator procedure that keeps the same browser cookie while restarting the backend process.
