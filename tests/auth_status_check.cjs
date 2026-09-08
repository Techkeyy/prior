/* Post-logout auth-status regression harness (runs under plain node, no deps).
 *
 * Loads the REAL src/prior/static/app.js bundle with minimal browser stubs
 * and proves the banner/URL invariants behaviorally:
 *  - ?auth=signed-in may render the success notice exactly once (logged out)
 *  - authoritative (authenticated) state never uses the query banner
 *  - consumeAuthQueryParam() strips the stale param via history.replaceState
 *  - after cleanup the logged-out decision yields no "Signed in" text
 *  - the sign-out handler is wired to the cleanup
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const nav = { href: "http://local/app?auth=signed-in", replaced: [] };
global.location = {
  get href() { return nav.href; },
  get search() { return new URL(nav.href).search; },
  get pathname() { return new URL(nav.href).pathname; },
  get hash() { return new URL(nav.href).hash; },
};
global.history = {
  replaceState(...args) {
    nav.replaced.push(args);
    nav.href = new URL(args[2], "http://local").href;
  },
  pushState() {},
};
global.document = { getElementById: () => null, querySelectorAll: () => [] };
global.window = { addEventListener: () => {}, scrollTo: () => {} };
global.fetch = async () => { throw new Error("no network in harness"); };

const appJs = path.join(__dirname, "..", "src", "prior", "static", "app.js");
const bundle = require(appJs);
assert.ok(bundle.authStatusNotice, "bundle must export authStatusNotice");
assert.ok(bundle.consumeAuthQueryParam, "bundle must export consumeAuthQueryParam");
const { authStatusNotice, consumeAuthQueryParam } = bundle;

// 1. Successful login may show the signed-in success state (once, logged out).
assert.strictEqual(authStatusNotice(false, "signed-in"), "signed-in");
// 2. Authenticated state never derives UI from the query param.
assert.strictEqual(authStatusNotice(true, "signed-in"), "");
assert.strictEqual(authStatusNotice(true, null), "");
// 3. Incomplete logins map to the guest-mode notice, unknowns to nothing.
assert.strictEqual(authStatusNotice(false, "error"), "auth-incomplete");
assert.strictEqual(authStatusNotice(false, "cancelled"), "auth-incomplete");
assert.strictEqual(authStatusNotice(false, null), "");
assert.strictEqual(authStatusNotice(false, "bogus"), "");
// 4. Cleanup strips the stale param from the URL.
nav.href = "http://local/app?auth=signed-in";
assert.strictEqual(consumeAuthQueryParam(), true);
assert.strictEqual(new URL(nav.href).searchParams.get("auth"), null);
assert.ok(nav.href.startsWith("http://local/app"), nav.href);
// 5. Post-cleanup logged-out decision contains no signed-in state.
assert.strictEqual(
  authStatusNotice(false, new URL(nav.href).searchParams.get("auth")), ""
);
// 6. Unrelated query/hash state survives cleanup.
nav.href = "http://local/app?auth=signed-in&job=abc#sec";
consumeAuthQueryParam();
const kept = new URL(nav.href);
assert.strictEqual(kept.searchParams.get("job"), "abc");
assert.strictEqual(kept.hash, "#sec");
// 7. No-op when no auth param is present.
const calls = nav.replaced.length;
nav.href = "http://local/app";
assert.strictEqual(consumeAuthQueryParam(), false);
assert.strictEqual(nav.replaced.length, calls);
// 8. Sign-out handler wiring: the logout click path performs the cleanup.
const src = fs.readFileSync(appJs, "utf8");
assert.ok(
  /data-signout[\s\S]{0,800}consumeAuthQueryParam\(\)/.test(src),
  "sign-out handler must clear the stale auth query param"
);
// 9. The stale copy from the bug report can never render again: after the
//    fixed loadIdentity consumes it, the signed-out branch sees no param.
nav.href = "http://local/app?auth=signed-in";
consumeAuthQueryParam();
const afterLogout = new URL(nav.href).searchParams.get("auth");
assert.strictEqual(authStatusNotice(false, afterLogout), "");

console.log("FRONTEND_AUTH_STATUS_OK");
const outFile = process.argv[2];
if (outFile) {
  fs.writeFileSync(outFile, "FRONTEND_AUTH_STATUS_OK\n", "utf8");
}
