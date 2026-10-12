"""Private context tests run only on guarded disposable PostgreSQL, with fake JWT keys."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.db.contexts import ContextConflict, content_hash, read_context, write_context
from event_radar.db.models import UserContextRevision
from event_radar.models.product_context import ProductUserContext
from event_radar.shared.worker import run_regional_worker
from tests.auth_helpers import CONFIG, signed, signing_fixture
from tests.test_development_evidence import regional_rows
from tests.test_product_context import MINIMAL
from tests.test_shared_worker_integration import budget, scope
from tests.test_shared_worker_integration import worker as worker

A = {
    **MINIMAL,
    "interests": ["PRIVATE_ALPHA_workshops"],
    "social_preferences": ["Natural conversation through participation"],
}
B = {
    "base_location": {"locality": "Petaluma", "timezone": "America/Los_Angeles"},
    "exclusions": ["PRIVATE_BETA_crowds"],
    "solo_considerations": ["Prefer independent outdoor activities"],
    "travel": {"maximum_one_way_minutes": 30},
    "cost": {"maximum_per_activity": "15", "currency": "USD"},
}


def test_signed_two_user_context_api(database, monkeypatch, caplog):
    engine, config = database
    command.upgrade(config, "head")
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    ids = [claims["sub"], str(uuid4())]
    headers = [{"Authorization": "Bearer " + signed(key, {**claims, "sub": uid})} for uid in ids]
    with TestClient(create_app()) as client:
        assert client.get("/api/me/context", headers=headers[0]).status_code == 404
        a = client.post("/api/me/context", headers=headers[0], json=A)
        b = client.post("/api/me/context", headers=headers[1], json=B)
        assert a.status_code == b.status_code == 201
        assert a.headers["cache-control"] == "no-store"
        a, b = a.json(), b.json()
        assert a["revision_id"] != b["revision_id"] and a["content_hash"] != b["content_hash"]
        assert client.get("/api/me/context", headers=headers[0]).json() == a
        # No account selector is authoritative, and no arbitrary-user route exists.
        own = client.get(
            f"/api/me/context?user_id={ids[0]}", headers={**headers[1], "X-User-ID": ids[0]}
        )
        assert own.json() == b
        assert client.get(f"/api/users/{ids[0]}/context", headers=headers[1]).status_code == 404
        cross = client.put(
            "/api/me/context",
            headers=headers[1],
            json={"expected_revision_id": a["revision_id"], "context": A},
        )
        assert cross.status_code == 409 and "PRIVATE_" not in cross.text
        assert client.post("/api/me/context", headers=headers[0], json=A).status_code == 409
        update = {
            "expected_revision_id": a["revision_id"],
            "context": {**A, "objectives": ["Learn a skill"]},
        }
        newer = client.put("/api/me/context", headers=headers[0], json=update)
        assert newer.status_code == 200 and newer.json()["revision"] == 2
        assert client.put("/api/me/context", headers=headers[0], json=update).status_code == 409
        malformed = client.put(
            "/api/me/context",
            headers=headers[0],
            json={**update, "context": {**A, "unexpected": "PRIVATE_INVALID"}},
        )
        assert malformed.status_code == 422 and "PRIVATE_" not in malformed.text
        assert client.get("/api/me/context", headers=headers[1]).json() == b
        assert client.get("/api/me/context").status_code == 401
        forged = signed(key, {**claims, "role": "service_role"})
        assert (
            client.get("/api/me/context", headers={"Authorization": "Bearer " + forged}).status_code
            == 401
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserContextRevision)) == 3
        history = session.scalars(
            select(UserContextRevision)
            .where(UserContextRevision.user_id == UUID(ids[0]))
            .order_by(UserContextRevision.revision)
        ).all()
        assert history[0].context_payload["objectives"] is None
        assert history[1].context_payload["objectives"] == ["Learn a skill"]
    assert "PRIVATE_" not in "\n".join(
        record.getMessage() for record in caplog.records if record.name == "event_radar.api"
    )


def test_concurrent_context_updates(database):
    engine, config = database
    command.upgrade(config, "head")
    uid = uuid4()
    with Session(engine) as session, session.begin():
        original = write_context(
            session, uid, ProductUserContext.model_validate(A), expected_revision_id=None
        )
    barrier = Barrier(2)

    def update(n):
        try:
            with Session(engine) as session, session.begin():
                barrier.wait(timeout=10)
                return write_context(
                    session,
                    uid,
                    ProductUserContext.model_validate({**A, "objectives": [str(n)]}),
                    expected_revision_id=original.revision_id,
                ).revision
        except ContextConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, [1, 2]))
    assert sorted(results, key=str) == [2, "conflict"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserContextRevision)) == 2


def test_context_history_and_database_immutability(database):
    engine, config = database
    command.upgrade(config, "head")
    uid = uuid4()
    with Session(engine) as session, session.begin():
        original = write_context(
            session, uid, ProductUserContext.model_validate(A), expected_revision_id=None
        )
    for operation in (
        "UPDATE user_context_revisions SET revision = 9",
        "DELETE FROM user_context_revisions",
    ):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(operation))
    with Session(engine) as session:
        persisted = read_context(session, uid)
        assert persisted == original and persisted.content_hash == content_hash(persisted.context)
        assert persisted.created_at.tzinfo
        assert read_context(session, uuid4()) is None
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname='user_context_revisions'")
        )
    # A direct client with a SELECT grant still has no RLS policy permitting private reads.
    role = "context_reader_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE {role}"))
        connection.execute(text(f"GRANT SELECT ON user_context_revisions TO {role}"))
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {role}"))
            assert connection.execute(text("SELECT id FROM user_context_revisions")).all() == []
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP OWNED BY {role}"))
            connection.execute(text(f"DROP ROLE {role}"))


async def test_context_does_not_change_shared_evidence(worker):
    deps, source, semantics, discovery = worker
    result = await run_regional_worker(scope(), deps, budget=budget())
    assert result.status == "success"
    before_calls = (source.calls, len(semantics.calls), len(discovery.calls))
    with Session(deps.engine) as session:
        before = regional_rows(session)
    with Session(deps.engine) as session, session.begin():
        for profile in (A, B):
            uid = uuid4()
            write_context(
                session, uid, ProductUserContext.model_validate(profile), expected_revision_id=None
            )
            assert read_context(session, uid)
    with Session(deps.engine) as session:
        assert regional_rows(session) == before
        assert "PRIVATE_" not in str(before)
    assert before_calls == (source.calls, len(semantics.calls), len(discovery.calls))
    assert "PRIVATE_" not in str(semantics.calls)
    from datetime import date

    from sqlalchemy import event

    statements, planning_inputs = [], []
    original_plan = discovery.plan

    async def capture(context):
        planning_inputs.append(context.model_dump(mode="json"))
        return await original_plan(context)

    discovery.plan = capture

    def query(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(deps.engine, "before_cursor_execute", query)
    try:
        another = await run_regional_worker(scope(date(2026, 10, 16)), deps, budget=budget())
        assert another.status == "success"
    finally:
        event.remove(deps.engine, "before_cursor_execute", query)
    assert planning_inputs
    assert "PRIVATE_" not in str(planning_inputs) + str(semantics.calls)
    assert not any("user_context_revisions" in statement for statement in statements)


def test_simultaneous_initial_context_creation(database):
    engine, config = database
    command.upgrade(config, "head")
    uid, barrier = uuid4(), Barrier(2)

    def create(profile):
        try:
            with Session(engine) as session, session.begin():
                barrier.wait(timeout=10)
                return write_context(
                    session,
                    uid,
                    ProductUserContext.model_validate(profile),
                    expected_revision_id=None,
                ).revision
        except ContextConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (A, B)))
    assert sorted(results, key=str) == [1, "conflict"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserContextRevision)) == 1


def test_invalid_service_input_and_corrupt_read_fail_safely(database, monkeypatch, caplog):
    from pydantic import ValidationError

    from event_radar.auth.identity import AuthenticatedUser, get_current_user
    from event_radar.db.models import AppUser

    engine, config = database
    command.upgrade(config, "head")
    uid = uuid4()
    invalid = ProductUserContext.model_validate(A).model_copy(
        update={"interests": ["PRIVATE_INVALID"] * 21}
    )
    with pytest.raises(ValidationError):
        with Session(engine) as session, session.begin():
            write_context(session, uid, invalid, expected_revision_id=None)
    with Session(engine) as session:
        assert session.get(AppUser, uid) is None
        assert session.scalar(select(func.count()).select_from(UserContextRevision)) == 0
    # Privileged corruption fixture only: malformed stored content cannot escape readback.
    with Session(engine) as session, session.begin():
        session.add(AppUser(id=uid))
        session.flush()
        session.add(
            UserContextRevision(
                id=uuid4(),
                user_id=uid,
                revision=1,
                schema_version="user-context-v1",
                content_hash="0" * 64,
                context_payload={**A, "unknown": "PRIVATE_CORRUPT"},
            )
        )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=uid)
    with TestClient(app) as client:
        response = client.get("/api/me/context")
    assert response.status_code == 503 and response.json()["error"]["code"] == "context_unavailable"
    assert "PRIVATE_" not in response.text
    assert "PRIVATE_" not in str(
        [r.getMessage() for r in caplog.records if r.name == "event_radar.api"]
    )
