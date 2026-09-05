const app = document.getElementById("app");
const state = {
  job: null,
  memory: null,
  dash: null,
  workspace: null,
  baseProof: null,
  error: "",
  busy: false,
  showLessonDetails: false,
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
    if (wsBadge) wsBadge.style.display = "none";
    nav.innerHTML = `
      <a href="#how-it-works" data-anchor="how-it-works">How it works</a>
      <a href="/proof" data-nav="proof" class="proof-link">Technical proof</a>
      <a href="/app" data-nav="app" class="button button-primary button-small nav-launch-btn">Launch PRIOR</a>
    `;
  } else {
    if (wsBadge) wsBadge.style.display = "";
    nav.innerHTML = `
      <a href="/app" data-nav="app" class="${current === "app" ? "active" : ""}">Workspace</a>
      <a href="/memory" data-nav="memory" class="${current === "memory" ? "active" : ""}">Memory</a>
      <a href="/proof" data-nav="proof" class="proof-link ${current === "proof" ? "active" : ""}">Technical proof</a>
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

/* Stage pills follow the backbone: request, memory, contract, agent,
   work, review, learning. Activity is a section, not a stage. */
function stageOf(job) {
  if (!job) return "Request";
  if (job.status === "specified") return "Contract";
  if (job.status === "working" || job.status === "hired") return "Work";
  if (job.status === "delivered") return "Review";
  if (job.status === "rejected") return "Learning";
  return "Learning";
}

function stagesHtml(active) {
  const items = ["01 Request", "02 Memory", "03 Contract", "04 Agent", "05 Work", "06 Review", "07 Learning", "08 Activity"];
  const reached = { Request: 0, Memory: 1, Contract: 2, Agent: 3, Work: 4, Review: 5, Learning: 6, Activity: 7 };
  return `<div class="journey-rail" aria-label="Workflow progress">${items.map((label) => {
    const raw = label.slice(3);
    const cls = reached[raw] < reached[active] ? "journey-step journey-active" : raw === active ? "journey-step journey-active" : "journey-step journey-pending";
    return `<span class="${cls}">${escapeHtml(label)}</span>`;
  }).join("")}</div>`;
}

/* Visual priority follows the job. The active stage gets the spotlight;
   irrelevant stages collapse to quiet placeholders. */
function priority(job, section) {
  const s = job ? job.status : null;
  const stored = job && job.proposed_lesson && job.proposed_lesson.status === "active";
  const proposed = job && job.status === "rejected" && job.proposed_lesson && job.proposed_lesson.status !== "ignored";
  switch (section) {
    case "memory":
      if (s === "specified" && job.contract && !job.contract.baseline) return "spot";
      return "";
    case "contract":
      if (s === "specified") return "spot";
      if (s === "working" || s === "hired" || s === "delivered") return "";
      return "quiet";
    case "agent":
      if (s === "specified") return "spot";
      if (!job) return "quiet";
      return "";
    case "work":
      if (s === "working" || s === "hired") return "spot";
      if (!job || s === "specified") return "quiet";
      return "";
    case "review":
      if (s === "delivered") return "spot";
      return "quiet";
    case "learning":
      if (proposed || stored) return "spot";
      if (!job) return "quiet";
      return "";
    default:
      return "";
  }
}

function head(eyebrow, status, hot) {
  return `<div class="panel-topline"><div><p class="panel-label${eyebrow === "Memory" || eyebrow === "Learning" ? " memory" : ""}">${escapeHtml(eyebrow)}</p></div><span class="status-pill ${hot ? "status-safe" : "status-preview"}">${escapeHtml(status)}</span></div>`;
}

function contractStatus(job) {
  if (!job) return "NOT PREPARED";
  if (job.status === "specified" && job.contract && !job.contract.baseline) return "MEMORY APPLIED";
  if (job.status === "specified") return "READY";
  if (job.status === "working" || job.status === "hired") return "IN PROGRESS";
  if (job.status === "delivered") return "FULFILLED";
  return "COMPLETED";
}

function providerCard(job) {
  const p = (job && job.provider) || {};
  const source = p.source;
  if (source === "local-development") {
    return `<p style="font-size:19px;font-weight:700;margin:0 0 8px;">${escapeHtml(p.name || "PRIOR Local Research Agent")}</p><div class="factgrid"><div class="fact"><p class="fl">Network</p><p class="fv">Local</p></div><div class="fact"><p class="fl">Research source</p><p class="fv">Wikipedia</p></div></div><p class="meta small">Development provider. Not Virtuals ACP.</p>`;
  }
  if (source === "virtuals-acp") {
    return `<dl class="kv"><dt>Agent</dt><dd><strong>${escapeHtml(p.name || "Virtuals ACP Agent")}</strong></dd><dt>Network</dt><dd>Virtuals ACP</dd>${job.acp_job_id ? `<dt>Job</dt><dd><span class="mono">${escapeHtml(job.acp_job_id)}</span></dd>` : ""}${job.tx_hash ? `<dt>Tx</dt><dd><span class="mono">${escapeHtml(job.tx_hash)}</span></dd>` : ""}</dl>`;
  }
  return "";
}

function agentSection(job) {
  const ws = state.workspace;
  if (job && job.provider) return providerCard(job);
  if (ws && ws.hire_mode === "local") {
    return `<p style="font-size:19px;font-weight:700;margin:0 0 8px;">PRIOR Local Research Agent</p><div class="factgrid"><div class="fact"><p class="fl">Network</p><p class="fv">Local</p></div><div class="fact"><p class="fl">Research source</p><p class="fv">Wikipedia</p></div></div><p class="meta small">Development provider. Not Virtuals ACP.</p>`;
  }
  if (ws && ws.hire_mode === "virtuals") {
    return `<p><strong>Virtuals ACP.</strong> <span class="meta">A registered offering is required before hiring.</span></p>`;
  }
  return `<p class="meta">No hire path configured yet. Jobs will fail honestly.</p>`;
}

function memoryBanner(job) {
  const c = job.contract || {};
  if (c.memory_status === "unavailable") {
    return `<div class="error">${escapeHtml(c.memory_message)}</div>`;
  }
  if (c.applied_lessons && c.applied_lessons.length) {
    const items = c.applied_lessons.map((l) => `
      <li>
        <span class="clause">${escapeHtml(l.requirement)}</span>
        <div class="meta small">Learned from a previous rejected research job. ${escapeHtml(l.match_reason || "Matched to this research request.")}</div>
      </li>`).join("");
    return `
      <div class="learned" aria-label="Remembered requirements">
        <p class="kicker memory">Memory applied</p>
        <p><strong>${c.applied_lessons.length} previous lesson changed this contract.</strong></p>
        <p class="meta"><strong>Learned from Prior:</strong></p>
        <ul class="clean">${items}</ul>
        <p class="clause-note">This requirement will be sent to whichever agent performs this job.</p>
      </div>
    `;
  }
  return "";
}

function workerReceived(job) {
  const req = job.worker_requirement;
  if (!req) return "";
  const learned = req.learned_requirements || [];
  return `<div class="panel" aria-label="What the worker received">
    <p class="kicker">Sent to the worker</p>
    ${learned.length ? `<p class="clause">${escapeHtml(learned.join("; "))}</p><p class="meta">This learned clause was included in the worker instructions.</p>` : `<p class="meta">No learned clause was needed for this job.</p>`}
  </div>`;
}

function activityHtml(jobs) {
  if (!jobs || !jobs.length) {
    return `<p class="meta">No jobs yet in this workspace. Your first job will appear here with its date, status, provider, and memory outcome.</p>`;
  }
  const rows = jobs.slice(0, 8).map((j, i) => {
    const when = String(j.created_at || "").replace("T", " ").replace(/(\+00:00|Z)$/, "");
    const applied = (j.contract && j.contract.applied_lessons && j.contract.applied_lessons.length) || 0;
    const learned = j.proposed_lesson && j.proposed_lesson.status === "active" ? 1 : 0;
    const title = (j.spec && j.spec.raw) || (j.contract && j.contract.title) || j.id;
    const provider = (j.provider && j.provider.name) || "Not hired yet";
    return `<li><span class="n">${String(i + 1).padStart(2, "0")}</span><span class="t"><a href="/app" data-open-job="${escapeAttr(j.id)}">${escapeHtml(title)}</a><br /><span class="s">${escapeHtml(j.status)} · ${escapeHtml(provider)} · ${applied ? "1 remembered clause applied" : "no clause applied"}${learned ? " · 1 lesson learned" : ""} · ${escapeHtml(when)}</span></span></li>`;
  }).join("");
  return `<ol class="journey">${rows}</ol>`;
}

function render() {
  updateNav();
  const current = route();
  if (current === "landing") return renderLanding();
  if (current === "memory") return renderMemory();
  if (current === "proof") return renderProof();
  return renderDashboard();
}

function foot() {
  return `<footer class="site-footer"><div><a href="/" data-nav="landing" class="footer-brand">PRIOR</a><span>Contracts that learn from rejected agent work.</span></div><div><a href="/app" data-nav="app">Launch PRIOR</a><a href="/memory" data-nav="memory">Memory</a><a href="/proof" data-nav="proof">Technical proof</a></div></footer>`;
}

function shell(html) {
  let notif = "";
  if (state.notification) {
    notif = `<div class="success-banner" role="status"><span class="notice-icon" aria-hidden="true">✓</span><p>${escapeHtml(state.notification)}</p></div>`;
  }
  let err = "";
  if (state.error) {
    err = `<div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(state.error)}</p></div>`;
  }
  app.innerHTML = `${notif}${err}${html}${foot()}`;
  bind();
}

function renderLanding() {
  shell(`
    <section class="landing-hero" aria-label="PRIOR Overview">
      <div class="landing-hero-content">
        <p class="eyebrow">MEMORY-NATIVE AGENT CONTRACTING</p>
        <h1 class="landing-title">Every failed job makes the next contract smarter.</h1>
        <p class="landing-lede">PRIOR learns from rejected agent work and turns what went wrong into reusable requirements for future jobs.</p>
        <div class="landing-cta-row">
          <a href="/app" data-nav="app" class="button button-primary landing-main-cta">Launch PRIOR</a>
          <a href="#how-it-works" data-anchor="how-it-works" class="button button-secondary">See how PRIOR learns</a>
        </div>
        <p class="hero-proof-sub"><a href="/proof" data-nav="proof" class="meta proof-link">Inspect verified technical proof →</a></p>
      </div>
    </section>

    <section class="ws-section landing-problem" aria-label="The Breakdown">
      <p class="eyebrow">THE BREAKDOWN</p>
      <h2>Why hiring autonomous agents repeatedly fails.</h2>
      <p class="meta">Repeatedly hiring agents with incomplete instructions causes repeated mistakes. Without institutional memory, context is lost across jobs.</p>
      <div class="problem-grid">
        <div class="problem-card problem-without">
          <p class="panel-label">WITHOUT PRIOR</p>
          <ul class="clean">
            <li><strong>Blank-slate hiring:</strong> Every agent starts from zero with no memory of prior failures.</li>
            <li><strong>Repeated mistakes:</strong> Agents continuously deliver hallucinated or unsourced data.</li>
            <li><strong>Manual prompt rewrites:</strong> You must manually re-type missing rules into every prompt.</li>
            <li><strong>Fragile execution:</strong> No contract layer encloses agent work or enforces acceptance criteria.</li>
          </ul>
        </div>
        <div class="problem-card problem-with">
          <p class="panel-label memory">WITH PRIOR</p>
          <ul class="clean">
            <li><strong>Continuous contract learning:</strong> Rejections instantly generate reusable requirements.</li>
            <li><strong>Automatic clause injection:</strong> Subsequent jobs inherit approved lessons automatically.</li>
            <li><strong>Cross-agent retention:</strong> Memory persists across different agent providers and runs.</li>
            <li><strong>Rigorous acceptance:</strong> Every contract includes clear deliverables and verification criteria.</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="ws-section landing-signature" aria-label="Signature Transformation">
      <p class="eyebrow memory">SIGNATURE TRANSFORMATION</p>
      <h2>From rejected work to unbreakable contract.</h2>
      <p class="meta">How a single rejection permanently elevates contract quality for every future agent.</p>
      
      <div class="signature-flow">
        <div class="sig-step">
          <span class="sig-num">01</span>
          <div class="sig-content">
            <p class="panel-label">JOB 1 · STANDARD CONTRACT</p>
            <h3>Initial Request Delivered</h3>
            <p class="meta">Worker returns market findings, but key claims lack verifiable source citations.</p>
          </div>
        </div>

        <div class="sig-step">
          <span class="sig-num">02</span>
          <div class="sig-content">
            <p class="panel-label" style="color:var(--danger);">JOB 1 · REJECTION &amp; FEEDBACK</p>
            <h3>Operator Rejection</h3>
            <p class="meta quote">"Material factual claims lacked verifiable source links."</p>
          </div>
        </div>

        <div class="sig-step">
          <span class="sig-num">03</span>
          <div class="sig-content">
            <p class="panel-label memory">SIBYL · APPROVED LESSON</p>
            <h3>PRIOR Extracts Reusable Clause</h3>
            <p class="clause">"Include primary verifiable source URLs for all key factual claims."</p>
          </div>
        </div>

        <div class="sig-step sig-spotlight">
          <span class="sig-num">04</span>
          <div class="sig-content">
            <div class="panel-topline">
              <p class="panel-label memory">JOB 2 · NEXT CONTRACT</p>
              <span class="status-pill status-safe">MEMORY APPLIED</span>
            </div>
            <h3>Future Agents Inherit Requirement</h3>
            <p class="meta">Every subsequent research job automatically embeds this requirement before the agent begins work.</p>
          </div>
        </div>
      </div>
    </section>

    <section id="how-it-works" class="ws-section landing-steps" aria-label="How It Works">
      <p class="eyebrow">HOW IT WORKS</p>
      <h2>The self-improving contracting loop.</h2>
      <p class="meta">Six distinct stages turn user intent into rigorous, verifiable agent deliverables.</p>

      <div class="steps-grid">
        <div class="step-card">
          <span class="step-badge">01</span>
          <h3>Ask</h3>
          <p class="meta">Describe your task in natural language. PRIOR structures your goal into discrete deliverables.</p>
        </div>
        <div class="step-card">
          <span class="step-badge">02</span>
          <h3>Remember</h3>
          <p class="meta">PRIOR queries Sibyl memory to retrieve relevant lessons learned from previous rejected jobs.</p>
        </div>
        <div class="step-card">
          <span class="step-badge">03</span>
          <h3>Contract</h3>
          <p class="meta">A formal contract is assembled with acceptance criteria, deliverables, and learned clauses.</p>
        </div>
        <div class="step-card">
          <span class="step-badge">04</span>
          <h3>Agent</h3>
          <p class="meta">Dispatches the work to the appropriate execution agent with strict contract instructions.</p>
        </div>
        <div class="step-card">
          <span class="step-badge">05</span>
          <h3>Review</h3>
          <p class="meta">Inspect the agent deliverable and findings. Accept the work or reject it with feedback.</p>
        </div>
        <div class="step-card">
          <span class="step-badge">06</span>
          <h3>Learn</h3>
          <p class="meta">Rejecting work prompts a new reusable clause that you approve to improve all future contracts.</p>
        </div>
      </div>
    </section>

    <section class="ws-section landing-trust" aria-label="Architectural Guarantees">
      <p class="eyebrow">ARCHITECTURAL GUARANTEES</p>
      <h2>Built for rigorous agent operations.</h2>
      <p class="meta">Enterprise-grade isolation, explicit human approval, and cross-provider durability.</p>

      <div class="trust-grid">
        <div class="trust-card">
          <h3>Contracts Improve Continuously</h3>
          <p class="meta">Every rejected job sharpens future requirements. Your institutional playbook gets stronger with each run.</p>
        </div>
        <div class="trust-card">
          <h3>Cross-Agent Persistence</h3>
          <p class="meta">Memory persists across different agent models and execution providers. You don't lose lessons when switching agents.</p>
        </div>
        <div class="trust-card">
          <h3>Cryptographic Isolation</h3>
          <p class="meta">Workspaces are isolated per user. Learned clauses, contracts, and deliverables never leak across workspaces.</p>
        </div>
        <div class="trust-card">
          <h3>Human In The Loop</h3>
          <p class="meta">No silent prompt modifications. You review and approve every learned clause before it becomes an active rule.</p>
        </div>
      </div>
    </section>

    <section class="ws-section landing-proof-strip" aria-label="Technical Proof">
      <div class="proof-strip-card">
        <div>
          <p class="eyebrow">VERIFIED REPLAY &amp; PROOF</p>
          <h3>Technical proof you can inspect.</h3>
          <p class="meta">Read-only live records from real execution runs. Zero fund spending, zero mock claims.</p>
        </div>
        <div class="proof-strip-badges">
          <div class="proof-badge-item">
            <span class="badge badge-ok">VERIFIED</span>
            <span class="mono small">Sibyl Memory</span>
          </div>
          <div class="proof-badge-item">
            <span class="badge badge-ok">VERIFIED READ</span>
            <span class="mono small">Base B20 RPC</span>
          </div>
          <div class="proof-badge-item">
            <span class="badge badge-neutral">FAIL-CLOSED</span>
            <span class="mono small">Virtuals ACP</span>
          </div>
        </div>
        <div>
          <a href="/proof" data-nav="proof" class="button button-secondary">Inspect proof →</a>
        </div>
      </div>
    </section>

    <section class="landing-bottom-cta" aria-label="Get Started">
      <div class="bottom-cta-card">
        <p class="eyebrow">GET STARTED WITH PRIOR</p>
        <h2>Make the next job smarter than the last.</h2>
        <p class="lede">Launch your private workspace and run your first research contract now.</p>
        <div class="row center">
          <a href="/app" data-nav="app" class="button button-primary landing-main-cta">Launch PRIOR</a>
        </div>
      </div>
    </section>
  `);
}

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
  const stage = stageOf(job && job.status !== "refused" ? job : null);

  if (job && job.status === "refused") {
    shell(`
      <div class="app-header">
        <div>
          <p class="eyebrow">YOUR WORKSPACE</p>
          <h1>What do you need done?</h1>
          <p class="lede">Every rejected job can teach PRIOR a clause the next contract should not forget.</p>
        </div>
        <span class="status-pill status-safe">${escapeHtml(state.workspace && state.workspace.network ? state.workspace.network.toUpperCase() : "LOCAL")}</span>
      </div>
      ${stagesHtml("Request")}
      <div class="error" role="alert"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(job.error || "PRIOR focuses on research jobs.")}</p></div>
      <div class="row"><button class="button button-secondary" data-reset>Start over</button></div>
      ${memorySection(lessons, dash.count)}
      ${activitySection(dash.jobs)}
    `);
    return;
  }

  shell(`
    <div class="app-header">
      <div>
        <p class="eyebrow">YOUR WORKSPACE</p>
        <h1>What do you need done?</h1>
        <p class="lede">Every rejected job can teach PRIOR a clause the next contract should not forget.</p>
      </div>
      <span class="status-pill status-safe">${escapeHtml(state.workspace && state.workspace.network ? state.workspace.network.toUpperCase() : "LOCAL")}</span>
    </div>
    ${stagesHtml(stage)}

    <section class="opcard" aria-label="New request">
      <form id="specify">
        <label class="left" for="need">Research request</label>
        <textarea id="need" name="text" placeholder="Example: Research the top five AI wallet companies and compare their features" required></textarea>
        <div class="row center">
          <button type="submit" class="button button-primary"${state.busy ? " disabled" : ""}>${state.busy ? "Checking memory..." : "Find an agent"}</button>
        </div>
      </form>
      <div class="chips">
        <span class="chip" data-chip="Research the top five AI wallet companies." role="button" tabindex="0">Top AI wallet companies</span>
        <span class="chip" data-chip="Research the top five decentralized exchanges." role="button" tabindex="0">Top decentralized exchanges</span>
        <span class="chip" data-chip="Compare leading Layer-2 rollups by volume." role="button" tabindex="0">Leading L2 rollups</span>
      </div>
    </section>

    ${memorySection(lessons, dash.count, priority(job, "memory"))}
    ${contractSection(job, priority(job, "contract"))}
    ${agentSectionHtml(job, priority(job, "agent"))}
    ${workSection(job, priority(job, "work"))}
    ${reviewSection(job)}
    ${learningSection(job, priority(job, "learning"))}
    ${activitySection(dash.jobs)}
  `);
  if (job && (job.status === "working" || job.status === "hired")) poll(job.id);
}

function memorySection(lessons, count, level) {
  const status = `${count} active ${count === 1 ? "lesson" : "lessons"}`;
  const preview = lessons.slice(0, 2).map((l) => `
    <div class="learned" aria-label="Learned clause">
      <p class="panel-label memory">Learned clause</p>
      <p class="clause">${escapeHtml(l.requirement)}</p>
      <dl class="memory-facts">
        <dt>Applies to</dt><dd>${escapeHtml(l.job_type)} jobs</dd>
        <dt>Status</dt><dd>Active</dd>
      </dl>
    </div>`).join("");
  return `
    <section class="ws-section" aria-label="Memory">
      ${head("Memory", status, count > 0)}
      <h2>Your memory.</h2>
      <p class="meta">What PRIOR already knows.</p>
      <div class="opblock${level === "spot" ? " spotlight" : ""}">
      ${lessons.length ? `
        ${preview}
        ${lessons.length > 2 ? `<p class="meta small">Showing the 2 most recent of ${lessons.length}.</p>` : ""}
        <p><a class="meta" href="/memory" data-nav="memory">View all memory clauses →</a></p>
      ` : `
        <p><strong>No lessons yet.</strong></p>
        <p class="meta">Rejected work can become a reusable requirement after you approve it.</p>
        <p><a class="meta" href="/memory" data-nav="memory">View Memory →</a></p>
      `}
      </div>
    </section>`;
}

function contractSection(job, level) {
  if (!job) {
    return `
    <section class="ws-section" aria-label="Contract">
      ${head("Contract", "Not prepared", false)}
      <h2>What the agent will actually be asked to do.</h2>
      <div class="opblock quiet">
        <div class="opgrid">
          <div><h3>Request</h3><p class="meta">No request yet.</p></div>
          <div><h3>Requirements</h3><p class="meta">Created after the memory check.</p></div>
        </div>
      </div>
    </section>`;
  }
  const c = job.contract || {};
  const learnedSet = new Set((c.applied_lessons || []).map((l) => l.requirement));
  const standard = (c.acceptance || []).filter((item) => !learnedSet.has(item));
  const status = contractStatus(job);
  return `
    <section class="ws-section" aria-label="Contract">
      ${head("Contract", status, status === "MEMORY APPLIED" || status === "READY")}
      <h2>What the agent will actually be asked to do.</h2>
      ${memoryBanner(job)}
      <div class="opblock${status === "MEMORY APPLIED" ? " memory-applied" : level === "spot" ? " spotlight" : ""}">
        <div class="opgrid">
          <div><h3>Request</h3><p>${escapeHtml((job.spec && job.spec.raw) || c.goal || "")}</p>
            <h3>Deliverables</h3><ul class="clean">${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
          </div>
          <div><h3>Standard</h3><ul class="clean">${standard.map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
            ${(c.applied_lessons || []).length ? `<h3>Learned from Prior</h3><ul class="clean">${(c.applied_lessons || []).map((l) => `<li><strong>${escapeHtml(l.requirement)}</strong></li>`).join("")}</ul>` : `<p class="meta small">Standard requirements apply. No learned clause matched.</p>`}
          </div>
        </div>
      </div>
      ${job.status === "specified" ? `<div class="row"><button class="button button-primary" data-hire${state.busy ? " disabled" : ""}>${state.busy ? "Hiring..." : "Hire agent with this contract"}</button><button class="button button-secondary" data-reset>Cancel</button></div>` : ""}
    </section>`;
}

function agentSectionHtml(job, level) {
  const ready = (job && job.provider) || (state.workspace && (state.workspace.hire_mode === "local" || state.workspace.hire_mode === "virtuals"));
  const status = ready ? "Ready" : "Not configured";
  const quiet = level === "quiet";
  return `
    <section class="ws-section" aria-label="Agent">
      ${head("Agent", status, !!ready)}
      <h2>Who is doing the work.</h2>
      ${quiet ? `<div class="opblock quiet"><p class="meta">No agent needed yet. The provider appears once a request exists.</p></div>` : `
      <div class="opblock${level === "spot" ? " spotlight" : ""}">
        ${agentSection(job)}
      </div>`}
    </section>`;
}

function workSection(job, level) {
  if (!job || job.status === "specified" || job.status === "refused") {
    return `
    <section class="ws-section" aria-label="Work">
      ${head("Work", "Idle", false)}
      <h2>Current job.</h2>
      <div class="opblock quiet"><p class="meta">${!job ? "Nothing is running. Submit a request and hire an agent to start work." : "Contract ready. Work starts when you hire the agent."}</p></div>
    </section>`;
  }
  if (job.status === "working" || job.status === "hired") {
    return `
    <section class="ws-section" aria-label="Work">
      ${head("Work", "Working", true)}
      <h2>Current job.</h2>
      <div class="opblock${level === "spot" ? " spotlight" : ""}">
        <div class="skeleton" role="status">Agent selected. Working now. Gathering research and applying your contract requirements.</div>
        <p class="meta" style="margin-top:12px;">Stage: <strong>${escapeHtml(job.acp_phase || job.status)}</strong>. This section updates when the deliverable is ready.</p>
      </div>
    </section>`;
  }
  return `
    <section class="ws-section" aria-label="Work">
      ${head("Work", "Done", false)}
      <h2>Current job.</h2>
      <div class="opblock quiet"><p class="meta">This job finished the work stage. See Review and Learning below.</p></div>
    </section>`;
}

function reviewSection(job) {
  if (!job || job.status !== "delivered") return "";
  const value = (job.deliverable && job.deliverable.value) || {};
  const findings = value.findings || [];
  return `
    <section class="ws-section" aria-label="Review">
      ${head("Review", "Ready", true)}
      <h2>Review the agent work.</h2>
      <p class="meta">Retrieved: ${escapeHtml(value.retrieved_at || "just now")}</p>
      ${workerReceived(job)}
      <div class="findings">
        ${findings.map((f, i) => {
          const dlKeys = [];
          if (f.pricing) dlKeys.push({ label: "Pricing", val: f.pricing });
          if (f.supported_platforms || f["supported platforms"]) dlKeys.push({ label: "Supported platforms", val: f.supported_platforms || f["supported platforms"] });
          if (f.strengths) dlKeys.push({ label: "Strengths", val: f.strengths });
          if (f.weaknesses) dlKeys.push({ label: "Weaknesses", val: f.weaknesses });
          
          for (const [k, v] of Object.entries(f)) {
            if (!["name", "company", "type", "summary", "products", "pricing", "supported_platforms", "supported platforms", "strengths", "weaknesses", "sources", "citations", "evidence", "warning", "retrieved_at"].includes(k)) {
              if (typeof v === "string" && v) dlKeys.push({ label: k.replace(/_/g, " "), val: v });
            }
          }

          return `
          <article class="finding" style="margin-bottom:20px;">
            <div class="panel-topline">
              <h3 style="margin:0;">${i + 1}. ${escapeHtml(f.name || "Finding")}</h3>
              <span class="status-pill status-safe">${escapeHtml(f.type || "Product")}</span>
            </div>
            <p style="margin:10px 0 16px;">${escapeHtml(f.summary || "")}</p>
            ${dlKeys.length ? `
              <div class="factgrid" style="margin-bottom:14px;">
                ${dlKeys.map(dk => `
                  <div class="fact" style="grid-column: span 2;">
                    <p class="fl">${escapeHtml(dk.label)}</p>
                    <p class="fv" style="font-size:14px;line-height:1.5;font-weight:400;">${escapeHtml(dk.val)}</p>
                  </div>
                `).join("")}
              </div>
            ` : ""}
            ${(f.sources || []).map((s) => `<p class="meta">Source: <a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a></p>`).join("")}
          </article>`;
        }).join("") || `<div class="panel"><p>No findings returned from worker.</p></div>`}
      </div>
      ${(value.notes || []).length ? `<ul class="meta">${value.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}
      <div class="row" id="deliverable-actions">
        <button class="button button-primary" data-accept${state.busy ? " disabled" : ""}>Accept work</button>
        <button class="button button-secondary" data-show-reject>Reject work</button>
      </div>
      <form id="reject" hidden style="margin-top:20px;">
        <div class="panel" style="border-left:5px solid var(--accent);">
          <p class="panel-label" style="color:var(--accent);">Reject and teach Prior</p>
          <p>What was missing or wrong? PRIOR will propose one reusable clause from your answer.</p>
          <label for="reason">Rejection reason</label>
          <textarea name="reason" id="reason" placeholder="Example: Material factual claims lacked verifiable source links." required></textarea>
          <div class="row">
            <button type="submit" class="button button-primary"${state.busy ? " disabled" : ""}>Submit rejection</button>
            <button type="button" class="button button-secondary" data-hide-reject>Cancel</button>
          </div>
        </div>
      </form>
    </section>`;
}

function learningSection(job, level) {
  if (!job || job.status === "specified" || job.status === "working" || job.status === "hired" || job.status === "delivered") {
    return `
    <section class="ws-section" aria-label="Learning">
      ${head("Learning", "No lesson yet", false)}
      <h2>What this job taught PRIOR.</h2>
      <div class="opblock quiet"><p class="meta">PRIOR only learns after you reject work for a real reason and approve the resulting lesson.</p></div>
    </section>`;
  }
  if (job.status === "rejected" && job.proposed_lesson && job.proposed_lesson.status !== "ignored") {
    const lesson = job.proposed_lesson;
    const stored = lesson.status === "active";
    return `
    <section class="ws-section" aria-label="Learning">
      ${head("Learning", stored ? "Stored" : "Gap found", true)}
      <h2>What this job taught PRIOR.</h2>
      ${stored ? `<p class="meta">Stored with Sibyl Memory. Future matching jobs can now inherit this requirement.</p>` : ""}
      <div class="learned" aria-label="Contract gap">
        <p class="panel-label memory">Contract gap found</p>
        <p class="meta">Your feedback:</p>
        <p>"${escapeHtml(lesson.reason || job.rejection_reason || "")}"</p>
        <p class="meta">PRIOR proposes:</p>
        <p class="clause">"${escapeHtml(lesson.requirement)}"</p>
        <p class="meta">If approved, this becomes a reusable requirement for future matching jobs.</p>
      </div>
      <form id="edit-lesson">
        <label for="requirement">Clause text (you can edit it)</label>
        <input id="requirement" name="requirement" type="text" value="${escapeAttr(lesson.requirement)}" required />
        <div class="row">
          <button class="button button-primary" data-add${state.busy ? " disabled" : ""}>Add to PRIOR</button>
          <button class="button button-secondary" data-edit${state.busy ? " disabled" : ""}>Save edited text</button>
          <button class="button button-secondary" data-ignore${state.busy ? " disabled" : ""}>Ignore</button>
        </div>
      </form>
    </section>`;
  }
  const saved = job.proposed_lesson && job.proposed_lesson.status === "active";
  return `
    <section class="ws-section" aria-label="Learning">
      ${head("Learning", saved ? "Stored" : "No lesson yet", !!saved)}
      <h2>What this job taught PRIOR.</h2>
      <div class="opblock${saved ? " spotlight" : " quiet"}">
      ${saved ? `<p>Learned clause saved: <strong>${escapeHtml(job.proposed_lesson.requirement)}</strong>. Stored with Sibyl Memory.</p>` : `<p class="meta">No reusable rule came out of this job.</p>`}
      </div>
      <div class="row"><button class="button button-primary" data-reset>Start a new job</button><a class="button button-secondary" href="/memory" data-nav="memory">Open Memory</a></div>
    </section>`;
}

function activitySection(jobs) {
  const n = (jobs || []).length;
  return `
    <section class="ws-section" aria-label="Activity">
      ${head("Activity", n ? `${n} ${n === 1 ? "job" : "jobs"}` : "Empty", n > 0)}
      <h2>Your recent jobs.</h2>
      <div class="opblock">
        <p class="meta">Real workspace history only. Select a job to reopen its summary.</p>
        ${activityHtml(jobs)}
      </div>
    </section>`;
}

async function renderMemory() {
  try {
    state.memory = await api("/api/memory");
  } catch (err) {
    state.error = err.message;
  }
  const lessons = (state.memory && state.memory.lessons) || [];
  const active = (state.memory && state.memory.count) || 0;
  const activeLessons = lessons.filter((l) => l.status === "active");
  const inactiveLessons = lessons.filter((l) => l.status !== "active");
  shell(`
    <div class="app-header">
      <div>
        <p class="eyebrow memory">INSTITUTIONAL MEMORY</p>
        <h1>Your memory.</h1>
        <p class="lede">Reusable requirements learned from previous work in this workspace. Other workspaces never see them.</p>
      </div>
      <span class="status-pill ${active > 0 ? "status-safe" : "status-preview"}">${active} ACTIVE ${active === 1 ? "CLAUSE" : "CLAUSES"}</span>
    </div>
    ${state.memory && state.memory.status === "unavailable" ? `<div class="error"><span class="notice-icon" aria-hidden="true">!</span><p>${escapeHtml(state.memory.message)}</p></div>` : ""}
    <section class="ws-section" aria-label="Active lessons">
      <div class="panel-topline">
        <div><p class="panel-label">ACTIVE LESSONS</p></div>
        <span class="status-pill status-safe">${active} STORED</span>
      </div>
      ${!lessons.length ? `
        <div class="panel" aria-label="Empty memory">
          <h2>PRIOR has not learned anything here yet.</h2>
          <p class="meta">Complete a job and reject work for a real reason. If you approve the lesson, PRIOR will use it to improve future contracts.</p>
          <div class="row"><a class="button button-primary" href="/" data-nav="home">Start a job</a></div>
        </div>` : ""}
      ${activeLessons.map((l, i) => `
        <article class="memory-card" aria-label="Learned clause">
          <div class="memory-top"><span class="status-pill status-safe">ACTIVE</span><span class="meta small mono">L_${escapeHtml(String(i + 1).padStart(3, "0"))}</span></div>
          <p class="panel-label memory">Learned clause</p>
          <h2>${escapeHtml(l.requirement)}</h2>
          <dl class="memory-facts">
            <dt>Source</dt><dd>Rejected job · ${escapeHtml((l.source_job_id || "past research").replace(/^job_/, ""))}</dd>
            <dt>Applies to</dt><dd>${escapeHtml(l.job_type)} jobs</dd>
            <dt>Status</dt><dd>Active in Sibyl</dd>
          </dl>
          <p class="meta">PRIOR will automatically consider this clause for future matching jobs.</p>
          <div class="row"><button class="button button-secondary button-small" data-disable="${escapeAttr(l.id)}">Disable clause</button></div>
        </article>`).join("")}
      ${inactiveLessons.map((l) => `
        <article class="memory-card inactive" aria-label="Inactive clause">
          <div class="memory-top"><span class="status-pill status-preview">${escapeHtml(l.status)}</span><span class="meta small">${escapeHtml(l.job_type)}</span></div>
          <h2>${escapeHtml(l.requirement)}</h2>
        </article>`).join("")}
    </section>
  `);
}

async function renderProof() {
  let proofHtml = "";
  if (state.baseProof) {
    const bp = state.baseProof;
    proofHtml = `
      <div class="panel" aria-label="Base result" style="margin-top:20px;">
        <div class="panel-topline">
          <div><p class="panel-label">LIVE BASE RPC RESULT</p></div>
          <span class="status-pill status-safe">VERIFIED</span>
        </div>
        <p><strong>Network:</strong> ${escapeHtml(bp.network_name)}</p>
        <p><strong>RPC Endpoint:</strong> <code class="mono">${escapeHtml(bp.rpc)}</code></p>
        <div class="factgrid">
          <div class="fact">
            <p class="fl">Policy Registry</p>
            <p class="fv"><code class="mono">${escapeHtml(bp.policy_registry)}</code></p>
            <p class="meta small"><code class="mono">policyExists(0)</code> = <strong>${bp.policyExists_0 === "0x0000000000000000000000000000000000000000000000000000000000000001" ? "true (0x01)" : escapeHtml(bp.policyExists_0)}</strong></p>
          </div>
          <div class="fact">
            <p class="fl">B20 Factory</p>
            <p class="fv"><code class="mono">${escapeHtml(bp.factory)}</code></p>
            <p class="meta small"><code class="mono">isB20(factory)</code> = <strong>${bp.isB20_factory === "0x0000000000000000000000000000000000000000000000000000000000000000" ? "false (0x00)" : escapeHtml(bp.isB20_factory)}</strong></p>
          </div>
        </div>
        <p class="meta">${escapeHtml(bp.product_reason)}</p>
      </div>`;
  }
  const ws = state.workspace;
  const mode = ws && ws.hire_mode === "local" ? "Local Research Agent" : ws && ws.hire_mode === "virtuals" ? "Virtuals ACP" : "No hire provider configured";
  shell(`
    <div class="proof-header">
      <div>
        <p class="eyebrow">VERIFIED REPLAY &amp; PROOF</p>
        <h1>Evidence you can inspect.</h1>
        <p class="lede">Read-only records from real PRIOR execution runs. Nothing here spends funds or invents state.</p>
      </div>
      <span class="status-pill status-safe">READ ONLY</span>
    </div>

    <div class="proof-shell">
      <div class="proof-integrity">
        <span class="status-pill status-safe">SIBYL &amp; BASE VERIFIED</span>
        <p>Cold-start recall, multi-user isolation, and Base B20 precompile reads are operational on this node.</p>
      </div>

      <section class="ws-section" aria-label="Sibyl Memory">
        <div class="panel-topline">
          <div><p class="panel-label">01 · SIBYL MEMORY INTEGRATION</p></div>
          <span class="status-pill status-safe">VERIFIED</span>
        </div>
        <h2>Persistent learning across processes.</h2>
        <p class="meta">Rejected jobs become approved clauses. New requests recall them before the next contract is written.</p>
        <details class="proof"><summary>View implementation details</summary>
          <p class="meta">Approved lessons are stored as WARM lesson records, isolated per workspace. Recall uses text search plus listing in the same workspace. Relevant files: <code class="mono">src/prior/memory.py</code>, <code class="mono">src/prior/contract.py</code>, <code class="mono">src/prior/providers/base.py</code>. Evidence: <code class="mono">evidence/fresh-session-prior.json</code>, <code class="mono">evidence/stable-deployment-flow.json</code>.</p>
        </details>
      </section>

      <section class="ws-section" aria-label="Base">
        <div class="panel-topline">
          <div><p class="panel-label">02 · BASE B20 READ INTEGRATION</p></div>
          <span class="status-pill status-safe">VERIFIED B20 READ</span>
        </div>
        <h2>Live precompile read on Base.</h2>
        <p class="meta">Runs a live read when you click below. No payment, registration, transfer, or settlement is performed here.</p>
        <div class="row">
          <button class="button button-primary" data-verify-base="mainnet"${state.busy ? " disabled" : ""}>Run Base mainnet read</button>
          <button class="button button-secondary" data-verify-base="sepolia"${state.busy ? " disabled" : ""}>Run Base Sepolia read</button>
        </div>
        ${proofHtml}
      </section>

      <section class="ws-section" aria-label="Virtuals ACP">
        <div class="panel-topline">
          <div><p class="panel-label">03 · VIRTUALS ACP V2</p></div>
          <span class="status-pill status-preview">NOT CONFIGURED</span>
        </div>
        <h2>Honest fail-closed state.</h2>
        <p class="meta">No registered buyer, no registered seller, no offering, and no real ACP job exist yet, so no partner credit is claimed. The adapter is ready and fails honestly without credentials. Active provider: ${escapeHtml(mode)}.</p>
        <details class="proof"><summary>View implementation details</summary>
          <p class="meta">Adapter: <code class="mono">src/prior/providers/virtuals.py</code> through <code class="mono">acp-bridge/</code> with the official Node SDK v2. Validation: <code class="mono">scripts/verify_virtuals_acp.py</code>. Evidence: <code class="mono">evidence/virtuals-acp-live.json</code>.</p>
        </details>
      </section>

      <div class="row"><a class="button button-secondary" href="/app" data-nav="app">Back to workspace</a></div>
    </div>
  `);
}

function bind() {
  document.querySelectorAll("[data-nav]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const href = a.getAttribute("href");
      history.pushState({}, "", href);
      state.error = "";
      state.notification = "";
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  document.querySelectorAll("[data-anchor]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const targetId = a.getAttribute("data-anchor");
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
    await run(async () => {
      const text = new FormData(specify).get("text");
      state.job = await api("/api/jobs", { method: "POST", body: JSON.stringify({ text }) });
    });
  });

  const hire = document.querySelector("[data-hire]");
  if (hire) hire.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/hire`, { method: "POST" });
  }));

  const reset = document.querySelector("[data-reset]");
  if (reset) reset.addEventListener("click", () => {
    state.job = null;
    state.error = "";
    state.notification = "";
    history.pushState({}, "", "/app");
    render();
  });

  const accept = document.querySelector("[data-accept]");
  if (accept) accept.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/accept`, { method: "POST" });
    state.notification = "Work accepted. Thank you.";
  }));

  const showReject = document.querySelector("[data-show-reject]");
  if (showReject) showReject.addEventListener("click", () => {
    const form = document.getElementById("reject");
    if (form) form.hidden = false;
    const actions = document.getElementById("deliverable-actions");
    if (actions) actions.hidden = true;
    const reason = document.getElementById("reason");
    if (reason) reason.focus();
  });

  const hideReject = document.querySelector("[data-hide-reject]");
  if (hideReject) hideReject.addEventListener("click", () => {
    const form = document.getElementById("reject");
    if (form) form.hidden = true;
    const actions = document.getElementById("deliverable-actions");
    if (actions) actions.hidden = false;
  });

  const reject = document.getElementById("reject");
  if (reject) reject.addEventListener("submit", async (event) => {
    event.preventDefault();
    await run(async () => {
      const reason = new FormData(reject).get("reason");
      state.job = await api(`/api/jobs/${state.job.id}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
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
        state.notification = "Clause disabled. Future jobs will not use it.";
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
      state.notification = "Clause saved. PRIOR will use it in future matching jobs.";
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
    state.job = job;
    if (job.status === "working" || job.status === "hired") {
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

function updateWorkspaceBadge() {
  const badge = document.getElementById("workspace-badge");
  if (!badge) return;
  const wsId = state.workspace && state.workspace.workspace_id;
  if (wsId) {
    const raw = wsId.replace(/^ws_/, "");
    const shortId = raw.length > 8 ? `${raw.slice(0, 4)}...${raw.slice(-4)}` : raw;
    badge.textContent = `WS ${shortId}`;
    badge.title = `Workspace: ${wsId}`;
  } else {
    badge.textContent = `WS local`;
  }
}

async function boot() {
  try {
    state.workspace = await api("/api/workspace");
  } catch (err) {
    state.workspace = { hire_mode: "none" };
  }
  updateWorkspaceBadge();
  render();
}

window.addEventListener("popstate", render);
boot();
