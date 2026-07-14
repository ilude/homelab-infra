# Handoff: Federated Personal Agent, Development, Infrastructure, and Content Platform

**Suggested repository path:** `docs/agent-platform-design-handoff.md`  
**Created from discussion:** July 14, 2026  
**Primary working repository:** https://github.com/ilude/homelab-infra  
**Status:** Exploratory design handoff — not an approved architecture or implementation plan

---

## 1. Instructions to the Next Agent

Read this document completely before proposing changes.

This handoff records a broad system idea that is intentionally not fully settled. The user expects to provide additional documents covering:

1. content aggregation and personalized discovery ideas;
2. OnRamp-vNext ideas and application-platform direction;
3. potentially other related architecture, infrastructure, agent, and product notes.

Do **not** assume the first plausible architecture is the correct one. Do not immediately implement a message bus, memory platform, sandbox manager, or agent orchestrator merely because one appears to fit.

The next design session should:

1. inspect the current `homelab-infra` repository and its local/private values wiring;
2. read the existing architecture and operator documents listed in this handoff;
3. ingest the additional documents supplied by the user;
4. distinguish confirmed requirements from tentative ideas and implementation candidates;
5. identify contradictions, missing information, and decisions that have been prematurely implied;
6. propose small, reversible experiments that generate evidence;
7. preserve repository-native safety and approval workflows;
8. avoid live infrastructure mutation unless the user separately requests it and approves a reviewed plan.

The user explicitly recognizes that these ideas are broad and partly hand-wavy. The goal is to create a coherent direction while retaining enough flexibility to discover that an early design, implementation, framework, or product choice is wrong.

### Epistemic labels used in this document

- **USER GOAL:** Something the user explicitly wants.
- **CONFIRMED:** Observed in the referenced repositories or explicitly stated by the user.
- **CURRENT CONTRACT:** A boundary already documented in `homelab-infra`.
- **WORKING HYPOTHESIS:** A promising design direction that has not been accepted.
- **CANDIDATE:** A technology or pattern worth evaluating.
- **OPEN QUESTION:** Not decided and should not be silently resolved.
- **WARNING:** A security, ownership, or architectural risk.

---

## 2. Executive Summary

### 2.1 User goal

The user wants to evolve the existing homelab and agent work into a coherent, self-hosted system that can support:

- local and remote Pi coding/worker agents;
- one or more persistent Hermes agents acting as human-facing coordinators;
- separation between personal-homelab and work-related agent domains;
- several execution and sandbox backends:
  - full virtual machines;
  - Proxmox LXC;
  - Docker or Podman containers;
  - microVMs;
  - WebAssembly/WASI;
- reusable application-development services similar in spirit to Firebase or Supabase;
- a message bus for agent-to-agent and service-to-service communication;
- centralized but appropriately partitioned knowledge, RAG, preferences, and procedural memory;
- a system that gradually learns:
  - who the user is;
  - how the user works;
  - what the user prefers;
  - how the user typically designs, reviews, operates, and troubleshoots systems;
- a personalized content aggregation and discovery platform based on Onboard;
- ingestion and ranking of content from sources such as:
  - YouTube;
  - X.com;
  - Reddit;
  - RSS/Atom feeds;
  - other websites, services, and future connectors;
- safe experimentation with competing architectural approaches.

### 2.2 Working system shape

A promising, but not approved, decomposition is:

```text
Human
  |
  +-- Hermes Personal
  |
  +-- Hermes Work
          |
          v
  Deterministic agent/control fabric
  - identity and realm boundaries
  - task routing
  - capability registry
  - approvals
  - policy
  - audit
  - event/task transport
          |
          +-- Pi coding/worker agents
          +-- infrastructure adapters
          +-- content-ingestion workers
          +-- knowledge/memory services
          +-- development-service broker
          +-- sandbox broker
                  |
                  +-- WASI
                  +-- rootless Podman
                  +-- Docker
                  +-- LXC
                  +-- full VM
                  +-- microVM
```

The key idea is that Hermes should not become an all-powerful central control plane. Hermes may be the conversational coordinator or “operator cockpit,” while deterministic services enforce policy, route tasks, issue scoped credentials, create sandboxes, retain audit history, and protect domain boundaries.

### 2.3 Existing repository ownership direction

The existing `homelab-infra` documents already point toward:

```text
homelab-infra
    durable infrastructure substrate

OnRamp / OnRamp-vNext
    general application platform and app catalog

Hermes
    operator cockpit across approved repository-native workflows

Onboard
    user-facing dashboard/content product candidate

Pi
    local or remote coding/worker agent candidate
```

The larger system should extend this ownership model rather than invent a competing deployment path.

---

## 3. User Intent and Non-Negotiable Constraints

### 3.1 USER GOAL: experimentation is required

The architecture must support experimentation. It should be possible to compare alternatives without making every early choice a permanent platform dependency.

Examples:

- NATS versus another message transport;
- OpenBrain versus a custom Postgres memory schema;
- shared service versus isolated per-realm service;
- rootless Podman versus disposable VM for a task class;
- WASI component versus ordinary container tool;
- extending Onboard versus extracting a new content backend;
- a complete Supabase stack versus smaller shared primitives;
- centralized Hermes coordination versus more federated domain coordinators.

Experiments should be:

- bounded in scope;
- reversible;
- observable;
- measurable;
- isolated from durable infrastructure;
- documented with hypotheses and exit criteria;
- easy to remove if unsuccessful.

### 3.2 USER GOAL: coherent system, not disconnected projects

The user is not simply trying to deploy Pi, Hermes, NATS, Supabase, a vector database, and Firecracker independently.

The desired outcome is one understandable system where:

- repositories have explicit ownership;
- agents use common task and event contracts;
- sandbox backends are selected through policy rather than hard-coded into every agent;
- development services can be provisioned consistently;
- memory and preference data have provenance and scope;
- content discovery feeds back into the user profile;
- work and personal data remain appropriately separated;
- infrastructure remains recoverable and auditable.

### 3.3 USER GOAL: preserve human control

The system may automate planning, testing, content ingestion, summarization, and bounded operations. It must not silently turn broad model access into unrestricted infrastructure authority.

Important operations should preserve:

- plan/review/apply boundaries;
- explicit approvals;
- clear summaries;
- audit evidence;
- rollback paths;
- limited credentials;
- transparent attribution of what executed and why.

### 3.4 USER GOAL: learn the user without creating an opaque “AI brain”

The desired personalization system must distinguish among:

- facts explicitly stated by the user;
- inferred preferences;
- repeated behavior;
- one-time behavior;
- old preferences that may no longer be valid;
- personal-only data;
- work-only data;
- sensitive information;
- source documents;
- agent-generated summaries;
- procedural knowledge;
- content-interest signals.

“RAG” alone is not sufficient. The eventual design likely needs separate concepts for:

- documents and retrieval;
- confirmed profile facts;
- inferred preferences;
- procedural memory;
- episodic history;
- feedback and interaction events;
- ranking features;
- confidence, provenance, expiration, and correction.

### 3.5 CURRENT CONTRACT: repository-native operations remain authoritative

Do not make Hermes or an agent-created database a new source of truth for infrastructure or application deployment.

The current repository-native workflow uses:

```text
just validate
just plan
just apply
```

A future agent layer may invoke or summarize these workflows, but must not bypass them with ad hoc SSH, direct API mutations, or generated live commands unless a separately approved design explicitly changes the contract.

---

## 4. Repositories and Source URLs

### 4.1 Primary infrastructure repository

**Repository:** `ilude/homelab-infra`  
**URL:** https://github.com/ilude/homelab-infra

Relevant files:

- README:
  https://github.com/ilude/homelab-infra/blob/main/README.md
- Documentation index:
  https://github.com/ilude/homelab-infra/blob/main/docs/README.md
- Hermes operator pilot PRD:
  https://github.com/ilude/homelab-infra/blob/main/docs/hermes-operator-pilot-prd.md
- OnRamp application-platform contract:
  https://github.com/ilude/homelab-infra/blob/main/docs/onramp-app-platform-contract.md
- Hermes tuning:
  https://github.com/ilude/homelab-infra/blob/main/docs/hermes-tuning.md
- OnRamp host runbook:
  https://github.com/ilude/homelab-infra/blob/main/docs/onramp-host-runbook.md
- OnRamp/SearXNG handoff:
  https://github.com/ilude/homelab-infra/blob/main/docs/onramp-searxng-handoff.md
- Service state backup:
  https://github.com/ilude/homelab-infra/blob/main/docs/service-state-backup.md
- Managed service registry:
  https://github.com/ilude/homelab-infra/blob/main/infra/services.json

### 4.2 Application-platform repository

**Repository:** `traefikturkey/onramp`  
**URL:** https://github.com/traefikturkey/onramp

Relevant files:

- README:
  https://github.com/traefikturkey/onramp/blob/main/README.md
- Agent/operator repository guide:
  https://github.com/traefikturkey/onramp/blob/main/.agents/README.md
- Service catalog:
  https://github.com/traefikturkey/onramp/blob/main/SERVICES.md
- OpenBrain service:
  https://github.com/traefikturkey/onramp/blob/main/services-available/openbrain.yml
- OpenBrain generated documentation:
  https://github.com/traefikturkey/onramp/blob/main/services-docs/openbrain.md
- Ollama service:
  https://github.com/traefikturkey/onramp/blob/main/services-available/ollama.yml
- Ollama NVIDIA override:
  https://github.com/traefikturkey/onramp/blob/main/overrides-available/ollama-nvidia.yml
- Ollama AMD override:
  https://github.com/traefikturkey/onramp/blob/main/overrides-available/ollama-amd.yml

### 4.3 Personalized dashboard/content repository

**Repository:** `traefikturkey/onboard`  
**URL:** https://github.com/traefikturkey/onboard

Relevant files observed during this discussion:

- README:
  https://github.com/traefikturkey/onboard/blob/main/README.md
- Project dependencies:
  https://github.com/traefikturkey/onboard/blob/main/pyproject.toml
- Flask application factory:
  https://github.com/traefikturkey/onboard/blob/main/app/factory.py
- Feed implementation:
  https://github.com/traefikturkey/onboard/blob/main/app/models/feed.py
- Click tracking:
  https://github.com/traefikturkey/onboard/blob/main/app/services/link_tracker.py

### 4.4 Pi agent harness

The original repository URL `https://github.com/badlogic/pi-mono` currently redirects to:

- https://github.com/earendil-works/pi
- Project site: https://pi.dev

Pi describes itself as an agent harness including:

- a coding-agent CLI;
- an agent runtime with tool calling and state management;
- a multi-provider LLM API;
- extensions, skills, and related packages.

Its documentation explicitly states that Pi does not provide a built-in permission system for filesystem, process, network, or credential access and recommends external sandboxing or containerization.

### 4.5 Hermes Agent

- Repository: https://github.com/NousResearch/hermes-agent

Hermes is being considered as a persistent coordinator/operator interface with:

- a dashboard and messaging gateways;
- memory and skills;
- scheduling;
- subagent delegation;
- infrastructure-facing plugins or adapters;
- multiple model/provider options.

The exact Hermes version and enabled feature set must be confirmed from private values and the managed pin set in the local repository.

### 4.6 Claude Code

Claude Code was discussed as an alternative or complementary coding-agent harness, especially where polished coding behavior is more important than local-model independence.

Official starting point:

- https://docs.anthropic.com/en/docs/claude-code/overview

No decision has been made to integrate Claude Code into the platform.

### 4.7 Theo Browne / Lakebed concept

The user referenced the “theo.gg Lakebed idea.”

No canonical public repository or stable official design document was located during this session. Previous discussion treated Lakebed as a possible example of an agent-native programmable runtime in which code becomes a tool-composition language, but that characterization must **not** be treated as authoritative.

**Required follow-up:** ask the user for the specific video, post, transcript, repository, or notes about Lakebed and ingest that material before using Lakebed as an architectural requirement.

### 4.8 Sandboxing and execution references

- Firecracker:
  https://github.com/firecracker-microvm/firecracker
- Firecracker project site:
  https://firecracker-microvm.github.io/
- Cloud Hypervisor:
  https://github.com/cloud-hypervisor/cloud-hypervisor
- Kata Containers:
  https://github.com/kata-containers/kata-containers
- Wasmtime:
  https://github.com/bytecodealliance/wasmtime
- Wasmtime documentation:
  https://docs.wasmtime.dev/
- WASI:
  https://wasi.dev/

### 4.9 Messaging and development-service references

- NATS:
  https://nats.io/
- NATS documentation:
  https://docs.nats.io/
- Supabase self-hosting:
  https://supabase.com/docs/guides/self-hosting
- Infisical:
  https://infisical.com/docs/self-hosting/overview
- Forgejo:
  https://forgejo.org/docs/latest/
- Proxmox VE:
  https://pve.proxmox.com/pve-docs/

### 4.10 OpenBrain reference

The current OnRamp service documentation references:

- https://github.com/NateBJones-Projects/OB1

Treat this as a candidate memory component. Verify the current repository, image provenance, API/MCP behavior, data model, maintenance status, licensing, and suitability before making it foundational.

---

## 5. Confirmed Current State of `homelab-infra`

### 5.1 CONFIRMED: purpose and repository split

`homelab-infra` contains reusable OpenTofu and Ansible runbooks for Proxmox workloads and managed services.

The public repository is intentionally generic. Real domains, IPs, DNS records, credentials, endpoints, private inventory, and OpenTofu state belong in an ignored nested `values/` repository, normally stored in private Forgejo.

This split is important and should remain intact.

### 5.2 CONFIRMED: currently modeled services

The repository currently models or references services including:

- Technitium DNS;
- Caddy;
- Forgejo;
- Forgejo Actions runner;
- Infisical;
- Tailscale client;
- Hermes;
- a Debian 13 OnRamp application host;
- SearXNG as a temporary OnRamp-host workload.

The current `infra/services.json` includes dependency, state-order, execution-resource, inventory, and Terraform-module metadata.

This registry may become useful for future capability discovery or infrastructure adapters, but it should not automatically be repurposed into the agent task registry without design review.

### 5.3 CONFIRMED: infrastructure workflow safety

The repository already implements substantial safety behavior:

- artifact pinning and hash verification;
- private values separation;
- saved plan metadata;
- rejection of stale plans;
- backup-age requirements for destructive stateful changes;
- canary behavior for multiple stateful services;
- service-specific recovery;
- direct host-key verification for LXC access;
- reviewed `validate`, `plan`, and `apply` stages.

Any agent integration should preserve these controls rather than replacing them with a generic “run command” tool.

### 5.4 CONFIRMED: current Hermes deployment

Hermes is managed as an LXC with:

- dashboard support;
- service-local Caddy;
- a runtime user, commonly `anvil`;
- managed application pins;
- managed runtime dependencies;
- persistent Hermes state;
- backup/restore handling;
- tuning for compression and delegation.

### 5.5 WARNING: current Hermes authority

The repository README states that the Hermes runtime account receives full passwordless sudo through a managed sudoers policy and should be treated as root-equivalent within its LXC.

This may be acceptable for the current pilot, but it should not become the authority model for the larger agent platform.

The target architecture should consider:

- no ambient SSH authority over all managed systems;
- no standing infrastructure secrets in conversational agent state;
- scoped task credentials;
- operation-specific brokers;
- approvals outside the model;
- deterministic policy;
- retained audit events;
- revocable access.

### 5.6 CURRENT CONTRACT: Hermes is an operator cockpit

The existing Hermes operator PRD explicitly establishes that:

- `homelab-infra` remains the durable infrastructure source of truth;
- OnRamp owns general application workloads;
- Hermes operates through approved repository-native workflows;
- Hermes must not become a second or third deployment control plane;
- live mutation requires explicit approval;
- private values must not leak into summaries, logs, or tracked files.

This is a strong foundation for the broader design.

---

## 6. Confirmed Current State of OnRamp

### 6.1 CONFIRMED: current platform shape

The current OnRamp repository is a Docker Compose-oriented self-hosting platform built around:

- service definitions;
- enabled-service symlinks and environment files;
- service scaffolding;
- overrides;
- Traefik;
- Cloudflare DNS-01/HTTPS behavior;
- generated service documentation;
- Makefile-based lifecycle commands;
- persistent configuration and data directories.

It is a useful application catalog and deployment convention, but it is not currently:

- an agent harness;
- a policy engine;
- a sandbox broker;
- a message bus;
- a microVM manager;
- a complete multi-tenant development platform.

### 6.2 CONFIRMED: app-platform ownership contract

The current `homelab-infra` contract says:

- `homelab-infra` owns the VM/substrate, durable networking, static infrastructure DNS, and OpenTofu state;
- OnRamp or OnRamp-vNext should own general application workloads and app lifecycle;
- Hermes may aggregate and operate across both through approved workflows;
- app deployment state should not become OpenTofu state by default.

### 6.3 OPEN QUESTION: “OnRamp” versus “OnRamp-vNext”

The repository and current contract use both OnRamp and OnRamp-vNext terminology.

The next agent must determine:

- whether OnRamp-vNext is a branch, unpublished repository, local checkout, design document, or future rewrite;
- which current OnRamp behaviors are retained;
- whether Compose remains the target workload format;
- whether rootless Podman becomes the preferred runtime;
- whether OnRamp becomes an API/service rather than Makefile-driven deployment;
- how app state, secrets, DNS, reverse proxying, backups, upgrades, and health checks are represented.

Do not assume the existing `traefikturkey/onramp` implementation is identical to the intended OnRamp-vNext architecture.

---

## 7. Confirmed Current State of Onboard

### 7.1 CONFIRMED: useful existing capabilities

Onboard currently contains useful foundations for a personal dashboard and feed reader:

- Flask application;
- application factory and dependency injection improvements;
- RSS/Atom feed ingestion using `feedparser`;
- scheduled feed refreshes;
- feed caching;
- configurable feed processors;
- configurable filters;
- bookmark management APIs;
- click tracking;
- an HTML dashboard and feed presentation layer.

The feed code currently downloads feeds, converts entries into internal `FeedArticle` objects, applies processors and filters, de-duplicates items, sorts by publication time, and stores cached article data.

The click tracker currently records click events in SQLite.

### 7.2 CONFIRMED: current limitations relative to the goal

Onboard is not yet the complete personalized aggregation platform described by the user.

Likely gaps include:

- durable normalized content storage;
- multi-source connector framework;
- source-specific cursor and rate-limit handling;
- transcript and metadata extraction;
- canonical URL resolution;
- robust cross-source duplicate detection;
- content clustering;
- embeddings and topic models;
- explicit user feedback;
- recommendation explanations;
- model evaluation;
- realm/privacy controls;
- event-driven ingestion;
- scalable worker separation;
- long-term behavioral profile;
- per-item provenance and processing state;
- API contracts for external agents and services.

### 7.3 WORKING HYPOTHESIS: Onboard should become the product surface

A likely direction is to let Onboard become the user-facing product and feedback interface while moving ingestion, normalization, enrichment, ranking, and durable storage into separate services.

This is not yet a decision. A future design should compare:

1. extending the Flask application directly;
2. separating a content backend while retaining the current UI;
3. rebuilding selected parts while preserving feed, bookmark, and layout behavior;
4. treating Onboard only as a client of a new content platform.

---

## 8. Proposed Conceptual Architecture

This section records promising ideas from the discussion. It is not an accepted implementation plan.

### 8.1 Domain coordinators

Potential Hermes instances:

```text
Hermes Personal
- homelab operations
- personal projects
- personal knowledge
- content discovery
- personal scheduling and research

Hermes Work
- work projects
- work-approved tools
- work-only knowledge
- more restrictive policies
- no automatic access to personal behavioral history
```

The separate instances could be backed by:

- separate operating environments;
- separate secret projects;
- separate message-bus accounts or clusters;
- separate databases/schemas;
- separate vector stores;
- separate model-routing policies;
- narrow, explicit cross-realm exports.

### 8.2 Deterministic agent/control fabric

**WORKING HYPOTHESIS:** introduce a deterministic service layer between Hermes and workers.

Possible responsibilities:

- realm and identity enforcement;
- capability registration;
- worker presence;
- task submission;
- task routing;
- approval state;
- policy evaluation;
- retry and timeout behavior;
- idempotency;
- audit trail;
- artifact references;
- sandbox selection;
- scoped credential requests;
- cost and resource budgets;
- progress events;
- cancellation;
- result normalization.

This service should be ordinary testable software. An LLM may propose actions, but it should not be the sole authority deciding whether an action is allowed.

### 8.3 Pi agents as workers

A Pi process could be:

- attached to a developer workstation;
- attached to one repository;
- started inside a disposable development environment;
- registered as a specialized worker;
- limited to one realm;
- allowed to request selected sandbox profiles;
- terminated after a task;
- long-running but credential-minimal.

Potential worker registration:

```json
{
  "agent_id": "pi-personal-rust-01",
  "realm": "personal",
  "agent_type": "pi",
  "capabilities": [
    "git.read",
    "git.patch",
    "cargo.build",
    "cargo.test"
  ],
  "sandbox_profiles": [
    "rootless-container",
    "disposable-vm"
  ],
  "model_profiles": [
    "local-default",
    "remote-complex"
  ]
}
```

The exact protocol is not decided.

### 8.4 Message bus

**CANDIDATE:** NATS with JetStream.

Why it was suggested:

- simple request/reply;
- pub/sub;
- durable streams;
- work queues;
- account and subject isolation;
- relatively low operational overhead;
- useful for transient presence plus durable tasks/events.

Possible alternatives to evaluate:

- RabbitMQ;
- Redis Streams;
- PostgreSQL-backed queues;
- Temporal for workflows;
- a deliberately simpler HTTP plus database task service;
- separate transports for transient agent presence and durable workflow state.

Do not choose NATS only because it was discussed. First define the required semantics:

- delivery guarantee;
- ordering;
- replay;
- retention;
- consumer concurrency;
- request/reply;
- cancellation;
- dead-letter handling;
- payload size;
- realm isolation;
- audit requirements;
- operational complexity.

### 8.5 Example subject or event namespace

Illustrative only:

```text
agent.personal.presence.<agent-id>
agent.personal.capability.registered

task.personal.code.requested
task.personal.infrastructure.requested
task.personal.content.requested
task.personal.<task-id>.progress
task.personal.<task-id>.completed
task.personal.<task-id>.failed

approval.personal.<task-id>.requested
approval.personal.<task-id>.granted
approval.personal.<task-id>.denied

sandbox.personal.requested
sandbox.personal.<sandbox-id>.ready
sandbox.personal.<sandbox-id>.destroyed

memory.personal.candidate
memory.personal.accepted
memory.personal.corrected

content.personal.raw.youtube
content.personal.raw.reddit
content.personal.normalized
content.personal.enriched
content.personal.ranked
content.personal.feedback
```

### 8.6 Task envelope

A future task contract may need:

```yaml
task_id: uuid
correlation_id: uuid
realm: personal
requester:
  identity: hermes-personal
  session_id: ...
capability: code.change
target:
  repository: ...
sandbox:
  profile: untrusted-code
  persistence: discard
network:
  policy: allowlist
credentials:
  requested_scopes:
    - forgejo.repo.read
budgets:
  wall_time_seconds: 3600
  cpu: 4
  memory_mb: 8192
  model_cost_limit: ...
approval:
  required: false
artifacts:
  input_refs: []
policy_version: ...
idempotency_key: ...
```

This must be refined before implementation.

---

## 9. Sandbox and Execution Strategy

### 9.1 USER GOAL: multiple backends

The system should support a range of execution technologies because they solve different problems.

Do not force every task into one runtime.

### 9.2 Candidate execution classes

| Backend | Likely role | Important limitation |
|---|---|---|
| WASM/WASI | Narrow deterministic tools, parsing, policy checks, transforms | Not a general Linux environment |
| Rootless Podman | Trusted builds, app services, ordinary disposable jobs | Shares the host kernel |
| Docker | Compatibility with existing images and Compose workloads | Docker daemon access can become host-equivalent |
| Proxmox LXC | Persistent lightweight Linux services/workspaces | Shares Proxmox host kernel |
| Full Proxmox VM | Stronger durable boundary, complex dev stacks, Windows, appliances | Heavier startup/resource cost |
| microVM | Fast disposable hostile-code boundary | Requires lifecycle/image/network tooling |
| Direct host process | Early local prototype only | Weak isolation; should not be a production default |

### 9.3 WORKING HYPOTHESIS: one sandbox broker API

Agents should not contain direct code for every backend.

Possible abstraction:

```text
POST   /sandboxes
GET    /sandboxes/{id}
POST   /sandboxes/{id}/exec
POST   /sandboxes/{id}/artifacts
DELETE /sandboxes/{id}
```

A request should describe requirements, not implementation:

```yaml
realm: personal
profile: untrusted-repository
resources:
  cpu: 4
  memory_mb: 8192
  timeout_seconds: 3600
network:
  mode: allowlist
  destinations:
    - github.com
    - crates.io
source:
  repository: ...
credentials:
  - scope: repository.read
persistence:
  workspace: discard
  artifacts: retain
```

Policy or broker logic selects the backend.

### 9.4 Suggested experimentation order

A practical sequence discussed was:

1. rootless Podman;
2. Proxmox disposable VM clone;
3. Proxmox LXC for appropriate persistent or lower-risk workloads;
4. Wasmtime for narrow components;
5. Firecracker or another microVM backend after contracts stabilize.

This is only a starting hypothesis.

Firecracker should not be adopted merely because it is technically attractive. A prototype must establish that its startup density or isolation model solves a real problem not adequately handled by Proxmox VM templates or containers.

### 9.5 WASI relationship to the larger system

WASI is especially promising for:

- Compose validation;
- OpenTofu plan parsing;
- secret redaction;
- URL normalization;
- content classification;
- metadata extraction;
- deterministic ranking features;
- policy evaluation helpers;
- small data transformations.

A WASI component should receive explicit capabilities rather than a shell.

Tasks requiring package installation, browsers, arbitrary binaries, complete repository builds, Docker Compose, or broad development environments should use containers or VMs.

---

## 10. Development Services Platform

### 10.1 USER GOAL

Agents building applications frequently need common backend services. The user wants a self-hosted experience analogous to Firebase or Supabase without requiring every project to manually assemble databases, authentication, object storage, queues, and preview environments.

### 10.2 WORKING HYPOTHESIS: development-service broker

Instead of giving agents administrator credentials to every backing service, expose project-oriented operations:

```text
create project
create preview environment
create PostgreSQL database/schema
create object-storage bucket
create message namespace
create cache
create auth tenant
issue scoped application credentials
rotate credentials
destroy preview
promote preview
inspect usage/status
```

### 10.3 Candidate service profiles

#### Minimal

- Postgres database or schema;
- object-storage bucket;
- message namespace;
- application secrets;
- DNS/HTTPS endpoint;
- optional cache.

#### Standard application backend

- minimal profile;
- authentication;
- API layer;
- background worker;
- Redis/Valkey;
- observability;
- migration workflow.

#### Supabase-compatible

- isolated Supabase stack;
- Postgres;
- Auth;
- Storage;
- Realtime;
- Functions;
- Studio.

### 10.4 OPEN QUESTIONS

- Shared services versus one stack per project?
- How are previews expired and garbage-collected?
- Should OnRamp own project definitions?
- Should Forgejo Actions create previews?
- Does each agent receive credentials directly, or does the sandbox receive them?
- How are migrations promoted?
- How are backups and restores handled?
- How much multi-tenancy is acceptable?
- Is full Supabase worth the operational burden for most projects?
- Should a lighter platform be assembled from Postgres, MinIO, an auth service, NATS, and a small API gateway?
- How are application quotas enforced?

---

## 11. Knowledge, Memory, RAG, and Personalization

### 11.1 Required conceptual separation

Do not implement one undifferentiated vector store called “memory.”

Potential memory classes:

| Class | Examples |
|---|---|
| Confirmed profile | timezone, preferred name, owned systems |
| Preference | favors Go/Rust static binaries, preferred tooling |
| Procedural | desired validation and rollout workflow |
| Episodic | what happened during a prior troubleshooting session |
| Project | decisions, architecture, tasks, open questions |
| Documents | PRDs, runbooks, notes, transcripts, repositories |
| Behavioral event | clicked, saved, dismissed, watched, abandoned |
| Inference | likely interest or preference inferred by a model |
| Negative constraint | do not cross personal/work data, disliked content |
| Temporary context | current task/session state |

### 11.2 Metadata needed for trustworthy memory

A memory record may require:

```text
realm
source
source URI/reference
source timestamp
created timestamp
last confirmed timestamp
author
confidence
sensitivity
visibility
expiration or decay
memory class
embedding model/version
supporting evidence
contradicting evidence
supersedes/superseded-by
user-confirmed flag
deletion/correction history
```

### 11.3 Memory candidate workflow

A safer model:

```text
agent observes or infers something
        |
        v
memory candidate
        |
        +-- auto-reject
        +-- auto-accept under narrow rules
        +-- merge with existing record
        +-- request confirmation
        +-- mark as low-confidence inference
        +-- expire later
```

The system should never turn one model inference into a permanent user fact without provenance.

### 11.4 Work/personal separation

At minimum, evaluate:

- separate databases or schemas;
- separate encryption keys;
- separate vector indexes;
- separate object-store prefixes/buckets;
- separate Infisical projects;
- separate bus accounts or clusters;
- separate Hermes state;
- explicit export objects for anything shared.

A general “shared memory sync” is unsafe.

Possible shared exports should be narrow and intentional, such as a small set of non-sensitive user preferences. Raw personal history, work documents, customer information, credentials, and conversations should not cross realms by default.

### 11.5 CANDIDATE: OpenBrain

OpenBrain is already packaged in OnRamp and may be useful for an MVP.

Before adoption, evaluate:

- schema and typed-table model;
- MCP interface;
- authentication and authorization;
- realm isolation;
- provenance;
- confidence and correction;
- deletion semantics;
- backup/restore;
- embedding model changes;
- data portability;
- maintenance and community health;
- whether it can support memory classes beyond generic RAG.

---

## 12. Personalized Content Aggregation

### 12.1 USER GOAL

Use Onboard as the basis for a system that surfaces videos, posts, threads, articles, and other content that the user is likely to find interesting.

Potential sources include:

- YouTube;
- X.com;
- Reddit;
- RSS/Atom;
- blogs;
- podcasts;
- newsletters;
- future source connectors.

Additional user documents are expected in this area. Do not finalize this subsystem before reading them.

### 12.2 Candidate pipeline

```text
source connector
    |
    v
raw source event/object
    |
    v
normalization
    |
    +-- canonical URL
    +-- author/channel
    +-- timestamps
    +-- source IDs
    +-- media metadata
    +-- provenance
    |
    v
content extraction
    |
    +-- description/body
    +-- transcript where permitted
    +-- links/entities
    +-- thumbnails/artifacts
    |
    v
deduplication and clustering
    |
    v
classification and embeddings
    |
    v
candidate generation
    |
    v
personal relevance ranking
    |
    v
Onboard presentation
    |
    v
explicit and implicit feedback events
```

### 12.3 Content item requirements

A normalized content item may include:

```text
canonical ID
source
source-native ID
canonical URL
original URLs
title
author/channel/account
publication timestamp
ingestion timestamp
content type
description/body
transcript reference
language
topics/entities
embedding reference
cluster ID
processing status
source provenance
rights/access constraints
recommendation features
ranking history
user state
```

### 12.4 Feedback signals

Clicks are insufficient. Add explicit and implicit signals such as:

- save;
- bookmark;
- watch/read later;
- completed;
- partially consumed;
- abandoned quickly;
- more like this;
- less like this;
- hide;
- already seen;
- mute source;
- mute topic;
- follow topic;
- follow creator;
- send to Hermes;
- convert into a project/research item;
- mark as useful;
- mark as low quality;
- mark as clickbait.

### 12.5 Ranking approach

Start with transparent scoring rather than an opaque end-to-end model.

Possible features:

```text
explicit topic preference
source/creator preference
semantic similarity to saved items
freshness
novelty
project relevance
quality/social signal
content length/type fit
previous negative feedback
duplicate penalty
topic saturation penalty
already-seen penalty
```

An LLM may enrich, summarize, classify, or rerank a limited candidate set. It should not be the only ranking mechanism.

### 12.6 Recommendation explanation

The UI should be able to explain why an item appeared, for example:

```text
Recommended because:
- this matches your Proxmox and agent-runtime interests;
- you saved related Firecracker content;
- this creator has produced several items you completed;
- this topic has not been shown recently.
```

This helps the user correct bad assumptions and helps evaluate whether personalization is working.

### 12.7 Source connector risks

The future design must account for:

- API availability and cost;
- authentication;
- rate limits;
- terms of service;
- deleted or private content;
- source-specific identifiers;
- duplicate syndicated content;
- unreliable timestamps;
- transcript availability;
- scraping fragility;
- content safety and prompt injection;
- malicious HTML or documents;
- data retention and copyright constraints.

---

## 13. Security and Trust Boundaries

### 13.1 Core principles

1. No LLM is a source of truth.
2. No agent receives more authority than the current task requires.
3. Personal and work data do not share a brain merely because the same human owns both.
4. Every mutation should identify:
   - requester;
   - target;
   - capability;
   - policy;
   - approval;
   - executor;
   - result.
5. Credentials should be scoped, short-lived where possible, and injected into the execution environment rather than conversational context.
6. Destructive actions require stronger approval than read-only operations.
7. Logs and summaries must be sanitized.
8. Sandboxes are disposable by default.
9. Artifact retention is explicit.
10. Prompt content and retrieved documents are untrusted input.

### 13.2 Capability examples

Avoid a universal capability such as:

```text
shell.execute
ssh.root
docker.socket
proxmox.admin
```

Prefer narrower operations:

```text
infra.status
infra.validate
infra.plan
infra.apply-reviewed-plan

service.status
service.logs.sanitized
service.restart-approved

git.repository.read
git.patch.propose
git.tests.run
git.commit.create
git.push.approved

content.ingest.youtube
content.normalize
content.rank
memory.candidate.write
```

### 13.3 Approval matrix example

Illustrative only:

| Operation | Default |
|---|---|
| Read public repository | automatic |
| Search approved personal knowledge | automatic |
| Run tests in disposable sandbox | automatic |
| Create disposable preview | automatic with quota |
| Store low-risk memory candidate | automatic |
| Convert inference into confirmed profile | user confirmation |
| Change tracked infrastructure source | review |
| Run `just plan` | explicit request or policy |
| Run `just apply` | explicit approval |
| Destroy stateful service | strong explicit approval plus backup |
| Cross realm export | explicit policy and usually confirmation |
| Send public post/message | explicit approval |
| Use work credentials | work-realm policy only |

### 13.4 Audit model

Do not rely solely on full conversation transcripts.

Retain structured events:

```text
task requested
policy evaluated
approval requested
approval granted/denied
credential issued
sandbox created
command or capability invoked
artifact produced
result summarized
sandbox destroyed
credential revoked/expired
```

Sensitive raw logs should have stricter access and retention than sanitized task summaries.

---

## 14. Observability and Evaluation

The system needs evidence about whether it works.

### 14.1 Agent-task metrics

Possible metrics:

- task success rate;
- human correction rate;
- rollback rate;
- tests passed;
- repeated attempts;
- tool-call count;
- model cost;
- wall-clock time;
- sandbox startup time;
- failure category;
- policy denials;
- approval frequency;
- artifact usefulness;
- regressions introduced.

### 14.2 Personalization metrics

Possible metrics:

- save rate;
- completion rate;
- hide rate;
- repeat-source saturation;
- diversity;
- novelty;
- “why recommended” usefulness;
- explicit rating;
- time to first useful item;
- number of recommendations caused by stale/incorrect preferences;
- correction propagation time.

### 14.3 Infrastructure-operation metrics

Possible metrics:

- validation outcome;
- plan/apply drift;
- stale-plan refusal;
- destructive changes;
- backup verification;
- change success;
- service health after apply;
- rollback success;
- secret leakage checks.

### 14.4 Experimental record

Each significant experiment should record:

```text
problem
hypothesis
alternatives
scope
isolation boundary
implementation
metrics
expected result
actual result
failure modes
operational burden
security findings
decision
follow-up
removal plan
```

---

## 15. Experimentation-First Engineering Rules

These rules are central to the user’s request.

### 15.1 Keep interfaces stable, implementations replaceable

Examples:

- define a sandbox request before committing to Firecracker;
- define a task envelope before committing to NATS;
- define a memory record before committing to OpenBrain;
- define a content item before selecting Postgres tables or a search engine;
- define a project-service request before deploying Supabase.

### 15.2 Prefer thin vertical slices

A good experiment crosses the minimum number of layers needed to answer one question.

Example:

```text
Hermes Personal
  -> submit read-only code task
  -> message transport
  -> one Pi worker
  -> rootless Podman sandbox
  -> result event
  -> Hermes summary
```

Do not initially add:

- five message-bus clusters;
- multiple model routers;
- a full policy DSL;
- Firecracker;
- Supabase;
- a vector database;
- content ranking;
- work realm.

### 15.3 Do not generalize from one implementation

A useful pattern is to avoid building a large universal abstraction until at least two real use cases expose the shared shape.

For example:

- implement Podman and one Proxmox VM backend before finalizing the sandbox driver API;
- implement RSS and one non-RSS connector before finalizing the content connector contract;
- implement one coding task and one infrastructure-read task before finalizing agent capability taxonomy.

### 15.4 Make removal cheap

Experimental components should have:

- isolated deployment definitions;
- distinct data paths;
- clear state ownership;
- no undocumented dependencies;
- explicit cleanup commands;
- data export if state matters;
- feature flags or configuration gates.

### 15.5 Record superseded decisions

Use ADR-style statuses:

```text
proposed
experimental
accepted
rejected
superseded
retired
```

Do not delete history merely because a first design failed.

---

## 16. Suggested Phased Design and Delivery

### Phase 0: ingest and reconcile documents

No infrastructure changes.

Deliverables:

- source/document register;
- glossary;
- consolidated goals;
- constraints;
- current-state diagram;
- contradiction list;
- open-question register;
- candidate-decision map;
- experimentation principles.

### Phase 1: system context and ownership

Deliverables:

- system context diagram;
- repository ownership matrix;
- realm/trust-boundary diagram;
- data ownership matrix;
- agent role definitions;
- source-of-truth definitions;
- initial threat model.

### Phase 2: read-only agent coordination experiment

Goal:

- one Hermes instance submits a read-only task;
- one Pi worker receives it;
- one transport carries status and results;
- no infrastructure mutation;
- no persistent broad credentials.

Measure:

- reliability;
- latency;
- amount of custom integration;
- task observability;
- cancellation;
- duplicate handling;
- agent reconnect behavior.

### Phase 3: sandbox broker experiment

Implement two backends:

- rootless Podman;
- disposable Proxmox VM clone.

Optionally implement one small WASI tool.

Compare:

- startup time;
- cleanup;
- networking;
- credentials;
- artifacts;
- isolation;
- development ergonomics;
- failure recovery.

Do not add microVMs until this experiment shows a concrete gap.

### Phase 4: repository-native infrastructure adapter

Start read-only:

```text
infra.status
infra.validate
infra.plan-summary
```

Only later add:

```text
infra.apply-reviewed-plan
```

Maintain the existing `just validate`, `just plan`, and `just apply` contract.

### Phase 5: memory/profile pilot

Start with:

- confirmed facts;
- explicit preferences;
- source provenance;
- user corrections;
- personal realm only.

Do not begin by ingesting every transcript or browsing event.

### Phase 6: content aggregation pilot

Start with:

- current RSS support;
- one additional source connector;
- normalized content schema;
- durable item storage;
- explicit feedback;
- simple transparent ranking;
- Onboard presentation.

### Phase 7: development-service broker pilot

Start with a minimal project profile:

- database;
- bucket;
- message namespace;
- secrets;
- preview URL;
- automatic expiration.

Evaluate full Supabase only after the minimal profile demonstrates real limitations.

### Phase 8: work realm

Do not clone the personal system wholesale.

First define:

- work data classification;
- approved model providers;
- approved connectors;
- secret handling;
- retention;
- audit requirements;
- cross-realm prohibitions;
- whether any work data may enter personal infrastructure.

---

## 17. Open Questions

### 17.1 Product and scope

- Is this primarily a personal operating platform, a development platform, a homelab operator, a content product, or a shared foundation for all four?
- Which use case should prove the architecture first?
- What must be useful within the first month?
- What is explicitly not in scope?

### 17.2 Agent topology

- One Hermes per realm, one per infrastructure domain, or one coordinator with domain adapters?
- Are Pi workers ephemeral, persistent, or both?
- Can Pi initiate tasks, or only accept them?
- How are agents authenticated?
- How are agent versions and capabilities discovered?
- How are model/provider policies selected?

### 17.3 Messaging/workflow

- Does the system need a message bus, workflow engine, or both?
- Are durable tasks better represented in Postgres/Temporal than directly in a stream?
- What delivery guarantees are required?
- What state is authoritative during reconnects?
- How are long-running tasks cancelled?

### 17.4 Sandbox

- Which tasks truly require microVMs?
- Is a Proxmox VM template sufficiently fast?
- Is nested KVM acceptable?
- Should a dedicated bare-metal sandbox worker be introduced?
- How are base images built and verified?
- How is outbound network policy enforced?
- How are artifacts extracted from a destroyed sandbox?
- How are GPU workloads handled?

### 17.5 Development services

- Full Supabase or smaller primitives?
- Shared Postgres cluster versus per-project database?
- Which auth service?
- Which S3-compatible object store?
- How are preview environments represented in OnRamp?
- How are project resources garbage-collected?
- How are quotas and cost budgets enforced?

### 17.6 Memory

- Is OpenBrain sufficient?
- What is the canonical profile store?
- How does the user inspect and correct memory?
- Which observations may be retained automatically?
- How are old preferences decayed?
- How are contradictory facts resolved?
- What is shared between Hermes instances?

### 17.7 Content

- Which source APIs are available and acceptable?
- What content should be retained?
- Does the system need full text/transcripts or only metadata?
- How are X.com and Reddit access costs/limits handled?
- What is the primary ranking objective?
- How should diversity and serendipity be balanced against relevance?
- Is Onboard retained as Flask, partially rewritten, or treated as a UI client?

### 17.8 Repository structure

- Should agent-fabric code live in `homelab-infra`, OnRamp-vNext, or a new repository?
- Where do shared schemas live?
- Where do realm policies live?
- Where do private personalization values live?
- How are versioned contracts distributed to agents?

---

## 18. Recommended Immediate Work in the Local Session

The next local agent should not begin with code.

### Step 1: inspect repository state

Run the repository-approved discovery commands and inspect:

```bash
git status --short --branch
git log -5 --oneline
find docs -maxdepth 2 -type f | sort
```

Also read any repository-level agent instructions before editing.

### Step 2: read current contracts

At minimum:

```text
README.md
docs/README.md
docs/hermes-operator-pilot-prd.md
docs/onramp-app-platform-contract.md
docs/hermes-tuning.md
docs/onramp-host-runbook.md
docs/onramp-searxng-handoff.md
infra/services.json
```

### Step 3: ingest the new user-provided documents

For each supplied document, record:

- source and date;
- intended scope;
- explicit requirements;
- implied assumptions;
- proposed technologies;
- decisions;
- unresolved questions;
- conflicts with existing contracts;
- whether it is current, historical, speculative, or superseded.

### Step 4: produce a consolidated design workspace

Suggested files, subject to existing repo conventions:

```text
docs/agent-platform/
  README.md
  source-register.md
  goals-and-non-goals.md
  current-state.md
  system-context.md
  trust-boundaries.md
  open-questions.md
  experiment-roadmap.md
  decision-log.md
```

Do not create this structure blindly if the repository already has a preferred location or naming convention.

### Step 5: propose the first evidence-producing experiment

The experiment should:

- be personal-realm only;
- be read-only;
- use one Hermes and one Pi worker;
- use one transport;
- use one sandbox backend;
- avoid broad credentials;
- produce structured task and audit events;
- have measurable success/failure criteria;
- have a complete removal path.

### Step 6: review with the user before implementation

Present:

- consolidated understanding;
- areas of uncertainty;
- contradictions;
- first experiment;
- what will intentionally remain undecided;
- expected evidence;
- blast radius;
- cleanup plan.

---

## 19. Candidate First Experiment

This is an example, not a decision.

### Hypothesis

A lightweight task fabric can let Hermes delegate a repository-analysis task to Pi without giving Hermes or Pi broad infrastructure authority.

### Scope

- personal realm only;
- one Hermes instance;
- one Pi worker;
- one repository;
- read-only repository analysis;
- rootless Podman sandbox;
- no secret injection;
- no Git push;
- no infrastructure mutation.

### Flow

```text
User asks Hermes to analyze a repository
    |
Hermes creates structured task
    |
Task is persisted and delivered
    |
Pi worker claims task
    |
Sandbox broker creates rootless container
    |
Repository is mounted/read-only or cloned with read-only token
    |
Pi performs analysis
    |
Artifacts and structured result are retained
    |
Sandbox is destroyed
    |
Hermes presents result
```

### Questions answered

- Is a message bus necessary?
- How much state belongs in a database?
- Can Pi be driven cleanly as a worker?
- How are progress and cancellation represented?
- What result shape is useful to Hermes?
- What logs are necessary?
- Can the sandbox remain credential-minimal?
- What fails when the worker disconnects?
- How are duplicate task deliveries handled?

### Exit criteria

The experiment is successful if:

- the task survives worker restart;
- the task cannot access infrastructure credentials;
- duplicate delivery does not duplicate side effects;
- the user can see progress;
- the final artifact is attributable and reproducible;
- cleanup leaves no running workload or writable repository copy;
- the implementation is small enough to replace.

---

## 20. Decisions That Must Not Be Presumed

The following statements were discussed but are **not settled decisions**:

- NATS is the final message bus.
- JetStream is the final durable workflow store.
- A new `agent-fabric` repository must be created.
- Hermes is always centralized.
- There will be exactly two Hermes agents.
- OpenBrain is the final memory system.
- pgvector is the only retrieval backend.
- Firecracker is required.
- WASI will run the complete agent harness.
- Supabase is the development platform.
- Onboard must be rewritten.
- Onboard must remain Flask.
- OnRamp-vNext uses Podman for every workload.
- Proxmox LXC is acceptable for untrusted agent code.
- personal and work realms may share infrastructure.
- model inference will be entirely local.
- model inference will be entirely remote.
- Lakebed’s architecture is accurately understood.
- the first implementation should be production-ready.

---

## 21. Concise Architecture Principles

Use these as design checks:

1. **Repository-native truth:** agents operate existing systems; they do not silently replace them.
2. **Deterministic authority:** policy and approvals live outside the model.
3. **Scoped execution:** one task receives only the authority it needs.
4. **Realm isolation:** personal and work are separate by default.
5. **Disposable by default:** sandboxes and preview environments expire.
6. **Provenance everywhere:** memory, content, actions, and decisions have sources.
7. **Explainability:** recommendations and mutations should be understandable.
8. **Reversibility:** experiments and components have removal paths.
9. **Evidence before standardization:** measure real uses before freezing abstractions.
10. **Operational simplicity matters:** an elegant platform that cannot be maintained is a failed design.
11. **No infrastructure YOLO:** preserve plans, backups, approvals, and rollback.
12. **No opaque super-brain:** profile, RAG, events, documents, and inferences remain distinguishable.

---

## 22. Final Context for the Next Agent

The user is intentionally exploring a large design space. The ideas are not incomplete because the user expects an agent to guess the missing architecture. They are incomplete because the correct architecture must emerge through document reconciliation, prototypes, operational experience, and explicit choices.

The next agent should act as a systems architect and experimental partner:

- understand first;
- preserve existing safety contracts;
- make uncertainty visible;
- keep alternatives alive where evidence is absent;
- build only enough to answer the next important question;
- document what was learned;
- allow failed experiments to improve the design;
- move incrementally toward one coherent system.

The goal is not to produce a perfect architecture diagram immediately.

The goal is to create a disciplined process that can discover the right system.
