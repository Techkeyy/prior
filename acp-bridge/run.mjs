/**
 * Buyer-side commands for official @virtuals-protocol/acp-node-v2.
 * Adapter: PrivyAlchemyEvmProviderAdapter
 */
import { createAgent, done, fail, flattenOfferings, loadSdk } from "./lib.mjs";

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

function sanitizeJson(value) {
  return JSON.parse(JSON.stringify(value, (key, val) =>
    typeof val === "bigint" ? val.toString() : val));
}

function summarizeHistory(entries) {
  return (entries || []).slice(0, 100).map((e) => {
    if (!e || typeof e !== "object") return { kind: "unknown" };
    const summary = { kind: e.kind || "unknown" };
    if (e.event && typeof e.event.type === "string") summary.eventType = e.event.type;
    if (typeof e.contentType === "string") summary.contentType = e.contentType;
    if (typeof e.from === "string") summary.from = e.from;
    for (const key of ["timestamp", "createdAt", "at"]) {
      if (e[key] !== undefined && e[key] !== null) {
        try { summary.at = new Date(e[key]).toISOString(); } catch { summary.at = String(e[key]); }
        break;
      }
    }
    return summary;
  });
}

function sanitizeBudget(budget) {
  if (!budget || typeof budget !== "object") return null;
  try {
    const out = {};
    if (budget.amount !== undefined) out.amount = String(budget.amount);
    if (typeof budget.symbol === "string") out.symbol = budget.symbol;
    if (budget.decimals !== undefined) out.decimals = Number(budget.decimals);
    const token = budget.address || budget.tokenAddress || null;
    if (token) out.tokenAddress = String(token);
    return Object.keys(out).length ? out : null;
  } catch {
    return null;
  }
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
    return done({ ok: true, keyword, agents: flattenOfferings(agents) });
  }

  if (cmd === "discover") {
    // READ-ONLY live marketplace discovery. Unlike "browse", this never
    // short-circuits to SELLER_WALLET_ADDRESS and returns full agent and
    // offering objects (public registry data only, no credentials).
    const keyword = args[0] || "research";
    const topK = Math.min(Math.max(parseInt(args[1] || "25", 10) || 25, 1), 50);
    let extra = {};
    if (args[2]) {
      try { extra = JSON.parse(args.slice(2).join(" ")); } catch { extra = {}; }
      if (typeof extra !== "object" || extra === null) extra = {};
    }
    const params = { topK, ...extra };
    const mod = await loadSdk();
    const { agent } = await createAgent(mod, "buyer");
    const agents = (await agent.browseAgents(keyword, params)) || [];
    return done({ ok: true, keyword, params, count: agents.length, agents });
  }

  if (cmd === "create-offering-job") {
    // REAL write path for a marketplace-selected offering. Uses the official
    // createJobByOfferingName(chainId, offeringName, providerAddress,
    // requirementData, { evaluatorAddress }) with PRIOR as its own evaluator,
    // matching the established accept/reject lifecycle. Only invoked with a
    // frozen HirePlan; never performs discovery.
    const providerAddress = args[0];
    const offeringName = args[1] || "research";
    const requirementRaw = args.slice(2).join(" ");
    if (!providerAddress || !providerAddress.startsWith("0x")) {
      fail("create-offering-job requires a 0x seller wallet address.");
    }
    let requirementData = {};
    try {
      requirementData = JSON.parse(requirementRaw);
    } catch {
      fail("create-offering-job requires JSON requirementData matching the offering schema.");
    }
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const myAddress = await agent.getAddress();
    const jobId = await agent.createJobByOfferingName(
      chain.id,
      offeringName,
      providerAddress,
      requirementData,
      { evaluatorAddress: myAddress }
    );
    return done({
      ok: true,
      jobId: String(jobId),
      phase: "job.created",
      chainId: chain.id,
      providerAddress,
      offeringName,
    });
  }

  if (cmd === "offering-refresh") {
    // READ-ONLY freshness lookup for one exact provider + offering. No
    // search, no selection, no write. Used to revalidate a frozen HirePlan.
    const providerAddress = args[0];
    const offeringName = args[1] || "";
    if (!providerAddress) fail("offering-refresh requires a seller wallet address.");
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const detail = await agent.getAgentByWalletAddress(providerAddress);
    if (!detail) {
      return done({ ok: true, found: false, providerAddress });
    }
    const offering = ((detail.offerings || []).find((o) => o && o.name === offeringName)) || null;
    return done({
      ok: true,
      found: true,
      chainId: chain.id,
      agentName: detail.name || null,
      walletAddress: detail.walletAddress || providerAddress,
      lastActiveAt: detail.lastActiveAt || null,
      chains: (detail.chains || []).map((c) => c && c.chainId).filter((v) => v !== undefined),
      offering: offering ? {
        name: offering.name,
        description: offering.description || "",
        requirements: offering.requirements ?? null,
        priceType: offering.priceType || "",
        priceValue: offering.priceValue ?? null,
        requiredFunds: Boolean(offering.requiredFunds),
        slaMinutes: offering.slaMinutes ?? null,
        isHidden: Boolean(offering.isHidden),
        isPrivate: Boolean(offering.isPrivate),
      } : null,
    });
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
    const description = String(
      requirement.job_description || requirement.goal || requirement.raw || offeringName
    ).slice(0, 8000);
    const jobId = await agent.createJob(chain.id, {
      providerAddress,
      evaluatorAddress: myAddress,
      expiredAt,
      description,
    });
    console.error(`[BUYER] On-chain Job created: ${jobId}`);

    await agent.sendMessage(chain.id, jobId.toString(), JSON.stringify(requirement), "requirement");

    return done({
      ok: true,
      jobId: String(jobId),
      phase: "job.created",
      chainId: chain.id,
    });
  }

  if (cmd === "status") {
    // STRICTLY READ-ONLY. This command must never fund, complete, reject,
    // create, or message. It fetches the job, reads history, derives the
    // current phase plus budget/funding evidence, and returns it.
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const session = agent.getOrCreateSession(jobId, chain.id);
    await session.fetchJob().catch(() => {});
    const onChainStatus = (session.job?.status || "").toUpperCase();
    const hasBudgetEvent = (session.entries || []).some(
      (e) => e.kind === "system" && e.event?.type === "budget.set"
    );
    const budget = sanitizeBudget(session.job?.budget);
    const hasBudget = budget !== null || hasBudgetEvent || session.status === "budget_set";
    const funded = session.status === "funded";
    await session.fetchJob().catch(() => {});
    const entries = await agent.getTransport().getHistory(chain.id, jobId).catch(() => []);
    for (const e of entries) session.appendEntry(e);
    let deliverable = session.job?.deliverable || deliverableFromSession(session);
    if (!deliverable && ((session.job?.status || "").toUpperCase() === "SUBMITTED" || session.status === "submitted")) {
      deliverable = "Deliverable confirmed submitted on-chain by provider.";
    }
    const job = session.job || null;
    return done(sanitizeJson({
      ok: true,
      jobId,
      chainId: chain.id,
      phase: (session.job?.status || session.status || "open").toLowerCase(),
      onChainStatus: onChainStatus || null,
      sessionStatus: session.status || null,
      providerAddress: job?.providerAddress || null,
      evaluatorAddress: job?.evaluatorAddress || null,
      clientAddress: job?.clientAddress || null,
      budget,
      hasBudget,
      funded,
      deliverable: deliverable || null,
      history: summarizeHistory(session.entries),
      expiredAt: job?.expiredAt !== undefined && job?.expiredAt !== null
        ? String(job.expiredAt) : null,
    }));
  }

  if (cmd === "fund") {
    const [jobId] = args;
    const mod = await loadSdk();
    const { agent, chain } = await createAgent(mod, "buyer");
    const session = agent.getOrCreateSession(jobId, chain.id);
    await session.fetchJob();
    await session.fund();
    return done({ ok: true, jobId, action: "fund", phase: session.status });
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
    return done({
      ok: true,
      jobId,
      action: cmd,
      phase: (session.job?.status || session.status || cmd).toLowerCase(),
    });
  }

  fail(`Unknown ACP bridge command: ${cmd}`);
}

main().catch((err) => fail(String(err?.stack || err)));
