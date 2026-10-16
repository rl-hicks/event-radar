"""Synthetic-only logical recovery; source uses the existing guarded fixture."""

import json
import os
import shutil
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text

from alembic import command
from scripts import database_recovery as recovery
from scripts.database_recovery import capture, check_bundle, run_client, verify_restored
from tests.test_database_security import quarantine, seed_e0


@pytest.fixture
def recovery_database(database, tmp_path, monkeypatch):
    engine, config = database
    ids, _ = seed_e0(engine, config)
    quarantine(engine)
    # A tiny Auth analogue proves data inclusion/identity links, not GoTrue recovery.
    with engine.begin() as c:
        c.execute(text("CREATE SCHEMA auth"))
        c.execute(text("CREATE TABLE auth.users(id uuid PRIMARY KEY, encrypted_password text)"))
        c.execute(text("CREATE TABLE auth.identities(id uuid PRIMARY KEY REFERENCES auth.users)"))
        for uid in ids:
            c.execute(text("INSERT INTO auth.users VALUES (:id,'synthetic-hash')"), {"id": uid})
            c.execute(text("INSERT INTO auth.identities VALUES (:id)"), {"id": uid})
    url = engine.url
    # All credentials are synthetic. File-based libpq credentials model operator handling.
    passfile = tmp_path / "passfile"
    passfile.write_text(f"127.0.0.1:{url.port}:*:{url.username}:{url.password}\n")
    passfile.chmod(0o600)
    servicefile = tmp_path / "services"
    servicefile.write_text(
        "\n".join(
            f"[{service}]\nhost=127.0.0.1\nport={url.port}\nuser={url.username}\n"
            f"dbname={db}\npassfile={passfile}\nsslmode=disable\n"
            for service, db in (("source", "event_radar_test"), ("restore", "event_radar_restore"))
        )
    )
    servicefile.chmod(0o600)
    monkeypatch.setenv("PGSERVICEFILE", str(servicefile))
    clients = Path(os.environ.get("RECOVERY_PG_BIN", "/usr/lib/postgresql/17/bin"))
    dump, restore = str(clients / "pg_dump"), str(clients / "pg_restore")
    assert Path(dump).exists(), "RECOVERY_PG_BIN must select PostgreSQL 17 clients"
    try:
        yield engine, config, dump, restore
    finally:
        with psycopg.connect(service="source", autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS event_radar_restore")
            c.execute("DROP SCHEMA auth CASCADE")


def restore_bundle(bundle, restore):
    with psycopg.connect(service="source", autocommit=True) as c:
        c.execute("CREATE DATABASE event_radar_restore")
    with psycopg.connect(service="restore") as c:
        c.execute("DROP SCHEMA public")  # Empty, newly created disposable target only.
        c.execute("CREATE SCHEMA auth")
        c.execute("CREATE TABLE auth.users(id uuid PRIMARY KEY, encrypted_password text)")
        c.execute("CREATE TABLE auth.identities(id uuid PRIMARY KEY REFERENCES auth.users)")
    for name in ("public.dump", "auth.dump"):
        run_client(
            [
                restore,
                "--exit-on-error",
                "--single-transaction",
                "--dbname",
                "service=restore",
                str(bundle / name),
            ]
        )


@pytest.mark.parametrize("revision", ["0001_app_users", "head"])
def test_synthetic_backup_restore(recovery_database, tmp_path, revision):
    _, config, dump, restore = recovery_database
    if revision == "head":
        command.upgrade(config, "head")
    bundle = tmp_path / "bundle"
    counts = capture("source", bundle, dump)
    assert counts["public.app_users"] == counts["auth.users"] == 2
    assert (bundle / "public.dump").stat().st_mode & 0o777 == 0o600
    assert bundle.stat().st_mode & 0o777 == 0o700
    assert check_bundle(bundle)["revision"] == (
        "0006_hosted_access_hardening" if revision == "head" else revision
    )
    restore_bundle(bundle, restore)
    from scripts.database_recovery import structure

    with psycopg.connect(service="restore") as c:
        actual = structure(c)
    expected = check_bundle(bundle)["structure"]
    for part, baseline in zip(actual, expected, strict=True):
        assert part == baseline
    assert verify_restored("restore", bundle) == counts
    with psycopg.connect(service="restore") as c:
        c.execute("ALTER TABLE public.app_users DISABLE ROW LEVEL SECURITY")
    with pytest.raises(RuntimeError, match="structure/security"):
        verify_restored("restore", bundle)
    with psycopg.connect(service="restore") as c:
        c.execute("ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY")
    # Duplicate restore fails safely; no raw SQL or row data in exception text.
    with pytest.raises(RuntimeError, match="Database client failed"):
        run_client(
            [
                restore,
                "--exit-on-error",
                "--single-transaction",
                "--dbname",
                "service=restore",
                str(bundle / "public.dump"),
            ]
        )
    assert verify_restored("restore", bundle) == counts
    with psycopg.connect(service="restore") as c:
        c.execute("UPDATE public.app_users SET updated_at=updated_at + interval '1 second'")
    with pytest.raises(RuntimeError, match="private row integrity"):
        verify_restored("restore", bundle)
    damaged = tmp_path / "damaged"
    shutil.copytree(bundle, damaged)
    (damaged / "auth.dump").unlink()
    with pytest.raises(RuntimeError, match="Incomplete or corrupt"):
        check_bundle(damaged)
    (damaged / "auth.dump").write_bytes(b"truncated")
    with pytest.raises(RuntimeError, match="Incomplete or corrupt"):
        check_bundle(damaged)
    manifest = json.loads((damaged / "manifest.json").read_text())
    manifest["files"].pop("auth.dump")
    (damaged / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="Incomplete or corrupt"):
        check_bundle(damaged)


def test_snapshot_consistency_under_concurrent_change(recovery_database, tmp_path, monkeypatch):
    _, _, dump, restore = recovery_database
    bundle = tmp_path / "concurrent-bundle"
    original_inventory = recovery.inventory
    original_structure = recovery.structure
    original_client = recovery.run_client
    snapshots = []
    checked_connections = []
    transaction_warnings = []
    original_connect = psycopg.connect

    def observed_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        # Retain only SQLSTATE, never database notice text/private diagnostics.
        connection.add_notice_handler(lambda notice: transaction_warnings.append(notice.sqlstate))
        return connection

    monkeypatch.setattr(recovery.psycopg, "connect", observed_connect)

    def assert_transaction(connection):
        assert connection.execute("SHOW transaction_isolation").fetchone() == ("repeatable read",)
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
        # Confirm server enforcement too; the savepoint contains the expected error.
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with connection.transaction():
                connection.execute("UPDATE public.app_users SET updated_at=updated_at")
        checked_connections.append(connection)

    def change_both(service):
        # A different connection commits while the reader's transaction remains open.
        # No sleeps or race-dependent timing: the caller resumes only after commit.
        with psycopg.connect(service=service) as writer:
            writer.execute(
                "UPDATE public.app_users SET updated_at=updated_at + interval '1 second'"
            )
            writer.execute(
                "UPDATE auth.users SET encrypted_password=encrypted_password || '-changed'"
            )

    with psycopg.connect(service="source") as c:
        before = original_inventory(c)

    def concurrent_inventory(connection):
        assert_transaction(connection)
        # capture() has already exported its snapshot; move the live source before
        # manifest reads. Both dumps must still agree with the pre-change evidence.
        change_both("source")
        result = original_inventory(connection)
        assert result == before
        return result

    def concurrent_dump(args, **kwargs):
        if "--schema=auth" in args:
            change_both("source")  # Another commit between the two archive reads.
        if any(arg.startswith("--snapshot=") for arg in args):
            snapshots.append(next(arg for arg in args if arg.startswith("--snapshot=")))
        return original_client(args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(recovery, "inventory", concurrent_inventory)
        patch.setattr(recovery, "run_client", concurrent_dump)
        counts = capture("source", bundle, dump)
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]
    assert len(checked_connections) == 1 and checked_connections[0].closed
    assert check_bundle(bundle)["inventory"] == before
    with psycopg.connect(service="source") as c:
        after = original_inventory(c)
    assert after["public.app_users"] != before["public.app_users"]
    assert after["auth.users"] != before["auth.users"]
    restore_bundle(bundle, restore)
    assert verify_restored("restore", bundle) == counts  # Real archives, pre-change data.

    def concurrent_structure(connection):
        assert_transaction(connection)
        result = original_structure(connection)  # Establish verification's snapshot.
        change_both("restore")
        return result

    def stable_inventory(connection):
        assert_transaction(connection)
        result = original_inventory(connection)
        assert result == before
        return result

    with monkeypatch.context() as patch:
        patch.setattr(recovery, "structure", concurrent_structure)
        patch.setattr(recovery, "inventory", stable_inventory)
        assert verify_restored("restore", bundle) == counts
    assert len(checked_connections) == 3
    assert checked_connections[1] is checked_connections[2]
    assert all(connection.closed for connection in checked_connections)
    assert "25001" not in transaction_warnings  # No nested/already-active BEGIN warning.
    # A new verification sees the committed change and correctly rejects it.
    with pytest.raises(RuntimeError, match="private row integrity"):
        verify_restored("restore", bundle)
