const app = document.getElementById("app");
const state = {
  job: null,
  memory: null,
  dash: null,
  workspace: null,
  baseProof: null,
  health: null,
  hirePlan: null,
  fundPlan: null,
  error: "",
  busy: false,
  showReject: false,
  notification: ""
};

function route() {
  const p = location.pathname;
  if (p === "/app") return "app";
  if (p === "/memory") return "memory";
  if (p === "/proof") return "proof";
  return "landing";
}

function updateNav() {
  const current = route();
  const nav = document.getElementById("site-nav");
  const wsBadge = document.getElementById("workspace-badge");
  if (!nav) return;

  if (current === "landing") {
    if (wsBadge) { wsBadge.classList.remove("show"); wsBadge.textContent = ""; }
    nav.innerHTML = `
      <a href="/#how-it-works" data-anchor="how-it-works">How it works</a>
      <a href="/proof" data-nav="proof" class="proof-link">Proof</a>
    `;
  } else {
    if (wsBadge) {
      const raw = state.workspace && state.workspace.workspace_id
        ? state.workspace.workspace_id.replace(/^ws_/, "") : "";
      const shortId = raw.length > 8 ? `${raw.slice(0, 4)}...${raw.slice(-4)}` : raw;
      wsBadge.textContent = raw ? `ws ${shortId}` : "";
      wsBadge.classList.toggle("show", current === "proof" && raw !== "");
      wsBadge.title = state.workspace ? `Workspace: ${state.workspace.workspace_id}` : "Workspace";
    }
    nav.innerHTML = `
      <a href="/app" data-nav="app" class="${current === "app" ? "active" : ""}">Workspace</a>
      <a href="/memory" data-nav="memory" class="${current === "memory" ? "active" : ""}">Memory</a>
      <a href="/proof" data-nav="proof" class="proof-link ${current === "proof" ? "active" : ""}">Proof</a>
    `;
  }
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data.detail || data.message || text || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

/* Lifecycle stages. Activity is history, not a stage. */
const STAGES = ["Request", "Memory", "Contract", "Agent", "Work", "Review", "Learn"];

function stageIndex(job) {
  if (!job) return 0;
  if (job.status === "specified") return 2;
  if (job.status === "hired" || job.status === "working") return 4;
  if (job.status === "delivered") return 5;
  return 6;
}

function stagesHtml(job) {
  const active = stageIndex(job);
  const memApplied = job && job.contract && !job.contract.baseline;
  const items = STAGES.map((label, i) => {
    let cls = "journey-step";
    if (i < active) cls += " done";
    else if (i === active) cls += " now" + (label === "Memory" && memApplied ? " now-memory" : "");
    else cls += " upcoming";
    return `<span class="${cls}"><span class="dot" aria-hidden="true"></span><span class="lbl">${label}</span></span>`;
  });
  return `<div class="journey-rail" role="status" aria-label="Job progress, current step: ${STAGES[active]}">${items.join('<span class="journey-sep" aria-hidden="true"></span>')}</div>`;
}

function foot() {
  return `<footer class="site-footer"><div><a href="/" data-nav="landing" class="footer-brand">PRIOR</a><span>It remembers what the job taught us.</span></div><div><a href="/app" data-nav="app">Open PRIOR</a><a href="/memory" data-nav="memory">Memory</a><a href="/proof" data-nav="proof">Technical proof</a><a href="https://github.com/Techkeyy/prior" target="_blank" rel="noreferrer">Source</a></div></footer>`;
}

function shell(html, wide) {
  let notif = "";
  if (state.notification) {
    notif = `<div class="success-banner" role="status"><span class="notice-icon" aria-hidden="true">&#10003;</span><p>${escapeHtml(state.notification)}</p></div>`;
  }
  let err = "";
  if (state.error) {
    err = `<div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(state.error)}</p></div>`;
  }
  app.className = wide ? "app-shell landing" : "app-shell";
  app.innerHTML = `${notif}${err}${html}${foot()}`;
  bind();
}

/* ---------------------------------------------------------------- landing */

function renderLanding() {
  shell(`
    <section class="landing-hero">
      <div class="landing-hero-grid">
        <div>
          <p class="eyebrow">Memory for agent work</p>
          <h1>Your next agent should know what the last one got wrong.</h1>
          <p class="landing-lede">PRIOR helps you hire AI agents without repeating the same mistakes. When an agent falls short, you explain why once. PRIOR turns that into a requirement and adds it to every future contract before the next agent starts.</p>
          <div class="landing-cta-row">
            <a href="/app" data-nav="app" class="button button-primary landing-main-cta">Open PRIOR</a>
            <a href="/#how-it-works" data-anchor="how-it-works" class="button button-secondary">See how it learns</a>
          </div>
          <p class="hero-proof-sub"><a href="/proof" data-nav="proof" class="proof-link">See the technical proof</a></p>
        </div>
        <div class="hero-demo" aria-label="Example of memory applied to a new contract">
          <div class="hd-step">
            <div class="hd-label"><span class="hd-title">A job that fell short</span><span class="status-pill">Rejected</span></div>
            <p class="hd-quote">"The comparison had no side-by-side summary. I had to build it myself."</p>
          </div>
          <div class="hd-step">
            <div class="hd-label"><span class="hd-title">What you taught PRIOR</span><span class="tag tag-memory">Learned</span></div>
            <p class="hd-clause">"Include an explicit side-by-side comparison whenever multiple products are requested."</p>
            <p class="meta small">Stored only after you approved it.</p>
          </div>
          <div class="hd-step">
            <div class="hd-label"><span class="hd-title">The next contract, before any agent starts</span><span class="status-pill status-safe">Memory applied</span></div>
            <ul class="clean req-list hd-contract">
              <li><span class="check" aria-hidden="true">&#8226;</span>Research each requested product</li>
              <li class="learned-row"><span class="check" aria-hidden="true">&#10003;</span>Include an explicit side-by-side comparison<span class="tag tag-memory" style="margin-left:8px;">From your memory</span></li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section id="how-it-works">
      <div class="section-head">
        <p class="eyebrow">How it works</p>
        <h2>Every job leaves a lesson. PRIOR puts it to work.</h2>
        <p class="lede">The loop is short, and you stay in charge of what gets remembered.</p>
      </div>
      <div class="loop-flow">
        <div class="loop-step">
          <span class="n">01</span>
          <h3>A job falls short</h3>
          <p>You review the agent's work and reject it for a real reason, in plain language.</p>
        </div>
        <div class="loop-step">
          <span class="n">02</span>
          <h3>PRIOR proposes a rule</h3>
          <p>From your reason, PRIOR drafts one reusable requirement. You approve it, edit it, or ignore it.</p>
        </div>
        <div class="loop-step ls-memory">
          <span class="n">03</span>
          <h3>The lesson is stored</h3>
          <p>Approved rules live in your memory, tied to your account, not to one browser or one agent.</p>
        </div>
        <div class="loop-step ls-memory">
          <span class="n">04</span>
          <h3>The next contract improves</h3>
          <p>When a future request matches, PRIOR inserts the requirement before the agent begins.</p>
        </div>
      </div>
    </section>

    <section>
      <div class="split">
        <div>
          <p class="eyebrow memory">The memory advantage</p>
          <h2>PRIOR doesn't remember the job. It remembers what the job taught us.</h2>
          <p class="lede">Job transcripts are noise. A learned requirement is signal. Each entry in your memory is one rule you approved, with a clear origin, that shapes every matching contract from that day forward.</p>
          <p><a class="button button-secondary" href="/memory" data-nav="memory">Look at a memory page</a></p>
        </div>
        <ul class="check-lines panel">
          <li><span class="check" aria-hidden="true">&#10003;</span><span><strong>Include verifiable source links for every key claim.</strong><br /><span class="meta small">Learned from a rejected research job in March.</span></span></li>
          <li><span class="check" aria-hidden="true">&#10003;</span><span><strong>Compare the requested items side by side, not one after another.</strong><br /><span class="meta small">Learned from a rejected comparison job.</span></span></li>
          <li><span class="check" aria-hidden="true">&#10003;</span><span><strong>State the date of the data, because pricing goes stale.</strong><br /><span class="meta small">Learned from outdated market figures.</span></span></li>
        </ul>
      </div>
    </section>

    <section>
      <div class="split">
        <div>
          <p class="eyebrow">Hiring and control</p>
          <h2>You hire. You review. You decide what is remembered.</h2>
          <p class="lede">PRIOR prepares the contract, hands it to an agent through the Virtuals Agent Commerce protocol, and brings the result back for your judgment. Nothing enters your memory without your approval, and nothing is ever rewritten silently.</p>
        </div>
        <ul class="check-lines">
          <li><span class="check" aria-hidden="true">&#10003;</span><span>See the full contract, including learned requirements, before you hire.</span></li>
          <li><span class="check" aria-hidden="true">&#10003;</span><span>Accept or reject real delivered work, with your reason recorded.</span></li>
          <li><span class="check" aria-hidden="true">&#10003;</span><span>Approve, edit, or ignore every proposed lesson.</span></li>
          <li><span class="check" aria-hidden="true">&#10003;</span><span>Sign in once and your memory follows you to any device.</span></li>
        </ul>
      </div>
    </section>

    <section>
      <div class="proof-strip">
        <div>
          <p class="eyebrow">Built on real infrastructure</p>
          <h3>Every claim is inspectable.</h3>
          <p class="meta">Sibyl memory stores what you approve. Virtuals ACP delivers the work. Base settles it. The proof page shows live reads, not screenshots.</p>
        </div>
        <a href="/proof" data-nav="proof" class="button button-secondary">Inspect technical proof</a>
      </div>
    </section>

    <section class="landing-bottom-cta">
      <p class="eyebrow">Get started</p>
      <h2>Make the next job smarter than the last.</h2>
      <p class="lede">Open a workspace and describe what you need done. No account required to try it.</p>
      <div class="landing-cta-row">
        <a href="/app" data-nav="app" class="button button-primary landing-main-cta">Open PRIOR</a>
      </div>
    </section>
  `, true);
}

/* -------------------------------------------------------------- workspace */

async function renderDashboard() {
  try {
    state.dash = await api("/api/memory");
  } catch (err) {
    state.error = err.message;
    state.dash = { lessons: [], count: 0, jobs: [], status: "unavailable" };
  }
  const job = state.job;
  const dash = state.dash || { lessons: [], count: 0, jobs: [] };
  const lessons = (dash.lessons || []).filter((l) => l.status === "active");

  if (job && job.status === "refused") {
    shell(`
      ${workspaceHeader()}
      ${stagesHtml(null)}
      <div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(job.error || "PRIOR focuses on research jobs.")}</p></div>
      ${composerCard(null)}
      ${memoryStrip(lessons)}
      ${activitySection(dash.jobs)}
    `);
    return;
  }

  let flow = "";
  if (!job) {
    flow = `${composerCard(null)}${memoryStrip(lessons)}`;
  } else if (job.status === "specified") {
    flow = `${requestLine(job)}${memoryAppliedBanner(job)}${contractPanel(job)}${agentPreview()}`;
  } else if (job.status === "hired" || job.status === "working") {
    flow = `${requestLine(job)}${collapsedContract(job)}${workPanel(job)}`;
  } else if (job.status === "delivered") {
    flow = `${requestLine(job)}${collapsedContract(job)}${reviewPanel(job)}`;
  } else {
    flow = `${requestLine(job)}${collapsedContract(job)}${learningPanel(job)}`;
  }

  shell(`
    ${workspaceHeader()}
    ${stagesHtml(job)}
    ${flow}
    ${activitySection(dash.jobs)}
  `);
  if (job && (job.status === "working" || job.status === "hired")) poll(job.id);
  maybeShowAuthPrompt();
}

function workspaceHeader() {
  return `
    <div class="app-header">
      <div>
        <p class="eyebrow">Your workspace</p>
        <h1>What do you need done?</h1>
        <p class="lede">PRIOR checks what it learned from your past jobs, puts it into the contract, then hires an agent to do the work.</p>
      </div>
    </div>`;
}

function composerCard(job) {
  const blocked = job && !["accepted", "rejected", "refused"].includes(job.status);
  return `
    <section class="opcard" aria-label="New request"${blocked ? ' data-dimmed="true"' : ""}>
      <form id="specify">
        <label class="left" for="need">${blocked ? "This job is in progress" : "Describe the job"}</label>
        <textarea id="need" name="text" placeholder="Example: Research three AI wallets and compare their features, pricing, and where they are available." required ${blocked ? "disabled" : ""}></textarea>
        <div class="row">
          <button type="submit" class="button button-primary"${state.busy || blocked ? " disabled" : ""}>${state.busy ? "Checking your memory..." : "Prepare contract"}</button>
          ${blocked ? `<button type="button" class="button button-ghost button-small" data-reset>Abandon and start over</button>` : ""}
        </div>
      </form>
      ${blocked ? "" : `
      <p class="meta small chips-label">Need a starting point?</p>
      <div class="chips">
        <span class="chip" data-chip="Research the top five AI wallet companies and compare their features." role="button" tabindex="0">Top five AI wallet companies</span>
        <span class="chip" data-chip="Research the top five decentralized exchanges." role="button" tabindex="0">Top five decentralized exchanges</span>
        <span class="chip" data-chip="Compare leading Layer-2 rollups by volume." role="button" tabindex="0">Leading Layer-2 rollups</span>
      </div>`}
    </section>`;
}

function memoryStrip(lessons) {
  if (lessons.length) {
    return `<p class="memory-note"><span class="tag tag-memory">Memory</span><span>PRIOR remembers ${lessons.length} approved ${lessons.length === 1 ? "requirement" : "requirements"} and will check them against your next request. <a href="/memory" data-nav="memory">View memory</a></span></p>`;
  }
  return `<p class="memory-note"><span class="status-pill">Memory</span><span>Nothing learned yet. If a job disappoints you, reject it and PRIOR can turn your reason into a rule for next time. <a href="/memory" data-nav="memory">How memory works</a></span></p>`;
}

function requestLine(job) {
  const raw = (job.spec && job.spec.raw) || (job.contract && job.contract.goal) || "";
  return `
    <div class="panel-topline" style="margin-top:4px;">
      <p class="meta" style="margin:0;"><strong>Request:</strong> ${escapeHtml(raw)}</p>
      <button class="button button-ghost button-small" data-reset>Start over</button>
    </div>`;
}

function learnedList(items) {
  return items.map((l) => `
    <li class="learned-row"><span class="check" aria-hidden="true">&#10003;</span>
      <span><strong>${escapeHtml(l.requirement)}</strong>${l.match_reason ? `<br /><span class="meta small">${escapeHtml(l.match_reason)}</span>` : ""}</span>
    </li>`).join("");
}

function memoryAppliedBanner(job) {
  const c = job.contract || {};
  if (c.memory_status === "unavailable") {
    return `<div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(c.memory_message || "Memory is unavailable. PRIOR will not guess at learned requirements.")}</p></div>`;
  }
  if (c.applied_lessons && c.applied_lessons.length) {
    return `
      <section class="learned" aria-label="Memory applied">
        <div class="panel-topline" style="margin-bottom:6px;">
          <p class="kicker memory" style="margin:0;">Memory applied</p>
          <span class="status-pill status-safe">Before the agent starts</span>
        </div>
        <p style="font-size:15.5px;">PRIOR remembered what you taught it from an earlier job and added ${c.applied_lessons.length === 1 ? "this requirement" : "these requirements"} to the new contract:</p>
        <ul class="clean req-list">${learnedList(c.applied_lessons)}</ul>
        <p class="clause-note">The agent receives these with the job. Nothing here was invented; each line came from your own approved feedback.</p>
      </section>`;
  }
  return `<p class="meta memory-note"><span class="status-pill">Checked</span><span>No past lesson matched this request yet, so the contract uses your standard requirements.</span></p>`;
}

function agentPreview() {
  const ws = state.workspace || {};
  if (ws.hire_mode === "virtuals") {
    return `<p class="meta memory-note"><span class="status-pill">Agent</span><span>Work is delivered by a registered Virtuals ACP agent. PRIOR sends the contract, including learned requirements, when you hire.</span></p>`;
  }
  if (ws.hire_mode === "local") {
    return `<p class="meta memory-note"><span class="status-pill">Agent</span><span>This environment uses the local research agent for testing. It is not Virtuals ACP.</span></p>`;
  }
  return `<p class="meta memory-note"><span class="status-pill">Agent</span><span>No hire path is configured in this environment. Hiring will fail honestly rather than pretend.</span></p>`;
}

function contractPanel(job) {
  const c = job.contract || {};
  const learnedSet = new Set((c.applied_lessons || []).map((l) => l.requirement));
  const standard = (c.acceptance || []).filter((item) => !learnedSet.has(item));
  const busy = state.busy;
  return `
    <section class="opblock spotlight" aria-label="Prepared contract">
      <div class="panel-topline">
        <h2 style="margin:0;">The contract the agent will receive</h2>
        <span class="status-pill${learnedSet.size ? " status-safe" : ""}">${learnedSet.size ? "Memory applied" : "Ready"}</span>
      </div>
      <div class="opgrid" style="margin-top:16px;">
        <div>
          <h3>Task</h3>
          <p>${escapeHtml((job.spec && job.spec.raw) || c.goal || "")}</p>
          <h3>Deliverables</h3>
          <ul class="clean">${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
        </div>
        <div>
          <h3>Requirements the agent must meet</h3>
          <ul class="clean req-list">
            ${standard.map((d) => `<li><span class="check" aria-hidden="true">&#8226;</span>${escapeHtml(d)}</li>`).join("")}
            ${learnedList(c.applied_lessons || [])}
          </ul>
          <p class="meta small" style="margin-top:10px;"><span class="tag tag-memory">From your memory</span> marks rules you approved on an earlier job.</p>
        </div>
      </div>
      <div class="row">
        <button class="button button-primary" data-hire${busy ? " disabled" : ""}>${busy ? "Finding an agent..." : "Find an agent for this contract"}</button>
        <button class="button button-ghost" data-reset>Discard</button>
      </div>
      ${hireConfirmHtml()}
    </section>`;
}

function hireConfirmHtml() {
  const plan = state.hirePlan;
  if (!plan) return "";
  const remembered = (plan.remembered || []).map(
    (r) => `<li class="learned-row"><span class="check" aria-hidden="true">&#10003;</span>${escapeHtml(r)}</li>`).join("");
  return `
    <div class="learned" aria-label="Hire confirmation" style="margin-top:18px;">
      <div class="panel-topline" style="margin-bottom:6px;">
        <p class="kicker memory" style="margin:0;">Review before hiring</p>
        <span class="status-pill status-safe">Read only so far</span>
      </div>
      <dl class="kv">
        <dt>Agent</dt><dd>${escapeHtml(plan.agent || "Virtuals ACP agent")}</dd>
        <dt>Offering</dt><dd>${escapeHtml(plan.offering || "")}</dd>
        <dt>Network</dt><dd>${escapeHtml(plan.network || "Virtuals ACP")}</dd>
        <dt>Price</dt><dd>${escapeHtml(plan.price || "")}</dd>
      </dl>
      <p class="meta">Why this match: ${escapeHtml(plan.match_reason || "")}</p>
      ${remembered ? `<p class="meta">What PRIOR remembered:</p><ul class="clean req-list">${remembered}</ul>` : `<p class="meta">No past lesson matched this request.</p>`}
      <p class="meta">What will be sent:</p>
      <p class="hd-quote">${escapeHtml((plan.will_be_sent || "").slice(0, 500))}</p>
      <div class="row">
        <button class="button button-primary" data-hire-confirm${state.busy ? " disabled" : ""}>${state.busy ? "Hiring..." : "Confirm hire"}</button>
        <button class="button button-ghost" data-hire-cancel>Back</button>
      </div>
      <p class="hint">Confirming creates a real paid ACP job. Nothing has been hired yet.</p>
    </div>`;
}

function collapsedContract(job) {
  const c = job.contract || {};
  const learned = (c.applied_lessons || []).length;
  return `
    <details class="disclose" aria-label="Contract for this job">
      <summary>Contract for this job${learned ? ` (with ${learned} learned ${learned === 1 ? "requirement" : "requirements"})` : ""}</summary>
      <div class="panel">
        <h3>Deliverables</h3>
        <ul class="clean">${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
        <h3>Requirements</h3>
        <ul class="clean req-list">
          ${(c.acceptance || []).map((item) => {
            const isLearned = (c.applied_lessons || []).some((l) => l.requirement === item);
            return `<li${isLearned ? ' class="learned-row"' : ""}><span class="check" aria-hidden="true">${isLearned ? "&#10003;" : "&#8226;"}</span>${escapeHtml(item)}</li>`;
          }).join("")}
        </ul>
      </div>
    </details>`;
}

function workPanel(job) {
  const p = job.provider || {};
  const name = p.name || "Virtuals ACP agent";
  const phase = job.acp_phase || (job.status === "hired" ? "job funded, agent starting" : "working");
  if (job.prior_lifecycle === "expired") {
    return `
    <section class="opblock" aria-label="Expired job">
      <div class="panel-topline">
        <h2 style="margin:0;">This job timed out</h2>
        <span class="status-pill"><span class="status-dot" aria-hidden="true"></span>Expired</span>
      </div>
      <p class="meta" style="margin-top:12px;">The agreed deadline passed with no delivered work. Raw ACP state is still <strong>${escapeHtml(phase)}</strong>, which the chain does not flip on its own. PRIOR will not fund or retry this job.</p>
      <p class="meta small mono">Job ${escapeHtml(job.acp_job_id || job.id)}</p>
      <div class="row"><button class="button button-secondary" data-reset>Start a new job</button></div>
    </section>`;
  }
  return `
    <section class="opblock" aria-label="Work in progress">
      <div class="panel-topline">
        <h2 style="margin:0;">The agent is working</h2>
        <span class="status-pill status-live"><span class="status-dot pulse" aria-hidden="true"></span>Live</span>
      </div>
      <div class="skeleton" role="status" style="margin-top:12px;">Hired ${escapeHtml(name)}. Contract and learned requirements delivered. Waiting for the agent's submission.</div>
      <p class="meta" style="margin-top:12px;">Protocol phase: <strong>${escapeHtml(phase)}</strong>. This page updates on its own, and your review options appear when the work is delivered.</p>
      <p class="meta small mono">Job ${escapeHtml(job.acp_job_id || job.id)}</p>
      ${fundBlock(job)}
    </section>`;
}

function fundAmount(job) {
  const budget = job.acp_budget || {};
  const value = Number(budget.amount);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

function fundBlock(job) {
  if (job.fund_state === "funded") {
    return `<p class="meta" style="margin-top:12px;"><span class="tag tag-memory">Funded</span> The agent budget is escrowed. PRIOR will bring the result back for review.</p>`;
  }
  if (job.fund_state === "fund_ambiguous" || job.fund_state === "funding") {
    return `<p class="meta" style="margin-top:12px;">A funding outcome is uncertain. Reconcile before retrying; PRIOR will not fund twice.</p>`;
  }
  const amount = fundAmount(job);
  if (amount === null) {
    return "";
  }
  if (state.fundPlan) {
    const plan = state.fundPlan;
    return `
    <div class="learned" aria-label="Funding confirmation" style="margin-top:18px;">
      <div class="panel-topline" style="margin-bottom:6px;">
        <p class="kicker memory" style="margin:0;">Confirm funding</p>
        <span class="status-pill status-safe">Read only so far</span>
      </div>
      <p style="font-size:15.5px;">Fund <strong>${escapeHtml(plan.agent || "")}</strong> ${escapeHtml(String(plan.amount))} ${escapeHtml(plan.currency || "USDC")} to start <strong>${escapeHtml(plan.offering || "")}</strong>?</p>
      <p class="meta">PRIOR uses the job budget to pay the agent. Nothing has been funded yet.</p>
      <div class="row">
        <button class="button button-primary" data-fund-confirm${state.busy ? " disabled" : ""}>${state.busy ? "Funding..." : `Fund ${escapeHtml(String(plan.amount))}`}</button>
        <button class="button button-ghost" data-fund-cancel>Back</button>
      </div>
    </div>`;
  }
  if (job.fund_state !== null && job.fund_state !== undefined
      && job.fund_state !== "fund_failed" && job.fund_state !== "fund_prepared") {
    return "";
  }
  return `
    <div class="row">
      <button class="button button-secondary" data-fund${state.busy ? " disabled" : ""}>Fund ${escapeHtml(String(amount))} USDC</button>
    </div>
    <p class="hint">The agent requested ${escapeHtml(String(amount))} USDC to start. Funding needs your explicit confirmation.</p>`;
}

function userReason(job, lesson) {
  const raw = String(job.rejection_reason || lesson.reason || "");
  return raw.replace(/^Learned from rejected job \S+:\s*/i, "");
}

function workerLine(job) {
  const req = job.worker_requirement;
  if (!req || !Array.isArray(req.learned_requirements)) return "";
  const learned = req.learned_requirements.filter((item) => String(item || "").trim());
  if (!learned.length) return "";
  return `<p class="meta small"><span class="tag tag-memory">Memory applied</span> The agent received ${learned.length} learned ${learned.length === 1 ? "requirement" : "requirements"} with this job.</p>`;
}

function reviewPanel(job) {
  const value = (job.deliverable && job.deliverable.value) || {};
  const findings = Array.isArray(value.findings) ? value.findings : [];
  const comparison = value.comparative_summary || (value.deliverables && (value.deliverables.comparative_summary || value.deliverables.comparison));
  const textBlob = value.text && typeof value.text === "string" ? value.text.trim() : "";
  const body = findings.length ? `
      <div class="findings">
        ${findings.map((f, i) => {
          const primary = [];
          const detail = [];
          const skip = new Set(["name", "company", "type", "summary", "sources", "citations"]);
          for (const [k, v] of Object.entries(f)) {
            if (skip.has(k) || typeof v !== "string" || !v) continue;
            const label = k.replace(/_/g, " ");
            const row = { label, val: v };
            if (/evidence|discovery|url|domain|retrieved/i.test(k)) detail.push(row);
            else primary.push(row);
          }
          const rowsHtml = (rows) => rows.map((e) => `<dt>${escapeHtml(e.label)}</dt><dd>${escapeHtml(e.val)}</dd>`).join("");
          return `
          <article class="finding">
            <div class="panel-topline">
              <h3 style="margin:0;">${i + 1}. ${escapeHtml(f.name || f.company || "Finding")}</h3>
              ${f.type ? `<span class="status-pill">${escapeHtml(f.type)}</span>` : ""}
            </div>
            ${f.summary ? `<p style="margin:10px 0 12px;">${escapeHtml(f.summary)}</p>` : ""}
            ${primary.length ? `<dl class="kv">${rowsHtml(primary)}</dl>` : ""}
            ${(f.sources || []).length ? `<p class="meta small">${f.sources.map((s) => `Source: <a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a>`).join(" &middot; ")}</p>` : ""}
            ${detail.length ? `<details class="disclose"><summary>Verification detail</summary><dl class="kv">${rowsHtml(detail)}</dl></details>` : ""}
          </article>`;
        }).join("")}
      </div>` : textBlob
      ? `<p class="deliverable-text">${escapeHtml(textBlob)}</p>`
      : comparison ? `<p class="deliverable-text">${escapeHtml(String(comparison))}</p>`
      : Object.keys(value).length
      ? `<dl class="kv">${Object.entries(value).map(([k, v]) => `<dt>${escapeHtml(String(k).replace(/_/g, " "))}</dt><dd>${escapeHtml(typeof v === "object" && v !== null ? JSON.stringify(v, null, 1) : String(v))}</dd>`).join("")}</dl>`
      : `<p class="meta">The agent submitted its work, but it arrived without readable content.</p>`;
  const comparisonBlock = findings.length && comparison ? `<div class="comparison"><p class="kicker">Side-by-side summary</p><p class="deliverable-text">${escapeHtml(String(comparison))}</p></div>` : "";
  return `
    <section class="opblock spotlight" aria-label="Delivered work" style="margin-top:18px;">
      <div class="panel-topline">
        <h2 style="margin:0;">The result is ready for your review</h2>
        <span class="status-pill status-live"><span class="status-dot" aria-hidden="true"></span>Delivered</span>
      </div>
      ${workerLine(job)}
      ${comparisonBlock}
      ${body}
      <div class="row" id="deliverable-actions"${state.showReject ? " hidden" : ""}>
        <button class="button button-primary" data-accept${state.busy ? " disabled" : ""}>Accept this work</button>
        <button class="button button-secondary" data-show-reject>Reject and teach PRIOR</button>
      </div>
      <form id="reject"${state.showReject ? "" : " hidden"} style="margin-top:8px;">
        <label for="reason">What went wrong?</label>
        <textarea id="reason" name="reason" placeholder="Example: Key factual claims had no source links, so I could not verify them." required></textarea>
        <p class="hint">PRIOR will draft one reusable requirement from your answer. Nothing is stored until you approve it.</p>
        <div class="row">
          <button type="submit" class="button button-primary"${state.busy ? " disabled" : ""}>Submit rejection</button>
          <button type="button" class="button button-ghost" data-hide-reject>Keep for now</button>
        </div>
      </form>
    </section>`;
}

function learningPanel(job) {
  if (job.status === "accepted") {
    return `
      <section class="opblock" aria-label="Job accepted">
        <div class="panel-topline">
          <h2 style="margin:0;">Work accepted</h2>
          <span class="status-pill status-live">Contract fulfilled</span>
        </div>
        <p class="meta">The result matched your contract, so PRIOR kept nothing new. Your memory only grows from lessons you approve.</p>
        <div class="row">
          <button class="button button-primary" data-reset>Start a new job</button>
          <a class="button button-secondary" href="/memory" data-nav="memory">View memory</a>
        </div>
      </section>`;
  }
  const lesson = job.proposed_lesson;
  if (job.status === "rejected" && lesson && lesson.status === "proposed") {
    return `
      <section class="opblock spotlight" aria-label="Proposed lesson" style="margin-top:18px;">
        <div class="panel-topline">
          <h2 style="margin:0;">What should PRIOR remember for next time?</h2>
          <span class="tag tag-memory">Your call</span>
        </div>
        <p class="meta">Your rejection:</p>
        <p class="hd-quote">"${escapeHtml(userReason(job, lesson))}"</p>
        <p class="meta" style="margin-top:14px;">PRIOR proposes this reusable requirement:</p>
        <div class="learned" style="margin:10px 0 16px;">
          <p class="clause" style="margin:0;">"${escapeHtml(lesson.requirement)}"</p>
        </div>
        <form id="edit-lesson">
          <label for="requirement">You can edit the wording before approving</label>
          <input id="requirement" name="requirement" type="text" value="${escapeAttr(lesson.requirement)}" required />
          <div class="row">
            <button class="button button-primary" data-add${state.busy ? " disabled" : ""}>Add to my memory</button>
            <button class="button button-secondary" data-edit${state.busy ? " disabled" : ""}>Save edited text</button>
            <button class="button button-ghost" data-ignore${state.busy ? " disabled" : ""}>Not this time</button>
          </div>
        </form>
        <p class="hint">PRIOR has not stored anything yet. Only "Add" or "Save edited text" puts this requirement into your memory.</p>
      </section>`;
  }
  const saved = lesson && lesson.status === "active";
  const duplicate = lesson && lesson.status === "duplicate";
  return `
    <section class="opblock${saved ? "" : " quiet"}" aria-label="Learning outcome">
      ${saved ? `
      <div class="learned" style="margin:0;">
        <div class="panel-topline" style="margin-bottom:4px;">
          <p class="kicker memory" style="margin:0;">Added to your memory</p>
          <span class="status-pill status-safe">Active</span>
        </div>
        <p class="clause" style="margin:0;">"${escapeHtml(lesson.requirement)}"</p>
        <p class="clause-note">Matching contracts will include this requirement from now on.</p>
      </div>` : duplicate ? `
      <p class="meta" style="margin:0;">This requirement was already in your memory, so nothing new was stored.</p>` : `
      <p class="meta" style="margin:0;">No lesson came from this job. PRIOR learns only from rejections you explain, and rules you approve.</p>`}
      <div class="row">
        <button class="button button-primary" data-reset>Start a new job</button>
        <a class="button button-secondary" href="/memory" data-nav="memory">View memory</a>
      </div>
    </section>`;
}

function statusOutcome(status) {
  if (status === "accepted") return `<span class="outcome"><span class="st-accepted">Accepted</span></span>`;
  if (status === "delivered") return `<span class="outcome"><span class="st-open">Awaiting review</span></span>`;
  if (status === "rejected") return `<span class="outcome"><span class="st-rejected">Rejected</span></span>`;
  if (status === "refused") return `<span class="outcome"><span class="st-rejected">Declined</span></span>`;
  if (status === "specified") return `<span class="outcome"><span class="st-open">Contract ready</span></span>`;
  return `<span class="outcome"><span class="st-open">In progress</span></span>`;
}

function activityHtml(jobs) {
  if (!jobs || !jobs.length) {
    return `<p class="meta">No jobs yet. Your first job will appear here with its date, status, and what memory did for it.</p>`;
  }
  const rows = jobs.slice(0, 10).map((j) => {
    const when = String(j.created_at || "").slice(0, 10);
    const applied = (j.contract && j.contract.applied_lessons && j.contract.applied_lessons.length) || 0;
    const learned = j.proposed_lesson && j.proposed_lesson.status === "active" ? 1 : 0;
    const title = (j.spec && j.spec.raw) || (j.contract && j.contract.title) || j.id;
    const markers = [
      applied ? `<span class="mem">Memory applied</span>` : "",
      learned ? `<span class="learned-yes">Lesson learned</span>` : ""
    ].filter(Boolean).join(" &middot; ");
    return `<li>
      <span class="t"><a href="/app" data-open-job="${escapeAttr(j.id)}">${escapeHtml(title)}</a>
      <span class="s">${escapeHtml(jobProviderLabel(j))}${markers ? ` &middot; ${markers}` : ""}</span></span>
      <span style="display:inline-flex;gap:14px;align-items:baseline;"><span class="when">${escapeHtml(when)}</span>${statusOutcome(j.status)}</span>
    </li>`;
  }).join("");
  return `<ul class="journey">${rows}</ul>`;
}

function jobProviderLabel(j) {
  const p = j.provider;
  if (p && p.name) return escapeHtml(p.name);
  if (j.status === "specified") return "Not hired yet";
  return "Not hired yet";
}

function activitySection(jobs) {
  const n = (jobs || []).length;
  return `
    <section class="ws-section" aria-label="Recent jobs" style="margin-top:44px;">
      <div class="panel-topline">
        <h2 style="margin:0;font-size:18px;">Recent jobs</h2>
        <span class="meta small">${n} total</span>
      </div>
      ${activityHtml(jobs)}
    </section>`;
}

/* ------------------------------------------------------------------ memory */

async function renderMemory() {
  try {
    state.memory = await api("/api/memory");
    state.dash = state.memory;
  } catch (err) {
    state.error = err.message;
    state.memory = { lessons: [], count: 0, status: "unavailable", message: err.message };
  }
  const mem = state.memory || { lessons: [], count: 0 };
  const lessons = mem.lessons || [];
  const active = mem.count || 0;
  const activeLessons = lessons.filter((l) => l.status === "active");
  const pausedLessons = lessons.filter((l) => l.status !== "active");

  const rowHtml = (l, i, isActive) => `
    <article class="memory-row${isActive ? "" : " inactive"}">
      <div class="memory-top">
        <span class="tag ${isActive ? "tag-memory" : ""}">${isActive ? "Active requirement" : "Paused"}</span>
        <span class="meta small">${formatDate(l.created_at)}</span>
      </div>
      <h2>${escapeHtml(l.requirement)}</h2>
      <div class="memory-facts">
        <span class="fact"><span>Applies to</span><strong>${escapeHtml(l.job_type)} jobs</strong></span>
        <span class="fact"><span>Source</span><strong>${isActive && l.source_job_id ? `a job you rejected (${escapeHtml(String(l.source_job_id).replace(/^job_/, "").slice(0, 8))})` : "one of your jobs"}</strong></span>
        <span class="fact"><span>Approval</span><strong>Approved by you</strong></span>
      </div>
      <div class="memory-foot">
        <p class="meta small" style="margin:0;">${isActive
          ? "New matching contracts include this requirement before the agent starts."
          : "Paused. PRIOR will not add it to new contracts."}</p>
        <div style="display:flex;gap:8px;">
          ${l.source_job_id ? `<button class="button button-ghost button-small" data-open-job="${escapeAttr(l.source_job_id)}">See the job</button>` : ""}
          ${isActive ? `<button class="button button-secondary button-small" data-disable="${escapeAttr(l.id)}">Pause this requirement</button>` : ""}
        </div>
      </div>
    </article>`;

  shell(`
    <div class="app-header">
      <div>
        <p class="eyebrow memory">What PRIOR has learned</p>
        <h1>Your memory.</h1>
        <p class="lede">Requirements learned from jobs you rejected and approved. They flow into every new contract that matches, and never leave this workspace.</p>
      </div>
      <span class="status-pill${active ? " status-safe" : ""}">${active} active</span>
    </div>
    ${mem.status === "unavailable" ? `<div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(mem.message || "Memory is unavailable right now.")}</p></div>` : ""}
    ${!lessons.length && mem.status !== "unavailable" ? `
    <section class="opblock" aria-label="Empty memory">
      <h2 style="font-size:20px;">Nothing learned yet.</h2>
      <p class="meta">That is normal for a fresh workspace. When a delivered job disappoints, reject it and explain why. PRIOR will propose a reusable requirement, and only what you approve ends up here.</p>
      <div class="row"><a class="button button-primary" href="/app" data-nav="app">Start a job</a></div>
    </section>` : ""}
    ${activeLessons.map((l, i) => rowHtml(l, i, true)).join("")}
    ${pausedLessons.length ? `
      <p class="panel-label" style="margin-top:36px;">Paused</p>
      ${pausedLessons.map((l, i) => rowHtml(l, i, false)).join("")}` : ""}
  `);
}

function formatDate(iso) {
  const s = String(iso || "");
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s.slice(0, 10);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/* ------------------------------------------------------------------- proof */

async function renderProof() {
  if (!state.health) {
    try { state.health = await api("/api/health"); } catch { state.health = null; }
  }
  const ws = state.workspace || {};
  const h = state.health;
  const checkOf = (name) => (h && h.checks || []).find((c) => c.name === name) || null;
  const sibyl = checkOf("sibyl-memory");
  const buyer = checkOf("virtuals-acp-buyer");
  const local = checkOf("local-provider");
  let proofHtml = "";
  if (state.baseProof) {
    const bp = state.baseProof;
    proofHtml = `
      <div class="panel" aria-label="Base result">
        <div class="panel-topline">
          <p class="kicker" style="margin:0;">Live Base RPC result</p>
          <span class="status-pill status-safe">Verified</span>
        </div>
        <p><strong>${escapeHtml(bp.network_name)}</strong> via <code class="mono">${escapeHtml(bp.rpc)}</code></p>
        <dl class="kv">
          <dt>Policy registry</dt><dd><code class="mono">${escapeHtml(bp.policy_registry)}</code><br /><span class="meta small">policyExists(0) = ${bp.policyExists_0 === "0x0000000000000000000000000000000000000000000000000000000000000001" ? "true (0x01)" : "returned " + escapeHtml(String(bp.policyExists_0)).slice(0, 10) + "..."}</span></dd>
          <dt>B20 factory</dt><dd><code class="mono">${escapeHtml(bp.factory)}</code><br /><span class="meta small">isB20(factory) = ${bp.isB20_factory === "0x0000000000000000000000000000000000000000000000000000000000000000" ? "false (0x00)" : "returned " + escapeHtml(String(bp.isB20_factory)).slice(0, 10) + "..."}</span></dd>
        </dl>
        <p class="meta small">${escapeHtml(bp.product_reason || "")}</p>
        <p class="meta small">Not claimed: ${escapeHtml(bp.not_claimed || "")}</p>
      </div>`;
  }
  const virtualsLive = ws.hire_mode === "virtuals";
  shell(`
    <div class="proof-header">
      <div>
        <p class="eyebrow">Technical proof</p>
        <h1>Evidence you can inspect.</h1>
        <p class="lede">Read-only records from real PRIOR runs on this deployment. Nothing here spends funds or invents state.</p>
      </div>
      <span class="status-pill">Read only</span>
    </div>

    <div class="proof-integrity">
      <span class="status-pill${h ? " status-safe" : ""}">${h ? escapeHtml(h.overall || "unknown") : "Status unavailable"}</span>
      <p>${h ? `Build <code class="mono">${escapeHtml(String(h.build_commit || "unknown")).slice(0, 12)}</code>. Source: <a href="https://github.com/Techkeyy/prior" target="_blank" rel="noreferrer" style="color:var(--memory);">github.com/Techkeyy/prior</a>` : "The health endpoint could not be reached."}</p>
    </div>

    <section class="ws-section" aria-label="Memory proof">
      <div class="panel-topline">
        <p class="proof-num">01 &middot; Memory</p>
        <span class="status-pill${sibyl && sibyl.status === "PASS" ? " status-safe" : ""}">${sibyl ? escapeHtml(sibyl.status) : "unknown"}</span>
      </div>
      <h2>Sibyl-backed learning that survives restarts.</h2>
      <p class="meta">Approved lessons are written as Sibyl memory entities, isolated per workspace, and recalled to mutate the next matching contract. Recall was verified across separate processes and cold starts.</p>
      <details class="proof"><summary>Implementation and evidence files</summary>
        <p class="meta">Code: <code class="mono">src/prior/memory.py</code>, <code class="mono">src/prior/contract.py</code>. Evidence: <code class="mono">evidence/fresh-session-prior.json</code>, <code class="mono">evidence/stable-deployment-flow.json</code>, <code class="mono">evidence/deployed-sibyl-flow.json</code>.</p>
      </details>
    </section>

    <section class="ws-section" aria-label="Virtuals ACP proof">
      <div class="panel-topline">
        <p class="proof-num">02 &middot; Agent commerce</p>
        <span class="status-pill${virtualsLive && buyer && buyer.status === "PASS" ? " status-safe" : "status-live"}">${virtualsLive ? "Virtuals ACP active" : "Local provider"}</span>
      </div>
      <h2>Work is delivered through Virtuals ACP.</h2>
      <p class="meta">${virtualsLive
        ? "This deployment hires through the official ACP Node SDK v2 (buyer side) against a registered seller offering. Jobs you hire carry their ACP job id and, once settled, their Base transaction. The active path is a known registered provider; live marketplace discovery of arbitrary agents is a planned phase, not a current claim."
        : "This environment runs the local research agent instead of Virtuals ACP. The ACP adapter is present and fails honestly without credentials; no partner credit is claimed here."}</p>
      <details class="proof"><summary>Implementation and evidence files</summary>
        <p class="meta">Adapter: <code class="mono">src/prior/providers/virtuals.py</code> via <code class="mono">acp-bridge/</code> (<code class="mono">@virtuals-protocol/acp-node-v2</code>). Validation: <code class="mono">scripts/verify_virtuals_acp.py</code>. Evidence: <code class="mono">evidence/virtuals-acp-live.json</code>, <code class="mono">evidence/production-acp-persistence.json</code>.</p>
      </details>
    </section>

    <section class="ws-section" aria-label="Base proof">
      <div class="panel-topline">
        <p class="proof-num">03 &middot; Base</p>
        <span class="status-pill status-live">Live read on demand</span>
      </div>
      <h2>Base, read live from your browser.</h2>
      <p class="meta">ACP jobs on this deployment settle on Base. You can also run a direct read against the official B20 precompile endpoints right now. No payment, registration, or transfer is performed.</p>
      <div class="row">
        <button class="button button-primary" data-verify-base="mainnet"${state.busy ? " disabled" : ""}>Run Base mainnet read</button>
        <button class="button button-secondary" data-verify-base="sepolia"${state.busy ? " disabled" : ""}>Run Base Sepolia read</button>
      </div>
      ${proofHtml}
    </section>

    <section class="ws-section" aria-label="Deployment proof">
      <div class="panel-topline">
        <p class="proof-num">04 &middot; Deployment</p>
        <span class="status-pill">Public and reproducible</span>
      </div>
      <h2>One service, honest checks.</h2>
      <p class="meta">Python + FastAPI behind Caddy with HTTPS, systemd services for the app and the ACP buyer, SQLite Sibyl storage on the host, and a doctor endpoint the UI just read above.</p>
      ${local ? `<div class="proof-row"><span>Local provider: ${escapeHtml(local.status)} (${escapeHtml(local.detail)})</span></div>` : ""}
      <div class="row"><a class="button button-secondary" href="/app" data-nav="app">Back to workspace</a></div>
    </section>
  `);
}

/* ------------------------------------------------------------------ render */

function render() {
  updateNav();
  const current = route();
  if (current === "landing") return renderLanding();
  if (current === "memory") return renderMemory();
  if (current === "proof") return renderProof();
  return renderDashboard();
}

/* -------------------------------------------------------------------- bind */

function bind() {
  document.querySelectorAll("[data-nav]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const href = a.getAttribute("href");
      history.pushState({}, "", href);
      state.error = "";
      state.notification = "";
      state.showReject = false;
      state.hirePlan = null;
    state.fundPlan = null;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  document.querySelectorAll("[data-anchor]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const href = a.getAttribute("href") || "";
      const targetId = a.getAttribute("data-anchor") || href.split("#")[1] || "";
      if (route() !== "landing") {
        history.pushState({}, "", "/");
        state.error = "";
        state.notification = "";
        render();
      }
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      }
    });
  });

  document.querySelectorAll("[data-open-job]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const id = a.getAttribute("data-open-job");
      run(async () => {
        state.job = await api(`/api/jobs/${id}`);
        state.showReject = false;
        state.hirePlan = null;
    state.fundPlan = null;
        history.pushState({}, "", "/app");
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  });

  document.querySelectorAll("[data-chip]").forEach(chip => {
    const fill = () => {
      const text = chip.getAttribute("data-chip");
      const textarea = document.getElementById("need");
      if (textarea) {
        textarea.value = text;
        textarea.focus();
      }
    };
    chip.addEventListener("click", fill);
    chip.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fill();
      }
    });
  });

  const specify = document.getElementById("specify");
  if (specify) specify.addEventListener("submit", async (event) => {
    event.preventDefault();
    const terminalStatuses = new Set(["accepted", "rejected", "refused"]);
    if (state.job && !terminalStatuses.has(state.job.status)) {
      return;
    }
    await run(async () => {
      const text = new FormData(specify).get("text");
      state.job = await api("/api/jobs", { method: "POST", body: JSON.stringify({ text }) });
      state.hirePlan = null;
    state.fundPlan = null;
    });
  });

  const hire = document.querySelector("[data-hire]");
  if (hire) hire.addEventListener("click", () => run(async () => {
    const res = await api(`/api/jobs/${state.job.id}/hire/prepare`, { method: "POST" });
    state.job = res.job;
    state.hirePlan = res.hire_plan;
  }));

  const hireConfirm = document.querySelector("[data-hire-confirm]");
  if (hireConfirm) hireConfirm.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/hire/execute`, { method: "POST" });
    state.hirePlan = null;
    state.fundPlan = null;
  }));

  const hireCancel = document.querySelector("[data-hire-cancel]");
  if (hireCancel) hireCancel.addEventListener("click", () => {
    state.hirePlan = null;
    state.fundPlan = null;
    render();
  });

  const fund = document.querySelector("[data-fund]");
  if (fund) fund.addEventListener("click", () => run(async () => {
    const res = await api(`/api/jobs/${state.job.id}/fund/prepare`, { method: "POST" });
    state.job = res.job;
    state.fundPlan = res.fund_plan;
  }));

  const fundConfirm = document.querySelector("[data-fund-confirm]");
  if (fundConfirm) fundConfirm.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/fund/execute`, { method: "POST" });
    state.fundPlan = null;
  }));

  const fundCancel = document.querySelector("[data-fund-cancel]");
  if (fundCancel) fundCancel.addEventListener("click", () => {
    state.fundPlan = null;
    render();
  });

  const reset = document.querySelector("[data-reset]");
  if (reset) reset.addEventListener("click", () => {
    state.job = null;
    state.error = "";
    state.notification = "";
    state.showReject = false;
    state.hirePlan = null;
    state.fundPlan = null;
    history.pushState({}, "", "/app");
    render();
  });

  const accept = document.querySelector("[data-accept]");
  if (accept) accept.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/accept`, { method: "POST" });
    state.notification = "Work accepted. That contract is fulfilled.";
  }));

  const showReject = document.querySelector("[data-show-reject]");
  if (showReject) showReject.addEventListener("click", () => {
    state.showReject = true;
    render();
    const reason = document.getElementById("reason");
    if (reason) reason.focus();
  });

  const hideReject = document.querySelector("[data-hide-reject]");
  if (hideReject) hideReject.addEventListener("click", () => {
    state.showReject = false;
    render();
  });

  const reject = document.getElementById("reject");
  if (reject) reject.addEventListener("submit", async (event) => {
    event.preventDefault();
    await run(async () => {
      const reason = new FormData(reject).get("reason");
      state.job = await api(`/api/jobs/${state.job.id}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
      state.showReject = false;
    });
  });

  const add = document.querySelector("[data-add]");
  if (add) add.addEventListener("click", (event) => {
    event.preventDefault();
    lessonAction("add");
  });

  const edit = document.querySelector("[data-edit]");
  if (edit) edit.addEventListener("click", (event) => {
    event.preventDefault();
    lessonAction("edit");
  });

  const ignore = document.querySelector("[data-ignore]");
  if (ignore) ignore.addEventListener("click", (event) => {
    event.preventDefault();
    lessonAction("ignore");
  });

  document.querySelectorAll("[data-disable]").forEach((button) => {
    button.addEventListener("click", async () => {
      await run(async () => {
        state.memory = await api(`/api/memory/${button.getAttribute("data-disable")}/disable`, { method: "POST" });
        state.notification = "Requirement paused. Future contracts will not include it.";
      });
    });
  });

  document.querySelectorAll("[data-verify-base]").forEach((button) => {
    button.addEventListener("click", async () => {
      const net = button.getAttribute("data-verify-base") || "mainnet";
      await run(async () => {
        state.baseProof = await api(`/api/base/verify?network=${net}`);
      });
    });
  });
}

async function lessonAction(action) {
  const form = document.getElementById("edit-lesson");
  const requirement = form ? new FormData(form).get("requirement") : null;
  await run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/lessons`, {
      method: "POST",
      body: JSON.stringify({ action, requirement }),
    });
    if (action === "add" || action === "edit") {
      state.notification = "Added to your memory. Matching contracts will use it from now on.";
    }
  });
}

async function run(fn) {
  state.busy = true;
  state.error = "";
  render();
  try {
    await fn();
  } catch (err) {
    state.error = err.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function poll(id) {
  try {
    const job = await api(`/api/jobs/${id}`);
    if (!state.job || state.job.id !== id) return;
    state.job = job;
    if ((job.status === "working" || job.status === "hired") && job.prior_lifecycle !== "expired") {
      setTimeout(() => poll(id), 1200);
    } else {
      render();
    }
  } catch (err) {
    state.error = err.message;
    render();
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}
function escapeAttr(value) { return escapeHtml(value); }

async function boot() {
  try {
    state.workspace = await api("/api/workspace");
  } catch (err) {
    state.workspace = { hire_mode: "none" };
  }
  render();
  loadIdentity();
}

function identitySlot() {
  return document.getElementById("identity-state");
}

/* First-entry auth choice (guest vs Google) on /app only. Presentation state
   only: sessionStorage decides whether the dialog has been shown this browser
   session. It is NEVER authentication truth; /api/auth/me remains the sole
   source of signed-in state, and the dialog is rendered only after /api/auth/me
   has answered unauthenticated. */
const AUTH_PROMPT_KEY = "prior_auth_prompt_seen";
let authPromptEl = null;

function authPromptSeen() {
  try { return window.sessionStorage.getItem(AUTH_PROMPT_KEY) === "1"; } catch { return true; }
}

function markAuthPromptSeen() {
  try { window.sessionStorage.setItem(AUTH_PROMPT_KEY, "1"); } catch { /* private mode: skip re-prompt */ }
}

function maybeShowAuthPrompt() {
  if (authPromptEl) return;
  if (route() !== "app") return;
  if (typeof document === "undefined" || !document.body) return;
  const me = state.identity;
  if (!me || me.authenticated) return;
  if (authPromptSeen()) return;

  const previouslyFocused = document.activeElement;
  const wrap = document.createElement("div");
  wrap.className = "auth-prompt";
  const googleBtn = me.google_configured
    ? `<a class="button button-primary" href="/api/auth/google/start">Continue with Google</a>`
    : `<p class="ap-body" style="margin:0 0 10px;">Google sign in is unavailable right now.</p>`;
  wrap.innerHTML = `
    <div class="auth-prompt-card" role="dialog" aria-modal="true" aria-labelledby="ap-title" aria-describedby="ap-body">
      <h2 id="ap-title">Save your PRIOR memory</h2>
      <p id="ap-body" class="ap-body">Sign in to keep your jobs and learned requirements across browsers. You can also continue without signing in.</p>
      <div class="auth-prompt-actions">
        ${googleBtn}
        <button type="button" class="button button-secondary" data-auth-guest>Continue as guest</button>
      </div>
      <p class="auth-prompt-sub">Your PRIOR memory follows you, not your browser.</p>
    </div>`;
  document.body.appendChild(wrap);
  authPromptEl = wrap;

  const card = wrap.querySelector(".auth-prompt-card");
  const focusables = Array.from(card.querySelectorAll("a[href], button"));

  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      closePrompt();
      return;
    }
    if (event.key !== "Tab" || !focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onBackdropClick(event) {
    if (event.target === wrap) closePrompt();
  }

  function closePrompt() {
    // A real dismissal is the choice: guest button, Escape, or backdrop.
    // Display alone never marks the prompt seen.
    markAuthPromptSeen();
    document.removeEventListener("keydown", onKeydown, true);
    wrap.removeEventListener("click", onBackdropClick);
    [document.getElementById("site-header"), app].forEach((el) => {
      if (el) { el.removeAttribute("inert"); el.removeAttribute("aria-hidden"); }
    });
    wrap.remove();
    authPromptEl = null;
    if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
  }

  [document.getElementById("site-header"), app].forEach((el) => {
    if (el) { el.setAttribute("inert", ""); el.setAttribute("aria-hidden", "true"); }
  });
  document.addEventListener("keydown", onKeydown, true);
  wrap.addEventListener("click", onBackdropClick);
  wrap.querySelector("[data-auth-guest]").addEventListener("click", closePrompt);
  const googleLink = wrap.querySelector('.auth-prompt-actions a[href="/api/auth/google/start"]');
  if (googleLink) googleLink.addEventListener("click", markAuthPromptSeen);
  if (focusables.length) focusables[0].focus();
}

// Authentication truth comes ONLY from /api/auth/me. The ?auth=... query
// value is a transient navigation signal, never proof of authentication: a
// logged-out browser presenting a stale signed-in query must never see a "Signed in"
// claim. The account branch ("Signed in as <...>") is the sole success UI.
function authStatusNotice(isAuthenticated, authParam) {
  if (isAuthenticated) return "";
  if (authParam === "error" || authParam === "cancelled" || authParam === "signed-in") return "auth-incomplete";
  return "";
}

function consumeAuthQueryParam() {
  try {
    if (typeof location === "undefined" || typeof history === "undefined") return false;
    const url = new URL(location.href, "http://local");
    if (!url.searchParams.has("auth")) return false;
    url.searchParams.delete("auth");
    const rest = url.searchParams.toString();
    history.replaceState({}, "", url.pathname + (rest ? "?" + rest : "") + url.hash);
    return true;
  } catch { return false; }
}

async function loadIdentity() {
  const slot = identitySlot();
  if (!slot) return;
  // Capture the one-time navigation signal, then consume it on EVERY load:
  // authenticated and signed-out alike. The URL must never retain auth state.
  const authParam = new URLSearchParams(location.search).get("auth");
  consumeAuthQueryParam();
  let me;
  try {
    me = await api("/api/auth/me");
  } catch (err) {
    slot.textContent = "";
    return;
  }
  state.identity = me;
  if (me && me.authenticated && me.account) {
    slot.innerHTML = `
      <span class="id-signed" title="Signed in">Signed in as ${escapeHtml(me.account.email || me.account.display_name || "account")}</span>
      <button class="button button-ghost button-small" data-signout type="button">Sign out</button>`;
    const out = slot.querySelector("[data-signout]");
    if (out) out.addEventListener("click", async () => {
      try { await api("/api/auth/logout", { method: "POST" }); } catch (err) { /* stay signed in on failure */ }
      // Presentation only, never auth truth: signing out must not immediately
      // re-prompt a returning user this session.
      markAuthPromptSeen();
      consumeAuthQueryParam();
      loadIdentity();
      try { state.workspace = await api("/api/workspace"); } catch (err) { /* keep */ }
      render();
    });
    return;
  }
  const notice = authStatusNotice(Boolean(me && me.authenticated), authParam);
  const authNotice = notice === "auth-incomplete"
    ? `<span class="id-note">Sign in did not complete. Guest mode still works.</span>` : "";
  const googleBtn = me && me.google_configured
    ? `<a class="button button-secondary button-small" href="/api/auth/google/start">Continue with Google</a>`
    : `<span class="id-note" title="Server not configured yet">Google sign in unavailable</span>`;
  const emailBtn = me && me.email_configured
    ? `<button class="button button-ghost button-small" data-email-toggle type="button">Continue with email</button>`
    : ``;
  slot.innerHTML = `
    <span class="id-save">Save your PRIOR memory</span>
    ${googleBtn}${emailBtn}${authNotice}
    <form class="id-email-form" data-email-form hidden>
      <input type="email" name="email" placeholder="you@example.com" required autocomplete="email" />
      <button class="button button-secondary button-small" type="submit">Send code</button>
      <span class="id-note" data-email-status></span>
    </form>
    <form class="id-email-form" data-code-form hidden>
      <input type="text" name="code" inputmode="numeric" placeholder="6 digit code" required autocomplete="one-time-code" />
      <button class="button button-secondary button-small" type="submit">Verify</button>
      <span class="id-note" data-code-status></span>
    </form>`;
  maybeShowAuthPrompt();
  const toggle = slot.querySelector("[data-email-toggle]");
  const emailForm = slot.querySelector("[data-email-form]");
  const codeForm = slot.querySelector("[data-code-form]");
  if (toggle && emailForm) toggle.addEventListener("click", () => {
    emailForm.hidden = !emailForm.hidden;
    if (codeForm) codeForm.hidden = true;
  });
  if (emailForm) emailForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = slot.querySelector("[data-email-status]");
    const address = new FormData(emailForm).get("email");
    try {
      await api("/api/auth/email/start", { method: "POST", body: JSON.stringify({ email: address }) });
      if (status) status.textContent = "Code sent if delivery is configured. Check your inbox.";
      emailForm.hidden = true;
      if (codeForm) {
        codeForm.hidden = false;
        codeForm.dataset.email = String(address || "");
      }
    } catch (err) {
      if (status) status.textContent = String(err.message || err);
    }
  });
  if (codeForm) codeForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = slot.querySelector("[data-code-status]");
    const form = new FormData(codeForm);
    try {
      await api("/api/auth/email/verify", {
        method: "POST",
        body: JSON.stringify({ email: codeForm.dataset.email || form.get("email") || "", code: form.get("code") }),
      });
      loadIdentity();
      try { state.workspace = await api("/api/workspace"); } catch (err) { /* keep */ }
      render();
    } catch (err) {
      if (status) status.textContent = String(err.message || err);
    }
  });
}

window.addEventListener("popstate", render);
if (typeof document !== "undefined" && document.getElementById("app")) boot();

// Exported for node-based unit tests; browsers ignore this block.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { authStatusNotice, consumeAuthQueryParam, route };
}
