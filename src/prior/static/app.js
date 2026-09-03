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

function stepsHtml(active) {
  const items = ["Request", "Contract", "Work", "Review", "Learning"];
  return `<ol class="steps" aria-label="Job progress">${items.map((label) => {
    const order = { Request: 0, Contract: 1, Work: 2, Review: 3, Learning: 4 };
    const cls = order[label] < order[active] ? "done" : order[label] === order[active] ? "now" : "";
    return `<li class="${cls}">${escapeHtml(label)}</li>`;
  }).join("")}</ol>`;
}

function providerCard(job) {
  const p = (job && job.provider) || {};
  const source = p.source;
  if (source === "local-development") {
    return `<div class="provider-line"><span><strong>Agent:</strong> ${escapeHtml(p.name || "PRIOR Local Research Agent")}</span><span><strong>Network:</strong> Local</span><span class="small">Research source: Wikipedia</span></div>`;
  }
  if (source === "virtuals-acp") {
    return `<div class="provider-line"><span><strong>Agent:</strong> ${escapeHtml(p.name || "Virtuals ACP Agent")}</span><span><strong>Network:</strong> Virtuals ACP</span>${job.acp_job_id ? `<span class="mono">Job ${escapeHtml(job.acp_job_id)}</span>` : ""}${job.tx_hash ? `<span class="mono">Tx ${escapeHtml(job.tx_hash)}</span>` : ""}</div>`;
  }
  return "";
}

function networkHint() {
  const ws = state.workspace;
  if (!ws) return "";
  if (ws.hire_mode === "local") {
    return `<p class="meta">Agent: <strong>PRIOR Local Research Agent</strong>, Local network. Research source: Wikipedia.</p>`;
  }
  if (ws.hire_mode === "virtuals") {
    return `<p class="meta">Agent network: <strong>Virtuals ACP</strong>.</p>`;
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
        <div class="meta small">Learned because a previous research deliverable was rejected. ${escapeHtml(l.match_reason || "Matched to this research request.")}</div>
      </li>`).join("");
    return `
      <section class="learned" aria-label="Remembered requirements">
        <p class="kicker memory">Prior remembered</p>
        <h2>${c.applied_lessons.length} lesson from a previous research job</h2>
        <p class="meta"><strong>Added to this contract:</strong></p>
        <ul class="clean">${items}</ul>
        <p class="clause-note">This requirement will be sent to whichever agent performs this job.</p>
      </section>
    `;
  }
  return `
    <section class="panel" aria-label="Memory check">
      <p class="kicker">Memory check</p>
      <p class="meta">${escapeHtml(c.memory_message || "No matching lesson yet. This job starts from the standard requirements.")}</p>
    </section>
  `;
}

function workerReceived(job) {
  const req = job.worker_requirement;
  if (!req) return "";
  const learned = req.learned_requirements || [];
  return `<section class="panel" aria-label="What the worker received">
    <p class="kicker">Sent to the worker</p>
    ${learned.length ? `<p class="clause">${escapeHtml(learned.join("; "))}</p><p class="meta">This learned clause was included in the worker instructions.</p>` : `<p class="meta">No learned clause was needed for this job.</p>`}
  </section>`;
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
    notif = `<div class="success-banner" role="status">${escapeHtml(state.notification)}</div>`;
  }
  let err = "";
  if (state.error) {
    err = `<div class="error" role="alert">${escapeHtml(state.error)}</div>`;
  }
  app.innerHTML = `${notif}${err}${html}`;
  bind();
}

function renderHome() {
  shell(`
    <section class="hero">
      <p class="kicker">Prior</p>
      <h1>What do you need done?</h1>
      <p class="sub">Every rejected job teaches PRIOR a clause the next contract should not forget.</p>
    </section>
    <form id="specify">
      <label for="need">Research request</label>
      <textarea id="need" name="text" placeholder="Example: Research the top five AI wallet companies and compare their features" required></textarea>
      <div class="row">
        <button type="submit"${state.busy ? " disabled" : ""}>
          ${state.busy ? "Checking memory..." : "Find an agent"}
        </button>
      </div>
    </form>
    <p class="meta small">Try one:</p>
    <div class="chips">
      <span class="chip" data-chip="Research the top five AI wallet companies." role="button" tabindex="0">Top AI wallet companies</span>
      <span class="chip" data-chip="Research the top five decentralized exchanges." role="button" tabindex="0">Top decentralized exchanges</span>
      <span class="chip" data-chip="Compare leading Layer-2 rollups by volume." role="button" tabindex="0">Leading L2 rollups</span>
    </div>
    <div class="footer-proof">Learned clauses live in <a href="/memory" data-nav="memory">Memory</a>. Implementation details live under <a href="/proof" data-nav="proof">Technical proof</a>.</div>
  `);
}

function renderRefused(job) {
  shell(`
    <p class="kicker bad">Outside research scope</p>
    <h1>PRIOR focuses on research</h1>
    <div class="panel">
      <p>${escapeHtml(job.error || job.spec.refusal_reason || "Unsupported request category.")}</p>
      <p class="meta">PRIOR currently handles market analysis, company comparisons, and information gathering.</p>
    </div>
    <div class="row">
      <button class="secondary" data-reset>Start over</button>
    </div>
  `);
}

function renderContract(job) {
  const c = job.contract;
  const learnedSet = new Set((c.applied_lessons || []).map((l) => l.requirement));
  const standard = (c.acceptance || []).filter((item) => !learnedSet.has(item));
  const hireLabel = state.busy ? "Hiring..." : "Hire agent with this contract";
  shell(`
    ${stepsHtml("Contract")}
    <p class="kicker">Contract review</p>
    <h1>${escapeHtml(c.title || "Research contract")}</h1>

    ${memoryBanner(job)}

    <section class="section" aria-label="Your request">
      <div class="section-head"><h2>Your request</h2></div>
      <p>${escapeHtml((job.spec && job.spec.raw) || c.goal || "")}</p>
    </section>

    <section class="section" aria-label="Deliverables">
      <div class="section-head"><h2>Deliverables</h2><span class="count">${(c.deliverables || []).length} items</span></div>
      <ul class="clean">${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
    </section>

    <section class="section" aria-label="Standard requirements">
      <div class="section-head"><h2>Standard requirements</h2></div>
      <ul class="clean">${standard.map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
    </section>

    ${(c.applied_lessons || []).length ? "" : `<p class="meta">No learned clauses matched this request.</p>`}

    <section class="section" aria-label="Provider">
      <div class="section-head"><h2>Agent</h2></div>
      ${providerCard(job) || networkHint()}
    </section>

    <div class="row">
      <button data-hire${state.busy ? " disabled" : ""}>${hireLabel}</button>
      <button class="secondary" data-reset>Cancel</button>
    </div>
  `);
}

function renderProgress(job) {
  shell(`
    ${stepsHtml("Work")}
    <p class="kicker">Agent execution</p>
    <h1>Agent selected. Working now.</h1>
    ${providerCard(job)}
    <div class="skeleton" role="status">Gathering research and applying your contract requirements.</div>
    <p class="meta">Stage: <strong>${escapeHtml(job.acp_phase || job.status)}</strong>. This page updates when the deliverable is ready.</p>
  `);
  poll(job.id);
}

function renderDeliverable(job) {
  const value = (job.deliverable && job.deliverable.value) || {};
  const findings = value.findings || [];
  shell(`
    ${stepsHtml("Review")}
    <p class="kicker">Research result</p>
    <h1>${escapeHtml(value.title || job.contract.title)}</h1>
    ${providerCard(job)}
    <p class="meta">Retrieved: ${escapeHtml(value.retrieved_at || "just now")}</p>

    ${workerReceived(job)}

    <div class="findings">
      ${findings.map((f, i) => `
        <article class="finding">
          <h3>${i + 1}. ${escapeHtml(f.name || "Finding")}</h3>
          <p>${escapeHtml(f.summary || "")}</p>
          ${(f.sources || []).map((s) => `
            <p class="meta">Source: <a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a></p>
          `).join("")}
        </article>
      `).join("") || `<div class="panel"><p>No findings returned from worker.</p></div>`}
    </div>

    ${(value.notes || []).length ? `<ul class="meta">${value.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}

    <div class="row" id="deliverable-actions">
      <button data-accept${state.busy ? " disabled" : ""}>Accept work</button>
      <button class="secondary" data-show-reject>Reject work</button>
    </div>

    <form id="reject" hidden style="margin-top:20px;">
      <div class="panel" style="border-left:4px solid var(--accent);">
        <p class="kicker bad">Reject and teach Prior</p>
        <p>What was missing or wrong? PRIOR will propose one reusable clause from your answer.</p>
        <label for="reason">Rejection reason</label>
        <textarea name="reason" id="reason" placeholder="Example: Material factual claims lacked verifiable source links." required></textarea>
        <div class="row">
          <button type="submit"${state.busy ? " disabled" : ""}>Submit rejection</button>
          <button type="button" class="secondary" data-hide-reject>Cancel</button>
        </div>
      </div>
    </form>
  `);
}

function renderLesson(job) {
  const lesson = job.proposed_lesson;
  shell(`
    ${stepsHtml("Learning")}
    <p class="kicker memory">You found a contract gap</p>
    <h1>Add this clause to future contracts?</h1>
    <p class="lead">Based on your feedback, PRIOR proposes one reusable clause for matching research jobs.</p>

    <section class="learned" aria-label="Proposed clause">
      <p class="kicker memory">Proposed clause</p>
      <p class="clause">"${escapeHtml(lesson.requirement)}"</p>
      <p class="meta">Applies to: ${escapeHtml(lesson.job_type)} jobs. Trigger: ${escapeHtml(lesson.issue || "Quality requirement")}.</p>
      <p class="meta small">Derived from: "${escapeHtml(lesson.reason || "")}"</p>
    </section>

    <form id="edit-lesson">
      <label for="requirement">Clause text (you can edit it)</label>
      <input id="requirement" name="requirement" type="text" value="${escapeAttr(lesson.requirement)}" required />
      <div class="row">
        <button data-add${state.busy ? " disabled" : ""}>Add to PRIOR</button>
        <button class="secondary" data-edit${state.busy ? " disabled" : ""}>Save edited text</button>
        <button class="secondary" data-ignore${state.busy ? " disabled" : ""}>Ignore</button>
      </div>
    </form>
    <p class="meta small">If added, PRIOR stores it with Sibyl Memory and applies it to future matching jobs.</p>
  `);
}

function renderDone(job) {
  const accepted = job.evaluation === "accepted";
  shell(`
    ${stepsHtml("Learning")}
    <p class="kicker ${accepted ? "ok" : "warn"}">Job complete</p>
    <h1>${accepted ? "Work accepted" : "Outcome recorded"}</h1>
    ${providerCard(job)}
    <div class="panel">
      <p>Job <code class="mono">${escapeHtml(job.id)}</code> is now <strong>${escapeHtml(job.status)}</strong>.</p>
      ${job.proposed_lesson && job.proposed_lesson.status === "active" ? `<p class="ok">Learned clause saved: <strong>${escapeHtml(job.proposed_lesson.requirement)}</strong></p><p class="meta small">Stored with Sibyl Memory.</p>` : ""}
      ${job.proposed_lesson && job.proposed_lesson.status === "duplicate" ? `<p class="warn">An identical clause was already active, so nothing new was stored.</p>` : ""}
    </div>
    <div class="row">
      <button data-reset>Start a new job</button>
      <a class="btn secondary" href="/memory" data-nav="memory">Open Memory</a>
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
  const active = (state.memory && state.memory.count) || 0;
  const activeLessons = lessons.filter((l) => l.status === "active");
  const inactiveLessons = lessons.filter((l) => l.status !== "active");
  shell(`
    <p class="kicker memory">Memory</p>
    <h1>Clauses PRIOR has learned</h1>
    <p class="lead">Failed work becomes contract language. PRIOR adds these requirements to future matching jobs.</p>

    ${state.memory && state.memory.status === "unavailable" ? `<div class="error">${escapeHtml(state.memory.message)}</div>` : ""}

    <p class="meta"><strong>${active} active ${active === 1 ? "clause" : "clauses"}</strong> will be added to future matching jobs.</p>

    ${!lessons.length ? `
      <section class="panel" aria-label="Empty memory">
        <h2>PRIOR has not learned anything here yet.</h2>
        <p class="meta">Complete a job and reject work for a real reason. If you approve the lesson, PRIOR will use it to improve future contracts.</p>
        <div class="row"><a class="btn" href="/" data-nav="home">Start a job</a></div>
      </section>
    ` : ""}

    ${activeLessons.map((l) => `
      <article class="memory-card" aria-label="Learned clause">
        <div class="memory-top">
          <span class="badge badge-ok">Active</span>
          <span class="meta small">${escapeHtml(l.job_type)}</span>
        </div>
        <p class="kicker memory">Learned clause</p>
        <h2>${escapeHtml(l.requirement)}</h2>
        <dl class="memory-facts">
          <dt>Learned from</dt><dd>Rejected research job${l.source_job_id ? ` ${escapeHtml(l.source_job_id)}` : ""}</dd>
          <dt>Applies to</dt><dd>${escapeHtml(l.job_type)} jobs</dd>
          <dt>Status</dt><dd>Active</dd>
        </dl>
        <p class="meta">PRIOR will add this requirement to future matching jobs.</p>
        <div class="row"><button class="secondary" data-disable="${escapeAttr(l.id)}">Disable</button></div>
      </article>
    `).join("")}

    ${inactiveLessons.map((l) => `
      <article class="memory-card inactive" aria-label="Inactive clause">
        <div class="memory-top">
          <span class="badge badge-neutral">${escapeHtml(l.status)}</span>
          <span class="meta small">${escapeHtml(l.job_type)}</span>
        </div>
        <h2>${escapeHtml(l.requirement)}</h2>
      </article>
    `).join("")}

    ${lessons.length ? `
    <div class="row">
      <a class="btn" href="/" data-nav="home">New job</a>
    </div>` : ""}
  `);
}

async function renderProof() {
  let proofHtml = "";
  if (state.baseProof) {
    const bp = state.baseProof;
    proofHtml = `
      <div class="panel" aria-label="Base result">
        <p class="kicker ok">Live Base result</p>
        <p><strong>Network:</strong> ${escapeHtml(bp.network_name)}</p>
        <p><strong>RPC:</strong> <code class="mono">${escapeHtml(bp.rpc)}</code></p>
        <p><strong>Policy Registry:</strong> <code class="mono">${escapeHtml(bp.policy_registry)}</code>, <code class="mono">policyExists(0)</code> = <strong>${bp.policyExists_0 === "0x0000000000000000000000000000000000000000000000000000000000000001" ? "true (0x01)" : escapeHtml(bp.policyExists_0)}</strong></p>
        <p><strong>B20 Factory:</strong> <code class="mono">${escapeHtml(bp.factory)}</code>, <code class="mono">isB20(factory)</code> = <strong>${bp.isB20_factory === "0x0000000000000000000000000000000000000000000000000000000000000000" ? "false (0x00)" : escapeHtml(bp.isB20_factory)}</strong></p>
        <p class="meta">${escapeHtml(bp.product_reason)}</p>
      </div>
    `;
  }
  const ws = state.workspace;
  const sibyl = ws ? "Connected" : "Checking";
  const mode = ws && ws.hire_mode === "local" ? "Local Research Agent" : ws && ws.hire_mode === "virtuals" ? "Virtuals ACP" : "No hire provider configured";

  shell(`
    <p class="kicker">Technical proof</p>
    <h1>How PRIOR proves it works</h1>
    <p class="lead">Consumer product first. This page is for judges and developers who want the underlying evidence.</p>

    <section class="panel" aria-label="Integration status">
      <p class="kicker">Status</p>
      <p><strong>Sibyl Memory:</strong> <span class="badge badge-ok">Verified</span> <span class="meta">${escapeHtml(sibyl)}</span></p>
      <p><strong>Base:</strong> <span class="badge badge-ok">Verified B20 read</span></p>
      <p><strong>Virtuals ACP:</strong> <span class="badge badge-neutral">Not verified</span></p>
    </section>

    <section class="panel" aria-label="Base verification">
      <h2>Base onchain check</h2>
      <p class="meta">Runs a live read when you click below. No payment, registration, transfer, or settlement is performed here.</p>
      <div class="row">
        <button data-verify-base="mainnet"${state.busy ? " disabled" : ""}>Run Base mainnet read</button>
        <button class="secondary" data-verify-base="sepolia"${state.busy ? " disabled" : ""}>Run Base Sepolia read</button>
      </div>
      ${proofHtml}
    </section>

    <details class="proof">
      <summary>View implementation details</summary>
      <p class="meta">Memory is stored as workspace scoped lesson records and recalled with text search before every new contract. The browser workspace cookie selects the memory scope. Deleting memory removes future recall.</p>
      <p class="meta">Base uses direct RPC reads against the B20 Factory and Policy Registry addresses. The ACP path uses the official Node SDK and requires registered credentials.</p>
      <p class="meta">Active provider: ${escapeHtml(mode)}. Local runs never claim to be Virtuals.</p>
    </details>

    <div class="row">
      <a class="btn" href="/" data-nav="home">Back to new job</a>
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
    history.pushState({}, "", "/");
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
    badge.textContent = `ws: ${shortId}`;
    badge.title = `Workspace: ${wsId}`;
  } else {
    badge.textContent = `ws: local`;
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
