# E2 first-user vertical slice integration note (design only)

E2 implementation, accounts, hosted migrations, AI #3 spending and delivery need
separate phase authorization after required E1 acceptance/handoff. This note does
not activate an E2 roadmap or waive its payment/onboarding requirements.

The first real user should be the owner acting as an ordinary account. The system
must use one generalized path:

**Shared regional snapshot → authenticated User Context → AI #3 curation →
persisted Weekend Packet → authenticated retrieval → email notification.**

## Minimum contracts to implement after authorization

1. **Identity and context.** Reuse E0's authenticated account/token authority.
   Derive the account ID server-side, not from a caller-controlled owner selector.
   Store validated, versioned User Context and weekend-specific intent under that
   account's ownership. Preserve immutable revision IDs/content hashes for later
   packet provenance. Do not import historical private-state files.

2. **Shared input selection.** Resolve region, Friday and approved research policy
   through the WP6 regional read contract. Pin snapshot ID, content hash, research
   as_of and quality. Define an explicit freshness/partial-data policy: missing
   research produces a pending/unavailable state; partial research is labeled.
   Never silently substitute another weekend or trigger collection/semantics/
   discovery from packet reads, API startup or a user request. Zero, one or many
   accounts can consume the same snapshot without changing it.

3. **AI #3 boundary.** Personalization starts only after the shared snapshot and
   the authenticated user's context revisions have been read. Its separate
   request contains those inputs, and its separate budget, prompt/curation-policy
   version and model are recorded. Validate output references against shared
   opportunity/evidence IDs and preserve factual uncertainty. Preferences,
   rankings, directions and private explanations never enter the shared research
   key, snapshot, WP4 or WP5 payloads. Do not treat a generic activity list as
   evidence of useful personalized curation.

4. **Packet provenance and isolation.** Proposed packet/job identity includes
   account, weekend, context/intent revision, shared snapshot and curation policy.
   Store the validated result with those references/hashes, curation run ID,
   model/policy version, timestamps and usage. Each user has an independent
   result; authorization and database access rules prevent cross-account reads,
   edits or enumeration. Enforce ownership on every packet/context request with
   the existing E0 authority model. These schemas/endpoints are not implemented
   by the scheduling assignment.

5. **Delivery eligibility.** A successfully persisted, validated packet becomes
   eligible for an idempotent notification/outbox operation. Use the Product
   Definition's initial email direction (Resend), verified recipient and normal
   consent/access rules. Link to authenticated packet retrieval; avoid private
   context in email/logs. Key notification deduplication by packet and channel.
   Retrying email must not rerun curation or regional research. Legacy private
   Telegram is not the initial product delivery path.

6. **First-user provisioning.** Initially, an authorized operator may provision
   the owner's ordinary account/context through the same general contracts that
   onboarding will later use. If a development/beta entitlement is approved,
   implement a general auditable mechanism with scope, issuer, reason and expiry.
   No owner-ID tests, privileged preference overrides, special packet generator
   or implicit owner bypass. Later onboarding and Stripe must feed these same
   contracts. A beta entitlement does not remove governing E2 payment acceptance
   obligations.

## First useful proof and safeguards

After E2 authorization, the minimum useful milestone is one real ordinary account,
one persisted context, one pinned shared universe, one real AI #3 curation, one
persisted personalized packet and normal email delivery/retrieval. A minimal
protected context/packet interface is sufficient; elaborate dashboards are not a
prerequisite. Obtain explicit authority for real AI #3 and email operations.

Before claiming the generalized design works, use two materially different
synthetic contexts to prove independent packet outputs, identical shared inputs,
zero upstream research calls and cross-account denial. Also test context revision
changes, partial/missing snapshots, duplicate curation triggers, malformed AI #3
references, notification retries, entitlement checks and secret/log boundaries.
Keep E0 API/auth, migrations, frontend, import isolation and security CI intact.

The existing WP8 proof establishes shared-input reuse and differing deterministic
selection, not real personalization, persisted packets or delivery. The October
16 real regional run established collection/semantic persistence and a valid
planner stop, not real adaptive research/verification. Future E2 claims must
distinguish those boundaries and must not invent the historical planner rationale.
