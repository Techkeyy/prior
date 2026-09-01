/**
 * Shared v2 ACP helpers.
 * Official adapter: PrivyAlchemyEvmProviderAdapter
 * Official env: *_WALLET_ADDRESS, *_WALLET_ID, *_SIGNER_PRIVATE_KEY
 * Never log credential values.
 */
export function fail(message, extra = {}) {
  console.error(message);
  console.log(JSON.stringify({ ok: false, error: message, ...extra }));
  process.exit(1);
}

export function requiredEnv(name) {
  const value = process.env[name];
  if (!value || !String(value).trim()) {
    fail(`Missing ${name}. Virtuals credentials are not configured.`);
  }
  return value;
}

export async function loadSdk() {
  try {
    return await import("@virtuals-protocol/acp-node-v2");
  } catch (err) {
    fail(
      "Official ACP SDK @virtuals-protocol/acp-node-v2 is not installed. Run npm install in acp-bridge/.",
      { detail: String(err) }
    );
  }
}

export async function resolveChain() {
  const chainName = (process.env.ACP_NETWORK || "base-mainnet").toLowerCase();
  try {
    const infra = await import("@account-kit/infra");
    return chainName.includes("sepolia") ? infra.baseSepolia : infra.base;
  } catch (err) {
    fail("Could not import @account-kit/infra chain objects.", { detail: String(err) });
  }
}

export async function createAgent(mod, role = "buyer") {
  const { AcpAgent, PrivyAlchemyEvmProviderAdapter } = mod;
  if (typeof AcpAgent?.create !== "function") {
    fail("Installed SDK is missing AcpAgent.create.");
  }
  if (typeof PrivyAlchemyEvmProviderAdapter?.create !== "function") {
    fail(
      "Installed SDK is missing PrivyAlchemyEvmProviderAdapter.create. " +
        "Refusing to use deprecated privateKey/entityId wallet setup."
    );
  }
  const prefix = role === "seller" ? "SELLER" : "BUYER";
  const chain = await resolveChain();
  const provider = await PrivyAlchemyEvmProviderAdapter.create({
    walletAddress: requiredEnv(`${prefix}_WALLET_ADDRESS`),
    walletId: requiredEnv(`${prefix}_WALLET_ID`),
    signerPrivateKey: requiredEnv(`${prefix}_SIGNER_PRIVATE_KEY`),
    chains: [chain],
  });
  const agent = await AcpAgent.create({ provider });
  return { agent, chain };
}

export function flattenOfferings(agents) {
  const offers = [];
  for (const agent of agents || []) {
    const offerings = agent.offerings || [];
    if (!offerings.length) {
      offers.push({
        id: agent.id,
        name: agent.name,
        description: agent.description,
        walletAddress: agent.walletAddress,
        offeringName: null,
        price: null,
      });
      continue;
    }
    for (const offering of offerings) {
      offers.push({
        id: agent.id,
        name: agent.name,
        description: agent.description || offering.description,
        walletAddress: agent.walletAddress,
        offeringName: offering.name,
        price: offering.priceValue,
        slaMinutes: offering.slaMinutes,
      });
    }
  }
  return offers;
}
