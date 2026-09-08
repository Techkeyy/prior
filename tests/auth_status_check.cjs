/* Auth query truth-source regressions (runs under plain node, no deps).
 *
 * Hard invariant: a URL query parameter is NEVER sufficient to claim the
 * user is authenticated. Only /api/auth/me state may establish signed-in
 * truth. Loads the REAL src/prior/static/app.js bundle with minimal stubs.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const nav = { href: "http://local/app", replaced: [] };
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
const src = fs.readFileSync(appJs, "utf8");
const bundle = require(appJs);
assert.ok(bundle.authStatusNotice, "bundle must export authStatusNotice");
assert.ok(bundle.consumeAuthQueryParam, "bundle must export consumeAuthQueryParam");
const { authStatusNotice, consumeAuthQueryParam } = bundle;

// 1. CORE: logged-out + ?auth=signed-in MUST NOT yield a signed-in claim.
assert.notStrictEqual(authStatusNotice(false, "signed-in"), "signed-in");
assert.strictEqual(authStatusNotice(false, "signed-in"), "auth-incomplete");
// 2. Authenticated state never derives UI from the query param.
assert.strictEqual(authStatusNotice(true, "signed-in"), "");
assert.strictEqual(authStatusNotice(true, null), "");
// 3. Incomplete logins stay truthful; unknowns yield nothing.
assert.strictEqual(authStatusNotice(false, "error"), "auth-incomplete");
assert.strictEqual(authStatusNotice(false, "cancelled"), "auth-incomplete");
assert.strictEqual(authStatusNotice(false, null), "");
assert.strictEqual(authStatusNotice(false, "bogus"), "");
// 4. No query-gated "Signed in" success copy may exist in the bundle. The
//    only "Signed in" render allowed is the authoritative account branch.
assert.ok(!src.includes("Signed in. Your PRIOR memory follows you"),
  "query-driven signed-in banner must be removed");
assert.ok(src.includes("Signed in as "),
  "authoritative account success UI must remain");
// 5. Consumption happens for BOTH states: the cleanup call precedes the
//    authenticated-branch return in loadIdentity (no early-return bypass).
const loadStart = src.indexOf("async function loadIdentity()");
const authReturn = src.indexOf("if (me && me.authenticated && me.account)");
const firstConsume = src.indexOf("consumeAuthQueryParam();", loadStart);
assert.ok(loadStart >= 0 && authReturn > loadStart && firstConsume > loadStart
  && firstConsume < authReturn,
  "auth query must be consumed before the authenticated branch");
// 6. Runtime: stale logged-out query is consumed and yields no signed-in UI.
nav.href = "http://local/app?auth=signed-in";
assert.strictEqual(consumeAuthQueryParam(), true);
assert.strictEqual(new URL(nav.href).searchParams.get("auth"), null);
assert.strictEqual(
  authStatusNotice(false, new URL(nav.href).searchParams.get("auth")), "");
// 7. Unrelated query/hash state survives cleanup.
nav.href = "http://local/app?auth=signed-in&job=abc#sec";
consumeAuthQueryParam();
const kept = new URL(nav.href);
assert.strictEqual(kept.searchParams.get("job"), "abc");
assert.strictEqual(kept.hash, "#sec");
// 8. No-op when no auth param is present.
const calls = nav.replaced.length;
nav.href = "http://local/app";
assert.strictEqual(consumeAuthQueryParam(), false);
assert.strictEqual(nav.replaced.length, calls);
// 9. Sign-out handler wiring: the logout click path performs the cleanup.
assert.ok(
  /data-signout[\s\S]{0,800}consumeAuthQueryParam\(\)/.test(src),
  "sign-out handler must clear the stale auth query param"
);
// 10. Owner scenario end state: logged out + formerly-stale URL -> nothing
//     that claims signed-in.
nav.href = "http://local/app?auth=signed-in";
consumeAuthQueryParam();
assert.strictEqual(
  authStatusNotice(false, new URL(nav.href).searchParams.get("auth")), "");

console.log("FRONTEND_AUTH_STATUS_OK");
const outFile = process.argv[2];
if (outFile) {
  fs.writeFileSync(outFile, "FRONTEND_AUTH_STATUS_OK\n", "utf8");
}
