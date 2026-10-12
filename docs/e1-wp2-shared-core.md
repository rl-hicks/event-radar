# E1 WP2 — environment-pure shared core

Status: implemented on the isolated E1 feature branch for review.

## Scope

WP2 establishes an import-safe shared entry surface for the regional research path without rewriting the legacy personal pipeline.

The concrete coupling removed here is the runtime dependency from `models.token_usage` to `event_radar.config.Settings`. Token pricing now accepts a structural pricing mapping/protocol; `from_settings` remains as a compatibility adapter but no longer imports the Settings module.

The new `event_radar.shared` package exposes only regional contracts and environment-pure model-usage telemetry required by later shared collection, semantic analysis and discovery work.

## Preserved behavior

- Existing `ModelTokenPricing.from_settings(config, model)` callers remain supported.
- Token parsing, aggregation, missing-aware accounting and cost semantics remain unchanged.
- No legacy personal orchestration, prompts, Telegram path, API/auth/DB behavior or deployment configuration is modified.
- No source adapter is moved yet; WP3 owns modular collection.

## Isolation evidence

A fresh subprocess imports and exercises `event_radar.shared` while actively blocking legacy configuration/runtime imports, network/database activity, private-path access and filesystem writes.

The process validates a populated synthetic Regional Weekend Universe and model-usage telemetry with a deliberately invalid pricing environment value. The import succeeds without constructing legacy Settings.

## Limits

This package does not claim the entire historical model graph is a public shared API. Legacy personal models may continue importing one another as long as the E1 shared entry surface remains independent. Later WP3–WP5 code should depend on `event_radar.shared` or other explicitly reviewed environment-pure modules rather than on the personal orchestration graph.
