"""WP8 test-only consumers: downstream selection never dispatches shared research."""

import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from event_radar.db.regional import (
    begin_regional_research_run,
    complete_regional_research_run,
    read_current_regional_universe,
    read_regional_snapshot,
)
from event_radar.models.regional import RegionalAnalysisRequest, RegionalWeekendUniverse
from event_radar.models.regional_discovery import DiscoveryContext
from event_radar.shared.discovery import build_coverage_snapshot
from tests.test_adaptive_regional_discovery import collection, universe
from tests.test_development_evidence import regional_rows


@dataclass(frozen=True)
class SyntheticConsumer:
    label: str
    kind: str
    participation_only: bool
    minimum_route_miles: Decimal
    accepts_partial: bool = True


WORKSHOP = SyntheticConsumer("synthetic-hands-on-workshop-reader", "event", True, Decimal(0))
HIKER = SyntheticConsumer("synthetic-long-route-reader", "hike", False, Decimal(8))


def select_locally(stored, context):
    """Candidate filtering only: does not promise price, availability or safe access."""
    if stored.quality_status == "partial" and not context.accepts_partial:
        return ()
    return tuple(
        opportunity
        for opportunity in stored.universe.opportunities
        if opportunity.kind == context.kind
        and (
            not context.participation_only
            or any(item.kind == "participation" for item in opportunity.semantics or ())
        )
        and (
            context.kind != "hike"
            or opportunity.route.distance_miles >= context.minimum_route_miles
        )
    )


def neutral_wires(value):
    return (
        RegionalAnalysisRequest(
            scope=value.scope, opportunities=value.opportunities
        ).model_dump_json(exclude_none=False),
        DiscoveryContext(
            scope=value.scope,
            coverage=build_coverage_snapshot(
                value.scope, collection().coverage, value.opportunities
            ),
            existing_opportunities=value.opportunities,
        ).model_dump_json(exclude_none=False),
    )


@pytest.mark.parametrize("quality", ["success", "partial"])
def test_two_distinct_consumers_reuse_one_snapshot(database, monkeypatch, quality):
    engine, config = database
    command.upgrade(config, "head")
    value = universe()
    with Session(engine) as session, session.begin():
        run = begin_regional_research_run(session, value.scope)
        snapshot = complete_regional_research_run(
            session,
            run.id,
            value,
            quality_status=quality,
            failure_code="unavailable" if quality == "partial" else None,
            diagnostics=value.diagnostics,
        )
        snapshot_id, digest = snapshot.id, snapshot.content_hash

    calls = Counter()
    targets = {
        "collection": "event_radar.shared.collection.collect_registered_sources",
        "semantics": "event_radar.shared.semantic_analysis.enrich_regional_semantics",
        "discovery": "event_radar.shared.discovery.run_adaptive_discovery",
        "worker": "event_radar.shared.worker.run_regional_worker",
        "network": "socket.socket.connect",
        "http": "httpx.AsyncClient.send",
    }
    for stage, target in targets.items():

        def forbidden(*args, _stage=stage, **kwargs):
            calls[_stage] += 1
            raise AssertionError("Consumer attempted upstream work: " + _stage)

        monkeypatch.setattr(target, forbidden)

    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = regional_rows(session)
    original_wires = neutral_wires(value)
    receipts = []
    # New session and independently deserialized universe for every repeated read.
    for context in (WORKSHOP, HIKER, HIKER, WORKSHOP):
        with Session(engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            stored = read_regional_snapshot(session, snapshot_id)
            current = read_current_regional_universe(session, value.scope.identity)
            assert stored == current
            assert stored.universe == value
            assert stored.snapshot_id == snapshot_id and stored.content_hash == digest
            assert stored.quality_status == quality
            selected = select_locally(stored, context)
            assert [o.opportunity_id for o in selected] == (
                ["community-workshop"] if context == WORKSHOP else ["synthetic-ridge-route"]
            )
            assert selected[0].unknowns
            if context == WORKSHOP:
                assert selected[0].occurrences[0].price.state == "conflicting"
                assert selected[0].occurrences[0].available.state == "unknown"
                assert len(selected[0].evidence) == 2
            else:
                assert selected[0].access_open.state == "unknown"
            assert neutral_wires(stored.universe) == original_wires
            serialized = json.dumps(regional_rows(session), default=str)
            for forbidden_key in (
                WORKSHOP.label,
                HIKER.label,
                "participation_only",
                "minimum_route_miles",
                "user_context",
                "permanent_directions",
                "temporary_directions",
                "telegram_chat_id",
                "why_it_may_fit",
                "personal_score",
            ):
                assert forbidden_key not in serialized
                assert all(forbidden_key not in wire for wire in original_wires)
            assert regional_rows(session) == before
            receipts.append((str(stored.snapshot_id), stored.content_hash))
    assert len(set(receipts)) == 1
    assert calls == Counter()
    # A strict downstream reader can decline degraded data without requesting refresh.
    strict = SyntheticConsumer("synthetic-strict-reader", "hike", False, Decimal(8), False)
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        stored = read_regional_snapshot(session, snapshot_id)
        assert bool(select_locally(stored, strict)) == (quality == "success")
        assert regional_rows(session) == before
    assert calls == Counter()
    print(
        json.dumps(
            {
                "quality": quality,
                "snapshot_id": str(snapshot_id),
                "content_hash": digest,
                "independent_reads": 5,
                "call_counts": dict.fromkeys(targets, 0),
                "selection_ids": ["community-workshop", "synthetic-ridge-route"],
            },
            sort_keys=True,
        )
    )


@pytest.mark.parametrize("field", ["user_context", "permanent_directions", "personal_score"])
def test_consumers_cannot_enter_shared_contracts(field):
    value = universe()
    for model, payload in (
        (RegionalWeekendUniverse, value.model_dump(mode="json")),
        (RegionalAnalysisRequest, json.loads(neutral_wires(value)[0])),
        (DiscoveryContext, json.loads(neutral_wires(value)[1])),
        (type(value.scope.identity), value.scope.identity.model_dump(mode="json")),
    ):
        payload[field] = "SYNTHETIC_PRIVATE_SENTINEL"
        with pytest.raises(ValidationError):
            model.model_validate(payload)
