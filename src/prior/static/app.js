const app = document.getElementById("app");
const state = { job: null, memory: null, error: "", busy: false };

function route() {
  return location.pathname === "/memory" ? "memory" : "home";
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

function render() {
  if (route() === "memory") return renderMemory();
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
  app.innerHTML = `${state.error ? `<div class="error">${escapeHtml(state.error)}</div>` : ""}${html}`;
  bind();
}

function renderHome() {
  shell(`
    <p class="kicker">Hire, then remember what it taught</p>
    <h1>What do you need done?</h1>
    <p class="lead">PRIOR hires a research agent, then keeps the lesson when a job goes badly so the next contract is stricter.</p>
    <form id="specify">
      <textarea name="text" placeholder="Research the top five AI wallet companies" required></textarea>
      <div class="row">
        <button type="submit"${state.busy ? " disabled" : ""}>Find an agent</button>
      </div>
    </form>
  `);
}

function renderRefused(job) {
  shell(`
    <h1>This build does research</h1>
    <div class="panel">
      <p>${escapeHtml(job.error || job.spec.refusal_reason || "Unsupported.")}</p>
    </div>
    <button class="secondary" data-reset>New job</button>
  `);
}

function memoryBanner(job) {
  const c = job.contract || {};
  if (c.memory_status === "unavailable") {
    return `<div class="error">${escapeHtml(c.memory_message)}</div>`;
  }
  if (c.applied_lessons && c.applied_lessons.length) {
    const items = c.applied_lessons.map((l) => `<li>${escapeHtml(l.requirement)} <span class="meta">(${escapeHtml(l.match_reason || "applied")})</span></li>`).join("");
    return `<div class="panel"><p class="kicker ok">PRIOR remembered ${c.applied_lessons.length} relevant lesson${c.applied_lessons.length === 1 ? "" : "s"}</p><ul>${items}</ul></div>`;
  }
  return `<p class="meta">${escapeHtml(c.memory_message || "No relevant lessons found. Starting with standard requirements.")}</p>`;
}

function renderContract(job) {
  const c = job.contract;
  shell(`
    <p class="kicker">Contract review</p>
    <h1>${escapeHtml(c.title)}</h1>
    ${memoryBanner(job)}
    <div class="panel">
      <p class="kicker">Deliver</p>
      <ul>${(c.deliverables || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
      <p class="kicker">Acceptance requirements</p>
      <ul>${(c.acceptance || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
    </div>
    <div class="row">
      <button data-hire${state.busy ? " disabled" : ""}>Hire this agent</button>
      <button class="secondary" data-reset>Start over</button>
    </div>
  `);
}

function providerLabel(job) {
  const source = job.provider && job.provider.source;
  if (source === "local-development") {
    return `<p class="kicker">LOCAL PROVIDER</p><p class="warn">Development provider. This is not Virtuals.</p>`;
  }
  if (source === "virtuals-acp") {
    return `<p class="kicker">Virtuals ACP</p>${job.acp_job_id ? `<p class="meta">ACP job ${escapeHtml(job.acp_job_id)}</p>` : ""}`;
  }
  return `<p class="meta">Provider: ${escapeHtml((job.provider && job.provider.name) || "unknown")}</p>`;
}

function renderProgress(job) {
  shell(`
    <h1>Working</h1>
    <div class="panel">
      ${providerLabel(job)}
      <p>${escapeHtml((job.provider && job.provider.summary) || (job.provider && job.provider.name) || "")}</p>
      <p class="meta">Phase: ${escapeHtml(job.acp_phase || job.status)}</p>
    </div>
  `);
  poll(job.id);
}

function renderDeliverable(job) {
  const value = (job.deliverable && job.deliverable.value) || {};
  const findings = value.findings || [];
  shell(`
    <p class="kicker">Deliverable</p>
    ${providerLabel(job)}
    <h1>${escapeHtml(value.title || job.contract.title)}</h1>
    <p class="meta">Retrieved ${escapeHtml(value.retrieved_at || "")}</p>
    ${(value.honored_requirements || []).length ? `<div class="panel"><p class="kicker">Requirements the worker received</p><ul>${value.honored_requirements.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul></div>` : ""}
    <div class="findings">
      ${findings.map((f) => `
        <article class="panel finding">
          <h3>${escapeHtml(f.name || "Finding")}</h3>
          <p>${escapeHtml(f.summary || "")}</p>
          ${(f.sources || []).map((s) => `<p class="meta"><a href="${escapeAttr(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.label || s.url)}</a></p>`).join("")}
        </article>
      `).join("")}
    </div>
    ${(value.notes || []).length ? `<ul class="meta">${value.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}
    <div class="row">
      <button data-accept>Accept</button>
      <button class="secondary" data-show-reject>Reject</button>
    </div>
    <form id="reject" hidden>
      <p>Why is this not good enough? PRIOR will propose a reusable lesson from your reason.</p>
      <textarea name="reason" placeholder="Important factual claims should include source links." required></textarea>
      <div class="row"><button type="submit">Reject and propose a lesson</button></div>
    </form>
  `);
}

function renderLesson(job) {
  const lesson = job.proposed_lesson;
  shell(`
    <p class="kicker">New lesson proposed</p>
    <h1>Should this change the next contract?</h1>
    <div class="panel">
      <p><strong>Scope:</strong> ${escapeHtml(lesson.job_type)} jobs</p>
      <p><strong>Lesson:</strong> ${escapeHtml(lesson.requirement)}</p>
      <p class="meta">${escapeHtml(lesson.reason)}</p>
    </div>
    <form id="edit-lesson">
      <label class="meta" for="requirement">Edit if needed</label>
      <input id="requirement" name="requirement" type="text" value="${escapeAttr(lesson.requirement)}" />
      <div class="row">
        <button data-add>Add to PRIOR</button>
        <button class="secondary" data-edit>Save edit</button>
        <button class="secondary" data-ignore>Ignore</button>
      </div>
    </form>
  `);
}

function renderDone(job) {
  shell(`
    <h1>${job.evaluation === "accepted" ? "Accepted" : "Recorded"}</h1>
    <div class="panel">
      <p>Job ${escapeHtml(job.id)} is ${escapeHtml(job.status)}.</p>
      ${job.proposed_lesson && job.proposed_lesson.status === "active" ? `<p class="ok">Lesson stored in Sibyl Memory: ${escapeHtml(job.proposed_lesson.requirement)}</p>` : ""}
      ${job.proposed_lesson && job.proposed_lesson.status === "duplicate" ? `<p class="warn">That lesson already exists (${escapeHtml(job.proposed_lesson.existing_id)}).</p>` : ""}
    </div>
    <div class="row">
      <button data-reset>New job</button>
      <a class="btn secondary" href="/memory">Open memory</a>
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
    <p class="kicker">Learned lessons</p>
    <h1>Memory</h1>
    ${state.memory && state.memory.status === "unavailable" ? `<div class="error">${escapeHtml(state.memory.message)}</div>` : ""}
    <p class="meta">${lessons.length} stored lesson${lessons.length === 1 ? "" : "s"}. Counts are from Sibyl, not a dashboard seed.</p>
    ${lessons.map((l) => `
      <article class="panel">
        <p class="kicker">${escapeHtml(l.status)} · ${escapeHtml(l.job_type)}</p>
        <h2>${escapeHtml(l.requirement)}</h2>
        <p class="meta">Learned from ${escapeHtml(l.source_job_id || "unknown job")}</p>
        <p class="meta">${escapeHtml(l.reason)}</p>
      </article>
    `).join("") || `<p>No lessons yet. Reject a research job with a real reason to propose one.</p>`}
  `);
}

function bind() {
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
  if (reset) reset.addEventListener("click", () => { state.job = null; state.error = ""; history.replaceState({}, "", "/"); render(); });
  const accept = document.querySelector("[data-accept]");
  if (accept) accept.addEventListener("click", () => run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/accept`, { method: "POST" });
  }));
  const showReject = document.querySelector("[data-show-reject]");
  if (showReject) showReject.addEventListener("click", () => {
    document.getElementById("reject").hidden = false;
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
}

async function lessonAction(action) {
  const form = document.getElementById("edit-lesson");
  const requirement = form ? new FormData(form).get("requirement") : null;
  await run(async () => {
    state.job = await api(`/api/jobs/${state.job.id}/lessons`, {
      method: "POST",
      body: JSON.stringify({ action, requirement }),
    });
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

window.addEventListener("popstate", render);
render();
