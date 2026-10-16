"""Forward-only application ACL/RLS hardening; no hosted execution is implicit."""

import sqlalchemy as sa

from alembic import op

revision = "0006_hosted_access_hardening"
down_revision = "0005_packet_delivery"
branch_labels = None
depends_on = None

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
FUNCTIONS = (
    "reject_user_context_mutation",
    "protect_curation_job",
    "protect_weekend_packet",
    "protect_delivery_binding",
    "protect_delivery_attempt",
    "protect_delivery_challenge",
    "protect_delivery_intent",
)
API = "event_radar_api"
WORKER = "event_radar_research"
OWNER = "event_radar_migrator"


def upgrade() -> None:
    connection = op.get_bind()
    # Fail closed on role drift. Never strip privileges from an existing unrelated role.
    for role in (API, WORKER, OWNER):
        existing = connection.execute(
            sa.text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
                "rolcanlogin FROM pg_roles WHERE rolname=:role"
            ),
            {"role": role},
        ).first()
        if existing is None:
            op.execute(
                f"CREATE ROLE {role} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            )
        elif any(existing):
            raise RuntimeError("Hardening role attributes require independent review")
        if connection.scalar(
            sa.text(
                "SELECT EXISTS(SELECT FROM pg_auth_members WHERE member="
                "(SELECT oid FROM pg_roles WHERE rolname=:role))"
            ),
            {"role": role},
        ):
            raise RuntimeError("Hardening roles must not inherit other roles")
    for role in (API, WORKER):
        if connection.scalar(
            sa.text(
                "SELECT has_database_privilege(:r,current_database(),'CREATE') "
                "OR EXISTS(SELECT FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles "
                "WHERE rolname=:r)) OR EXISTS(SELECT FROM pg_namespace WHERE nspowner="
                "(SELECT oid FROM pg_roles WHERE rolname=:r)) OR EXISTS(SELECT FROM pg_class "
                "WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=:r)) "
                "OR EXISTS(SELECT FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles "
                "WHERE rolname=:r))"
            ),
            {"r": role},
        ):
            raise RuntimeError("Runtime ownership or database CREATE requires separate review")
    clients = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
        )
    ]
    grantees = ", ".join(("PUBLIC", *clients, API, WORKER))
    # public can contain provider extensions: retain USAGE, remove object creation only.
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {grantees}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {API}, {WORKER}, {OWNER}")
    op.execute(f"GRANT CREATE ON SCHEMA public TO {OWNER}")
    # Only the dedicated application creator is administered. Provider defaults do
    # not follow an object on ownership transfer and are not inherited at creation.
    # Revoke BOTH global and schema-local grants: schema revokes cannot override
    # global grants, while global revokes cannot remove schema-local additions.
    for scope in ("", " IN SCHEMA public"):
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            op.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER}{scope} "
                f"REVOKE ALL ON {kind} FROM {grantees}"
            )
    # Remaining grants via another role would also expose future objects. Do not
    # revoke unrelated grantees; reject the conflict for independent review.
    for client in (*clients, API, WORKER):
        if connection.scalar(
            sa.text(
                "SELECT EXISTS(SELECT FROM pg_default_acl d, aclexplode(d.defaclacl) a "
                "WHERE d.defaclrole=(SELECT oid FROM pg_roles WHERE rolname=:owner) "
                "AND d.defaclnamespace IN (0,'public'::regnamespace) "
                "AND d.defaclobjtype IN ('r','S','f') AND "
                "(a.grantee=0 OR pg_has_role(:client,a.grantee,'USAGE')))"
            ),
            {"owner": OWNER, "client": client},
        ):
            raise RuntimeError("Effective client defaults require independent review")
    for table in TABLES:
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM {grantees}")
        # Table ACL revocation does not remove pre-existing column grants.
        columns = connection.scalars(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position"
            ),
            {"table": table},
        )
        names = ", ".join(connection.dialect.identifier_preparer.quote(c) for c in columns)
        for permission in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
            op.execute(f"REVOKE {permission} ({names}) ON public.{table} FROM {grantees}")
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        # Unknown policies could broaden access through PUBLIC/inherited roles. Stop, don't erase.
        if connection.scalar(
            sa.text(
                "SELECT EXISTS(SELECT FROM pg_policies WHERE schemaname='public' AND tablename=:t)"
            ),
            {"t": table},
        ):
            raise RuntimeError("Unexpected existing application RLS policy")
    api_reads = set(TABLES) - {"alembic_version", "regional_research_runs"}
    inserts = api_reads - {"regional_universes", "regional_universe_snapshots"}
    for table in sorted(api_reads):
        op.execute(f"GRANT SELECT ON public.{table} TO {API}")
        op.execute(
            f"CREATE POLICY api_access ON public.{table} TO {API} USING (true) WITH CHECK (true)"
        )
    for table in sorted(inserts):
        op.execute(f"GRANT INSERT ON public.{table} TO {API}")
    updates = {
        "app_users": "updated_at",  # PostgreSQL SELECT FOR UPDATE requires an UPDATE grant.
        "curation_jobs": "status, finished_at, failure_code, usage_payload",
        "delivery_bindings": "status, consent, revoked_at",
        "delivery_challenges": "consumed_at",
        "delivery_intents": "status, attempts, failure_code, updated_at",
        "delivery_attempts": "status, failure_code, finished_at",
    }
    for table, columns in updates.items():
        op.execute(f"GRANT UPDATE ({columns}) ON public.{table} TO {API}")
    for table in ("regional_universes", "regional_universe_snapshots", "regional_research_runs"):
        op.execute(f"GRANT SELECT, INSERT ON public.{table} TO {WORKER}")
        op.execute(
            f"CREATE POLICY research_access ON public.{table} TO {WORKER} "
            "USING (true) WITH CHECK (true)"
        )
    op.execute(
        f"GRANT UPDATE (current_snapshot_id, updated_at) ON public.regional_universes TO {WORKER}"
    )
    op.execute(
        "GRANT UPDATE (status, finished_at, snapshot_id, failure_code, "
        f"diagnostics_payload, discovery_summary) ON public.regional_research_runs TO {WORKER}"
    )
    for function in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM {grantees}")
        op.execute(f"ALTER FUNCTION public.{function}() SET search_path = pg_catalog, public")
        op.execute(f"ALTER FUNCTION public.{function}() OWNER TO {OWNER}")
    # Runtime roles own no objects. The separately controlled migrator owns bookkeeping too.
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} OWNER TO {OWNER}")
    # Effective checks catch inherited client access and ownership/role surprises.
    for client in (*clients, API, WORKER):
        for table in TABLES:
            forbidden = (
                client in clients
                or table == "alembic_version"
                or (client == WORKER and not table.startswith("regional_"))
                or (client == API and table == "regional_research_runs")
            )
            if forbidden and connection.scalar(
                sa.text(
                    "SELECT has_any_column_privilege(:r, :t, 'SELECT,INSERT,UPDATE,REFERENCES') "
                    "OR has_table_privilege(:r, :t, 'DELETE,TRUNCATE,TRIGGER')"
                ),
                {"r": client, "t": "public." + table},
            ):
                raise RuntimeError("Effective forbidden privileges remain; review inheritance")
        for function in FUNCTIONS:
            if connection.scalar(
                sa.text("SELECT has_function_privilege(:r,:f,'EXECUTE')"),
                {"r": client, "f": "public." + function + "()"},
            ):
                raise RuntimeError("Inherited application function execution remains")
        if connection.scalar(
            sa.text("SELECT has_schema_privilege(:r,'public','CREATE')"), {"r": client}
        ):
            raise RuntimeError("Effective schema CREATE remains")


def downgrade() -> None:
    # No unsafe permission restoration. Only guarded disposable teardown may cross this revision.
    if not op.get_context().config.attributes.get("disposable_security_teardown") or tuple(
        op.get_bind().execute(sa.text("SELECT current_database(), session_user")).one()
    ) != ("event_radar_test", "event_radar_test"):
        raise RuntimeError("Security hardening is forward-only; restore through reviewed recovery")
