/* "Start a new job" reset regressions (owner UAT bug) — plain node, no deps.

Hard invariant: EVERY rendered [data-reset] control (Start a new job, Start
over, Discard, Abandon and start over) must share one working handler. The
production bug: bind() used singular document.querySelector("[data-reset]")
so only the FIRST button (requestLine's small "Start over") had a listener;
the prominent "Start a new job" on the post-lesson Learn screen was dead.

Loads the REAL src/prior/static/app.js bundle with minimal stubs.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const appJs = path.join(__dirname, "..", "src", "prior", "static", "app.js");
const src = fs.readFileSync(appJs, "utf8");

/* ---- source locks ---- */
assert.ok(!src.includes('document.querySelector("[data-reset]")'),
  "singular data-reset selector must be gone (binds only the first button)");
assert.ok(src.includes('document.querySelectorAll("[data-reset]")'),
  "bind must enumerate every data-reset control");
assert.ok(src.includes("button.addEventListener(\"click\", resetToComposer)"),
  "every data-reset must share the one resetToComposer handler");
assert.ok(/function resetToComposer\(\)[\s\S]*?state\.job = null[\s\S]*?history\.pushState\(\{\}, "", "\/app"\);[\s\S]*?render\(\);/.test(src),
  "resetToComposer must clear only in-flight state, keep workspace, and rerender");
assert.strictEqual((src.match(/data-reset>/g) || []).length, 6,
  "all six reset controls must remain rendered (abandon, start over, discard, expired, accepted, learning)");

/* ---- fake DOM + network ---- */
const pushState = [];
let innerHTMLWrites = 0;
let lastHTML = "";
const appEl = {
  className: "",
  set innerHTML(v) { innerHTMLWrites += 1; lastHTML = v; },
  get innerHTML() { return lastHTML; },
};

class FakeButton {
  constructor(label) { this.label = label; this._l = {}; }
  addEventListener(type, fn) { (this._l[type] = this._l[type] || []).push(fn); }
  getAttribute() { return null; }
  click() { (this._l.click || []).forEach((f) => f()); }
}

const registry = { "[data-reset]": [], "[data-nav]": [], "[data-anchor]": [], "[data-open-job]": [], "[data-chip]": [], "[data-disable]": [], "[data-verify-base]": [] };

global.location = { pathname: "/app", search: "", hash: "", href: "http://local/app" };
global.history = { pushState(a, b, url) { pushState.push(url); }, replaceState() {} };
global.document = {
  getElementById(id) { return id === "app" ? appEl : null; },
  querySelector() { return null; },
  querySelectorAll(sel) { return registry[sel] || []; },
};
global.window = {
  addEventListener: () => {},
  scrollTo: () => {},
  sessionStorage: { getItem: () => "1", setItem: () => {} },
};
global.fetch = async (url) => {
  const body = String(url).startsWith("/api/memory")
    ? { lessons: [], count: 0, jobs: [], status: "ok" }
    : { workspace_id: "ws_test000000000001", hire_mode: "dynamic" };
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
};

const bundle = require(appJs);
assert.ok(typeof bundle.bind === "function" && typeof bundle.resetToComposer === "function",
  "bundle must export bind + resetToComposer for the harness");

(async () => {
  await new Promise((r) => setTimeout(r, 60));

  /* ---- functional: bind attaches to EVERY data-reset ---- */
  const before = innerHTMLWrites;
  const a = new FakeButton("Start over");
  const b = new FakeButton("Start a new job");
  const c = new FakeButton("Discard");
  registry["[data-reset]"] = [a, b, c];
  bundle.bind();
  for (const btn of [a, b, c]) {
    assert.ok((btn._l.click || []).length >= 1, `button "${btn.label}" received no click listener`);
  }

  /* ---- clicking the SECOND (previously dead) button resets to composer ---- */
  b.click();
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(pushState.includes("/app"), "reset must navigate (pushState) to /app");
  assert.ok(innerHTMLWrites > before, "reset must trigger a re-render");
  assert.ok(lastHTML.includes('id="need"'), "reset render must show the request composer");
  assert.ok(!lastHTML.includes("Learning outcome"), "reset render must leave the Learn screen");

  /* ---- the shared handler is literally the same function for all ---- */
  assert.strictEqual(a._l.click[0], c._l.click[0], "all reset buttons must share one handler");

  console.log("FRONTEND_RESET_WIRING_OK");
  const outFile = process.argv[2];
  if (outFile) fs.writeFileSync(outFile, "FRONTEND_RESET_WIRING_OK\n", "utf8");
})();
