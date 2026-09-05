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
    process.exit(0);
  }

  if (cmd === "create-job") {
    const providerAddress = args[0];
    const offeringName = args[1] || "research";
    const requirementRaw = args.slice(2).join(" ");
    let requirement = {};
    try {
      requirement = JSON.parse(requirementRaw);
    } catch {
      try {
        requirement = JSON.parse(requirementRaw.replace(/(\w+):/g, '"$1":'));
      } catch {
        requirement = { raw: requirementRaw };
      }
    }
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const myAddress = await agent.getAddress();
    console.error(`[BUYER] Creating on-chain ACP job on Base mainnet for ${providerAddress}...`);
    const expiredAt = Math.floor(Date.now() / 1000) + 3600;
    const description = (requirement.goal || requirement.raw || offeringName).slice(0, 500);
    const jobId = await agent.createJob(chain.id, {
      providerAddress,
      evaluatorAddress: myAddress,
      expiredAt,
      description,
    });
    console.error(`[BUYER] On-chain Job created: ${jobId}`);

    try {
      await agent.sendMessage(chain.id, jobId.toString(), JSON.stringify(requirement), "requirement");
    } catch (err) {
      console.error("Note: requirement message send:", String(err?.message || err));
    }

    console.log(
      JSON.stringify({
        ok: true,
        jobId: String(jobId),
        phase: "job.created",
        chainId: chain.id,
      })
    );
    process.exit(0);
  }

  if (cmd === "status") {
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const session = agent.getOrCreateSession(jobId, chain.id);
    await session.fetchJob().catch(() => {});
    const onChainStatus = (session.job?.status || "").toUpperCase();
    const hasBudgetEvent = (session.entries || []).some(
      (e) => e.kind === "system" && e.event?.type === "budget.set"
    );
    const hasBudget = session.job?.budget !== undefined || hasBudgetEvent || session.status === "budget_set";

    if (onChainStatus === "OPEN" && hasBudget) {
      try {
        console.error(`[BUYER] Auto-funding job ${jobId}...`);
        await session.fund();
        console.error(`[BUYER] Job ${jobId} auto-funded.`);
      } catch (err) {
        console.error("Auto-fund error:", String(err?.message || err));
      }
    }
    await session.fetchJob().catch(() => {});
    const entries = await agent.getTransport().getHistory(chain.id, jobId).catch(() => []);
    for (const e of entries) session.appendEntry(e);
    let deliverable = session.job?.deliverable || deliverableFromSession(session);
    if (!deliverable && ((session.job?.status || "").toUpperCase() === "SUBMITTED" || session.status === "submitted")) {
      deliverable = "Deliverable confirmed submitted on-chain by provider.";
    }
    console.log(
      JSON.stringify({
        ok: true,
        jobId,
        phase: (session.job?.status || session.status || "open").toLowerCase(),
        deliverable,
      })
    );
    process.exit(0);
  }

  if (cmd === "fund") {
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const session = agent.getOrCreateSession(jobId, chain.id);
    await session.fetchJob();
    await session.fund();
    console.log(JSON.stringify({ ok: true, jobId, action: "fund", phase: session.status }));
    process.exit(0);
  }

  if (cmd === "complete" || cmd === "reject") {
    const [jobId, reason] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const session = agent.getOrCreateSession(jobId, chain.id);
    await session.fetchJob().catch(() => {});
    if (cmd === "complete") await session.complete(reason || "Accepted by hiring user.");
    else await session.reject(reason || "Rejected by hiring user.");
    await session.fetchJob().catch(() => {});
    console.log(
      JSON.stringify({
        ok: true,
        jobId,
        action: cmd,
        phase: (session.job?.status || session.status || cmd).toLowerCase(),
      })
    );
    process.exit(0);
  }

  fail(`Unknown ACP bridge command: ${cmd}`);
}

main().catch((err) => fail(String(err?.stack || err)));
