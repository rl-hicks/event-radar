"""Private AI #3 execution claims and immutable canonical Weekend Packets."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_weekend_packets"
down_revision = "0003_user_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_context_owned_id", "user_context_revisions", ["id", "user_id"])
    op.create_table(
        "curation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id"), nullable=False
        ),
        sa.Column("context_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regional_universe_snapshots.id"),
            nullable=False,
        ),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("policy_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("usage_payload", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("identity", name="uq_curation_identity"),
        sa.UniqueConstraint(
            "id", "user_id", "context_revision_id", "snapshot_id", name="uq_curation_packet_binding"
        ),
        sa.ForeignKeyConstraint(
            ["context_revision_id", "user_id"],
            ["user_context_revisions.id", "user_context_revisions.user_id"],
            name="fk_curation_owned_context",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status IN ('success', 'partial') AND finished_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_curation_state",
        ),
    )
    op.create_table(
        "weekend_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("packet_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("execution_id", name="uq_packet_execution"),
        sa.ForeignKeyConstraint(
            ["execution_id", "user_id", "context_revision_id", "snapshot_id"],
            [
                "curation_jobs.id",
                "curation_jobs.user_id",
                "curation_jobs.context_revision_id",
                "curation_jobs.snapshot_id",
            ],
            name="fk_packet_execution_binding",
        ),
    )
    op.create_index("ix_packet_owner_created", "weekend_packets", ["user_id", "created_at"])
    for table in ("curation_jobs", "weekend_packets"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        # Revoke common Supabase roles if present; no hosted role assumptions or policies.
        op.execute(f"""
            DO $$ DECLARE client_role text; BEGIN
              FOREACH client_role IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = client_role) THEN
                  EXECUTE format('REVOKE ALL ON {table} FROM %I', client_role);
                END IF;
              END LOOP;
            END $$;
        """)
    op.execute("""
        CREATE FUNCTION protect_curation_job() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Curation jobs are retained' USING ERRCODE = '23000';
          END IF;
          IF OLD.status <> 'running' OR NEW.status = 'running'
             OR (to_jsonb(NEW) - ARRAY['status','finished_at','failure_code','usage_payload'])
                IS DISTINCT FROM
                (to_jsonb(OLD) - ARRAY['status','finished_at','failure_code','usage_payload']) THEN
            RAISE EXCEPTION 'Invalid curation transition' USING ERRCODE = '23000';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER curation_job_transition BEFORE UPDATE OR DELETE ON curation_jobs
        FOR EACH ROW EXECUTE FUNCTION protect_curation_job()
    """)
    op.execute("""
        CREATE FUNCTION protect_weekend_packet() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Packets are immutable' USING ERRCODE = '23000';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM curation_jobs WHERE id = NEW.execution_id
                         AND status IN ('success','partial')) THEN
            RAISE EXCEPTION 'Packet requires completed curation' USING ERRCODE = '23000';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER weekend_packet_immutable BEFORE INSERT OR UPDATE OR DELETE
        ON weekend_packets FOR EACH ROW EXECUTE FUNCTION protect_weekend_packet()
    """)


def downgrade() -> None:
    op.drop_table("weekend_packets")
    op.execute("DROP FUNCTION protect_weekend_packet()")
    op.drop_table("curation_jobs")
    op.execute("DROP FUNCTION protect_curation_job()")
    op.drop_constraint("uq_context_owned_id", "user_context_revisions", type_="unique")
