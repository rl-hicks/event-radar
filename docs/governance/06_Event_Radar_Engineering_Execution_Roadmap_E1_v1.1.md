# Event Radar — Engineering Execution Roadmap — E1

**Version:** 1.1 — ACCEPTED  
**Accepted:** 2026-10-03 by project owner in the E1 Execution Conversation; supersedes E1 Engineering Execution Roadmap v1.0 for active execution  
**Revision scope:** Strengthens WP3–WP5 and dependent worker/verification language around modular source adapters, source-coverage intelligence, reusable semantic enrichment, adaptive multi-pass discovery, and run-level research budgeting. The seven E1 outcomes, E2 boundary, and Engineering Phase Map v1.1 remain unchanged.  
**Engineering phase:** E1 — Shared Regional Intelligence  
**Disposition:** ACTIVE EXECUTION PLAN; E1 execution begins at WP0 through its dedicated conversation. Acceptance is **not** blanket authorization for live providers, recurring paid scheduling, hosted schema writes, deployment, merge, or destructive operations.  
**Upstream authority:** Project Definition v1.0; Product Definition v1.0; Product Phase Roadmap v1.0; Engineering Phase Map v1.1 (accepted 2026-10-03)  
**Predecessor:** E0 Phase Handoff / Closeout v1.0 — retained as the authoritative *historical phase-end record*, not rewritten for later integration  
**Required engineering evidence:** `docs/e1-core-coexistence-technical-note.md` (accepted WP8); `docs/security-baseline.md` (WP9)  
**Repository verification:** `rl-hicks/event-radar`, inspected against current GitHub refs on 2026-10-03. Re-verify all refs at E1 activation.

---

## 0. Accepted revision history (draft v0.1 → draft v0.2 → accepted v1.0)

| Area | v0.1 assumption | v0.2 revision and reason |
| --- | --- | --- |
| Repository baseline | E0 draft PR #1 unmerged; protected `main` still pre-E0 | PR #1 is merged; start WP0 from **current verified `main`**, presently `3a0fb5e9ff414ecd14d923d23551e07977d287a1`, in a new isolated E1 branch/worktree. The original E0 SHA remains evidence, not the default working base. |
| Historical preservation | Keep a live, independently operational personal pipeline through E1 | Owner has prioritized the public product and stopped automatic personal Thursday delivery. Preserve the archived pre-E0 implementation and useful research capabilities; do **not** demand personal-packet behavioral parity while extracting the shared engine. Any consequential removal or irreversible migration still needs review. |
| Legacy workflow | Protect scheduled personal Thursday packet execution | The current workflow has **manual `workflow_dispatch` only**. Do not re-enable its Thursday schedule; do not confuse legacy manual dispatch with the new E1 shared research job. |
| AI #1 / AI #2 | Add separate neutral paths while retaining identical personal paths | Establish **user-neutral contracts and payloads** as primary E1 production paths; allow bounded extraction/refactoring of existing stages. Preserve evidence handling, validation, source diversity, fallback, and telemetry—not private-policy payloads or identical personal output. |
| Regression evidence | Exact legacy CLI/Telegram/packet behavior is a standing E1 pass condition | Protect current E0 API/auth/database/web/security gates, source integrity, archived history and reusable research invariants. Adapt or retire personal-output tests **only with reviewed rationale and replacement coverage**, not by suppressing failures. The manual legacy workflow is not a required live E1 verification run. |
| Scheduling | Keep existing personal scheduler untouched and add shared workflow beside it | The personal cron has already been removed by accepted owner decision. E1 establishes a **separate** idempotent weekly shared job; paid/live scheduling and credentials require explicit owner approval. |
| Dependencies | Potential parallel starter/extraction work could be assumed | DogHat App Starter extraction is completed independently, **not an E1 prerequisite, task, or acceptance gate**. E1 uses the integrated Event Radar repository. |

The **seven governing E1 outcomes are unchanged**. Acceptance does not move E2 product capabilities into E1. The Engineering Phase Map v1.1 governing revision was approved explicitly by the owner before this roadmap was promoted.

### Accepted v1.1 execution refinement

| Area | v1.0 execution shape | v1.1 accepted refinement |
| --- | --- | --- |
| Regional collection | Reuse named Sonoma collectors as explicit factual inputs | Establish a source-adapter contract and registry so source-specific parsing remains specialized while orchestration is source-agnostic. Existing collectors become initial adapters rather than hard-coded pipeline branches. |
| Source awareness | Report source status/failure | Produce an explicit coverage assessment across source class, geography, time and opportunity type, including known unsearched/failed areas and no claim of regional completeness. |
| AI #1 | Neutral enrichment of scraped events | Make shared semantic analysis origin-agnostic: any verified regional candidate, including later WP5 discoveries, can pass through the same evidence-grounded semantic service. |
| AI #2 | One bounded complementary discovery stage | Treat discovery as an adaptive regional research subsystem. Multiple search/model calls and discovery waves are permitted when justified by coverage gaps, subject to an explicit run-level research budget, telemetry and stop rules. |
| Discovery outputs | Additional opportunities | Verify every discovered lead before admission, track duplicate/rejected leads, and surface recurring source leads separately for later adapter review; never auto-promote a newly found source to trusted production collection. |
| Cost posture | Minimize provider calls | Optimize shared research for regional-universe quality per run, not minimum raw call count. Because the result is reused across consumers, higher shared research spend can be rational, but live spend still requires an approved ceiling and must remain bounded/observable. |

This refinement changes implementation detail, not phase identity: E1 still produces one user-neutral Regional Weekend Universe reusable across multiple later consumers.

## 1. Mission, scope, and non-negotiable phase outcomes

Transform the validated single-user research engine into a **reusable, user-neutral regional intelligence layer**. The shared asset is a durable **Regional Weekend Universe**: sourced regional opportunities and their evidence-backed semantic characteristics for a bounded region and weekend, reusable by multiple later consumers. E1 provides the shared-research half of Product V1, not a paid or personalized external user loop.

The accepted Engineering Phase Map v1.1 §10 retains seven distinct conditions at E1 exit:

1. AI #1 / shared semantic analysis is user-neutral.
2. AI #2 / shared discovery is user-neutral.
3. A Regional Weekend Universe is persisted.
4. Regional opportunities retain provenance and semantic enrichment.
5. One regional research run can be reused for multiple user profiles.
6. The weekly shared research job is idempotent for a weekend/region.
7. Personal preference policy is not needed to generate the shared regional universe.

**Design test:** With no user account/profile, private context file, Telegram direction, personal prompt, or private state checkout, can the same explicit region/weekend research job produce an inspectable persisted universe that two different later consumers read without another provider/research run? E1 remains open if the answer is no.

The proving geography is bounded **Sonoma County / North Bay**, with a deliberately named initial region and timezone. No multi-region expansion is required. Shared event and activity semantics must remain rich enough for eventual personalization without themselves deciding what one specific person should do.

## 2. Accepted governing reconciliation and decision record

On 2026-10-03, the project owner approved Engineering Phase Map **v1.1**, explicitly replacing v1.0's requirement to operate the historic personal Thursday/Telegram service until public-product parity. The Project Manager reviewed and the owner accepted predecessor draft E1 v0.2 as this active **Engineering Execution Roadmap E1 v1.0**. This resolves the previously flagged conflict in v1.0 §§3, 5.5 and 30 and aligns E1's refactoring/verification requirements with the product-first direction. This section is a **decision record, not an unresolved blocker**.

Accepted migration posture: preserve recoverable historical source and the factual E0 closeout, tested reusable research capabilities, provenance and security boundaries; the legacy automatic Thursday job remains disabled, and manual invocation needs separate authorization. E1 is not required to preserve identical private packet/Telegram output, live personal-production parity, or personal-policy contracts. Bounded reviewed extraction/refactoring is allowed; consequential irreversible source/private-state/hosted-resource changes require separate authorization. E0 historical gates are not retroactively changed.

No Project Definition v1.0, Product Definition v1.0, or Product Phase Roadmap v1.0 revision is required for this decision. The accepted E1 outcome set and E2–E4 phase boundaries are unchanged. The seven E1 outcomes remain mandatory, including a real idempotent weekly shared research job; live provider calls, weekly activation and hosted changes each remain separately permissioned.

The Project Tracker must ingest this acceptance and the distinct post-E0 integration/personal-schedule-pause events. The original E0 Handoff / Closeout v1.0 remains an immutable historical account.

## 3. Verified repository and operational starting state (planning snapshot)

Current GitHub verification found:

| Item | Verified state |
| --- | --- |
| Repository | `rl-hicks/event-radar` |
| `main` HEAD | [`3a0fb5e9ff414ecd14d923d23551e07977d287a1`](https://github.com/rl-hicks/event-radar/commit/3a0fb5e9ff414ecd14d923d23551e07977d287a1) |
| E0 PR #1 | [Merged](https://github.com/rl-hicks/event-radar/pull/1); merge commit [`f03923dc2b186d914c301adb01320ad9080da88a`](https://github.com/rl-hicks/event-radar/commit/f03923dc2b186d914c301adb01320ad9080da88a) |
| Original pre-E0 archive branch | `archive/personal-pre-e0-2026-10-03` → `7ffb52bdb4ef62df139000957df15d135d32de50` |
| Later owner-approved operational change | [`3a0fb5e`](https://github.com/rl-hicks/event-radar/commit/3a0fb5e9ff414ecd14d923d23551e07977d287a1): removes both Thursday cron entries from `.github/workflows/event-radar.yml`; manual `workflow_dispatch` retained |
| Merge-to-pause diff | One workflow file changed; no runtime source change in that commit |
| Accepted cumulative E0 source | `b7d407942ce620be1a68638a4f915371f6de2784`; now in `main` history |
| Final E0 CI evidence | [PR CI run 37160502383](https://github.com/rl-hicks/event-radar/actions/runs/37160502383): 359 Python passes, one expected hosted-provider skip, all five real PostgreSQL tests, 39 web tests, source/build security gates |

The existing E0 application foundation includes isolated FastAPI/Auth/DB, Alembic `0001_app_users`, React/TS/Vite, deployed Vercel/Render staging and a separate Product Foundation CI. The deployed WP6 chain was verified during E0, **but the live providers' deployed commit metadata was not re-fetched during this roadmap revision**; do not infer that their current code equals today's `main`. The legacy research engine and private assets have not been deliberately deleted. This verification establishes GitHub repository state, **not** the contents or cleanliness of the owner's local worktrees or the private state repository.

The current personal workflow's obsolete Pacific-time guard still contains branches for schedule events, but its trigger is manual only; treat that dead configuration as optional later cleanup, not an invitation to restore automatic delivery. The original personal workflow is available as historical source at the archive ref. Its manual present-day path may be used only under separate authorization; it is **not** a WP0 baseline packet run.

**WP0 starting rule:** fetch and confirm `origin/main`, checkout a *new isolated E1 worktree/branch* from its then-current accepted SHA, and record divergence. Do not reset or assume `/home/robot/dev/event-radar-e0` or the original `/home/robot/dev/event-radar` is clean. Record local ignored/provider files by path/status only. Do not copy private runtime material. Do not create a fresh repository or depend on the completed DogHat App Starter extraction.

## 4. E1 engineering invariants and authorization boundaries

1. **Neutrality at the first shared input:** AI #1, AI #2, source selection, regional/geographic defaults and pre-persistence compression must not receive or encode personal User Context, private Markdown projections, permanent/temporary directions, personal schedule, cost/drive/social posture, or one user's home-base preferences. Emptying old personal fields is not depersonalization.
2. **Fact, shared descriptor, and personal verdict remain separate:** preserve occurrence/source evidence, supported semantic tags, observation time, freshness, explicit uncertainty, provider failure/degradation and source alternatives. “Would Robot enjoy this?” belongs downstream in E2, not in the shared universe.
3. **Preserve capability, not obsolete workflow parity:** retain/reuse tested collectors, normalization, conservative deduplication, weather, source validation, bounded provider calls, graceful degradation and cost/latency telemetry wherever sound. Bounded changes to old orchestration/prompts/models are allowed after reviewing changed contracts; historical archive remains available. Do not make deliberate behavior changes look like an unchanged-legacy regression.
4. **Maintain the E0 foundation:** preserve authenticated backend user identity, private/browser credential separation, current FastAPI isolation, Alembic ownership, PostgreSQL test safety, React/Vite build, CI/security checks and public-facing error/log protections. Shared worker runs outside API import/lifespan.
5. **Separate workflows:** the manual-only legacy `event-radar.yml` is not E1's worker. Never re-enable the old Thursday cron as an E1 shortcut. A new workflow has its own inputs, permissions, credentials, concurrency and bounded schedule; no live automatic spend before explicit owner approval.
6. **Durability and retries:** PostgreSQL owns shared universe and run state. Ephemeral GitHub Actions runners and date-named packets are not durable shared storage. Repeating the same logical region/weekend/version is safe and observable; a failed/degraded retry must not destroy the last good snapshot.
7. **Small first region, modular source boundary:** keep Sonoma County as the proving region, but make regional orchestration source-agnostic through a minimal adapter/registry contract. Source-specific scraping/API quirks belong inside adapters; adding an enabled source must not require hard-coded branches in the core research pipeline. Do not turn this into a speculative national plugin platform, make real travel-time claims without evidence, or pad discovery results.
8. **Explicit review for consequential operations:** no irreversible deletion/migration of useful sources or private assets; no hosted-schema write, deployment, recurring paid job, secret relocation or provider/model spend without bounded owner-approved execution. Repository branch/PR authorization is distinct from merge/deploy authorization.
9. **Evidence discipline:** approved contract/design precedes broad extraction; tests and real disposable-DB proof precede claims of persistence/idempotency; actual GitHub CI precedes phase completion. Codex reports are results to inspect, not self-accepting milestones.

## 5. Activation decisions to resolve in WP0–WP1

Within accepted Product/Phase scope, the E1 lead must propose and record these decisions before committing consequential schema/worker designs:

- **Region/weekend identity:** stable initial region identifier, timezone and coverage boundary; local Friday–Sunday window, UTC representation, explicit research `as_of`; how a Thursday weekly schedule targets a future weekend without changing the key on rerun.
- **Universe breadth:** regional events/occurrences, hike/activity representation, evidence/unknowns and candidate inclusion policy. Avoid accidentally retaining personal drive-friction or hiking-fitness rank as an exhaustive regional filter. Report omissions and source failures.
- **Provenance/semantics:** source alternatives, occurrence time/venue/price evidence, claim confidence/unknowns, semantic descriptors versus personal suitability, and stable identity/version strategy when primary source changes.
- **Run and snapshot semantics:** idempotency key, uniqueness and version/research-policy revisions, concurrent claim/lease or equivalent, retries, partial state, last-good snapshot, freshness, failed-provider diagnostics and backfill rules.
- **Refactor allowance:** smallest extraction that removes `models.* → token_usage → config.settings` import-time environment coupling and personal-context passage through AI #1/#2. Identify dependencies/tests that will be replaced or retired; archive is historical recovery, not active regression oracle.
- **Source architecture:** minimal adapter interface/registry, adapter metadata and coverage semantics needed for source-agnostic orchestration in one region. Decide how direct/authoritative sources, aggregators, calendars/APIs and bounded catalog sources report capabilities without pretending every source has identical extraction mechanics.
- **Regional research budget:** define a run-level provider/search budget and stop policy for adaptive discovery. Do not encode an arbitrary single-call requirement; constrain total approved spend, tool/search volume, wall-clock/retry behavior and observable marginal discovery instead.
- **Worker authority:** approved provider ceiling, data/credential location, minimal database privileges, staged hosted migration/deployment plan, and exact timing/approval for an active weekly shared schedule. GitHub Actions is the initial platform unless measured evidence justifies escalation.

These are execution design decisions, not permission to alter governing project scope. Resolve the §2 Phase Map conflict before activating implementation.

## 6. Proposed work packages and evidence-driven sequence

**Sequence:** WP0 → WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → WP7 → WP8 → WP9. WP1 contracts govern later work; implementation can use narrowly scoped Codex prompts and return evidence at each package. A successor package starts only after E1 Execution Conversation acceptance of its dependencies. The E1 lead may subdivide a package without silently expanding E1 or changing these exit requirements.

### E1-WP0 — Activate integrated repository and reconcile authority

**Mission:** establish a clean, product-first source-of-truth baseline and explicit execution permissions.

- Confirm and record the already accepted Engineering Phase Map v1.1 and this E1 roadmap v1.0; do not reopen the resolved migration conflict. Record the original archive as historical, and current verified `main` as the proposed integration base.
- Fetch and verify `origin/main` (planning snapshot `3a0fb5e…`), merged PR #1, the workflow schedule-pause commit and the archive branch. Create an isolated E1 worktree/branch at the actual accepted integrated tip. Inventory local status/provider files without inspecting/copying private contents. No rollback to pre-E0 `main` and no reuse of a stale unmerged E0 branch by assumption.
- Inspect accepted E0 closeout, WP8 technical note, WP9 security note, Product Foundation CI, active migration head, deployed-source provenance and manual-only legacy workflow. Baseline Python/web/static/security and disposable-PostgreSQL gates; use CI/owner-run evidence where local Docker privileges are unavailable. No live personal packet dispatch.
- Agree first region/timezone, high-level provider budget, and staged permissions. Record which old personal-only tests/contracts are informational versus must-preserve E0/public-research protections. Treat DogHat App Starter as outside the critical path.

**Exit evidence:** exact branch/SHA and clean isolated status; verified archived ref and manual-only workflow; record of accepted governing reconciliation; green accepted foundation baseline; recorded provider/deployment and private-state boundaries. Unresolved material governance, baseline, or permission dependencies must be escalated before affected implementation proceeds.

### E1-WP1 — Define the neutral regional research contract

**Mission:** make the shared fact/semantic/personal boundary executable before extraction.

- Specify `Region`, `WeekendWindow`/timezone/`as_of`, source coverage/status, regional opportunity and occurrence, evidence/provenance alternatives, semantic enrichment, important unknowns, freshness and audit-safe diagnostics. Decide how events and hikes enter a broad candidate universe.
- Inspect actual legacy `Event`, `WeekendEventCard`, `HikeCandidate`, `RecommendationContext`, AI request objects and prompts. Classify every relevant field as source fact, supported regional descriptor, uncertain dynamic fact, personal policy/verdict or operation-only data. Explicitly ban private fields and personal identifiers from shared request/output/storage contracts.
- Define stable region/weekend/run-version identity, factual validation and observation semantics. Use two materially different **synthetic** profiles only as negative contamination/read-reuse tests; the shared job must be constructible and runnable with **no profile at all**.
- Produce contract fixtures for multiple-source provenance, duplicate occurrences, unknown price/access, empty discovery, partial source failure and no opportunities; don't invent minimum event volume or user-profile schema.

**Exit evidence:** reviewed typed/serialized contract, field/provenance matrix, fixed-input timezone/window tests and a no-personal-context contract that can be enforced at payload boundaries.

### E1-WP2 — Extract an environment-pure reusable core

**Mission:** remove unsafe configuration/import coupling and establish a maintainable shared entry surface, using bounded refactoring rather than preserving an obsolete personal-call graph at all costs.

- Address the identified `models.curation → models.event_analysis → models.ai → models.token_usage → config.settings` import path. Separate type-only pricing/model dependencies from module-level legacy `Settings()` or inject configuration explicitly as justified. Import/constructing the chosen shared package must not read `.env`, private paths, perform network/DB I/O, write files or launch a CLI.
- Extract/reorganize only source-backed reusable contracts/utilities and validated adapters needed for WP3–WP5; preserve evidence/retry/telemetry behavior, not a claim that all historical symbols or packet output remain stable. Use existing tests as evidence when contracts remain; update tests deliberately for reviewed changed behavior.
- Keep the E0 API/auth/database/web paths intact and assert API startup does not launch research, migrations, Telegram, or worker activity. No privileged browser configuration introduced. Retain the archive unchanged as historical recovery. Report any proposed destructive deletion or migration for separate review.

**Exit evidence:** fresh-process shared-import side-effect guard, green E0 API/security foundations, reviewed migration/refactor diff and meaningful reusable-core tests. A sweeping unreviewed rewrite is a stop condition.

### E1-WP3 — Modular regional collection and coverage intelligence

**Mission:** build a source-agnostic regional collection layer that can accept specialized source adapters without hard-coding the research pipeline to a small set of websites.

- Define the minimal shared adapter contract and registry for regional collection. Each enabled source declares a stable source ID, source class, supported geography/coverage description, supported opportunity/evidence types, collection mechanism/config needs and bounded operational status. Specialized API, HTML, calendar, structured-data or catalog logic stays inside the adapter.
- Make orchestration source-agnostic: the regional collector executes the enabled registry for an explicit region/weekend/`as_of`, handles each adapter independently, and receives normalized candidates/evidence plus source-coverage status. Adding a conforming adapter should not require a new conditional branch in the core collection pipeline.
- Migrate/reuse the validated Sonoma Tourism and Happenings collectors as initial event adapters. Reuse Open-Meteo and the current hike/catalog capabilities where they fit the shared evidence contract; do not claim those adapters are complete regional coverage. Additional public source pilots may be added only through the same contract and reviewed source-specific implementation.
- Preserve normalized occurrence/price facts, conservative deduplication, source alternatives/provenance, observation time, explicit unknowns, factual rejections and raw-versus-retained candidate diagnostics. Failures degrade independently; one broken source must not erase another source's valid evidence.
- Produce a **coverage assessment** for the run: which source classes/geographic areas/time windows/opportunity classes were searched, failed, returned known-empty results, or remain unsearched/unknown. Coverage is evidence about research effort, not a claim that every regional opportunity was found.
- For hikes/outdoor candidates, distinguish durable route/location facts and current public evidence from `drive_friction_from_santa_rosa`, solo-fit, personal scoring or capped personal shortlist behavior. Treat unverified access/closures/tide/surf/travel time/ticket availability as unknown unless supported.
- Test with public/synthetic adapters: registry execution, adding an adapter without orchestration edits, duplicate source IDs, no enabled sources, one-source failure, deterministic fixed-input output/coverage, source-order independence where appropriate, and no private settings/context/directions. Never fabricate filler to satisfy event counts.

**Exit evidence:** source-adapter interface and registry, at least the current validated regional collectors running through that boundary, useful user-free normalized inventory, explicit source/coverage/failure report, recall/loss review against safe fixtures, and proof that the core collector has no private-input or source-name-specific orchestration dependency.

### E1-WP4 — Shared semantic intelligence over verified regional candidates

**Mission:** provide one reusable evidence-grounded semantic analysis service for regional opportunities regardless of whether the candidate originated from a deterministic WP3 adapter or later verified WP5 discovery.

- Define the distinct **regional** AI #1 request/prompt/structured response from WP1 contracts. Analyze supported experience, participation, interaction, setting/logistics and explicit uncertainty; never decide whether a particular person should attend. Public evidence and region/weekend context only; exclude `UserContext`, personal projections, directions and personal schedule text at every serialization point.
- Make the semantic service **origin-agnostic**. A verified candidate that satisfies the same factual/evidence contract can be enriched through the same path whether it came from Sonoma Tourism, a calendar/API adapter, hike catalog, direct organizer page or WP5 discovery. Do not create a richer semantic class for "collector events" and a thinner one for "discovered events."
- Reuse/adapt bounded batching, evidence references, supported-claim validation, partial-batch fallback, timeout/retry, token/cost/latency diagnostics and truthful unknown handling. Semantic descriptors must cite compatible evidence; promotional prose, inferred demographics and unsupported social-value claims are not facts.
- Preserve deterministic behavior under fixed provider fakes and ensure enrichment can be invoked incrementally on newly verified WP5 candidates without rerunning unrelated already-enriched inventory unless policy/version requires it.
- Test captured final provider payloads, unsupported/mismatched claims, conflicting evidence, no candidates, partial-batch failure, retry/fallback, and absent/divergent synthetic profiles yielding the **same shared input**. Live provider calls remain separately budgeted/approved and public-only.

**Exit evidence:** independently testable neutral AI #1 contract/prompt/service, validated evidence-linked semantic results across more than one candidate origin, incremental enrichment path for later verified discoveries, adverse-case coverage, usage/cost telemetry and proof of no private/personal fields in actual serialized requests.

### E1-WP5 — Adaptive regional discovery and coverage-gap research

**Mission:** use explicit regional coverage state to conduct enough complementary research to materially improve the shared universe without borrowing any individual's tastes and without treating discovery as a single cheap model call.

- Build discovery from **region + fixed weekend + existing public inventory + WP3 coverage assessment**. No user home, preference projection, personal directions, private schedule or private data. Discovery planning may use geography, day/time coverage, opportunity/source class, source failures and known unsearched areas; those dimensions are regional research state, not personalization.
- Treat AI #2 as a bounded **research subsystem**, not one mandatory request. It may perform multiple planning/search/model/tool calls and multiple discovery waves when coverage gaps justify them. Configure and enforce a **run-level research budget**: approved spend ceiling, search/tool-call bounds, wall-clock/retry limits and per-wave/overall telemetry. Do not optimize merely for minimum call count.
- Define explicit stop conditions. End discovery when the approved budget is exhausted, no material uncovered research directions remain, a wave produces no meaningful verified incremental coverage, provider/tool failure prevents safe continuation, or another configured diminishing-return threshold is met. No unbounded self-loop or hidden recursive research.
- Every discovery is initially a **lead**. Verify canonical public evidence for identity, region, weekend time, location and relevant claims before admitting it as a RegionalOpportunity. Preserve duplicate/rejected-lead reasons and alternate sources; search snippets or model assertions alone are not sufficient evidence.
- After verification, normalize/deduplicate/merge against the existing inventory and run the same WP4 semantic service for newly admitted candidates. Final universe candidates must have equivalent evidence/semantic standards regardless of whether WP3 or WP5 found them.
- Allow discovery to surface **candidate recurring sources** separately from event candidates. Record why a source may be useful and what it produced, but never auto-enable, auto-trust or bypass review to promote a discovered site into the WP3 registry.
- Reassess coverage after each bounded wave so later waves target remaining research gaps rather than repeatedly search already-saturated categories. Preserve separate status/diagnostics for planning, search/tool execution, verification, deduplication and semantic enrichment.
- Test that changing/omitting synthetic user profiles does not alter discovery plans or captured requests; zero legitimate discoveries remains valid. Include fixed synthetic recovery benchmarks with eligible opportunities intentionally absent from WP3, plus duplicate-only, invalid/unverified, empty, partial-failure, source-lead and budget-exhaustion cases. Never pad the universe to a target count.

**Exit evidence:** neutral adaptive discovery planner/executor with captured profile-independent requests, multiple-call/wave support under explicit budget/stop rules, evidence-verified unique additions and rejected/duplicate accounting, source-lead output separated from trusted registry state, quantified incremental coverage on fixed fixtures, and one combined WP3 → WP4 → WP5 path that produces a user-free evidence-backed universe candidate under success, empty and degraded conditions.

### E1-WP6 — Durable Regional Weekend Universe and provenance

**Mission:** make regional work a reusable, queryable asset rather than ephemeral packet text.

- Design the smallest forward Alembic migration from `0001_app_users`, justified by actual WP1–WP5 contracts. Represent region, weekend/logical run/version, opportunity/occurrence facts, source alternatives/evidence, enrichment, unknowns, timestamps, source coverage, discovery-wave/attempt status and audit-safe telemetry needed to explain how the universe was researched. Use explicit uniqueness and transactional invariants; don't pre-build E2 user-profile/packet schema.
- Define stable logical run identity and immutable/snapshot or equivalent last-good semantics; retries must not erase a successful universe when one provider fails. Preserve `unknown` versus known empty/false and observation/as-of versus scheduled event time.
- Implement explicit backend/worker read/write services and schema ownership via migrations; no client-authorized arbitrary user selector, frontend DB secret, startup `create_all()` or direct browser writes. Include necessary read-only internal consumption to support reuse tests.
- Run destructive tests **only** on disposable PostgreSQL: clean forward migration, downgrade/roundtrip where safe, ORM consistency, transaction rollback, two separate weekend keys, same-key replay, changed source provenance, partial failure, and readback without personal data.

**Exit evidence:** durable region/weekend universe with provenance preserved across replay, recoverable failure state, real PostgreSQL migration/integration test evidence, and E0 identity/auth schema regression green. Hosted migration remains a separate approved operation.

### E1-WP7 — Independent, idempotent weekly shared research worker

**Mission:** create one controlled shared run per region/weekend, safely reusable across consumers.

- Add a standalone regional worker/CLI distinct from `event_radar.main`, its audit mode and Telegram delivery. Accept explicit region/weekend/as-of/version, enabled source registry and approved run-level research budget. The worker executes WP3 factual collection/coverage → WP4 initial enrichment → WP5 bounded discovery/verification waves → WP4 enrichment of newly admitted discoveries → final merge → WP6 persistence, with audit-safe logs and actual model/search/tool usage, cost and latency diagnostics.
- Enforce idempotent same-key claiming/completion/replay and concurrent invocation behavior in PostgreSQL; demonstrate distinct-key isolation and recoverable partial/failure transitions without replacing a prior valid snapshot. No region run is implicitly triggered by a web request or FastAPI startup.
- Add a **separate** Product Shared Research GitHub Actions workflow under appropriately limited permissions/concurrency, independent from Product Foundation CI and the manual-only legacy `event-radar.yml`. Initial execution is manual, with synthetic/dry-run provider adapters for deterministic CI. Review a clearly defined weekly regional schedule and explicit owner approval before enabling any recurring paid external call. Do not re-add the old personal Thursday cron.
- Obtain explicit bounded authorization for one staging/public-only real regional research run, including its total spend ceiling and permitted search/model/tool classes, and before final scheduled-operation acceptance obtain authorization for activating the weekly shared schedule. The approved ceiling applies to the whole regional research run rather than an arbitrary one-call AI limit. Establish worker-specific secure credentials; never read the personal private-state repository or insert real credentials into PR CI.

**Exit evidence:** deterministic plus actual disposable-PostgreSQL replay/concurrency proof; independent and guarded worker; one approved, bounded real provider/staging run with stored/readable outcome; inspected workflow and approvals. **A disabled or hypothetical schedule is not evidence of active weekly operation.** If owner does not authorize live weekly activation, record this E1 exit requirement as pending and request a governing interpretation/decision—do not self-waive it.

### E1-WP8 — Reuse, quality, security and integrated regression proof

**Mission:** prove useful multi-consumer shared intelligence, not merely populated tables or a green workflow definition.

- One completed region/weekend universe is read by two materially different synthetic consumer profiles/test readers **without** another collection/AI call or mutation of the shared record. Profiles may inspect/filter later; no E2 per-user AI #3, persisted personal packets or paid account flow is required.
- Assess public/safe-fixture breadth and diversity, evidence validity, multi-source provenance, supported semantic richness, uncertainty, degraded-state truthfulness and loss from legacy scores/hike caps. Review WP3 coverage state plus WP5 incremental yield: verified unique additions, duplicate/rejected leads, research gaps remaining, discovery-wave cost/tool usage and any recurring-source leads. No universal quality claim from test count or raw event count; report concrete omissions and source coverage.
- Verify captured shared AI inputs and stored outputs are free of personal policy/private files/directions; protect source logs and artifacts, existing backend token authority and browser/public variables. Keep telemetry present or truthfully unknown.
- Extend Product Foundation CI with E1 typed/neutrality, negative payload, migration, provenance, idempotency, concurrence, reuse, API/worker import-isolation and security tests using disposable Postgres and controlled provider fakes. Inspect an **actual** PR/main CI run with all required DB tests executed rather than skipped. Review changes to former personal-output tests and their replacements: no weakening of E0 security/auth/persistence gates.
- Reconcile current staging deployment source against merged `main`; exercise hosted migration/provider only with explicit authorization, no automatic redeploy presumed from a branch push.

**Exit evidence:** two-consumer same-snapshot proof, meaningful source/semantic review, no-private-data payload/storage proof, actual integrated CI, one separately authorized real provider execution where required, and unchanged E0 public security/isolation fundamentals.

### E1-WP9 — Final E1 verification, closeout and successor routing

**Mission:** assess every governing E1 outcome as an independent PASS/PENDING/FAIL using actual repository/test/CI/DB/provider/workflow evidence, then return a factual phase decision to the E1 Execution Conversation and Project Manager.

- Reconcile the accepted repo baseline, cumulative diff, migration history, current and archived personal source, worker schedule/permissions, provider deployment provenance, neutral prompt payloads, persisted universe, reuse/idempotency tests and latest CI. Clearly distinguish synthetic vs real provider, local vs hosted DB, and configured vs active schedule.
- Confirm the archived original remains recoverable; no private data/secret leaks or unapproved destructive changes; current E0 API/auth/web/CI protections are intact. Do not demand old Telegram personal-packet parity or dispatch it for verification. Any intentional removal/refactor must have reviewed diff/evidence and suitable new shared-core coverage.
- Prepare **E1 Phase Handoff / Closeout** and **Draft Engineering Execution Roadmap — E2** only once the E1 Execution Conversation has accepted complete evidence. Project Manager reconciles/activates E2 separately; WP9 does not authorize E2, a merge, hosted migration or provider deployment by itself.

**Exit evidence:** seven-row phase gate with traceable proofs, cleared or explicitly escalated blockers, exact repo/CI/deployment state and accepted successor-routing package. No false claim that V1 is complete.

## 7. Final E1 acceptance matrix (all seven mandatory, unchanged)

| Governing Engineering Phase Map §10 outcome | Minimum acceptance proof |
| --- | --- |
| AI #1/shared semantic analysis is user-neutral | Reviewed origin-agnostic regional prompt/request/service, captured final provider serialization and supported-reference validation; no personal context/directions/projection; same request with absent/divergent synthetic profiles; verified candidates from WP3 and WP5 can use the same semantic contract. |
| AI #2/shared discovery is user-neutral | Coverage-driven region/weekend discovery plan with explicit run-level budget and stop rules; one or multiple evidence-validated search/model/tool calls permitted; captured plans/requests remain identical under absent/divergent profiles; verified/rejected/duplicate leads are distinguishable and zero discovered items remains valid. |
| A Regional Weekend Universe is persisted | Reviewed E1 migration, real PostgreSQL write/readback and stable region/weekend/version key, preserved last-good data and honest status. |
| Regional opportunities retain provenance and semantic enrichment | Inspectable occurrence/source alternatives, observation/as-of and supported enrichment/unknown fields survive storage and replay. |
| One regional research run can be reused for multiple user profiles | Two materially different synthetic consumer readers access one stored regional snapshot; no new collection/AI call or personal-policy contamination of shared state. |
| Weekly shared research job is idempotent for region/weekend | Separate shared workflow/worker, safe repeated and concurrent same-key live-DB execution, bounded approved real regional run and weekly activation evidence or explicit pending governance decision. |
| Personal preference policy not needed to generate shared universe | Shared worker executes with no personal user ID, `.env` legacy settings import, private context/directions, personal schedule, Telegram or AI #3; clean-process guards and payload checks pass. |

Additional mandatory protections: E0 API/auth/DB/web security and startup isolation remain verified; actual CI runs all required disposable PostgreSQL tests and scanner checks; private sources stay private; original pre-E0 branch persists; no excluded E2 functionality is misrepresented as E1. **Identical current personal-packet behavior is not an E1 acceptance gate under accepted Engineering Phase Map v1.1 (§2 decision record).** If any seven outcome lacks evidence, E1 stays open.

## 8. Verification, safety and operational practice

- **At each WP boundary:** record base/head SHAs, branch, changed files, test counts/skips and actual execution results. Review Codex report against source, diffs and CI logs before advancing. No auto-merge/deploy authority arises from package acceptance.
- **Testing:** locked Python/uv and Node installs; Ruff, mypy, pytest, ESLint, TypeScript, Vitest, build; current source/artifact security scans; fresh process guards; deterministic public/synthetic provider fixtures; E1 contract/negative-claim/provenance tests. Real disposable PostgreSQL via Compose/CI for migrations and concurrency. Do not turn off tests only because old personal behavior is deliberately refactored; document contract changes and add replacement coverage. Keep E0 security/auth/startup tests non-negotiable.
- **Data protection:** do not read, publish or copy the personal context/private state, old audit packets, tokens, user passwords, or provider-generated `.env`/`.vercel` contents to fixtures/PRs. Historical archive is code recovery, not consent to expose private assets. Scanner remains bounded; review actual diffs/artifacts.
- **Provider usage:** a proposed model/provider call is not permission. Present a bounded region/weekend/public-only research plan with total spend ceiling, permitted search/model/tool classes, retry/wall-clock bounds and stop conditions; owner approves secure config and a real run separately. WP5 may use multiple calls/waves inside that approved envelope—the control variable is total regional research budget and observable marginal value, not a fixed one-call rule. Errors/logs redact provider and DB secrets and do not record private contexts.
- **Hosted schema/deployment:** E1 migration first passes on disposable DB. Hosted Supabase forward migration requires reviewed plan, project/target confirmation and explicit approval; no destructive downgrade or accidental use of test fixture. Existing Render/Vercel hosting and Supabase Auth do not silently redeploy from the new E1 branch.
- **Scheduling:** Product Foundation CI can run on PR/main without paid research. Shared research workflow uses manual/dry run first. Activate automatic weekly shared execution only after approved cost/ownership/alerting decision; the old personal Thursday schedule stays disabled. Record a failed or unavailable provider run truthfully rather than spoof success.
- **Private legacy manual run:** not a routine regression check, not a required E1 gate, not a research worker. Manual use needs separate owner decision and private-state handling; optional cleanup/decommissioning of it is distinct from E1 shared-worker implementation.
- **Operational scope:** no irreversible data destruction, branch/archive rewrite, credential migration or paid infrastructure without authority. Preserve research provenance and recovery options during extraction.

## 9. Risks, stop conditions and E1 dependencies

| Risk | Signal and required response |
| --- | --- |
| Personal policy survives upstream | Shared collection, AI payload or DB record contains private User Context/projections/directions/personal ranking; halt neutral-path acceptance and correct at first entry. |
| Legacy settings contamination | Import of shared model reaches `config.settings` and reads legacy `.env`; fix extraction before claiming standalone core. |
| Over-refactor loses validated intelligence | Source parity/breadth, evidence alternatives, semantic richness, fallback or usage telemetry regress without reviewed explanation; retain tests/recover via archive and narrow the extraction. Do not require identical old personal packet outputs. |
| Over-filtering | Personal drive/hike scoring or old diagnostic event score removes regionally valid candidates; inspect loss and separate factual viability from personal desirability. |
| Hard-coded source orchestration | Core collection contains named-source branches or adding one conforming source requires editing central pipeline logic; move source-specific behavior behind the adapter/registry boundary. |
| Coverage theater | Source counts or a large event list are treated as proof of comprehensive regional research; preserve searched/failed/unsearched coverage state and concrete omissions. |
| Discovery runaway spend/loop | WP5 continues research without budget/stop enforcement or repeated waves add negligible verified coverage; stop the run, record diagnostics and tune the research budget/policy before live scheduling. |
| Unreviewed source promotion | A discovered website/source lead is automatically trusted or enabled in WP3; keep source leads separate until adapter/source review and tests. |
| Unsupported claims/lost provenance | Merged occurrences lose source references or AI produces unsupported time/price/location claims; fail validation/persistence gate. |
| Time/retry instability | Same weekend input produces new logical identity solely from wall clock, duplicate runs or destructive partial retry; fix key and transactions. |
| Scheduler/authorization confusion | Disabled legacy cron treated as shared schedule, workflow triggers unapproved provider spend, or a disabled new schedule is called live; block claim and seek owner decision. |
| Existing E0 security regression | API starts research, browser gets privileged DB/provider material, auth/user isolation fails or public private-state artifact appears; stop and repair. |
| Scope creep into E2 | User onboarding, Stripe, paid entitlement, per-user AI #3/packets/email added to E1; defer/escalate rather than re-scope silently. |
| Governance drift after acceptance | Proposed work silently reintroduces live personal-packet parity or weakens the accepted preservation safeguards; apply Phase Map v1.1 and return material divergence to PM/owner. |

## 10. Explicit exclusions — E2 or later / separate workstreams

E1 does **not** deliver persistent full per-user onboarding/User Context, Weekend Intent, user-specific AI #3 curation, individualized/persisted Weekend Packets, packet web view/history, Stripe/entitlement, real paid conversion, Resend notifications, self-service account/profile lifecycle, customer analytics, ChatGPT integration, restaurant/coffee database, outing chains, maps, national/multi-region launch, a dedicated queue infrastructure or a consumer-ready personalized site. Those capabilities belong to their governed later phases. A minimal **internal read-only shared-universe consumer** for the two-profile reuse proof is allowed and must not be marketed as a V1 packet.

The completed independent **DogHat App Starter extraction** is not an E1 work package or gate. Preserving the historical pre-E0 branch does not require developing a separate legacy product. Disabling the personal Thursday schedule has already occurred; E1 neither reverses that owner decision nor treats parity with that weekly output as success.

## 11. Accepted activation and control routing

The project owner accepted Engineering Phase Map v1.1 and originally promoted predecessor E1 roadmap v1.0 on 2026-10-03. The owner subsequently accepted this **E1 Engineering Execution Roadmap v1.1** refinement in the E1 Execution Conversation on 2026-10-03; it supersedes v1.0 for active execution while leaving the seven phase outcomes unchanged. The Project Manager owns the dedicated E1 Execution Conversation initializer and continuity with the Project Tracker. E1 begins at WP0; the execution conversation, not the predecessor E0 conversation, owns implementation.

At WP0, the E1 lead re-fetches current GitHub `main`, archive and workflow state, records the exact integrated starting SHA and isolated branch/worktree, inventories (without copying private contents) the owner's local status, verifies baseline tests and current staging deployment provenance, and proposes bounded provider/spend and hosted-data permissions. A planning snapshot is not proof of the actual live worktree or hosted deployment. The seven outcome gates in §7 govern E1 closeout; a configured but inactive weekly schedule cannot be claimed as operational evidence.

This acceptance authorizes coordination and bounded local E1 work through its execution conversation, beginning with WP0. **It does not automatically authorize** a merge, deployment, hosted migration, private-state access, real provider/model spend, paid recurring schedule, destructive operation or live personal-packet dispatch. Obtain distinct approval at the applicable work package. At E1 completion, produce the E1 Phase Handoff / Closeout and **draft** E2 roadmap for subsequent Project Manager/owner reconciliation; do not self-activate E2.
