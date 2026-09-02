const app = document.getElementById("app");
const state = {
  job: null,
  memory: null,
  workspace: null,
  baseProof: null,
  error: "",
  busy: false,
  showLessonDetails: false,
  notification: ""
};

function route() {
  const p = location.pathname;
  if (p === "/memory") return "memory";
  if (p === "/proof") return "proof";
  return "home";
}

function updateNavActive() {
  const current = route();
  document.querySelectorAll("nav a").forEach(a => {
    const target = a.getAttribute("data-nav") || (a.getAttribute("href") === "/memory" ? "memory" : a.getAttribute("href") === "/proof" ? "proof" : "home");
    if (target === current) {
      a.classList.add("active");
    } else {
      a.classList.remove("active");
    }
  });
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

function providerCard(job) {
  const p = (job && job.provider) || {};
  const source = p.source;
  if (source === "local-development") {
    return `<div class="panel">
      <p class="kicker">Execution Provider</p>
      <p><strong>Provider:</strong> ${escapeHtml(p.name || "PRIOR Local Research Agent")}</p>
      <p><strong>Network:</strong> <span class="badge badge-neutral">Local Provider (Wikipedia API)</span></p>
      <p class="meta">Truthful local development agent. Not Virtuals ACP.</p>
    </div>`;
  }
  if (source === "virtuals-acp") {
    return `<div class="panel">
      <p class="kicker">Execution Provider</p>
      <p><strong>Provider:</strong> ${escapeHtml(p.name || "Virtuals ACP Agent")}</p>
      <p><strong>Network:</strong> <span class="badge badge-ok">Virtuals ACP (Base)</span></p>
      ${job.acp_job_id ? `<p class="meta">ACP Job ID: ${escapeHtml(job.acp_job_id)}</p>` : ""}
      ${job.tx_hash ? `<p class="meta">Base Tx: ${escapeHtml(job.tx_hash)}</p>` : ""}
    </div>`;
  }
  return "";
}

function networkHint() {
  const ws = state.workspace;
  if (!ws) return "";
  if (ws.hire_mode === "local") {
    return `<p class="meta">Provider: <strong>PRIOR Local Research Agent</strong> · Network: <strong>Local (Wikipedia API)</strong></p>`;
  }
  if (ws.hire_mode === "virtuals") {
    return `<p class="meta">Network: <strong>Virtuals ACP</strong> · Base Onchain</p>`;
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
        <strong>${escapeHtml(l.requirement)}</strong>
        <div class="meta" style="margin-top:2px;">
          Origin: Job ${escapeHtml(l.source_job_id || "prior")} &bull; 
          Provenance: ${escapeHtml(l.provenance || "user-approved")} &bull; 
          Match: ${escapeHtml(l.match_reason || "domain overlap")}
        </div>
      </li>`).join("");

    return `
      <div class="panel panel-raised" style="border-left: 4px solid var(--ok); background: var(--ok-soft);">
        <p class="kicker ok" style="font-weight:700;">&check; PRIOR Remembered ${c.applied_lessons.length} Lesson${c.applied_lessons.length === 1 ? "" : "s"} From Similar Jobs</p>
        <p class="meta" style="color:var(--ok); margin-bottom:8px;">These learned requirements were automatically added to your contract:</p>
        <ul class="clean" style="color:var(--ink);">${items}</ul>
      </div>
    `;
  }
  return `
    <div class="panel" style="background: var(--surface-raised);">
      <p class="kicker">Memory Check</p>
      <p class="meta">${escapeHtml(c.memory_message || "No relevant lessons found for this domain yet. Starting with standard baseline requirements.")}</p>
    </div>
  `;
}

function workerReceived(job) {
  const req = job.worker_requirement;
  if (!req) return "";
  const learned = req.learned_requirements || [];
  const acceptance = req.acceptance || [];
  return `<div class="panel">
    <p class="kicker">Requirements Passed to Worker Payload</p>
    <ul class="clean">${acceptance.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    ${learned.length ? `<p class="meta ok"><strong>Sibyl-derived requirements:</strong> ${escapeHtml(learned.join("; "))}</p>` : `<p class="meta">No Sibyl-derived requirements on this job.</p>`}
  </div>`;
}

function render() {
  updateNavActive();
  const current = route();
  if (current === "memory") return renderMemory();
  if (current === "proof") return renderProof();
  if (!state.job) return renderHome();

  const job = state.job;
  if (job.status === "refused") return renderRefused(job);
  if (job.status === "specified") return renderContract(job);
  if (job.status === "working" || job.status === "hired") return renderProgress(job);
  if (job.status === "delivered") return renderDeliverable(job);
  if (job.status === "rejected" && job.proposed_lesson && job.proposed_lesson.status !== "ignored") {
    return renderLesson(job);
  }
  return renderDone(job);
}

function shell(html) {
  let notif = "";
  if (state.notification) {
    notif = `<div class="success-banner">${escapeHtml(state.notification)}</div>`;
  }
  let err = "";
  if (state.error) {
    err = `<div class="error">${escapeHtml(state.error)}</div>`;
  }
  app.innerHTML = `${notif}${err}${html}`;
  bind();
}

function renderHome() {
  shell(`
    <p class="kicker">Prior Memory & Agent Contracting</p>
    <h1>What do you need done?</h1>
    <p class="lead">PRIOR hires an AI agent, then remembers what the job taught us when something goes wrong so future contracts are automatically stricter.</p>
    
    <div class="chips">
      <span class="chip" data-chip="Research the top five AI wallet companies.">Top AI wallet companies</span>
      <span class="chip" data-chip="Research the top five decentralized exchanges.">Top decentralized exchanges</span>
      <span class="chip" data-chip="Compare leading Layer-2 rollups by volume.">Leading L2 rollups</span>
    </div>

    <form id="specify">
      <label for="need">Research Request</label>
      <textarea id="need" name="text" placeholder="e.g. Research the top five AI wallet companies and compare their features" required></textarea>
      <div class="row">
        <button type="submit"${state.busy ? " disabled" : ""}>
          ${state.busy ? "Checking memory..." : "Find an agent"}
        </button>
      </div>
    </form>
  `);
}

function renderRefused(job) {
  shell(`
    <p class="kicker bad">Scoping Refusal</p>
    <h1>This build focuses on research</h1>
    <div class="panel">
      <p>${escapeHtml(job.error || job.spec.refusal_reason || "Unsupported request category.")}</p>
      <p class="meta">PRIOR currently specializes in market analysis, company comparisons, and information-gathering jobs.</p>
    </div>
    <div class="row">
      <button class="secondary" data-reset>Start over</button>
    </div>
  `);
}

function renderContract(job) {
  const c = job.contract;
  const hireLabel = state.busy ? "Hiring & Executing..." : "Hire this agent";
  shell(`
    <p class="kicker">Job Specification & Terms</p>
    <h1>${escapeHtml(c.title || "Research Contract")}</h1>
    
    ${memoryBanner(job)}
    
    <div class="panel">
      <p class="kicker">Deliverables</p>
      <ul class="clean">${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
      
      <p class="kicker" style="margin-top:16px;">Acceptance Criteria</p>
      <ul class="clean">${(c.acceptance || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
    </div>

    ${networkHint()}

    <div class="row">
      <button data-hire${state.busy ? " disabled" : ""}>${hireLabel}</button>
      <button class="secondary" data-reset>Cancel</button>
    </div>
  `);
}

function renderProgress(job) {
  shell(`
    <p class="kicker">Agent Execution</p>
    <h1>Working on research...</h1>
    ${providerCard(job)}
    <div class="panel">
      <p class="meta">Phase: <strong>${escapeHtml(job.acp_phase || job.status)}</strong></p>
      <p>Gathering data and applying contract requirements in real time.</p>
    </div>
  `);
  poll(job.id);
}

function renderDeliverable(job) {
  const value = (job.deliverable && job.deliverable.value) || {};
  const findings = value.findings || [];
  shell(`
    <p class="kicker">Research Deliverable</p>
    <h1>${escapeHtml(value.title || job.contract.title)}</h1>
    ${providerCard(job)}
    <p class="meta">Retrieved: ${escapeHtml(value.retrieved_at || "just now")}</p>
    
    ${workerReceived(job)}

    <div class="findings">
      ${findings.map((f, i) => `
        <article class="panel finding">
          <h3>${i + 1}. ${escapeHtml(f.name || "Finding")}</h3>
          <p>${escapeHtml(f.summary || "")}</p>
          ${(f.sources || []).map((s) => `
            <p class="meta">&bull; <a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a></p>
          `).join("")}
        </article>
      `).join("") || `<p class="panel">No findings returned from worker.</p>`}
    </div>

    ${(value.notes || []).length ? `<ul class="meta">${value.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}

    <div class="row" id="deliverable-actions">
      <button data-accept${state.busy ? " disabled" : ""}>&check; Accept Deliverable</button>
      <button class="secondary" data-show-reject>&times; Reject with Reason</button>
    </div>

    <form id="reject" hidden style="margin-top:20px;">
      <div class="panel" style="border-left:3px solid var(--accent);">
        <p class="kicker bad">Rejection Feedback</p>
        <p>Why was this deliverable unsatisfactory? PRIOR will formulate a reusable rule from your reason and store it in Sibyl Memory.</p>
        <textarea name="reason" placeholder="e.g. Material factual claims lacked verifiable source links." required></textarea>
        <div class="row">
          <button type="submit"${state.busy ? " disabled" : ""}>Submit Rejection &amp; Propose Lesson</button>
          <button type="button" class="secondary" data-hide-reject>Cancel</button>
        </div>
      </div>
    </form>
  `);
}

function renderLesson(job) {
  const lesson = job.proposed_lesson;
  shell(`
    <p class="kicker ok">Sibyl Learning Opportunity</p>
    <h1>Should this change future contracts?</h1>
    <p class="lead">PRIOR extracted a reusable lesson from your rejection. If approved, future jobs in this domain will automatically enforce this term.</p>
    
    <div class="panel panel-raised">
      <p class="kicker">Proposed Lesson</p>
      <p><strong>Applies to:</strong> ${escapeHtml(lesson.job_type)} jobs</p>
      <p><strong>Trigger Issue:</strong> ${escapeHtml(lesson.issue || "Quality requirement")}</p>
      <p class="meta"><strong>Derived from:</strong> "${escapeHtml(lesson.reason || "")}"</p>
    </div>

    <form id="edit-lesson">
      <label for="requirement">Requirement Text (Editable)</label>
      <input id="requirement" name="requirement" type="text" value="${escapeAttr(lesson.requirement)}" required />
      <div class="row">
        <button data-add${state.busy ? " disabled" : ""}>&check; Approve &amp; Write to Sibyl</button>
        <button class="secondary" data-edit${state.busy ? " disabled" : ""}>Save Modified Text</button>
        <button class="secondary" data-ignore${state.busy ? " disabled" : ""}>Ignore This Lesson</button>
      </div>
    </form>
  `);
}

function renderDone(job) {
  const accepted = job.evaluation === "accepted";
  shell(`
    <p class="kicker ${accepted ? "ok" : "warn"}">Job Complete</p>
    <h1>${accepted ? "Job Accepted" : "Outcome Recorded"}</h1>
    ${providerCard(job)}
    <div class="panel">
      <p>Job <code>${escapeHtml(job.id)}</code> status: <strong>${escapeHtml(job.status)}</strong></p>
      ${job.proposed_lesson && job.proposed_lesson.status === "active" ? `<p class="ok">&check; Lesson written to Sibyl Memory: <strong>${escapeHtml(job.proposed_lesson.requirement)}</strong></p>` : ""}
      ${job.proposed_lesson && job.proposed_lesson.status === "duplicate" ? `<p class="warn">Note: An identical lesson was already active in Sibyl.</p>` : ""}
    </div>
    <div class="row">
      <button data-reset>Start a New Job</button>
      <a class="btn secondary" href="/memory" data-nav="memory">View All Learned Lessons</a>
    </div>
  `);
}

async function renderMemory() {
  try {
    state.memory = await api("/api/memory");
  } catch (err) {
    state.error = err.message;
  }
  const lessons = (state.memory && state.memory.lessons) || [];
  shell(`
    <p class="kicker">Sibyl WARM Store</p>
    <h1>Learned Lessons</h1>
    <p class="lead">Rules stored in Sibyl Memory for this workspace. These automatically modify future contracts when similar research is requested.</p>
    
    ${state.memory && state.memory.status === "unavailable" ? `<div class="error">${escapeHtml(state.memory.message)}</div>` : ""}
    
    <p class="meta"><strong>${(state.memory && state.memory.count) || 0} active lesson${((state.memory && state.memory.count) || 0) === 1 ? "" : "s"}</strong> currently enforced.</p>
    
    ${lessons.length ? lessons.map((l) => `
      <article class="panel" style="border-left: 3px solid ${l.status === "active" ? "var(--ok)" : "var(--line)"}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
          <span class="badge ${l.status === "active" ? "badge-ok" : "badge-neutral"}">${escapeHtml(l.status)}</span>
          <span class="meta">${escapeHtml(l.job_type)}</span>
        </div>
        <h2 style="font-size:20px; margin:10px 0 6px;">${escapeHtml(l.requirement)}</h2>
        <p class="meta">Trigger: ${escapeHtml(l.issue || "Quality requirement")} &bull; Source: Job ${escapeHtml(l.source_job_id || "past")}</p>
        <p class="meta">Reasoning: ${escapeHtml(l.reason || "")}</p>
        ${l.status === "active" ? `<div style="margin-top:12px;"><button class="secondary" data-disable="${escapeAttr(l.id)}" style="padding:6px 12px; font-size:13px;">Disable Rule</button></div>` : ""}
      </article>
    `).join("") : `<div class="panel"><p>No lessons recorded yet. Reject a research deliverable with a real reason to propose a new lesson.</p></div>`}

    <div class="row">
      <a class="btn" href="/" data-nav="home">New Job</a>
    </div>
  `);
}

async function renderProof() {
  let proofHtml = "";
  if (state.baseProof) {
    const bp = state.baseProof;
    proofHtml = `
      <div class="panel" style="border-left: 3px solid var(--ok); background:var(--surface);">
        <p class="kicker ok">&check; Base B20 Read Live Result</p>
        <p><strong>Network:</strong> ${escapeHtml(bp.network_name)}</p>
        <p><strong>RPC Endpoint:</strong> <code>${escapeHtml(bp.rpc)}</code></p>
        <p><strong>Policy Registry:</strong> <code>${escapeHtml(bp.policy_registry)}</code> &rarr; <code>policyExists(0)</code> = <strong>${bp.policyExists_0 === "0x0000000000000000000000000000000000000000000000000000000000000001" ? "true (0x01)" : escapeHtml(bp.policyExists_0)}</strong></p>
        <p><strong>B20 Factory:</strong> <code>${escapeHtml(bp.factory)}</code> &rarr; <code>isB20(factory)</code> = <strong>${bp.isB20_factory === "0x0000000000000000000000000000000000000000000000000000000000000000" ? "false (0x00)" : escapeHtml(bp.isB20_factory)}</strong></p>
        <p class="meta">${escapeHtml(bp.product_reason)}</p>
      </div>
    `;
  }

  shell(`
    <p class="kicker">System Verification</p>
    <h1>Integrations &amp; Technical Proof</h1>
    <p class="lead">Real-time status of Sibyl Memory, Base onchain interaction, and Agent Providers.</p>
    
    <div class="panel">
      <h2>1. Base Onchain Verification</h2>
      <p class="meta">Direct <code>eth_call</code> queries against Base B20 Factory and Policy Registry precompiles.</p>
      <div class="row">
        <button data-verify-base="mainnet"${state.busy ? " disabled" : ""}>Run Base Mainnet Query</button>
        <button class="secondary" data-verify-base="sepolia"${state.busy ? " disabled" : ""}>Run Base Sepolia Query</button>
      </div>
      ${proofHtml}
    </div>

    <div class="panel">
      <h2>2. Sibyl Memory Engine</h2>
      <p><strong>Storage Mode:</strong> SQLite WARM entities with FTS5 lexical indexing</p>
      <p><strong>Tenant Isolation:</strong> Workspace cookie (<code>prior_workspace</code>) mapped to Sibyl <code>tenant_id</code></p>
      <p class="meta">Delete Sibyl Memory and PRIOR loses the ability to remember past mistakes across sessions.</p>
    </div>

    <div class="panel">
      <h2>3. Provider Status</h2>
      <p><strong>Active Mode:</strong> ${state.workspace && state.workspace.hire_mode === "local" ? "Local Research Agent (Wikipedia API)" : "Virtuals ACP"}</p>
      <p class="meta">Truthful attribution: Local runs do not claim to be Virtuals.</p>
    </div>

    <div class="row">
      <a class="btn" href="/" data-nav="home">Back to Home</a>
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
    });
  });

  document.querySelectorAll("[data-chip]").forEach(chip => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-chip");
      const textarea = document.getElementById("need");
      if (textarea) {
        textarea.value = text;
        textarea.focus();
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
    history.pushState({}, "", "/");
    render();
  });

  const accept = document.querySelector("[data-accept]");
  if (accept) accept.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/accept`, { method: "POST" });
    state.notification = "Deliverable accepted.";
  }));

  const showReject = document.querySelector("[data-show-reject]");
  if (showReject) showReject.addEventListener("click", () => {
    const form = document.getElementById("reject");
    if (form) form.hidden = false;
    const actions = document.getElementById("deliverable-actions");
    if (actions) actions.hidden = true;
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
        state.notification = "Lesson disabled. Future jobs will not apply this rule.";
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
      state.notification = "Lesson approved and written to Sibyl Memory.";
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

async function boot() {
  try {
    state.workspace = await api("/api/workspace");
  } catch (err) {
    state.workspace = { hire_mode: "none" };
  }
  render();
}

window.addEventListener("popstate", render);
boot();
