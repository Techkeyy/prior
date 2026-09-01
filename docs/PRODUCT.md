# What PRIOR is

PRIOR helps a person hire a research agent without repeating the same mistakes, by turning a rejected job into an approved lesson that changes the next contract.

It does not remember the chat. It remembers what the job taught, after the user says so.

## One sentence

PRIOR helps people hiring research agents write better job terms after every failure, by storing the lesson in Sibyl Memory and putting it into the next agent contract.

## Core loop

```
describe job -> recall lessons from Sibyl -> write contract -> hire agent
             -> real deliverable -> accept or reject
             -> if reject: propose lesson -> user approves -> Sibyl write
             -> fresh session: Sibyl read -> next contract changes
```

## Magic moment

Session B, with no conversation from Session A, shows:

"PRIOR remembered 1 relevant lesson" and the new contract contains a requirement that did not exist until the user approved it.

## Load-bearing assumption

A custom Python process can write a lesson with `sibyl_memory_client.MemoryClient.set_entity` and a later, separate process can read that same lesson with `search_entities` / `get_entity` under the same tenant. If that is false, PRIOR is not a Sibyl product.

## What it is not

Not an agent marketplace, not a reputation system, not escrow-as-the-product, not a chatbot, not a wallet, not a static contract generator.

Virtuals is how the hire happens. Sibyl is why the next hire is different.

## MVP domain

Research and information-gathering jobs only. Other requests are refused in plain language.

## Identity

Smallest honest scope: a persistent workspace ID (cookie). That ID is the Sibyl `tenant_id`. User A's lessons do not load for User B. This is workspace isolation, not enterprise multi-tenancy.
