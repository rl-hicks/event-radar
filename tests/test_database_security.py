"""Actual PostgreSQL permissions; destructive setup only through the guarded test fixture."""

import secrets
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.db.contexts import write_context
from event_radar.db.delivery import accept_private_update, challenge, queue_delivery, revoke
from event_radar.db.regional import begin_regional_research_run, complete_regional_research_run
from event_radar.models.product_context import ProductUserContext
from event_radar.models.weekend_packet import CurationPolicy
from event_radar.services.packet_delivery import FakeTelegramTransport, dispatch_fake
from event_radar.services.packet_generation import generate_packet
from event_radar.services.personalized_curation import DeterministicCurationProvider
from tests.auth_helpers import CONFIG, signed, signing_fixture
from tests.test_weekend_packets import OUTDOOR, SOCIAL, no_external_calls, universe

__all__ = ["no_external_calls"]
ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "alembic_version",
    "app_users",
    "regional_universes",
    "regional_universe_snapshots",
    "regional_research_runs",
    "user_context_revisions",
    "curation_jobs",
    "weekend_packets",
    "delivery_bindings",
    "delivery_challenges",
    "delivery_intents",
    "delivery_attempts",
)


def seed_e0(engine, config):
    with engine.begin() as c:
        for role in (
            "anon",
            "authenticated",
            "postgres",
            "supabase_admin",
            "event_radar_api",
            "event_radar_research",
            "event_radar_migrator",
        ):
            if not c.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": role}):
                c.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        creator = c.scalar(text("SELECT current_user"))
        for role in ("postgres", "supabase_admin", creator):
            for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                c.execute(
                    text(
                        f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public "
                        f"GRANT ALL ON {kind} TO anon, authenticated"
                    )
                )
    command.upgrade(config, "0001_app_users")
    ids = [uuid4(), uuid4()]
    with engine.begin() as c:
        for uid in ids:
            c.execute(text("INSERT INTO app_users(id) VALUES (:id)"), {"id": uid})
        c.execute(text("GRANT ALL ON app_users,alembic_version TO anon,authenticated"))
        c.execute(text("GRANT SELECT(id) ON app_users TO anon"))
        before = c.execute(text("SELECT * FROM app_users ORDER BY id")).all()
        assert c.scalar(text("SELECT has_table_privilege('anon','app_users','SELECT')"))
    return ids, before


def quarantine(engine):
    sql = (ROOT / "sql/security/quarantine_e0.sql").read_text()
    with engine.begin() as c:
        c.execute(text(sql.replace("BEGIN;\n", "", 1).replace("COMMIT;\n", "", 1)))


def denied(engine, role, sql, state="42501"):
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as c:
            c.execute(text(f"SET LOCAL ROLE {role}"))
            c.execute(text(sql))
    assert error.value.orig.sqlstate == state


def role_engine(engine, role):
    # Real non-superuser login, not a superuser session that could SET ROLE back to an owner.
    login = role + "_test_login"
    password = secrets.token_hex(24)
    with engine.begin() as c:
        c.execute(
            text(
                f"CREATE ROLE {login} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
                f"NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{password}'"
            )
        )
        c.execute(text(f"GRANT {role} TO {login}"))
    return create_engine(engine.url.set(username=login, password=password))


def test_e0_upgrade_preservation_and_effective_permissions(database):
    engine, config = database
    _, before = seed_e0(engine, config)
    quarantine(engine)
    command.upgrade(config, "head")
    with engine.begin() as c:
        sql = (ROOT / "sql/security/verify_hardening.sql").read_text()
        c.execute(text(sql.replace("BEGIN READ ONLY;", "").replace("COMMIT;", "")))
    with engine.connect() as c:
        assert c.execute(text("SELECT * FROM app_users ORDER BY id")).all() == before
        assert (
            c.scalar(text("SELECT version_num FROM alembic_version"))
            == "0006_hosted_access_hardening"
        )
        assert set(inspect(c).get_table_names()) == set(TABLES)
        for t in TABLES:
            assert c.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:t)"), {"t": t}
            )
            assert (
                c.scalar(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=to_regclass(:t)"
                    ),
                    {"t": t},
                )
                == "event_radar_migrator"
            )
            for role in ("anon", "authenticated"):
                assert not c.scalar(
                    text(
                        "SELECT "
                        "has_any_column_privilege(:r,:t,'SELECT,INSERT,UPDATE,REFERENCES') OR "
                        "has_table_privilege(:r,:t,'DELETE,TRUNCATE,TRIGGER')"
                    ),
                    {"r": role, "t": t},
                )
        assert (
            c.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN "
                    "(SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace)"
                )
            )
            == 7
        )
        assert (
            c.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE "
                    "conrelid='weekend_packets'::regclass AND contype='f'"
                )
            )
            > 0
        )
        assert (
            c.scalar(
                text(
                    "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace "
                    "AND relkind='S'"
                )
            )
            == 0
        )
    for role in ("anon", "authenticated"):
        for t in TABLES:
            for sql in (
                f"SELECT * FROM {t}",
                f"DELETE FROM {t}",
                f"TRUNCATE {t}",
                f"INSERT INTO {t} DEFAULT VALUES",
                f"UPDATE {t} SET "
                + ("version_num=version_num" if t == "alembic_version" else "id=id"),
            ):
                denied(engine, role, sql)
    # RLS independently denies browser access even if a future ACL is accidentally restored.
    with engine.connect() as c:
        transaction = c.begin()
        try:
            c.execute(text("GRANT SELECT, INSERT ON app_users TO anon"))
            c.execute(text("SET LOCAL ROLE anon"))
            assert c.execute(text("SELECT * FROM app_users")).all() == []
            with pytest.raises(DBAPIError) as error:
                c.execute(text("INSERT INTO app_users(id) VALUES (:id)"), {"id": uuid4()})
            assert error.value.orig.sqlstate == "42501"
        finally:
            transaction.rollback()
    for role in ("event_radar_api", "event_radar_research"):
        for sql in (
            "SELECT * FROM alembic_version",
            "UPDATE alembic_version SET version_num='bad'",
            "CREATE TABLE public.unauthorized(id int)",
            "ALTER TABLE app_users DISABLE ROW LEVEL SECURITY",
            "TRUNCATE app_users",
            "CREATE ROLE unauthorized",
            "DROP TABLE app_users",
        ):
            denied(engine, role, sql)
    denied(engine, "event_radar_api", "INSERT INTO regional_universes DEFAULT VALUES")
    denied(engine, "event_radar_api", "SELECT * FROM regional_research_runs")
    denied(engine, "event_radar_research", "SELECT * FROM user_context_revisions")
    # The dedicated creator has no client defaults, including PostgreSQL's global PUBLIC EXECUTE.
    with engine.begin() as c:
        c.execute(text("SET LOCAL ROLE event_radar_migrator"))
        c.execute(text("CREATE TABLE public.security_probe(id int)"))
        c.execute(text("CREATE SEQUENCE public.security_probe_seq"))
        c.execute(
            text(
                "CREATE FUNCTION public.security_probe_fn() RETURNS integer LANGUAGE sql AS $$ "
                "SELECT 1 $$"
            )
        )
        for role in ("anon", "authenticated", "event_radar_api", "event_radar_research"):
            assert not c.scalar(
                text(
                    "SELECT has_table_privilege(:r,'security_probe','SELECT,INSERT,UPDATE,DELETE')"
                ),
                {"r": role},
            )
            assert not c.scalar(
                text(
                    "SELECT has_sequence_privilege(:r,'security_probe_seq','USAGE,SELECT,UPDATE')"
                ),
                {"r": role},
            )
            assert not c.scalar(
                text("SELECT has_function_privilege(:r,'security_probe_fn()','EXECUTE')"),
                {"r": role},
            )
        c.execute(text("DROP TABLE security_probe"))
        c.execute(text("DROP SEQUENCE security_probe_seq"))
        c.execute(text("DROP FUNCTION security_probe_fn()"))
    for creator in ("postgres", "supabase_admin"):
        with engine.begin() as c:
            c.execute(text(f"GRANT USAGE,CREATE ON SCHEMA public TO {creator}"))
            c.execute(text(f"SET LOCAL ROLE {creator}"))
            c.execute(text("CREATE TABLE security_probe(id int)"))
            c.execute(text("CREATE SEQUENCE security_probe_seq"))
            for client in ("anon", "authenticated"):
                assert not c.scalar(
                    text(
                        "SELECT "
                        "has_table_privilege(:r,'security_probe','SELECT,INSERT,UPDATE,DELETE') OR "
                        "has_sequence_privilege(:r,'security_probe_seq','USAGE,SELECT,UPDATE')"
                    ),
                    {"r": client},
                )
            c.execute(text("DROP TABLE security_probe"))
            c.execute(text("DROP SEQUENCE security_probe_seq"))


@pytest.mark.parametrize(
    "failure", ["late", "inherited", "global_default", "database_create", "unsafe_runtime"]
)
def test_failed_upgrade_keeps_quarantined_e0(database, failure):
    engine, config = database
    _, before = seed_e0(engine, config)
    quarantine(engine)
    if failure == "inherited":
        with engine.begin() as c:
            c.execute(text("GRANT event_radar_migrator TO anon"))
    if failure == "global_default":
        with engine.begin() as c:
            c.execute(
                text("ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT SELECT ON TABLES TO anon")
            )

    if failure == "database_create":
        with engine.begin() as c:
            c.execute(text("GRANT CREATE ON DATABASE event_radar_test TO event_radar_api"))
    if failure == "unsafe_runtime":
        with engine.begin() as c:
            c.execute(text("ALTER ROLE event_radar_api BYPASSRLS"))

    def fail_late(conn, cursor, statement, parameters, context, executemany):
        if failure == "late" and statement.startswith("ALTER TABLE public.delivery_attempts OWNER"):
            raise RuntimeError("injected late migration failure")

    event.listen(engine, "before_cursor_execute", fail_late)
    try:
        with pytest.raises((RuntimeError, DBAPIError)):
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        with engine.connect() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0001_app_users"
            assert set(inspect(c).get_table_names()) == {"app_users", "alembic_version"}
            assert c.execute(text("SELECT * FROM app_users ORDER BY id")).all() == before
        denied(engine, "authenticated", "SELECT * FROM app_users")
    finally:
        config.attributes.pop("connection", None)
        event.remove(engine, "before_cursor_execute", fail_late)
        with engine.begin() as c:
            if failure == "inherited":
                c.execute(text("REVOKE event_radar_migrator FROM anon"))
            if failure == "global_default":
                c.execute(
                    text(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE SELECT ON TABLES "
                        "FROM anon"
                    )
                )
            if failure == "database_create":
                c.execute(text("REVOKE CREATE ON DATABASE event_radar_test FROM event_radar_api"))
            if failure == "unsafe_runtime":
                c.execute(text("ALTER ROLE event_radar_api NOBYPASSRLS"))
            # Restore test-only injected schema defaults so later cases start independently.
            for role in ("postgres", "supabase_admin", "event_radar_test"):
                for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                    c.execute(
                        text(
                            f"ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public REVOKE "
                            f"ALL ON {kind} FROM anon,authenticated"
                        )
                    )


async def test_nonowner_api_curation_delivery_and_worker(database, monkeypatch):
    engine, config = database
    seed_e0(engine, config)
    quarantine(engine)
    command.upgrade(config, "head")
    api = role_engine(engine, "event_radar_api")
    worker = role_engine(engine, "event_radar_research")
    try:
        with api.connect() as c:
            assert c.scalar(text("SELECT current_user")) == "event_radar_api_test_login"
            assert not any(
                c.execute(
                    text(
                        "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles "
                        "WHERE rolname=current_user"
                    )
                ).one()
            )
        denied(api, "event_radar_api", "SET ROLE event_radar_migrator")
        denied(api, "event_radar_api", "SET ROLE event_radar_test")
        research = universe()
        now = research.scope.as_of + timedelta(hours=1)
        ids = [uuid4(), uuid4()]
        with Session(worker) as s, s.begin():
            run = begin_regional_research_run(s, research.scope)
            snapshot = complete_regional_research_run(s, run.id, research, quality_status="success")
            sid = snapshot.id
        with Session(api) as s, s.begin():
            for uid, profile in zip(ids, (SOCIAL, OUTDOOR), strict=True):
                write_context(
                    s, uid, ProductUserContext.model_validate(profile), expected_revision_id=None
                )
        results = [
            await generate_packet(
                api,
                uid,
                sid,
                CurationPolicy(research_policy_version=research.scope.research_policy_version),
                DeterministicCurationProvider(),
                now=now,
            )
            for uid in ids
        ]
        assert all(x.status == "success" for x in results)
        from event_radar.db.current_packet import read_current_packet

        with Session(api) as s:
            current = read_current_packet(
                s, ids[0], now=now, research_policy=research.scope.research_policy_version
            )
            assert current.state == "current" and current.packet is not None
            assert current.packet.packet_id == results[0].packet_id
        key, claims, verifier = signing_fixture(monkeypatch)
        monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
        monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
        headers = [
            {"Authorization": "Bearer " + signed(key, {**claims, "sub": str(uid)})} for uid in ids
        ]
        app = create_app()
        app.state.database._engine = api
        with TestClient(app) as client:
            for i, result in enumerate(results):
                assert client.get("/api/me", headers=headers[i]).status_code == 200
                assert (
                    client.get("/api/me/context", headers=headers[i]).json()["context"]["interests"]
                    == (SOCIAL, OUTDOOR)[i]["interests"]
                )
                url = f"/api/me/packets/{result.packet_id}"
                assert client.get(url, headers=headers[i]).status_code == 200
                assert client.get(url, headers=headers[1 - i]).status_code == 404
        with Session(api) as s, s.begin():
            token = challenge(s, ids[0])
            binding = accept_private_update(
                s, token, sender_id=12345, chat_id=12345, chat_type="private", sender_is_bot=False
            )
            bid = binding.id
            intent = queue_delivery(
                s, ids[0], results[0].packet_id, bid, "telegram", development=True
            )
        transport = FakeTelegramTransport()
        assert dispatch_fake(api, intent, transport, development=True) == "sent"
        with Session(api) as s, s.begin():
            revoke(s, ids[0], bid)
        denied(
            engine, "event_radar_api", "UPDATE user_context_revisions SET content_hash=content_hash"
        )
        denied(engine, "event_radar_api", "UPDATE weekend_packets SET content_hash=content_hash")
        denied(
            engine,
            "event_radar_research",
            "UPDATE regional_universe_snapshots SET content_hash=content_hash",
        )
        # Even a migrator with DML permission cannot bypass existing immutable triggers.
        denied(
            engine,
            "event_radar_migrator",
            "UPDATE user_context_revisions SET content_hash=content_hash",
            state="23000",
        )
        denied(engine, "event_radar_migrator", "DELETE FROM weekend_packets", state="23000")
        # Exercise actual E1 orchestration under its regional-only role, no activation/providers.
        from event_radar.shared.collection import SourceRegistration, SourceRegistry
        from event_radar.shared.worker import WorkerDependencies, run_regional_worker
        from tests.test_shared_worker_integration import Discovery, Semantics, Source, budget, scope

        discovery = Discovery()
        deps = WorkerDependencies(
            worker,
            SourceRegistry((SourceRegistration(Source()),)),
            Semantics(),
            discovery,
            discovery,
            discovery,
        )
        result = await run_regional_worker(scope(), deps, budget=budget())
        assert result.status == "success"
        replay = await run_regional_worker(scope(), deps, budget=budget())
        assert replay.status == "replayed"
    finally:
        api.dispose()
        worker.dispose()
        with engine.begin() as c:
            c.execute(text("DROP ROLE event_radar_api_test_login"))
            c.execute(text("DROP ROLE event_radar_research_test_login"))


def test_separately_administered_provider_defaults(database):
    engine, config = database
    seed_e0(engine, config)
    quarantine(engine)
    sql = (ROOT / "sql/security/provider_defaults.sql").read_text()
    with engine.begin() as c:
        c.execute(text(sql.replace("BEGIN;", "").replace("COMMIT;", "")))

    def reject_provider_administration(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin"):
            raise AssertionError("Already-clean provider defaults must not need authority again")

    event.listen(engine, "before_cursor_execute", reject_provider_administration)
    try:
        with engine.begin() as c:
            config.attributes["connection"] = c
            command.upgrade(config, "head")
    finally:
        config.attributes.pop("connection", None)
        event.remove(engine, "before_cursor_execute", reject_provider_administration)


def test_non_superuser_migration_executor(database):
    engine, config = database
    _, before = seed_e0(engine, config)
    quarantine(engine)
    password = secrets.token_hex(24)
    login = "event_radar_bootstrap_test"
    with engine.begin() as c:
        sql = (ROOT / "sql/security/provider_defaults.sql").read_text()
        c.execute(text(sql.replace("BEGIN;", "").replace("COMMIT;", "")))
        c.execute(
            text(
                f"CREATE ROLE {login} LOGIN INHERIT NOSUPERUSER NOBYPASSRLS "
                f"NOCREATEDB NOCREATEROLE PASSWORD '{password}'"
            )
        )
        c.execute(text(f"GRANT event_radar_migrator TO {login} WITH INHERIT TRUE, SET TRUE"))
        schema_owner = c.scalar(
            text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'")
        )
        c.execute(text(f"ALTER SCHEMA public OWNER TO {login}"))
        c.execute(text(f"ALTER TABLE app_users OWNER TO {login}"))
        c.execute(text(f"ALTER TABLE alembic_version OWNER TO {login}"))
    migration_engine = create_engine(engine.url.set(username=login, password=password))
    try:
        with migration_engine.begin() as c:
            assert not any(
                c.execute(
                    text(
                        "SELECT rolsuper,rolbypassrls,rolcreaterole "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                ).one()
            )
            config.attributes["connection"] = c
            command.upgrade(config, "head")
            assert c.execute(text("SELECT * FROM app_users ORDER BY id")).all() == before
            assert (
                c.scalar(text("SELECT version_num FROM alembic_version"))
                == "0006_hosted_access_hardening"
            )
    finally:
        config.attributes.pop("connection", None)
        migration_engine.dispose()
        with engine.begin() as c:
            owner = c.dialect.identifier_preparer.quote(schema_owner)
            c.execute(text(f"ALTER SCHEMA public OWNER TO {owner}"))
            for table in ("app_users", "alembic_version"):
                if (
                    c.scalar(
                        text(
                            "SELECT pg_get_userbyid(relowner) FROM pg_class "
                            "WHERE oid=to_regclass(:t)"
                        ),
                        {"t": table},
                    )
                    == login
                ):
                    c.execute(text(f"ALTER TABLE {table} OWNER TO event_radar_test"))
            c.execute(text(f"DROP ROLE {login}"))
