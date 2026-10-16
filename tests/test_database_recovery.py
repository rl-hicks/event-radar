"""Synthetic-only logical recovery; source uses the existing guarded fixture."""

import json
import os
import shutil
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text

from alembic import command
from scripts.database_recovery import capture, check_bundle, run_client, verify_restored
from tests.test_database_security import quarantine, seed_e0


@pytest.mark.parametrize("revision", ["0001_app_users", "head"])
def test_synthetic_backup_restore(database, tmp_path, monkeypatch, revision):
    engine, config = database
    ids, _ = seed_e0(engine, config)
    quarantine(engine)
    if revision == "head":
        command.upgrade(config, "head")
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
    bundle = tmp_path / "bundle"
    try:
        counts = capture("source", bundle, dump)
        assert counts["public.app_users"] == counts["auth.users"] == 2
        assert (bundle / "public.dump").stat().st_mode & 0o777 == 0o600
        assert bundle.stat().st_mode & 0o777 == 0o700
        assert check_bundle(bundle)["revision"] == (
            "0006_hosted_access_hardening" if revision == "head" else revision
        )
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
    finally:
        with psycopg.connect(service="source", autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS event_radar_restore")
            c.execute("DROP SCHEMA auth CASCADE")
