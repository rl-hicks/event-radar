"""Add backend-only verified bindings, hashed challenges and delivery audit/outbox."""

from alembic import op

revision = "0005_packet_delivery"
down_revision = "0004_weekend_packets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_packet_owner", "weekend_packets", ["id", "user_id"])
    op.execute("""
        CREATE TABLE delivery_bindings (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        channel VARCHAR(16) NOT NULL,
        revision INTEGER NOT NULL,
        destination VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL,
        consent BOOLEAN NOT NULL,
        verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT uq_binding_revision UNIQUE (user_id, channel, revision),
        CONSTRAINT uq_binding_owner UNIQUE (id, user_id),
        CONSTRAINT ck_binding_channel CHECK (channel IN ('telegram','email')),
        CONSTRAINT ck_binding_status CHECK (status IN ('active','revoked')),
        CONSTRAINT ck_binding_revision CHECK (revision > 0),
        FOREIGN KEY(user_id) REFERENCES app_users (id)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_binding_active_destination ON delivery_bindings (channel,
        destination) WHERE status = 'active'
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_binding_active_user ON delivery_bindings (user_id, channel)
        WHERE status = 'active'
    """)
    op.execute("""
        ALTER TABLE delivery_bindings ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        REVOKE ALL ON delivery_bindings FROM PUBLIC
    """)
    op.execute("""
        DO $$ DECLARE r text; BEGIN
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=r) THEN
        EXECUTE format('REVOKE ALL ON delivery_bindings FROM %I',r);
        END IF;
        END LOOP;
        END $$
    """)
    op.execute("""
        CREATE TABLE delivery_challenges (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        consumed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT uq_challenge_hash UNIQUE (token_hash),
        CONSTRAINT ck_challenge_expiry CHECK (expires_at > created_at),
        FOREIGN KEY(user_id) REFERENCES app_users (id)
        )
    """)
    op.execute("""
        ALTER TABLE delivery_challenges ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        REVOKE ALL ON delivery_challenges FROM PUBLIC
    """)
    op.execute("""
        DO $$ DECLARE r text; BEGIN
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=r) THEN
        EXECUTE format('REVOKE ALL ON delivery_challenges FROM %I',r);
        END IF;
        END LOOP;
        END $$
    """)
    op.execute("""
        CREATE TABLE delivery_intents (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        packet_id UUID NOT NULL,
        binding_id UUID NOT NULL,
        channel VARCHAR(16) NOT NULL,
        status VARCHAR(16) NOT NULL,
        attempts INTEGER NOT NULL,
        failure_code VARCHAR(32),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_delivery_intent UNIQUE (packet_id, channel, binding_id),
        CONSTRAINT fk_delivery_owned_binding FOREIGN KEY(binding_id, user_id) REFERENCES
        delivery_bindings (id, user_id),
        CONSTRAINT fk_delivery_owned_packet FOREIGN KEY(packet_id, user_id) REFERENCES
        weekend_packets (id, user_id),
        CONSTRAINT ck_delivery_channel CHECK (channel IN ('telegram','email')),
        CONSTRAINT ck_delivery_status CHECK (status IN
        ('pending','sending','sent','failed','ambiguous','revoked')),
        CONSTRAINT ck_delivery_attempts CHECK (attempts >= 0 AND attempts <= 3),
        CONSTRAINT ck_delivery_failure CHECK (failure_code IS NULL OR failure_code IN
        ('rejected','transport_unknown','invalid_response','revoked','packet_unavailable'))
        )
    """)
    op.execute("""
        ALTER TABLE delivery_intents ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        REVOKE ALL ON delivery_intents FROM PUBLIC
    """)
    op.execute("""
        DO $$ DECLARE r text; BEGIN
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=r) THEN
        EXECUTE format('REVOKE ALL ON delivery_intents FROM %I',r);
        END IF;
        END LOOP;
        END $$
    """)
    op.execute("""
        CREATE TABLE delivery_attempts (
        id UUID NOT NULL,
        intent_id UUID NOT NULL,
        number INTEGER NOT NULL,
        status VARCHAR(16) NOT NULL,
        failure_code VARCHAR(32),
        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        finished_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT uq_delivery_attempt UNIQUE (intent_id, number),
        CONSTRAINT ck_attempt_number CHECK (number BETWEEN 1 AND 3),
        CONSTRAINT ck_attempt_status CHECK (status IN
        ('sending','sent','failed','ambiguous')),
        CONSTRAINT ck_attempt_failure CHECK (failure_code IS NULL OR failure_code IN
        ('rejected','transport_unknown','invalid_response')),
        FOREIGN KEY(intent_id) REFERENCES delivery_intents (id)
        )
    """)
    op.execute("""
        ALTER TABLE delivery_attempts ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        REVOKE ALL ON delivery_attempts FROM PUBLIC
    """)
    op.execute("""
        DO $$ DECLARE r text; BEGIN
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname=r) THEN
        EXECUTE format('REVOKE ALL ON delivery_attempts FROM %I',r);
        END IF;
        END LOOP;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION protect_delivery_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Bindings are retained' USING ERRCODE='23000';
        END IF;
        IF OLD.status <> 'active' OR NEW.status <> 'revoked' OR NEW.consent
        OR NEW.revoked_at IS NULL
        OR (to_jsonb(NEW) - ARRAY['status','consent','revoked_at']) IS DISTINCT FROM
        (to_jsonb(OLD) - ARRAY['status','consent','revoked_at']) THEN
        RAISE EXCEPTION 'Invalid binding transition' USING ERRCODE='23000';
        END IF;
        RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER delivery_binding_guard BEFORE UPDATE OR DELETE ON delivery_bindings FOR
        EACH ROW EXECUTE FUNCTION protect_delivery_binding()
    """)
    op.execute("""
        CREATE FUNCTION protect_delivery_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Attempts are retained' USING ERRCODE='23000';
        END IF;
        IF OLD.status <> 'sending' OR NEW.status = 'sending' OR NEW.finished_at IS NULL
        OR (to_jsonb(NEW) - ARRAY['status','failure_code','finished_at']) IS DISTINCT FROM
        (to_jsonb(OLD) - ARRAY['status','failure_code','finished_at']) THEN
        RAISE EXCEPTION 'Invalid attempt transition' USING ERRCODE='23000';
        END IF;
        RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER delivery_attempt_guard BEFORE UPDATE OR DELETE ON delivery_attempts FOR
        EACH ROW EXECUTE FUNCTION protect_delivery_attempt()
    """)

    op.execute("""
        CREATE FUNCTION protect_delivery_challenge() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Challenges are retained' USING ERRCODE='23000';
          END IF;
          IF OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL
             OR (to_jsonb(NEW) - 'consumed_at') IS DISTINCT FROM
                (to_jsonb(OLD) - 'consumed_at') THEN
            RAISE EXCEPTION 'Invalid challenge transition' USING ERRCODE='23000';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER delivery_challenge_guard BEFORE UPDATE OR DELETE ON delivery_challenges
        FOR EACH ROW EXECUTE FUNCTION protect_delivery_challenge()
    """)
    op.execute("""
        CREATE FUNCTION protect_delivery_intent() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Delivery intents are retained' USING ERRCODE='23000';
          END IF;
          IF (to_jsonb(NEW) - ARRAY['status','attempts','failure_code','updated_at'])
              IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['status','attempts','failure_code','updated_at'])
             OR NOT (
               (OLD.status IN ('pending','failed') AND NEW.status IN ('sending','failed','revoked'))
               OR (OLD.status='sending' AND NEW.status IN ('sent','failed','ambiguous','revoked'))
             ) THEN
            RAISE EXCEPTION 'Invalid delivery transition' USING ERRCODE='23000';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER delivery_intent_guard BEFORE UPDATE OR DELETE ON delivery_intents
        FOR EACH ROW EXECUTE FUNCTION protect_delivery_intent()
    """)


def downgrade() -> None:
    op.drop_table("delivery_attempts")
    op.execute("""
        DROP FUNCTION protect_delivery_attempt()
    """)
    op.drop_table("delivery_intents")
    op.execute("DROP FUNCTION protect_delivery_intent()")
    op.drop_table("delivery_challenges")
    op.execute("DROP FUNCTION protect_delivery_challenge()")
    op.drop_table("delivery_bindings")
    op.execute("""
        DROP FUNCTION protect_delivery_binding()
    """)
    op.drop_constraint("uq_packet_owner", "weekend_packets", type_="unique")
