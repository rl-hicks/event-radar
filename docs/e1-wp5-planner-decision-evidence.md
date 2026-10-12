# E1 WP5 planner decision evidence

## Contract and retention

New discovery summaries contain `planning_decisions`: an ordered array of
`{wave, plan}`. The plan is the existing validated `DiscoveryPlan`, including
`should_continue`, rationale, gaps (IDs, dimension, description, rationale,
priority), and proposed tasks (IDs, gap references, search goal, optional area,
date and opportunity type). These are proposed tasks, not proof of execution:
use discovery operations and wave records for attempted research and outcomes.

Each plan allows at most 32 gaps and 32 tasks; each task references at most 32
gaps. Explanations/search goals are limited to 2,048 characters and area/type
labels to 128. Existing IDs remain limited to 120 characters. Up to 20 planning
decisions are retained, with unique ascending wave numbers within the configured
budget. Oversized/invalid plans are rejected, not silently truncated. These are
payload limits, not research quotas or instructions to search.

The engine revalidates injected planner output and records it before evaluating
`planner_stopped`, `no_tasks`, or budget bounds. Fatal later failures retain
earlier accepted decisions through the existing failure callback. A provider
failure before acceptance leaves an empty decision array; no plan is invented.
Valid early stops remain valid early stops.

Legacy summaries lacking this field validate with `planning_decisions: null`:
decision evidence was unavailable. An empty array means capture was enabled but
no plan was accepted. No migration or rewrite of stored evidence is required.
The existing WP6 JSON persistence and both public evidence exporters carry these
validated fields and include them in the canonical SHA-256 payload:

```bash
uv run python -m event_radar.development_evidence export-run --run-id RUN_UUID
uv run python -m event_radar.development_evidence export --snapshot-id SNAPSHOT_UUID
```

Continue using the dedicated target safeguards and ignored
`output/development-evidence/` location described in
[evidence runbook](e1-wp7-development-evidence.md).

Only the explicit public planning contract is retained, never provider envelopes,
requests, prompts or exceptions. Inputs remain the neutral regional scope,
coverage and public inventory; no personal context is loaded. Unknown/private
fields are forbidden, including in stored records read by exports. Validation is
a structural boundary, not a general PII detector for arbitrary prose; the
existing public-only inputs and neutral planner instructions remain essential.

## Separate planning-policy review (no strategy change)

The current planner prompt describes source-class, geography, time and broad
opportunity-type gaps, discourages invented counts and ranking, forbids personal
preferences, and explicitly permits stopping. This supports neutral regional
research and preserves zero-discovery outcomes.

Its definition also permits gaps in “evidence” and a general evidence limitation.
It does not explicitly separate materially uncovered regional areas from routine
uncertainty about availability, price or details of individual existing events.
Nor does it prescribe how a rationale should explain why a listed gap is or is
not worth searching. This ambiguity does not establish why the historical planner
stopped.

A future separately reviewed prompt change could ask the planner to distinguish
inventory coverage from item-level factual unknowns, explain the expected value
of each proposed task or why a gap does not warrant one, and retain valid early
stops. Evaluate that change first with deterministic regional cases; do not add
minimum search counts or force discovery. This correction changes no prompt.

## October 16–18 proof and limits

The execution lead reports run `b04d0caa-7a8b-4fd4-aedf-1e93b9f13380` and snapshot
`9c53c4de-3ec4-4634-a8d2-04242c113d1d` retained 107 opportunities, completed
semantic enrichment and WP5 planning, then stopped with `planner_stopped`.
That demonstrates collection, semantic enrichment, a planning invocation and
durable persistence. It does not demonstrate real discovery research or
independent verification, or establish whether the stopping decision was justified.
Its accepted plan cannot be recovered by this correction. No historical record
was changed or reconstructed.

All correction tests use deterministic fakes and a separate disposable database.
The retained evidence service is untouched. WP7 and E1 remain open for review.
