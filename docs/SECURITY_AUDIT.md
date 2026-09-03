# PRIOR Security Audit

Audit date: 2026-09-03

## Summary

| Area | Status | Evidence |
| --- | --- | --- |
| Tracked secrets and Git history | PASS | No private-key, signer-key, API-key, token, or seed-phrase pattern found. |
| Runtime secret handling | PASS | `.env` is ignored; production credentials file is outside the checkout with mode `600`. |
| Production ACP exposure | PASS | Production runs only `/opt/prior/.venv/bin/uvicorn`; `ACP_ENABLED=false`; no `node`, `seller.mjs`, `buyer.mjs`, or `run.mjs` process is running. |
| Provider attribution | PASS | Local execution is labelled `PRIOR Local Research Agent`, `Network: Local`; no ACP fallback badge exists. |
| ACP dependency audit | WARN | `npm audit --omit=dev` reports 24 vulnerabilities: 12 low, 5 moderate, 7 high, 0 critical. |

## High Findings

All findings below are production dependency graph findings in `acp-bridge`. The audit reports `189` production dependencies and `0` dev dependencies. ACP is disabled in the deployed application, so this graph is not loaded by the running FastAPI process.

| Finding | Dependency chain | Reachability now | Fix disposition |
| --- | --- | --- | --- |
| `GHSA-58qx-3vcg-4xpx`, uninitialized memory disclosure; `GHSA-96hv-2xvq-fx4p`, memory exhaustion | `@virtuals-protocol/acp-node-v2` → `@account-kit/infra` → `alchemy-sdk` → `@ethersproject/providers@5.8.0` → `ws@8.18.0` | WARN, not reachable while ACP is disabled and no Node bridge runs. Could be loaded when ACP is enabled. | Patched `ws@8.21.3` exists. The official provider pins `ws` exactly to `8.18.0`; `npm audit fix` does not apply a non-breaking fix. A direct root dependency and targeted override did not produce a valid reproducible tree, so they were reverted. `--force` was not used. |
| `GHSA-qjx8-664m-686j`, `js-cookie` prototype hijack | `@virtuals-protocol/acp-node-v2` → `@account-kit/infra` → `@account-kit/logging` → `@segment/analytics-next@1.74.0` → `js-cookie@3.0.1` | WARN, not reachable while ACP is disabled. This is a transitive analytics/browser package, not code imported by PRIOR. | npm reports no available fix. Upgrading account-kit to the audit-selected target would require a breaking downgrade of `@account-kit/smart-contracts` to `4.35.0`; not applied because it could break the official ACP v2 adapter. |
| Account-kit high roll-ups | `@account-kit/infra@4.88.5`, `@account-kit/logging@4.88.5`, `@account-kit/smart-contracts@4.88.5`, and `@virtuals-protocol/acp-node-v2@0.1.12` inherit the findings above. | WARN, not reachable while ACP is disabled. | No safe non-breaking upstream release was identified by npm. The official ACP v2 package remains pinned and the SDK probe passes. |

## Other Transitive Findings

The remaining audit output is `12` low and `5` moderate findings, primarily the same legacy `ethers`/`elliptic` chain and `@solana/web3.js`/`jayson`/`uuid` chain under `alchemy-sdk`. npm reports no safe fix for those paths. They are also behind the disabled ACP bridge and are not imported by the production FastAPI process.

## Controls

- `src/prior/providers/virtuals.py` refuses to start without the buyer v2 credentials and never falls back to the local provider.
- `src/prior/app.py` exposes only the FastAPI routes; the Node ACP bridge has no HTTP route and listens on no port.
- `deploy/prior.service` runs the Python app as the unprivileged `prior` user with `NoNewPrivileges`, `ProtectHome`, `ProtectSystem=strict`, and explicit writable paths.
- `/etc/prior/prior.env` contains no ACP credentials while ACP is disabled. Future signer values must remain in that outside-checkout file.
- The public production process and service status were checked after deployment. Caddy routes only to the Python upstream on `127.0.0.1:8789`.

## Recheck Commands

```bash
cd acp-bridge
npm ls --omit=dev --all
npm audit --omit=dev --audit-level=high
cd ..
node acp-bridge/run.mjs probe
```

The audit remains a warning, not a claim of zero dependency risk. A future ACP enablement must rerun this audit, the SDK probe, and the live ACP validation before credentials are used.
