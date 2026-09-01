# Virtuals integration status

Recorded 2026-09-02. Official sources:

- https://github.com/Virtual-Protocol/acp-node-v2
- https://github.com/Virtual-Protocol/acp-node-v2/blob/main/.env.example
- https://github.com/Virtual-Protocol/acp-node-v2/blob/main/src/examples/README.md
- https://github.com/Virtual-Protocol/acp-node (deprecated 1 Jun 2026)

## Installed package

| Item | Value |
| --- | --- |
| Package | `@virtuals-protocol/acp-node-v2` |
| Version | `0.1.12` (lockfile + `node_modules`) |
| Location | `acp-bridge/package.json` |
| Deprecated package present? | No. `@virtuals-protocol/acp-node` is not a dependency. |

## Current imports

After migration, the live adapter imports:

```
AcpAgent
PrivyAlchemyEvmProviderAdapter
AssetToken
```

from `@virtuals-protocol/acp-node-v2`.

Files:

- `acp-bridge/lib.mjs` — `PrivyAlchemyEvmProviderAdapter.create({ walletAddress, walletId, signerPrivateKey, chains })`
- `acp-bridge/run.mjs` — buyer commands: browse, create-job, status, fund, complete, reject
- `acp-bridge/buyer.mjs` — long-running buyer; `session.fund()` on `budget.set`
- `acp-bridge/seller.mjs` — long-running seller; `setBudget` then PRIOR research `submit`
- `src/prior/providers/virtuals.py` — Python `VirtualsAcpProvider`

`AlchemyEvmProviderAdapter` is **not** exported by the installed v2 `index.d.ts`.

## Whether old v1 code existed

Yes, in this repo, even though the npm package was already v2.

Removed v1-style wiring:

- `AlchemyEvmProviderAdapter.create({ walletAddress, privateKey, entityId })`
- Env names: `WHITELISTED_WALLET_PRIVATE_KEY`, `BUYER_AGENT_WALLET_ADDRESS`, `BUYER_ENTITY_ID`, `SELLER_AGENT_WALLET_ADDRESS`, `SELLER_ENTITY_ID`

That is the deprecated wallet-private-key + session/entity-ID architecture. It was not extended. It was replaced.

Python `virtuals-acp` was never installed (requires Python `<3.13`; this machine is 3.14).

## Whether migration was required

Yes. Package name was already v2; credential adapter was still v1-shaped and would not have worked against current Privy wallets.

## Exact missing credentials after migration

Names only. Values are not recorded here.

Buyer (required to create/browse ACP jobs):

- `BUYER_WALLET_ADDRESS`
- `BUYER_WALLET_ID`
- `BUYER_SIGNER_PRIVATE_KEY`

Seller (required to run `acp-bridge/seller.mjs`):

- `SELLER_WALLET_ADDRESS`
- `SELLER_WALLET_ID`
- `SELLER_SIGNER_PRIVATE_KEY`

Also off until explicitly enabled: `ACP_ENABLED`

v2 signer key (from official `.env.example`): Privy authorization key, base64 PKCS#8 P-256, typically starts with `MIGH`. Not an EOA hex key.

## Honest failure

If ACP is selected and those buyer vars are empty, PRIOR raises:

`Virtuals credentials are not configured.`

It does not fall back to LOCAL PROVIDER and claim ACP succeeded.

## Prepared drop-in path

Once credentials exist:

1. Set `ACP_ENABLED=true` and the six v2 vars in `.env`.
2. `PRIOR_LOCAL_PROVIDER=false`.
3. Run `node acp-bridge/seller.mjs` and `node acp-bridge/buyer.mjs`.
4. Hire in PRIOR: browse registered seller offering → `createJobByOfferingName` with learned `acceptance` in the requirement payload → fund → seller submits real research → user complete/reject.
