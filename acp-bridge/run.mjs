/**
 * Buyer-side commands for official @virtuals-protocol/acp-node-v2.
 * Adapter: PrivyAlchemyEvmProviderAdapter
 */
import { createAgent, fail, flattenOfferings, loadSdk } from "./lib.mjs";

const [cmd, ...args] = process.argv.slice(2);

function deliverableFromSession(session) {
  const entries = session?.entries || [];
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i];
    if (entry?.kind === "message" && entry.contentType === "deliverable") {
      return entry.content;
    }
  }
  return null;
}

async function main() {
  if (cmd === "probe") {
    const mod = await loadSdk();
    const names = Object.keys(mod);
    console.log(
      JSON.stringify({
        ok: names.includes("AcpAgent") && names.includes("PrivyAlchemyEvmProviderAdapter"),
        hasAcpAgent: names.includes("AcpAgent"),
        hasPrivyAlchemyEvmProviderAdapter: names.includes("PrivyAlchemyEvmProviderAdapter"),
        hasAlchemyEvmProviderAdapter: names.includes("AlchemyEvmProviderAdapter"),
        hasAssetToken: Boolean(mod.AssetToken),
      })
    );
    return;
  }

  if (cmd === "browse") {
    const keyword = args[0] || "research";
    const mod = await loadSdk();
    const { agent } = await createAgent(mod, "buyer");
    await agent.start();
    try {
      let agents = [];
      const preferred = process.env.SELLER_WALLET_ADDRESS;
      if (preferred) {
        const mine = await agent.getAgentByWalletAddress(preferred);
        if (mine) agents = [mine];
      }
      if (!agents.length) {
        agents = (await agent.browseAgents(keyword)) || [];
      }
      console.log(JSON.stringify({ ok: true, keyword, agents: flattenOfferings(agents) }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "create-job") {
    const [providerAddress, offeringName, requirementJson] = args;
    const requirement = JSON.parse(requirementJson);
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    await agent.start();
    try {
      const jobId = await agent.createJobByOfferingName(
        chain.id,
        offeringName,
        providerAddress,
        requirement,
        { evaluatorAddress: await agent.getAddress() }
      );
      console.log(
        JSON.stringify({
          ok: true,
          jobId: String(jobId),
          phase: "job.created",
          chainId: chain.id,
        })
      );
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "status") {
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    await agent.start();
    try {
      const session = await agent.getSession(chain.id, jobId);
      if (!session) fail(`No ACP session for job ${jobId}`);
      console.log(
        JSON.stringify({
          ok: true,
          jobId,
          phase: session.status,
          deliverable: deliverableFromSession(session),
        })
      );
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "fund") {
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    await agent.start();
    try {
      const session = await agent.getSession(chain.id, jobId);
      if (!session) fail(`No ACP session for job ${jobId}`);
      await session.fund();
      console.log(JSON.stringify({ ok: true, jobId, action: "fund", phase: session.status }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  if (cmd === "complete" || cmd === "reject") {
    const [jobId, reason] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    await agent.start();
    try {
      const session = await agent.getSession(chain.id, jobId);
      if (!session) fail(`No ACP session for job ${jobId}`);
      if (cmd === "complete") await session.complete(reason || "Accepted by hiring user.");
      else await session.reject(reason || "Rejected by hiring user.");
      console.log(JSON.stringify({ ok: true, jobId, action: cmd, phase: session.status }));
    } finally {
      await agent.stop?.();
    }
    return;
  }

  fail(`Unknown ACP bridge command: ${cmd}`);
}

main().catch((err) => fail(String(err?.stack || err)));
