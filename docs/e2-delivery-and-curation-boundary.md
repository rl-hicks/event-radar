# Future E2 delivery and AI #3 boundary (design only)

This note incorporates the owner's new Telegram development preference. It
clarifies the earlier E1 integration note for the authorized E2 overlap; email
through Resend remains mandatory for V1. No sender, bot secret, binding, packet
table or curation execution is implemented here.

## One canonical packet, multiple adapters

Future delivery request contract: packet ID + authenticated owner + verified
recipient-binding ID/version + channel + idempotency key. Supported directions
are Telegram and email. The dispatcher must load the persisted packet and binding,
verify ownership/consent/current binding status, and hand an adapter a bounded
rendering/link to that same packet. Adapters do not curate, collect research or
own a second packet implementation. Email and Telegram both refer to the same
canonical packet and authenticated Event Radar web view.

A future delivery record/outbox tracks pending/sent/failed outcomes and bounded
failure codes separately from packet quality. Eligibility follows successful
validated persistence, applicable entitlement and explicit channel consent.
Use packet + channel + binding revision for deduplication. Retry delivery only,
never regenerate research or AI #3. Ambiguous send outcomes need reconciliation;
do not promise exactly-once external delivery without provider evidence.

Telegram can be the first working development adapter after separate approval.
Use the existing bot only after reviewing product/legacy ownership and secure
credential configuration; do not read historical credentials. No owner/chat-ID
constant or privileged path is permitted.

A future binding must prove both authenticated account authority and destination
control. Proposed private-chat flow: signed-in backend creates a short-lived,
single-use high-entropy challenge bound to that account; the user presents it
through the bot's authenticated update channel. Backend validates update
authenticity and challenge, consumes it atomically, and records the proven chat
destination. Do not accept a chat ID from an ordinary API body as proof. Restrict
the initial design to private chats. Prevent challenge leakage/replay and
cross-account rebinding; require new proof for reassignment, revoke the old
binding, and recheck revocation immediately before sends. Group-chat authorization
is a later explicit scope decision.

Email uses a verified address, explicit delivery preference and Resend adapter.
Address changes require verification and binding revision replacement. The owner
chooses Telegram through the same preference/binding contract available to every
account. No live sender or real preference/binding is created in this assignment.

## Next AI #3 and persisted Weekend Packet package

Inputs must pin:
- one validated WP6 snapshot ID/hash/quality and regional weekend;
- one authenticated user's immutable context revision ID/hash/schema version;
- an explicit personalization policy, prompt and model version;
- future Weekend Intent only through a separately versioned, applicable contract.

Select input snapshots by region/weekend/policy and handle missing/stale/partial
research explicitly; consumer reads never trigger shared research. Invoke AI #3
only downstream with its own budget and authorization. Private context must not
flow back into WP3, WP4, WP5, regional identities or evidence exports.

Output should contain a finite high-signal set of existing opportunity IDs,
evidence-linked reasons, tradeoffs/friction and factual unknowns. No quota
padding or invented events, attributes, prices, times or personal preferences.
Validate every referenced opportunity/evidence ID against the pinned universe.

Preserve distinctions between natural interaction, co-presence, participation,
spectatorship and structured/repeated interaction. A crowd or alcohol category
does not establish social value. Evaluate solo practicality, travel/commitment
cost and experience value relative to explicitly supplied context; an exceptional
experience may justify higher friction. Missing preferences remain unknown.

Proposed packet persistence records account, weekend, snapshot/context references,
policy/model versions, curation run ID, validated recommendations, quality,
timestamps and known/unknown usage. Separate per-user job idempotency and ownership
checks protect cross-user results. Packet readiness then creates notification
eligibility; delivery does not determine or overwrite the packet's canonical facts.

The next proof should use deterministic differing users and then, only when
separately authorized, one real ordinary account, context, shared snapshot, real
AI #3 result, persisted packet, authenticated retrieval and approved delivery.
Manual provisioning can precede onboarding through general contracts. No owner
exception, Stripe bypass, paid-beta acceptance claim or E1 acceptance waiver follows.
