/* Fund-CTA poll/render regressions (owner UAT bug, ACP 78064).

Production bug: while a hired job stayed active, poll() updated state.job
(with the seller's budget) but never re-rendered; the DOM only refreshed on
the terminal transition — by which point the screen was "This job timed out"
and the funding action had never been visible.

Loads the REAL src/prior/static/app.js with minimal stubs and a scripted
backend. Timeline mirrors 78064: hired without budget, then budget appears
mid-poll while lifecycle stays active.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const appJs = path.join(__dirname, "..", "src", "prior", "static", "app.js");
const src = fs.readFileSync(appJs, "utf8");

/* ---- source locks ---- */
assert.ok(src.includes("if (keepPolling) schedulePoll(id, 1200);"),
  "poll must schedule exactly one follow-up when the job stays live");
assert.ok(src.includes("function ensurePolling(job)"), "single-flight starter required");
assert.ok(!/setTimeout\(\(\) => poll\(id\), 1200\)/.test(src),
  "raw recursive setTimeout(poll) loop must be gone");

/* ---- fake DOM + scripted backend ---- */
let html = "";
const appEl = { className: "", set innerHTML(v) { html = v; }, get innerHTML() { return html; } };
global.location = { pathname: "/app", search: "", hash: "", href: "http://local/app" };
global.history = { pushState() {}, replaceState() {} };
global.document = {
  getElementById(id) { return id === "app" ? appEl : null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
global.window = {
  addEventListener: () => {},
  scrollTo: () => {},
  sessionStorage: { getItem: () => "1", setItem: () => {} },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const jobCalls = [];
let phase = "no-budget";

const base = (over) => Object.assign({
  id: "job_e7615dfe9a7b", workspace_id: "ws_0b5c5cdd60504720",
  status: "hired", hire_state: "created", fund_state: null,
  acp_job_id: "78064", acp_phase: "open", acp_expired_at: "9999999999",
  prior_lifecycle: "active", acp_budget: null,
  provider: { name: "COINGAZURA", source: "virtuals-acp", network: "Virtuals ACP" },
  spec: { raw: "Review this approval", job_type: "research", deliverables: [], keywords: [], explicit_requirements: [] },
  contract: { title: "t", goal: "g", deliverables: [], acceptance: [], baseline: false, applied_lessons: [] },
  created_at: "2026-09-10T08:55:35+00:00", updated_at: "2026-09-10T09:13:46+00:00",
}, over);

global.fetch = async (url) => {
  const u = String(url);
  const json = (o) => ({ ok: true, status: 200, text: async () => JSON.stringify(o) });
  if (u.startsWith("/api/workspace")) return json({ workspace_id: "ws_0b5c5cdd60504720", hire_mode: "dynamic" });
  if (u.startsWith("/api/auth/me")) return json({ authenticated: false });
  if (u.startsWith("/api/memory")) return json({ lessons: [], count: 0, jobs: [], status: "ok" });
  if (u.startsWith("/api/jobs/")) {
    jobCalls.push(u);
    if (phase === "no-budget") return json(base({}));
    if (phase === "budget") return json(base({ acp_budget: { amount: "0.03", symbol: "USDC", decimals: 6 } }));
    if (phase === "delivered") return json(base({ status: "delivered", prior_lifecycle: "delivered", acp_budget: { amount: "0.03" }, deliverable: { type: "object", value: { text: "full review" } } }));
    if (phase === "funded") return json(base({ fund_state: "funded", acp_budget: { amount: "0.03" } }));
    if (phase === "expired") return json(base({ acp_expired_at: "1", prior_lifecycle: "expired" }));
    return json(base({}));
  }
  throw new Error("unmocked " + u);
};

const bundle = require(appJs);
assert.ok(bundle.state && typeof bundle.poll === "function" && typeof bundle.stopPolling === "function",
  "test seams must be exported");

(async () => {
  await sleep(50);

  /* ---- 1. hired without budget: work screen, no CTA yet ---- */
  bundle.state.job = base({});
  await bundle.poll("job_e7615dfe9a7b");
  await sleep(60);
  assert.ok(html.includes("The agent is working"), "work screen renders");
  assert.ok(!html.includes("data-fund>"), "no fund CTA before budget exists");

  /* ---- 2. budget appears mid-poll: SAME page must auto-show the CTA ---- */
  phase = "budget";
  await bundle.poll("job_e7615dfe9a7b");
  await sleep(60);
  assert.ok(html.includes("data-fund>"), "fund CTA must render on the poll that sees the budget");
  assert.ok(/Fund 0\.03 USDC/.test(html), "CTA must show the budget amount");

  /* ---- 3. exactly one follow-up timer: GET rate stays one-per-interval ---- */
  const before = jobCalls.length;
  await sleep(2600);
  const delta = jobCalls.length - before;
  assert.ok(delta >= 1 && delta <= 3, `single-flight cadence expected 1-3 GETs in 2.6s, got ${delta}`);

  /* ---- 4. funded state renders without any manual action ---- */
  phase = "funded";
  await sleep(1500);
  assert.ok(html.includes("Funded"), "funded state must surface automatically");

  /* ---- 5. delivered transition still renders the Review panel ---- */
  bundle.stopPolling();
  phase = "delivered";
  await bundle.poll("job_e7615dfe9a7b");
  await sleep(60);
  assert.ok(html.includes("ready for your review"), "delivered transition renders review");

  /* ---- 6. expired transition still renders the timeout panel ---- */
  bundle.state.job = base({});
  phase = "expired";
  await bundle.poll("job_e7615dfe9a7b");
  await sleep(60);
  assert.ok(html.includes("timed out"), "expired transition renders timeout");
  const afterTerminal = jobCalls.length;
  await sleep(2600);
  assert.strictEqual(jobCalls.length, afterTerminal, "terminal lifecycle must stop polling");

  /* ---- 7. stale in-flight response cannot resurrect over a reset ---- */
  bundle.stopPolling();
  phase = "budget";
  bundle.state.job = base({});
  const slow = bundle.poll("job_e7615dfe9a7b");
  bundle.state.job = null;
  bundle.stopPolling();
  await slow;
  await sleep(80);
  assert.strictEqual(bundle.state.job, null, "reset during flight must drop the old update");

  console.log("FRONTEND_POLL_CTA_OK");
  const outFile = process.argv[2];
  if (outFile) fs.writeFileSync(outFile, "FRONTEND_POLL_CTA_OK\n", "utf8");
})();
