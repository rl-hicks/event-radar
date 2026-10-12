# Event Radar — Engineering Phase Map Artifact

**Version:** 1.1  
**Status:** ACCEPTED / GOVERNING  
**Accepted:** 2026-10-03 by project owner  
**Supersedes:** Engineering Phase Map v1.0 (accepted 2026-10-02)  
**Artifact type:** Engineering Phase Map  
**Upstream authority:** Event Radar — Project Definition v1.0; Product Definition v1.0; Product Phase Roadmap v1.0  
**Project owner:** Robot

**Revision scope:** Narrow owner-requested change to post-E0 migration/coexistence posture. The accepted E0 closeout and E0 historical acceptance conditions remain unchanged. Technical stack, seven E1 outcomes, E2–E4 scope, and product/engineering mapping are unchanged.

---

## 1. Authority

This artifact defines the high-level technical progression required to deliver the Event Radar Product Phase Roadmap.

It governs:

- chosen technical foundation;
- high-level architecture boundaries;
- migration direction from the current personal system;
- engineering-phase structure;
- major dependencies;
- and the relationship between engineering phases and product milestones.

Detailed implementation belongs only in the active Engineering Execution Roadmap.

---

## 2. Starting technical reality

At project formation (2026-10-02), Event Radar already existed as a working personal system. This subsection records the reported historical entry baseline, not the post-E0 live operational status.

Reported formation baseline:

- repository: `rl-hicks/event-radar`;
- local development path: `~/dev/event-radar`;
- Python 3.13 with `uv`;
- public application repository plus private runtime/state repository;
- scheduled GitHub Actions production;
- Sonoma County Tourism collector;
- Happening Sonoma County collector;
- normalization/deduplication;
- source-aware pricing;
- Open-Meteo weather;
- curated 35-route hike catalog;
- AI #1 scraped-event semantic analysis;
- AI #2 complementary web discovery;
- AI #3 personalized final curation;
- private user context and preference policy;
- Telegram delivery;
- audit tooling;
- graceful source/provider degradation;
- token/cost telemetry;
- and a large automated Python test suite.

This historical baseline was subject to E0 verification. The accepted E0 Handoff / Closeout v1.0 records the verified phase-end state. Subsequently, E0 PR #1 merged into `main` (`f03923dc2b186d914c301adb01320ad9080da88a`); the project owner discontinued automatic personal delivery, and commit `3a0fb5e9ff414ecd14d923d23551e07977d287a1` removed both Thursday cron entries, retaining manual dispatch. The pre-E0 historical implementation is archived at `archive/personal-pre-e0-2026-10-03` (`7ffb52bdb4ef62df139000957df15d135d32de50`). Reverify live refs and local worktrees at E1 activation.

Plans do not substitute for repository inspection.

---

## 3. Productization strategy

The post-E0 engineering strategy is:

> **Evolve the existing `event-radar` repository in place into the multi-user product foundation, preserving recoverable historical source and validated reusable research capabilities without requiring ongoing parity of the original personal packet service.**

A clean-room rewrite is **not** the default.

The existing Python research engine remains the candidate core.

The repository will become a controlled multi-surface application:

- existing research/worker core;
- FastAPI backend/API;
- PostgreSQL persistence;
- React web client;
- scheduled shared research jobs;
- per-user personalization jobs;
- and production integrations.

The owner discontinued automatic personal Thursday packet delivery after E0 closed. The current legacy workflow is manual-only and is not a required ongoing productization service or E1 exit gate. It must not be automatically re-enabled to serve as the shared regional scheduler. The new shared regional worker is a separate, deliberately authorized path.

Bounded extraction/refactoring of personal-only orchestration, prompts, models, and tests is permitted where it advances the shared product architecture. Preserve useful evidence, collectors, normalization, source-aware validation, fallback/degradation and telemetry, security boundaries, and a recoverable historical source reference. Consequential irreversible removal or migration of private state, useful source, or production resources requires explicit review; the change in posture is not a blanket deletion authorization.

A separate clone/new repository is not the default plan. A material change in repository strategy requires Engineering Phase Map reconciliation.

---

## 4. Chosen technical foundation

### 4.1 Core language/runtime

**Python 3.13 + uv**

The existing research engine remains Python.

### 4.2 Backend/API

**FastAPI**

The backend owns:

- authenticated product APIs;
- domain/service orchestration;
- database access;
- entitlement checks;
- and product-facing access to packet/context state.

### 4.3 Database

**PostgreSQL**

Managed production database:

**Supabase Postgres**

Application persistence:

- SQLAlchemy 2.x;
- Alembic migrations.

### 4.4 Authentication

**Supabase Auth**

The web client uses Supabase authentication.

The FastAPI backend validates authenticated user identity and enforces authorization independently.

### 4.5 Frontend

**React + TypeScript + Vite**

The public web app is deployed on **Vercel**.

The frontend is not responsible for privileged business logic.

### 4.6 Backend hosting

**Render**

FastAPI is deployed as a Render web service.

### 4.7 Scheduled/background execution

**GitHub Actions remains the initial scheduler/worker platform.**

It will continue to run:

- weekly regional research;
- packet-generation batches;
- and CI.

GitHub Actions is an initial engineering choice, not a permanent product requirement.

A scheduler/queue migration occurs only if reliability, latency, concurrency, or scale evidence warrants it.

### 4.8 Billing

**Stripe Billing**

### 4.9 Email

**Resend**

### 4.10 AI

**OpenAI Responses API**

Model selection remains configuration.

The existing stage-specific model strategy may continue if it remains quality/reliability appropriate.

AI usage and cost telemetry remain mandatory.

### 4.11 Weather

**Open-Meteo**

### 4.12 CI/testing

Python:

- Ruff;
- mypy;
- pytest.

Web:

- TypeScript type checking;
- ESLint;
- Vitest / Testing Library.

Browser-level tests may be added when user-facing flows exist.

### 4.13 Local development

Local development will support:

- Python/uv;
- Node;
- local PostgreSQL through Docker Compose;
- and environment-based connection to required external test services.

Production secrets do not belong in the repository.

---

## 5. Major architecture boundaries

### 5.1 Shared regional intelligence versus personalization

Shared research must not load a private user preference model.

The regional research pipeline produces a reusable Regional Weekend Universe.

Per-user curation occurs downstream.

### 5.2 Durable state versus ephemeral workers

GitHub Actions runners are ephemeral.

Durable product state lives in PostgreSQL.

### 5.3 Web versus backend authority

The browser handles presentation and user interaction.

The backend owns authenticated access, entitlement checks, durable product operations, and privileged integration logic.

### 5.4 External AI boundary

No external AI interface receives unrestricted database credentials.

AI receives only the bounded context required for the stage being executed.

### 5.5 Legacy personal path

The original personal code is preserved as recoverable historical source; the live Thursday delivery schedule is already disabled by owner decision. Manual legacy dispatch may remain available but is not a required E1 regression run or shared-research execution path. It must not be invoked, re-enabled, or given new secrets without explicit authorization.

The E1 shared worker is independently invoked, user-neutral, isolated from private state and Telegram, and must not require personal preference files.

Identical personal packet/Telegram behavior and parity with the historical one-user service are **not** E1 exit requirements. Retain validated research behavior and replacement tests appropriate to the new contracts; document and review consequential retirements rather than hiding regressions by deleting tests.

---

# E0 — Productization Foundation

## 6. Objective

Establish and verify the technical foundation on which the public product can be built **without breaking the current personal Event Radar**.

E0 proves the factory works.

It does not claim V1 exists.

## 7. Expected capability at E0 exit

At E0 exit:

- the existing repository has a stable productization structure;
- the existing personal CLI and scheduled production path remain functional;
- local and deployed PostgreSQL connectivity work;
- Alembic migrations work;
- Supabase Auth works from the web client;
- FastAPI validates authenticated requests;
- the authenticated backend can perform a user-scoped database roundtrip;
- the React web app is deployed;
- the FastAPI backend is deployed;
- CI validates both Python and web code;
- environment/secrets boundaries are documented;
- and the existing research engine can coexist with the new web/API/database foundation.

## 8. Product relationship

E0 enables later V1 work.

It does not itself complete a Product Version.

---

# E1 — Shared Regional Intelligence

## 9. Objective

Transform the current single-user research pipeline into a reusable multi-user regional intelligence layer.

## 10. Expected capability at E1 exit

At E1 exit:

- AI #1/shared semantic analysis is user-neutral;
- AI #2/shared discovery is user-neutral;
- a Regional Weekend Universe is persisted;
- regional opportunities carry provenance and semantic enrichment;
- one regional research run can be reused for multiple user profiles;
- the weekly shared research job is idempotent for a weekend/region;
- and personal preference policy is no longer required to generate the shared regional universe.

## 11. Major dependencies

- E0 database/API/runtime foundation;
- current collectors and semantic pipeline;
- explicit shared-vs-personal context boundary.

## 12. Major risks

- accidentally preserving Robot-specific taste in shared prompts;
- excessive refactoring that destabilizes validated research components;
- losing source evidence or fallback behavior;
- and producing a generic semantic layer too weak for later personalization.

## 13. Product relationship

E1 provides the shared-research half of V1.

V1 is not complete until E2.

---

# E2 — Paid Personalized Beta

## 14. Objective

Build the complete external user flow required for Product V1.

## 15. Expected capability at E2 exit

At E2 exit:

- onboarding creates persistent User Context;
- authenticated users are isolated;
- Stripe subscription state controls entitlement;
- per-user curation runs from the shared Regional Weekend Universe;
- Weekend Packets are persisted;
- the current packet is visible on the website;
- Resend notifies the user;
- external beta users can complete the paid product loop;
- and V1 acceptance evidence can be collected.

## 16. Major dependencies

- E0 account/auth/persistence foundation;
- E1 Regional Weekend Universe;
- accepted V1 product decisions on beta price/onboarding minimums.

## 17. Major risks

- coupling billing too deeply to recommendation generation;
- onboarding that is either too weak or too burdensome;
- packet generation concurrency;
- privacy defects;
- and treating one successful internal profile as multi-user proof.

## 18. Product relationship

**Completes Product V1 — Paid Personalized Beta.**

---

# E3 — Recurring User Lifecycle

## 19. Objective

Turn the paid beta loop into a repeatable weekly service.

## 20. Expected capability at E3 exit

At E3 exit:

- persistent User Context can be edited;
- Weekend Intent is supported separately;
- packet history is available;
- subscription state persists and is self-service;
- weekly generation/notification operates predictably;
- engagement/return-use evidence is captured;
- degraded-state UX is user-visible;
- and normal repeat use does not require builder state maintenance.

## 21. Major dependencies

- successful V1 loop;
- actual beta-user evidence;
- stable shared research and per-user curation boundaries.

## 22. Major risks

- overfitting to a tiny beta sample;
- stale context;
- unclear temporary-vs-persistent semantics;
- recurring job duplication;
- and hidden failure states.

## 23. Product relationship

**Completes Product V2 — Repeatable Weekend Service.**

---

# E4 — Launch Hardening

## 24. Objective

Harden the recurring service until the complete Product Definition is operationally credible for sustained local use.

## 25. Expected capability at E4 exit

At E4 exit:

- account and authorization boundaries are hardened;
- recurring jobs are observable and recoverable;
- failed jobs are diagnosable;
- packet generation is idempotent and safe to retry;
- degraded states are consistent;
- cost/latency are visible;
- operational runbooks exist;
- deployment and migration practices are reliable;
- normal product operation is builder-independent;
- and the complete Product Definition readiness criteria are verified.

## 26. Major dependencies

- V1 and V2 evidence;
- stable recurring product behavior;
- known real-world failure patterns.

## 27. Major risks

- polishing before enough usage evidence exists;
- premature scale engineering;
- and adding future-product breadth during launch hardening.

## 28. Product relationship

**Completes Product V3 — Launch-Capable Local Product and the current project destination.**

---

## 29. Product/engineering mapping

| Engineering phase | Primary purpose | Product milestone |
|---|---|---|
| E0 | Productization foundation | Enables V1 |
| E1 | Shared Regional Intelligence | Enables V1 |
| E2 | Paid personalized external loop | Completes V1 |
| E3 | Recurring lifecycle | Completes V2 |
| E4 | Launch hardening | Completes V3 |

The numbering is intentionally not one-to-one.

---

## 30. Migration strategy

The revised product-first migration posture is:

1. Preserve the archived pre-E0 implementation and factual E0 closeout as historical recovery/evidence, rather than requiring continuous operation of the personal Thursday service.
2. Continue evolving the integrated `event-radar` repository in place and keep the accepted E0 web/API/auth/database/security foundation working.
3. Preserve, extract, adapt or refactor validated research capabilities into a user-neutral regional path; retire personal-only contracts with reviewed rationale and meaningful replacement coverage.
4. Persist public-product state in PostgreSQL and keep the shared regional job separate from private-state/Telegram execution.
5. Prove user-neutral shared regional intelligence, provenance, multi-consumer reuse and idempotent weekly execution in E1 before building paid per-user product behavior in E2.
6. Validate the public product through the governing V1–V3 milestones, not output parity with the historic personal packet.
7. Review/authorize consequential irreversible removal of useful source, private data, manual legacy execution, infrastructure, secrets or hosted state separately; do not treat schedule suspension as permission for destructive cleanup.

The existing personal Thursday cron was disabled after E0 by owner decision; it must not be restored as a shortcut for E1. There is no default clean-room rewrite or uncontrolled big-bang migration.

---

## 31. Future engineering territory

The following are outside the current Engineering Phase Map unless later admitted:

- ChatGPT Plugin/API tool surface;
- restaurant/coffee database;
- geographic chaining;
- maps;
- new regions;
- mobile applications;
- social/community features;
- dedicated queue infrastructure;
- Kubernetes;
- multi-region infrastructure.

---

## 32. Governing status

**ACCEPTED / GOVERNING — VERSION 1.1**

Accepted by the project owner on 2026-10-03. This version supersedes v1.0 for current engineering governance. The change concerns the post-E0 legacy coexistence and migration posture only; it does not retroactively change E0 requirements, its accepted historical closeout, the seven E1 outcomes, or the E2–E4 phase map. The Project Definition v1.0, Product Definition v1.0, and Product Phase Roadmap v1.0 remain unchanged.

Detailed execution exists only for the active phase.
