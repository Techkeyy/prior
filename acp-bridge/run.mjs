/**
 * Thin wrapper around the official Virtuals ACP Node SDK v2.
 * Method names come from os.virtuals.io/acp/sdk/getting-started.
 * This process never invents job ids or payment states.
 */
const [cmd, ...args] = process.argv.slice(2);

function fail(message, extra = {}) {
  console.error(message);
  process.exitCode = 1;
  console.log(JSON.stringify({ ok: false, error: message, ...extra }));
  process.exit(1);
}

async function loadSdk() {
  try {
    return await import("@virtuals-protocol/acp-node-v2");
  } catch (err) {
    fail(
      "Official ACP SDK @virtuals-protocol/acp-node-v2 is not installed. Run npm install in acp-bridge/.",
      { detail: String(err) }
    );
  }
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) fail(`Missing ${name}. Virtuals ACP cannot start without registry credentials.`);
  return value;
}

async function createAgent(mod) {
  const { AcpAgent, AlchemyEvmProviderAdapter } = mod;
  if (typeof AcpAgent?.create !== "function") {
    fail("Installed SDK is missing AcpAgent.create. Refusing to guess method names.");
  }
  const chainName = (process.env.ACP_NETWORK || "base-mainnet").toLowerCase();
  let chain;
  try {
    const infra = await import("@account-kit/infra");
    chain = chainName.includes("sepolia") ? infra.baseSepolia : infra.base;
  } catch (err) {
    fail("Could not import @account-kit/infra chain objects.", { detail: String(err) });
  }
  const provider = await AlchemyEvmProviderAdapter.create({
    walletAddress: requiredEnv("BUYER_AGENT_WALLET_ADDRESS"),
    privateKey: requiredEnv("WHITELISTED_WALLET_PRIVATE_KEY"),
    entityId: Number(requiredEnv("BUYER_ENTITY_ID")),
    chains: [chain],
  });
  const agent = await AcpAgent.create({ provider });
  return { agent, chain };
}

async function main() {
  if (cmd === "probe") {
    const mod = await loadSdk();
    const names = Object.keys(mod);
    console.log(
      JSON.stringify({
        ok: names.includes("AcpAgent"),
        exports: names,
        hasAcpAgent: typeof mod.AcpAgent === "function" || typeof mod.AcpAgent === "object",
        hasAssetToken: Boolean(mod.AssetToken),
      })
    );
    return;
  }

  if (cmd === "browse") {
    const keyword = args[0] || "research";
    const mod = await loadSdk();
    const { agent } = await createAgent(mod);
    await agent.start();
    try {
      const agents = await agent.browseAgents(keyword);
      console.log(JSON.stringify({ ok: true, keyword, agents: agents || [] }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "create-job") {
    const [providerAddress, offeringName, requirementJson] = args;
    const requirement = JSON.parse(requirementJson);
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod);
    await agent.start();
    try {
      const jobId = await agent.createJobByOfferingName(
        chain.id,
        offeringName,
        providerAddress,
        requirement,
        { evaluatorAddress: await agent.getAddress() }
      );
      console.log(JSON.stringify({ ok: true, jobId, phase: "job.created" }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "complete" || cmd === "reject") {
    const [jobId, reason] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod);
    await agent.start();
    try {
      const session = await agent.getSession(chain.id, jobId);
      if (!session) fail(`No ACP session for job ${jobId}`);
      if (cmd === "complete") await session.complete(reason || "Accepted by hiring user.");
      else await session.reject(reason || "Rejected by hiring user.");
      console.log(JSON.stringify({ ok: true, jobId, action: cmd }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  fail(`Unknown ACP bridge command: ${cmd}`);
}

main().catch((err) => fail(String(err?.stack || err)));
