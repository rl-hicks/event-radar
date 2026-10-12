# E1 WP8 — Shared reuse and regional quality evidence

## Scope and repository

Starting HEAD: `be3f6ccace4f94b3152de6d8b11ed0149881df29`.
Branch: `e1/shared-regional-intelligence`; PR #2 remains draft. Starting
worktree was clean and remote HEAD matched. Final commit and actual CI run are
reported in the execution handoff (the containing commit identifies this report).

This assignment adds only test-only readers, required CI evidence gates and this
report. No production profile, AI #3, endpoint, prompt, adapter, migration or
research strategy changed. WP8, WP7 and E1 are not accepted by this report.

## A. Deterministic two-consumer reuse proof

`tests/test_shared_consumer_reuse.py` persists the existing validated public
synthetic fixture once per isolated test case. A participation-oriented workshop
reader selects `community-workshop`; a long-route reader requiring at least
eight miles selects the 12-mile `synthetic-ridge-route`. These are candidate
filters, not personalized recommendations or promises of availability.

Both independently deserialize the same snapshot in new database-enforced
read-only transactions, repeat in reverse order, and check current-identity
readback. A fifth strict reader declines a partial snapshot without refreshing.
The selected records retain conflicting workshop prices, unknown availability,
unknown hike access, all provenance, and their original semantics. No claims are
silently improved. The success/partial labels exercise the storage quality
contract; the fixture itself deliberately contains imperfect source evidence.

First focused execution receipts (disposable records, not retained live evidence):

| Case | Snapshot ID | Reads | WP3 / WP4 / WP5 / worker / socket / HTTP calls |
| --- | --- | ---: | --- |
| Success | `de50a7f0-53a5-4e57-bcd1-353b8d77b0b1` | 5 | 0 / 0 / 0 / 0 / 0 / 0 |
| Partial | `06d64877-c735-4342-b62f-28793aa7379e` | 5 | 0 / 0 / 0 / 0 / 0 / 0 |

Both content hashes:
`b474aab93eb24839ea2464402c0cb4addbf553ce3bedef740fc160bf0e25c75b`.
IDs vary on subsequent executions. Tests compare every regional row before and
after reads, along with snapshot ID/hash, identity, complete validated content,
and neutral WP4/WP5 input serialization. Consumer labels, selection policy,
directions and scores cannot enter those typed contracts. Upstream/network
entrypoints are forbidden with counters; the disposable database also runs in
a network namespace with no external network. No paid adapter is invoked.

The two PostgreSQL cases are explicit required-pass entries in Product Foundation
CI, in addition to existing migration/auth/API/concurrency/idempotency tests and
the isolated evidence restart proof. Unexpected integration skips still fail CI.

## B. Real retained snapshot: method and integrity

Read only the public regional tables for:
- Run: `b04d0caa-7a8b-4fd4-aedf-1e93b9f13380`
- Snapshot: `9c53c4de-3ec4-4634-a8d2-04242c113d1d`
- Identity: Sonoma County, October 16–18, 2026,
  `e1-wp7-liveproof-2026-10-16-v1`
- As of: `2026-10-11T18:38:59.513327-07:00`
- Run and snapshot status: success
- Snapshot content hash:
  `1fcc03b832bd2fd2e9255ffe1c0f310fb0945017e528e72a0812a1aed6044e05`

The dedicated localhost evidence target and database/user identities were checked;
`SHOW transaction_read_only` returned `on`. Before/after counts were one run and
one snapshot. Repeated export was identical, WP6 content validation passed, and
canonical envelope SHA-256 checks passed. No writes, migrations or restarts of
the retained service occurred.

Fresh public inspection exports under ignored `output/development-evidence/`:
- `wp8-readonly-snapshot-bed7f3e6-1e97-4bd7-82af-4caaca890464.json`;
  SHA-256 `bca0f9f6af06cf33153c3831e0cc9157eb54ae4082b07793f0ae411b06b18ffb`
- `wp8-readonly-run-6bdc9787-5c1f-43ee-b4d6-ff26f8432948.json`;
  SHA-256 `974eb4a0ad40cfa470754efe3c73af6c7353ab496723920896dac7411de7f155`

The original export also passed its existing hash. New export envelopes explicitly
serialize legacy `planning_decisions: null`, so their envelope hash differs;
the stored universe content hash is unchanged. Counts below are computed from
the validated export: opportunities by kind/city, event occurrence starts
converted to America/Los_Angeles, evidence claims, descriptor kinds/confidence
and explicit uncertainty fields. No source URLs were fetched. This measures
retained evidence, not current public-page truth or recall against all events.

## Observed breadth, provenance and uncertainty

| Measure | Retained evidence |
| --- | --- |
| Inventory | 107 opportunities: 82 event occurrences, 25 catalog hikes |
| Event days, Pacific | Friday 21; Saturday 41; Sunday 20 |
| Source contributions before one duplicate merge | Tourism 9; Happening 74; catalog 25: 108 admitted inputs |
| Exclusions | One Happening outside-region record (83539); one duplicate occurrence (81923) |
| Source outcomes | All three collection sources succeeded; discovery returned 0 |
| Evidence | 108 records; 106 opportunities have one, one has two |
| Cross-source corroboration | No opportunity has evidence from different source IDs |
| Event location/time | All have city and start; 9 lack venue, 17 lack end time |
| Description | 9 event evidence records have only a title-based fallback summary |
| Price | 42 known numeric prices; 40 unknown; no structured conflicting prices |
| Availability/access | All 82 event availability states and all 25 hike access states unknown |
| Route facts | All 25 have distance/elevation/route text; 19 route uncertainty entries |
| Catalog freshness | Research cutoff August 7; run observation October 11 is not fresh trail verification |
| Hike range | 1.3–9.5 miles; no personal fitness/drive filtering in regional adapter |
| Semantics | 176 descriptors on 89 opportunities; 18 have empty descriptor arrays |
| Empty semantics | 9 Tourism events, 1 Happening event, 8 hikes |
| Descriptor kinds | Experience 82; setting 36; participation 30; logistics 19; interaction 9 |
| Descriptor confidence | High 154; moderate 18; low 4 |
| Structural support | All 176 resolve to local evidence bearing a description claim |
| Weather | No weather source/result in this run |

The 108 count is admitted input, not a raw fetched-row total; parser omissions
are not reconstructable from this snapshot. The outside-region exclusion is
additional to admitted inputs. Source statuses and a success label do not certify
completeness or independent verification.

Event geography: Petaluma 20, Santa Rosa 16, Sonoma 9, Healdsburg 8, Rohnert Park 7,
Glen Ellen 5, Sebastopol 3, Kenwood 3, Graton 2, Cotati 2, Forestville 2,
Guerneville 2, Windsor 1, Jenner 1, Rio Nido 1. Hikes: Santa Rosa 6, Jenner 6,
Windsor 3, Petaluma 2, Kenwood 2, Guerneville 2, and one each in Rohnert Park,
Sonoma, Bodega Bay and Glen Ellen. These are reported cities/nearest cities, not
precise spatial coverage. Petaluma and Santa Rosa account for 36/82 events.
No event in this snapshot is labeled Cloverdale or Bodega Bay; that does not prove
none occurs there.

Categories include music on 46 events, recreation on 8, kids-and-family on 6,
art on 5, and festival on 3 (overlapping labels). Thirty events have participation
descriptors, but these include browsing/listening/tasting as well as hands-on
activity. The remaining 52 cannot simply be labeled spectators. Live performance
is prominent; the retained contracts do not provide a reliable binary
participatory/spectator classification.

## Representative records and dispositions

| Evidence/example | Assessment and next disposition |
| --- | --- |
| Graton Friday flower show, `event-1a2e1a07050b66e07a58` | Strong retained description supports 09:00–16:00, venue, free admission and public activities. Saturday uses a differently ordered title, `event-2b48d277ae1bcd2e4c13`; separate date, not a duplicate to erase. Saturday price is unknown despite prose distinguishing free admission and paid food: retain unknown pending normalization review. |
| Slow Meditative Birding, `event-3c35bc84087fe887d0e9` | Four rich descriptors preserve activity, participation, setting and logistics, including the approximately 1.3-mile accessible outing. These support meaningful downstream filtering; attendance availability remains unverified. |
| Laguna Stewards, `event-e46c08273f1d7f111d3f`, and Trashlantis, `event-e5495354f992b6979e65` | Evidence-backed restoration work and a costumed bike rally demonstrate participatory options beyond spectator music. No inference of personal suitability is needed. |
| Tourism Beltane Ranch, `event-160ea4aaf108c0761d14` | Has dates/city/link, but no venue, real description, price or descriptors. All nine Tourism events show this pattern. Code-derived explanation: the listing parser constructs only title/time/city/URL; it does not extract detail-page prose. Review parser/detail acquisition separately, without pretending absent semantics is a model failure. |
| Andre Thierry, `event-901612c104231d99f09e` | Biography is retained but descriptors are empty and end time absent. Reasonable interpretation: the prose provides little concrete experience detail. The actual semantic model's omission rationale is not recorded. |
| T Barny Saturday/Sunday, `event-8395666024be8e9cb787` / `event-0d61406dfe9ae6604d23` | Listing window is 10:00–16:00 Pacific, while prose specifies demonstrations at 11:00 and 15:00. This may be open-studio hours versus sessions, not a timezone error. Preserve both; later source review should distinguish visit window from sub-events. Sunday merges source records 81742/81923 and retains both URLs; this is same-calendar provenance, not independent corroboration. |
| Americana, `event-5f98b4c5de2d0484ce07` | 08:00–22:30 Saturday (14.5 hours) is suspicious for a music listing. Prose has no corroborating clock times. AM/PM/source-metadata error is a hypothesis only; source-native payload/detail review is required before correction. |
| Haunted Wine Tour, three dates | Structured price is unknown although each description states guest/member prices. Four unknown-price records contain dollar amounts overall (these three plus Saturday Graton); not every amount is admission. Review bounded price extraction with fixtures rather than silently assigning a price. |
| Crane Creek Short Loop | No semantic descriptors; catalog-linked 1.4-mile route and estimated elevation remain usable facts with unknown access. Catalog links were not freshly verified. Some other hike descriptors merely restate route facts/categories; high descriptor confidence does not upgrade underlying estimated elevations. |

Seven exact case-folded title groups cover 17 events on different local dates:
Beltane, Haunted Wine Tour, Blind Scream, Guided Paddle, T Barny, Armstrong walks,
and Art & Music Gallery. No same-title same-day pair remains under this check.
This is not an exhaustive fuzzy duplicate audit. The two differently titled
Graton occurrences are also separate dates. Do not collapse recurring occurrences
or merge differing times by title alone; current deduplication requires matching
normalized title/start/city and compatible venue/end.

Structural citation validation found no dangling/unsupported-reference
descriptors; it does not prove every semantic inference. Representative prose
review found useful supported examples, but not an exhaustive entailment audit.
The interaction field sometimes describes performers (for example the Soph and
Jake duo), so it is not uniformly a measure of audience social interaction.
Thin Tourism input, uneven semantic richness and uncertain logistics limit
consumer utility even though candidate selection is plausible.

## Coverage and WP5 interpretation — observed vs inferred

Observed: `planner_stopped`, one accepted planning operation, zero research,
verification or web-search calls, zero waves/additions, and no source leads.
Historical accepted plan/gaps/tasks/rationale are unavailable. The new decision
capture applies only to future runs. No conclusion that stopping was justified
or that complementary research was unnecessary follows.

Code-derived: both calendar adapters register as `regional_calendar`; hikes as
`outdoor_catalog`. The registry has no direct-organizer, community-calendar,
ticketing or weather adapter. `unsearched_source_classes` is derived from
registered but unattempted sources, not all possible source classes. Thus an
empty list can coexist with substantial unregistered coverage gaps. The original
WP3 class assessment was not stored, so this is a code explanation, not recovered
historical planner input.

Reasonable coverage concerns: sparse represented geography outside the dominant
cities; Friday/Sunday lighter than Saturday; heavy music/calendar dependence;
no dedicated library, municipal recreation, volunteer, workshop or organizer
source coverage. Some such activities appear incidentally (Laguna Stewards), so
absence of dedicated sources does not mean zero representation. Specific missed
real events and the county-wide recall denominator remain unknown: no fresh
search was authorized. The 35-entry tracked hike catalog admits its 25 Sonoma
routes without the legacy personal hike cap; it still is a bounded catalog,
not all outdoor opportunities.

Existing deterministic tests cover source-class/time gaps, continued research,
verified/rejected/duplicate candidates, multi-wave budgets, no incremental yield,
failure, and stopped/no-task plans including stops with gaps. They prove
mechanics and safe stopping, not adequacy of a real planner's decision.

Important untested policy case: all registered sources succeed and the inventory
looks large, but meaningful unregistered classes or regional areas remain
uncovered; the planner may stop without the test establishing whether its
rationale is adequate. Another is distinguishing ordinary price/availability
unknowns from a material inventory coverage gap. See
[evidence-policy review](e1-wp5-planner-decision-evidence.md).
A separately reviewed prompt clarification could require explaining residual
material gaps and why searching is or is not warranted. First evaluate balanced
offline cases permitting justified stops. No minimum search count, prompt change
or new real research is implemented here.

## Neutrality, integration and remaining gates

Shared contracts persist regional facts/provenance and descriptive semantics,
not accounts, directions, preferences or scores. Test-only contexts are never
passed to collection/providers/persistence. Existing captured fake-provider
serialization, forbidden private-field tests, fresh-process import guards,
E0 token-authority/auth/API tests and security scans remain required. Public
performer names or public event contact prose are not consumer profiles; structural
validation/scanning is not a universal personal-data detector.

The retained schema separates regional tables from E0 identity tables. The
inspection selected only public regional evidence; no user-account tables,
private-state files or legacy Settings were accessed. Only the dedicated ignored
local database credential was read for guarded connection construction; it was
never printed or exported. Hosted resources were not contacted.

The seven outcomes remain distinct: neutral WP4/WP5 and persisted provenance have
synthetic contract/serialization and real snapshot evidence; multi-consumer reuse
now has distinct-reader PostgreSQL proof; idempotency has existing deterministic
database tests; personal-policy independence has existing import/worker guards.
Real WP5 research/verification, adequacy of planner stopping and comprehensive
regional coverage remain unverified. Weekly activation and current staging
deployment-source reconciliation remain pending separate operational review.
This branch push is not deployment evidence.

Local verification: **5 focused reuse tests passed; 702 full Python tests passed,
with one expected hosted-Supabase skip; 39 web tests passed**. The isolated
restart/readback/export proof, Ruff, mypy, source/build security scans, frontend
lint/types/build, CLI help and Alembic metadata checks passed. Final HEAD and exact
Product Foundation CI run are in the execution handoff. No gate was removed or weakened. Recommended next engineering work: fixture-based review of
Tourism detail loss, price normalization and the two timing ambiguities, followed
by a separately reviewed planner-policy evaluation. Preserve the real snapshot;
do not retroactively repair it or manufacture historical plan evidence.
