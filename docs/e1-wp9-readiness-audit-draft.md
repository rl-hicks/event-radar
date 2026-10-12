# E1 WP9 readiness audit — draft, not acceptance

Audit date: 2026-10-11 Pacific (2026-10-12 UTC).
Authority: accepted [E1 Roadmap v1.1](governance/06_Event_Radar_Engineering_Execution_Roadmap_E1_v1.1.md),
especially WP5–WP9 and §7; [Phase Map v1.1 §10](governance/04_Event_Radar_Engineering_Phase_Map_v1.1.md).
No requirement is waived or amended.

**Preliminary finding: six engineering-outcome PASS assessments; one PENDING
weekly-operation gate; no demonstrated FAIL of the seven stated outcomes.
E1 is not ready for final acceptance.** PASS is scoped to the named outcome and
evidence below, not live operational readiness, regional completeness, WP
acceptance, or permission to activate E2. Additional mandatory reconciliation and
owner decisions remain open.

## 1. Exact repository and review state

- Repository: `rl-hicks/event-radar`; worktree:
  `/home/robot/dev/event-radar-e1-wp7`.
- Audited branch: `e1/shared-regional-intelligence`.
- Audited starting HEAD and matching remote:
  `2418c3dc8775b608aa608abc72a8376b717373a1`; working tree clean.
- Current remote main:
  `3a0fb5e9ff414ecd14d923d23551e07977d287a1`.
- Archive ref `archive/personal-pre-e0-2026-10-03`:
  `7ffb52bdb4ef62df139000957df15d135d32de50`, still advertised by remote
  and locally resolvable as a commit. No archive rewrite or private-state access.
- [PR #2](https://github.com/rl-hicks/event-radar/pull/2): OPEN, draft, base main,
  head matching the audited commit. Title:
  “E1 shared regional intelligence — WP1/WP2/WP3 foundation”.
  Body still says WP3 is in progress; stale relative to current implementation.
  This audit does not update PR metadata.
- Only this audit document is authorized for commit/push. Its containing commit
  and final PR/CI state are reported in the handoff; matrix evidence is pinned to
  the audited implementation SHA above.

Relevant historical evidence: WP1 contract and WP2 shared-core notes;
WP5 correction and planning-decision notes; WP7 worker/evidence runbooks; WP8
reuse/quality report. Earlier notes contain historical pending statuses and test
counts. They are not substituted for current CI or readback evidence. The
`e1-core-coexistence-technical-note.md` is historical E0-era inspection, not
proof that today's shared implementation is absent. There is no standalone WP0
acceptance record among these E1 notes; activation history is traced through the
accepted roadmap and commit history, not invented.

## 2. Seven mandatory outcomes, independently assessed

| Governing outcome | Status | Exact supporting evidence | Limits / remaining requirement |
| --- | --- | --- | --- |
| 1. AI #1/shared semantic analysis is user-neutral | **PASS** | `models/regional.py::RegionalAnalysisRequest`, `models/regional_semantics.py`, `shared/semantic_analysis.py`, `services/regional_semantic_analysis.py`, `prompts/regional_semantic_analysis.md`. Tests: `test_regional_semantic_analysis.py::test_semantic_input_is_identical_for_divergent_consumers`, `test_descriptor_requires_description_evidence_from_same_opportunity`; `test_regional_semantic_provider.py::test_provider_sends_only_neutral_regional_request_and_structured_schema`. Combined fake worker tests enrich WP3 and verified WP5 candidates. Real run R below processed all 107 inputs with 11 semantic calls. | PASS for neutral inputs/contract and evidence-supported reference validation. Empty descriptors are permitted; not a claim that every inference is independently true or equally useful. |
| 2. AI #2/shared adaptive discovery is user-neutral | **PASS** | `models/regional_discovery.py::DiscoveryContext/DiscoveryPlan`; `shared/discovery.py::run_adaptive_discovery`; `services/adaptive_regional_discovery.py`; three `prompts/regional_discovery_*.md`. `test_adaptive_regional_discovery_provider.py::test_planner_is_neutral_structured_and_does_not_use_web_search`, `test_research_and_verification_use_separate_bounded_web_calls`; `test_shared_consumer_reuse.py` compares neutral serialized context under distinct consumers. Adaptive-loop, failure and planning-evidence suites cover unique additions/rejections/duplicates, multi-wave budgets and valid stops. R records one accepted planning call. | Real research, independent verification and source-lead discovery **not demonstrated**. PASS is neutrality and deterministic subsystem evidence, not a live end-to-end discovery pass. Governance permits zero discoveries; this audit does not invent a minimum search requirement. Lead must explicitly disposition this verification gap before claiming full WP5 live proof. |
| 3. Regional Weekend Universe is persisted | **PASS** | `alembic/versions/0002_regional_universes.py`; `db/models.py`; `db/regional.py` transactional identity/snapshot/run services. `test_regional_persistence_integration.py` proves replay, changed provenance, rollback and last-good behavior. CI C includes actual disposable PostgreSQL. R has validated retained snapshot S and both integrity-checked exports. | Local retained PostgreSQL and disposable CI evidence, not hosted E1 migration/deployment. Host failure/off-machine recovery is not established by a named volume alone. |
| 4. Opportunities retain provenance and semantic enrichment | **PASS** | `models/regional.py` evidence/occurrence/descriptor contracts; `shared/deduplication.py`; WP6 JSON serialization/readback and `db/evidence.py` exporters. R/S contain 108 evidence records and 176 descriptors; the T Barny merged occurrence retains both source records. `test_development_evidence.py`, `test_discovery_planning_evidence.py` and persistence tests verify readback, unknowns and export integrity. | Structural reference support is not comprehensive semantic entailment or independent corroboration. 18 opportunities have empty descriptors. Historical planner rationale remains absent; future decision capture cannot reconstruct it. Quality disposition remains required. |
| 5. One regional run can serve multiple profiles | **PASS** | `test_shared_consumer_reuse.py::test_two_distinct_consumers_reuse_one_snapshot[success/partial]`, explicitly required in CI C. Workshop versus long-route readers, repeated independent read-only sessions, equal snapshot ID/hash/facts, all regional rows unchanged, zero upstream/network counters; strict reader declines partial data. Exact synthetic IDs/hashes are in WP8 report. | Test-only synthetic consumers and disposable records, not production profiles or E2 curation. No claim of personalized suitability. |
| 6. Weekly shared research job is idempotent for region/weekend | **PENDING** | Engineering idempotency passes: `shared/worker.py::run_regional_worker`, `db/regional_claim.py::claim_regional_research`, session advisory locks; `test_shared_worker_integration.py::test_concurrent_same_key_and_distinct_key_isolation`, `test_full_worker_persistence_replay_and_read_only_reuse`, `test_partial_and_failed_refresh_preserve_last_good`, `test_process_death_releases_claim_and_recovers_committed_attempt`, `test_lost_database_session_cannot_finalize_without_a_new_claim`. R establishes one authorized live attempt. Separate `product-shared-research.yml` exists. | Workflow is manual-only, synthetic-only, disposable DB; no cron/live weekly operation. Roadmap WP7 explicitly requires activation approval/evidence or an explicit pending governing decision. No self-waiver. Whole-run spend/ownership/target/alerting decisions also precede recurring operation. |
| 7. Personal preference policy is unnecessary to generate the shared universe | **PASS** | `shared_worker.py`, `shared_runtime.py`, explicit neutral contracts/DI; `test_shared_core_isolation.py`, `test_regional_isolation.py`, `test_shared_worker_integration.py::test_worker_cli_fresh_process_no_personal_modules_or_network`, `test_shared_runtime.py`, `test_shared_consumer_reuse.py::test_consumers_cannot_enter_shared_contracts`. R used the guarded standalone worker. No Telegram/AI #3/profile input in this path. | Personal legacy code remains archived/present; that does not make it a shared dependency. Provider credentials and a DB connection are operational inputs, not personal preference policy. No private-state audit or universal prose PII guarantee is claimed. |

Code paths above are under `src/event_radar/` unless otherwise specified; test
paths are under `tests/`. C ran all cited test modules at the audited SHA.

## 3. Exact evidence anchors and verification scope

**CI C:** [Product Foundation CI 38195096145](https://github.com/rl-hicks/event-radar/actions/runs/38195096145),
head `2418c3dc8775b608aa608abc72a8376b717373a1`, SUCCESS.
Inspected actual job logs: **702 Python passed, one expected opt-in hosted
Supabase skip; 39 web passed**. Both reuse parameter cases, API/auth PostgreSQL,
migration, worker replay/concurrency/last-good/process-death cases printed
required PASS evidence. Isolated restart/readback/export test passed. Ruff,
mypy, source/build security, frontend lint/types/build and metadata/help gates
passed. Existing Starlette deprecation and SQLAlchemy cyclic-FK metadata warnings
are not new failures. No full suite rerun was needed for this document-only audit;
post-push CI is reported separately.

**Real run R:** `b04d0caa-7a8b-4fd4-aedf-1e93b9f13380`.
**Snapshot S:** `9c53c4de-3ec4-4634-a8d2-04242c113d1d`.
Region `sonoma-county-ca`, Friday `2026-10-16`,
policy `e1-wp7-liveproof-2026-10-16-v1`;
as_of `2026-10-11T18:38:59.513327-07:00`.
Started `2026-10-12T01:39:00.058668+00:00`;
finished `2026-10-12T01:41:06.262299+00:00`.
Status success, failure code null; snapshot quality success.
Snapshot hash:
`1fcc03b832bd2fd2e9255ffe1c0f310fb0945017e528e72a0812a1aed6044e05`.

This audit independently recalculated canonical SHA-256 for the existing
WP8 public exports and validated the complete 107-opportunity universe:
- `output/development-evidence/wp8-readonly-snapshot-bed7f3e6-1e97-4bd7-82af-4caaca890464.json`:
  `bca0f9f6af06cf33153c3831e0cc9157eb54ae4082b07793f0ae411b06b18ffb`.
- `output/development-evidence/wp8-readonly-run-6bdc9787-5c1f-43ee-b4d6-ff26f8432948.json`:
  `974eb4a0ad40cfa470754efe3c73af6c7353ab496723920896dac7411de7f155`.

R ran at `c7c85c41895f7c251717460ee3e9e89967dd9c41`, before planning-decision
capture and WP8 tests. It proves real collection, semantics, planning and
persistence. WP5 stopped with `planner_stopped`: no research/verification/search
calls. Known model-token subtotal was $0.0229426; this is not an invoice or proof
of a general $1 hard cap. The earlier 106-opportunity October 9 database was lost;
reported activity/failure there is not independently inspectable live proof.
Neither historical plan reconstruction nor another research attempt is permitted.

WP8 directly checked the retained local database read-only: one run, one snapshot,
unchanged content/counts. This audit rechecked exported evidence, **not current
database health or provider state**, and read no credential files. Retained service:
`event-radar-development-evidence`, DB/user `event_radar_evidence`,
127.0.0.1:55433, volume `event-radar-development-evidence-data`.
Disposable tests use separate DB/user `event_radar_test`, 127.0.0.1:55432,
URL/live-identity guards before destructive migration. Restart proof creates its
own disposable container/volume. Retained storage has no test tmpfs lifecycle.

Active migration lineage was verified via metadata-only Alembic commands:
`0001_app_users -> 0002_regional_universes (head)`. Hosted revision is unknown
in this audit; do not infer it from local migrations or older E0 documents.

## 4. E0 protection, schedule and staging reconciliation

Compared with current main, no changes appear under API/auth production code,
web, `render.yaml` or `web/vercel.json`. Reviewed E0 test adjustments add E1
tables/revision expectations; the app_users shape, destructive DB guards,
API import/lifespan isolation and authentication assertions remain. CI C retains
token-authority, signed-token/local-DB, API identity/concurrency and frontend
security tests. The sole hosted Supabase skip is explicit, not hosted success.

Both workflows remain manual-only. Legacy `event-radar.yml` contains obsolete
schedule-handling code but no active schedule trigger. Product shared research
uses contents:read, same-key concurrency, no live provider secrets, and only
synthetic runs against disposable PostgreSQL. A workflow file on an unmerged
feature branch is not a deployed weekly service.

Deployment evidence:
- `render.yaml` names `event-radar-api-staging`, targets
  `codex/e0-wp6-deployment-foundation`, has auto-deploy off, and runs API only.
- `web/vercel.json` defines Vite build/SPA routing, not a deployed SHA or branch.
- `docs/deployment.md` is historical E0 staging guidance, still references
  `0001_app_users` and that E0 deployment branch; it is not current E1 provenance.
- Read-only GitHub deployments API returned an empty array. This does **not**
  establish that Render/Vercel have no deployments; integrations may not publish
  GitHub deployment records.
- Current provider deployment IDs/SHAs, configured branches and hosted migration
  state were not inspected. No hosted/private credentials or dashboards accessed.
  WP8's required current staging-source reconciliation remains **PENDING**.
  Obtain redacted provider metadata and compare SHAs with verified main; do not
  redeploy simply to make the evidence match.

## 5. Outstanding issues, ranked and classified

| Priority | Issue | Classification | Required disposition |
| --- | --- | --- | --- |
| 1 | Gate 6 lacks active weekly operation | **Acceptance blocker** and **operational decision** | Owner authorizes a reviewed recurring plan and evidence is obtained, or competent governance explicitly resolves the requirement. While no such decision exists, keep PENDING; an owner refusal alone does not convert it to PASS. |
| 2 | Current staging sources unreconciled | **Acceptance blocker** to WP8/WP9 evidence completeness | Read-only redacted Render/Vercel deployment IDs/SHAs and branch/config evidence; compare with main, document differences and owner disposition. No automatic redeploy or migration. |
| 3 | Whole-run recurring spending controls/ownership unestablished | **Operational decision**, prerequisite to resolving gate 6 | Specify total envelope including WP4, WP5 and tool fees, failure/alerting/stop policy, durable target/backup and credentials. Current discovery cost threshold is post-response, model-token-only; semantic correction calls and tool fees are outside that threshold. SDK retries are disabled but this is not a whole-run monetary cap. Resolve roadmap's whole-run ceiling language explicitly before recurring approval. |
| 4 | Real WP5 research/verification and historical stop justification unavailable | **Operational/acceptance-evidence decision**, not an invented positive-yield requirement | Lead must distinguish neutrality PASS from unproven real discovery behavior. Decide whether deterministic proof plus permitted live stop satisfies the reviewed evidence scope or separately authorize a bounded future verification exercise. Never force search or fabricate the historical plan. |
| 5 | WP8 regional-quality disposition outstanding | **Acceptance review blocker**; individual improvements may be deferred | Lead reviews concrete limits below for meaningful reusable intelligence. Record accepted limitations versus required corrections; tests/counts cannot make that decision. |
| 6 | Stale PR title/body and seven tracked Windows artifacts | **Deferred housekeeping** for runtime; pre-merge review hygiene | In a separately authorized correction, update PR scope and remove only `:Zone.Identifier` sidecars, preserving governing Markdown. This audit changes neither. |
| 7 | Historical notes have stale readiness/deployment statements | **Deferred documentation reconciliation** | Preserve historical context; cross-link current evidence before final closeout, without rewriting governing outcomes or prior records. |

The seven tracked sidecars are in `docs/governance/`, appended to:
`01_Event_Radar_Project_Definition_v1.0.md`,
`02_Event_Radar_Product_Definition_v1.0.md`,
`03_Event_Radar_Product_Phase_Roadmap_v1.0.md`,
`04_Event_Radar_Engineering_Phase_Map_v1.0.md`,
`04_Event_Radar_Engineering_Phase_Map_v1.1.md`,
`06_Event_Radar_Engineering_Execution_Roadmap_E1_v1.1.md`, and
`Project-Conversation-Architecture-and-Development-Operating-Model-v1.0.md`.
They are unwanted tracked artifacts, not governing content. Their existence does
not invalidate runtime tests; no security exposure conclusion is inferred from
the filename alone.

## 6. WP8 quality disposition and safe deferrals

[WP8 report](e1-wp8-reuse-quality-evidence.md) establishes useful candidate
selection and honest uncertainty, not county-wide completeness:
82 events/25 hikes; Friday/Saturday/Sunday 21/41/20; 176 descriptors across 89
opportunities; 18 empty semantic arrays; 40 unknown prices; all event availability
and hike access unknown. Nine Tourism events lack substantive descriptions and
venues. Only one opportunity has two evidence records, both from one calendar.
No independent cross-source corroboration is established.

**Material review risks:** limited source classes and uneven geography;
`unsearched_source_classes` only reflects registered-but-unattempted sources,
so it can miss unregistered coverage; planner stop rationale unavailable; weak
Tourism detail and semantic richness. These warrant explicit quality acceptance
disposition, not a universal count threshold or mandatory minimum discoveries.

**Bounded defects/suspicions for later fixture-based work:** T Barny listing
window versus demonstration times may represent different time concepts;
Americana's 08:00–22:30 listing is suspicious but not a proven parser bug.
Seven repeated-title groups are separate dates, not permission to merge.
Unknown structured prices can coexist with amounts in prose that may describe
food, member rates or admission. Never silently correct preserved evidence.

Source expansion, richer descriptions, improved price normalization,
sub-event modeling, fuzzy duplicate review, wider outdoor coverage and prompt
clarification can be deferred **if** the lead accepts current utility/limits.
No governance requires complete county coverage, every descriptor nonempty, or
positive WP5 yield. Off-machine backup and robust recurring monitoring become
operational prerequisites if the owner chooses unattended retention/service;
a local named volume alone must not be represented as disaster recovery.
E2 profiles/AI #3/subscriptions/endpoints remain excluded, not WP9 blockers.

## 7. Minimum safe sequence toward acceptance

1. Execution lead reviews this preliminary matrix, WP8 quality and the real versus
   synthetic WP5 distinction; record unresolved interpretations without waiver.
2. Obtain read-only provider deployment provenance; reconcile against main and
   resolve staging differences/documentation claims without unapproved changes.
3. Separately correct PR metadata/Windows sidecars and any specifically required
   quality regression issues. Run relevant CI; preserve original evidence.
4. Resolve whole-run spending, durable execution target, retention, operational
   owner, alerting and weekly timing (explicit Pacific Friday key) in a reviewed
   plan. Current manual synthetic workflow is insufficient for live activation.
5. If additional real WP5 proof is required by the lead, request a new bounded
   authorization with future planning-decision capture. No retry/refresh or
   diagnostic call follows automatically from this audit.
6. Obtain explicit recurring activation approval and implementation/execution
   evidence, or an authoritative governing resolution. Until then gate 6 remains
   PENDING. Approval to research once is not approval to schedule.
7. Re-audit all seven outcomes, actual current CI, quality/security/staging and
   approvals. Only after execution-lead acceptance prepare final E1 closeout and
   draft E2 routing; neither is produced or activated here.

No paid calls, collection, hosted operations, schedule activation, deployment,
merge, evidence mutation or private credential access occurred during this audit.
Only this draft document is committed.
