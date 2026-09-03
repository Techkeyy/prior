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
  const items = ["Request", "Memory", "Contract", "Agent", "Work", "Review", "Learning", "Activity"];
  const reached = { Request: 0, Memory: 1, Contract: 2, Agent: 3, Work: 4, Review: 5, Learning: 6, Activity: 7 };
  return `<ol class="stages" aria-label="Workflow progress">${items.map((label) => {
    const cls = reached[label] < reached[active] ? "done" : label === active ? "now" : "";
    return `<li class="${cls}">${escapeHtml(label)}</li>`;
  }).join("")}</ol>`;
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
  return `<div class="ws-head"><p class="kicker${eyebrow === "Memory" || eyebrow === "Learning" ? " memory" : ""}">${escapeHtml(eyebrow)}</p><span class="ws-status${hot ? " hot" : ""}">${escapeHtml(status)}</span></div>`;
}

function contractStatus(job) {
  if (!job) return "NOT PREPARED";
  if (job.status === "specified" && job.contract && !job.contract.baseline) return "MEMORY APPLIED";
  if (job.status === "specified") return "READY";
  if (job.status === "working" || job.status === "hired") return "IN PROGRESS";
  if (job.status === "delivered") return "IN PROGRESS";
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
    return `<li><span class="n">${String(i + 1).padStart(2, "0")}</span><span class="t"><a href="/" data-open-job="${escapeAttr(j.id)}">${escapeHtml(title)}</a><br /><span class="s">${escapeHtml(j.status)} · ${escapeHtml(provider)} · ${applied ? "1 remembered clause applied" : "no clause applied"}${learned ? " · 1 lesson learned" : ""} · ${escapeHtml(when)}</span></span></li>`;
  }).join("");
  return `<ol class="journey">${rows}</ol>`;
}

function render() {
  updateNavActive();
  const current = route();
  if (current === "memory") return renderMemory();
  if (current === "proof") return renderProof();
  return renderDashboard();
}

function foot() {
  return `<footer class="workspace-foot"><span><a class="mark" href="/" data-nav="home" style="font-size:15px;">PRIOR</a> <span class="meta small">Contracts that learn.</span></span><span><a href="/" data-nav="home">New job</a> · <a href="/memory" data-nav="memory">Memory</a> · <a href="/proof" data-nav="proof">Technical proof</a></span></footer>`;
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
  app.innerHTML = `${notif}${err}${html}${foot()}`;
  bind();
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
      ${stagesHtml("Request")}
      <p class="kicker">Your workspace</p>
      <h1>What do you need done?</h1>
      <p class="lead">Every rejected job can teach PRIOR a clause the next contract should not forget.</p>
      <div class="error" role="alert">${escapeHtml(job.error || "PRIOR focuses on research jobs.")}</div>
      <div class="row"><button class="secondary" data-reset>Start over</button></div>
      ${memorySection(lessons, dash.count)}
      ${activitySection(dash.jobs)}
    `);
    return;
  }

  shell(`
    ${stagesHtml(stage)}
    <p class="kicker">Your workspace</p>
    <h1>What do you need done?</h1>
    <p class="lead">Every rejected job can teach PRIOR a clause the next contract should not forget.</p>

    <section class="opcard" aria-label="New request">
      <form id="specify">
        <label class="left" for="need">Research request</label>
        <textarea id="need" name="text" placeholder="Example: Research the top five AI wallet companies and compare their features" required></textarea>
        <div class="row center">
          <button type="submit"${state.busy ? " disabled" : ""}>${state.busy ? "Checking memory..." : "Find an agent"}</button>
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
      <p class="kicker memory">Learned clause</p>
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
        <p><a href="/memory" data-nav="memory">View Memory</a></p>
      ` : `
        <p><strong>No lessons yet.</strong></p>
        <p class="meta">Rejected work can become a reusable requirement after you approve it.</p>
        <p><a href="/memory" data-nav="memory">View Memory</a></p>
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
      ${job.status === "specified" ? `<div class="row"><button data-hire${state.busy ? " disabled" : ""}>${state.busy ? "Hiring..." : "Hire agent with this contract"}</button><button class="secondary" data-reset>Cancel</button></div>` : ""}
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
        <p class="meta">Stage: <strong>${escapeHtml(job.acp_phase || job.status)}</strong>. This section updates when the deliverable is ready.</p>
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
        ${findings.map((f, i) => `
          <article class="finding">
            <h3>${i + 1}. ${escapeHtml(f.name || "Finding")}</h3>
            <p>${escapeHtml(f.summary || "")}</p>
            ${(f.sources || []).map((s) => `<p class="meta">Source: <a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a></p>`).join("")}
          </article>`).join("") || `<div class="panel"><p>No findings returned from worker.</p></div>`}
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
        <p class="kicker memory">Contract gap found</p>
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
          <button data-add${state.busy ? " disabled" : ""}>Add to PRIOR</button>
          <button class="secondary" data-edit${state.busy ? " disabled" : ""}>Save edited text</button>
          <button class="secondary" data-ignore${state.busy ? " disabled" : ""}>Ignore</button>
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
      <div class="row"><button data-reset>Start a new job</button><a class="btn secondary" href="/memory" data-nav="memory">Open Memory</a></div>
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
    <p class="kicker">Your memory</p>
    <h1>Your memory.</h1>
    <p class="lead">Reusable requirements learned from previous work in this workspace. Other workspaces never see them.</p>
    ${state.memory && state.memory.status === "unavailable" ? `<div class="error">${escapeHtml(state.memory.message)}</div>` : ""}
    <section class="ws-section" aria-label="Active lessons">
      <p class="kicker">Active lessons</p>
      <p class="meta"><strong>${active} active ${active === 1 ? "clause" : "clauses"}.</strong></p>
      ${!lessons.length ? `
        <div class="panel" aria-label="Empty memory">
          <h2>PRIOR has not learned anything here yet.</h2>
          <p class="meta">Complete a job and reject work for a real reason. If you approve the lesson, PRIOR will use it to improve future contracts.</p>
          <div class="row"><a class="btn" href="/" data-nav="home">Start a job</a></div>
        </div>` : ""}
      ${activeLessons.map((l, i) => `
        <article class="memory-card" aria-label="Learned clause">
          <div class="memory-top"><span class="badge badge-ok">Active</span><span class="meta small mono">L_${escapeHtml(String(i + 1).padStart(3, "0"))}</span></div>
          <p class="kicker memory">Learned clause</p>
          <h2>${escapeHtml(l.requirement)}</h2>
          <dl class="memory-facts">
            <dt>Source</dt><dd>Rejected job · ${escapeHtml((l.source_job_id || "past research").replace(/^job_/, ""))}</dd>
            <dt>Applies to</dt><dd>${escapeHtml(l.job_type)} jobs</dd>
            <dt>Status</dt><dd>Active</dd>
          </dl>
          <p class="meta">PRIOR will automatically consider this clause for future matching jobs.</p>
          <div class="row"><button class="secondary" data-disable="${escapeAttr(l.id)}">Disable</button></div>
        </article>`).join("")}
      ${inactiveLessons.map((l) => `
        <article class="memory-card inactive" aria-label="Inactive clause">
          <div class="memory-top"><span class="badge badge-neutral">${escapeHtml(l.status)}</span><span class="meta small">${escapeHtml(l.job_type)}</span></div>
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
      <div class="panel" aria-label="Base result">
        <p class="kicker ok">Live Base result</p>
        <p><strong>Network:</strong> ${escapeHtml(bp.network_name)}</p>
        <p><strong>RPC:</strong> <code class="mono">${escapeHtml(bp.rpc)}</code></p>
        <p><strong>Policy Registry:</strong> <code class="mono">${escapeHtml(bp.policy_registry)}</code>, <code class="mono">policyExists(0)</code> = <strong>${bp.policyExists_0 === "0x0000000000000000000000000000000000000000000000000000000000000001" ? "true (0x01)" : escapeHtml(bp.policyExists_0)}</strong></p>
        <p><strong>B20 Factory:</strong> <code class="mono">${escapeHtml(bp.factory)}</code>, <code class="mono">isB20(factory)</code> = <strong>${bp.isB20_factory === "0x0000000000000000000000000000000000000000000000000000000000000000" ? "false (0x00)" : escapeHtml(bp.isB20_factory)}</strong></p>
        <p class="meta">${escapeHtml(bp.product_reason)}</p>
      </div>`;
  }
  const ws = state.workspace;
  const mode = ws && ws.hire_mode === "local" ? "Local Research Agent" : ws && ws.hire_mode === "virtuals" ? "Virtuals ACP" : "No hire provider configured";
  shell(`
    <p class="kicker">Technical proof</p>
    <h1>What PRIOR has actually demonstrated.</h1>
    <p class="lead">Read-only evidence from real runs. Nothing here sends a transaction or spends funds.</p>

    <section class="ws-section" aria-label="Sibyl Memory">
      <p class="kicker">01 · Sibyl Memory</p>
      <h2>Verified</h2>
      <p class="meta">Rejected jobs become approved clauses. New requests recall them before the next contract is written.</p>
      <details class="proof"><summary>View implementation details</summary>
        <p class="meta">Approved lessons are stored as WARM lesson records, isolated per workspace. Recall uses text search plus listing in the same workspace. Relevant files: <code class="mono">src/prior/memory.py</code>, <code class="mono">src/prior/contract.py</code>, <code class="mono">src/prior/providers/base.py</code>. Evidence: <code class="mono">evidence/fresh-session-prior.json</code>, <code class="mono">evidence/stable-deployment-flow.json</code>.</p>
      </details>
    </section>

    <section class="ws-section" aria-label="Base">
      <p class="kicker">02 · Base</p>
      <h2>Verified B20 read</h2>
      <p class="meta">Runs a live read when you click below. No payment, registration, transfer, or settlement is performed here.</p>
      <div class="row">
        <button data-verify-base="mainnet"${state.busy ? " disabled" : ""}>Run Base mainnet read</button>
        <button class="secondary" data-verify-base="sepolia"${state.busy ? " disabled" : ""}>Run Base Sepolia read</button>
      </div>
      ${proofHtml}
    </section>

    <section class="ws-section" aria-label="Virtuals ACP">
      <p class="kicker">03 · Virtuals ACP</p>
      <h2>Not verified</h2>
      <p class="meta">No registered buyer, no registered seller, no offering, and no real ACP job exist yet, so no partner credit is claimed. The adapter is ready and fails honestly without credentials. Active provider: ${escapeHtml(mode)}.</p>
      <details class="proof"><summary>View implementation details</summary>
        <p class="meta">Adapter: <code class="mono">src/prior/providers/virtuals.py</code> through <code class="mono">acp-bridge/</code> with the official Node SDK v2. Validation: <code class="mono">scripts/verify_virtuals_acp.py</code>. Evidence: <code class="mono">evidence/virtuals-acp-live.json</code>.</p>
      </details>
    </section>

    <div class="row"><a class="btn" href="/" data-nav="home">Back to workspace</a></div>
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
      if (route() === "home" && href === "/") state.job = null;
      render();
    });
  });

  document.querySelectorAll("[data-open-job]").forEach(a => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const id = a.getAttribute("data-open-job");
      run(async () => {
        state.job = await api(`/api/jobs/${id}`);
        history.pushState({}, "", "/");
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
