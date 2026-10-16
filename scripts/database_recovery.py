"""Private logical recovery bundle; no credentials in argv or public diagnostics.

Requires an approved libpq service, PostgreSQL 17 clients and a write/DDL freeze.
Capture is private-data extraction and needs separate hosted authorization.
This module never restores or changes a source database.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

FILES = ("public.dump", "auth.dump", "roles.json")


def run_client(args, *, env=None):
    result = subprocess.run(args, env=env, capture_output=True, check=False)
    if result.returncode:
        # pg_dump/restore stderr may contain row data, SQL, hostnames or secrets.
        raise RuntimeError("Database client failed; private operator investigation required")
    return result.stdout


def inventory(connection):
    """Canonical full-row hashes stay PRIVATE; public reporting uses counts only."""
    connection.execute("SET LOCAL timezone='UTC'")
    connection.execute("SET LOCAL datestyle='ISO, YMD'")
    result = {}
    tables = connection.execute(
        "SELECT schemaname,tablename FROM pg_tables "
        "WHERE schemaname IN ('public','auth') ORDER BY 1,2"
    ).fetchall()
    if ("public", "app_users") not in tables or ("auth", "users") not in tables:
        raise RuntimeError("Required application or authentication inventory missing")
    for schema, table in tables:
        rows = connection.execute(
            sql.SQL("SELECT to_jsonb(t)::text FROM {}.{} t").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchall()
        canonical = sorted(row[0] for row in rows)
        result[schema + "." + table] = {
            "count": len(rows),
            "sha256": hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
        }
    return result


def structure(connection):
    queries = (
        "SELECT c.relname,pg_get_userbyid(c.relowner),c.relrowsecurity,c.relforcerowsecurity,"
        "ARRAY(SELECT a::text FROM unnest(coalesce(c.relacl,acldefault("
        "CASE WHEN c.relkind='S' THEN 's'::\"char\" ELSE 'r'::\"char\" END,c.relowner))) a "
        "ORDER BY a::text) FROM pg_class c WHERE c.relnamespace='public'::regnamespace "
        "AND c.relkind IN ('r','S') ORDER BY 1",
        "SELECT table_name,column_name,data_type,is_nullable,column_default FROM "
        "information_schema.columns WHERE table_schema='public' ORDER BY 1,2",
        "SELECT c.relname,a.attname,a.attacl::text FROM pg_attribute a JOIN pg_class c "
        "ON c.oid=a.attrelid WHERE c.relnamespace='public'::regnamespace AND a.attnum>0 "
        "AND NOT a.attisdropped ORDER BY 1,2",
        "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace='public'::regnamespace ORDER BY 1,2",
        "SELECT tgrelid::regclass::text,tgname,tgenabled,pg_get_triggerdef(oid) FROM pg_trigger "
        "WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_class WHERE "
        "relnamespace='public'::regnamespace) ORDER BY 1,2",
        "SELECT tablename,policyname,roles::text,cmd,qual,with_check FROM pg_policies "
        "WHERE schemaname='public' ORDER BY 1,2",
        "SELECT p.proname,pg_get_userbyid(p.proowner),p.proacl::text,pg_get_functiondef(p.oid) "
        "FROM pg_proc p WHERE p.pronamespace='public'::regnamespace ORDER BY 1",
    )
    result = [list(map(list, connection.execute(query).fetchall())) for query in queries]
    # PG17 reparses a varchar literal-array cast as element casts during restore.
    # Normalize only this equivalent form, retaining every literal/operator/type.
    for row in result[3]:
        row[2] = re.sub(
            r"\(ARRAY\[((?:'[^']*'::character varying)"
            r"(?:, '[^']*'::character varying)*)\]\)::text\[\]",
            lambda match: (
                "ARRAY[" + ", ".join("(" + item + ")::text" for item in match[1].split(", ")) + "]"
            ),
            row[2],
        )
    return result


def capture(service, directory, pg_dump="pg_dump"):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", service):
        raise ValueError("Use a named libpq service, never a connection URL")
    if not run_client([pg_dump, "--version"]).decode().startswith("pg_dump (PostgreSQL) 17."):
        raise RuntimeError("PostgreSQL 17 dump client required")
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(directory, 0o700)
    # Exclusive destination and missing manifest distinguish interrupted bundles.
    with psycopg.connect(service=service) as connection:
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if connection.info.server_version // 10000 != 17:
            raise RuntimeError("Reviewed PostgreSQL 17 source required")
        snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        expected = inventory(connection)
        revision = connection.execute("SELECT version_num FROM public.alembic_version").fetchall()
        if len(revision) != 1 or revision[0][0] not in (
            "0001_app_users",
            "0006_hosted_access_hardening",
        ):
            raise RuntimeError("Unexpected source revision")
        for schema, filename, extra in (
            ("public", "public.dump", []),
            ("auth", "auth.dump", ["--data-only"]),
        ):
            target = directory / filename
            target.touch(mode=0o600)
            run_client(
                [
                    pg_dump,
                    "--dbname",
                    "service=" + service,
                    "--format=custom",
                    "--schema=" + schema,
                    "--snapshot=" + snapshot,
                    "--file=" + str(target),
                    *extra,
                ]
            )
        roles = connection.execute(
            "SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,"
            "rolcreaterole,rolreplication FROM pg_roles WHERE starts_with(rolname,'event_radar_') "
            "ORDER BY rolname"
        ).fetchall()
        memberships = connection.execute(
            "SELECT pg_get_userbyid(roleid),pg_get_userbyid(member),admin_option,"
            "inherit_option,set_option FROM pg_auth_members WHERE roleid IN "
            "(SELECT oid FROM pg_roles WHERE starts_with(rolname,'event_radar_')) "
            "OR member IN (SELECT oid FROM pg_roles WHERE starts_with(rolname,'event_radar_')) "
            "ORDER BY 1,2"
        ).fetchall()
        defaults = connection.execute(
            "SELECT pg_get_userbyid(defaclrole), CASE WHEN defaclnamespace=0 THEN NULL "
            "ELSE defaclnamespace::regnamespace::text END,defaclobjtype,defaclacl::text "
            "FROM pg_default_acl WHERE defaclrole IN (SELECT oid FROM pg_roles "
            "WHERE starts_with(rolname,'event_radar_')) ORDER BY 1,2,3"
        ).fetchall()
        private_json(
            directory / "roles.json",
            {"roles": roles, "memberships": memberships, "defaults": defaults},
        )
        manifest = {
            "format": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "server_version": connection.info.server_version,
            "revision": revision[0][0],
            "inventory": expected,
            "structure": structure(connection),
            "files": {name: digest(directory / name) for name in FILES},
        }
        private_json(directory / "manifest.json", manifest)
    return {name: value["count"] for name, value in expected.items()}


def private_json(path, value):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream, sort_keys=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_bundle(directory):
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["format"] != 1 or set(manifest["files"]) != set(FILES):
            raise ValueError
        for name in FILES:
            if digest(directory / name) != manifest["files"][name]:
                raise ValueError
        if not {"public.app_users", "public.alembic_version", "auth.users"} <= set(
            manifest["inventory"]
        ):
            raise ValueError
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Incomplete or corrupt recovery bundle") from error


def verify_restored(service, directory):
    manifest = check_bundle(directory)
    with psycopg.connect(service=service) as connection:
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if structure(connection) != manifest["structure"]:
            raise RuntimeError("Restored application structure/security comparison failed")
        if inventory(connection) != manifest["inventory"]:
            raise RuntimeError("Restored private row integrity comparison failed")
        revision = connection.execute("SELECT version_num FROM public.alembic_version").fetchall()
        if revision != [(manifest["revision"],)]:
            raise RuntimeError("Restored revision mismatch")
    return {name: value["count"] for name, value in manifest["inventory"].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "check", "verify"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--service")
    args = parser.parse_args()
    try:
        if args.action == "check":
            check_bundle(args.directory)
        elif not args.service:
            raise ValueError("Named service required")
        elif args.action == "capture":
            capture(args.service, args.directory)
        else:
            verify_restored(args.service, args.directory)
    except Exception:
        # Never print private exception contents or database diagnostics.
        raise SystemExit("Recovery operation FAILED; inspect privately") from None
    print("Recovery operation PASS (no identities reported)")


if __name__ == "__main__":
    main()
