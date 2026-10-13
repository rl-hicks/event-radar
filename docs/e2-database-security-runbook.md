# Prepared hosted security rollout and approval gate

**Do not execute without separate owner approval.** Target is existing Supabase project `event-radar`, `fbjwxfkzbxhkwixwypsa`. The lead-observed baseline is 0001 with two app_users rows as of October 13, 2026. This runbook is a proposal; no hosted status, backup, SQL result, role, secret or deployment was changed or independently verified by this implementation. Use the final handoff's full E2 SHA and exact-head CI; never execute from a moving branch tip.

Read [security design and privilege matrix](e2-database-security-remediation.md). This supersedes the old staging plan's 0005 target: secure staging requires **0006_hosted_access_hardening**. Do not rewrite revisions 0001–0005, stamp a revision, run per-revision upgrade commands, or use tests against hosted data.

## 1. Read-only preflight and recovery readiness

- Obtain the exact existing project's database connection from the owner-controlled Connect dialog. Confirm project ID, host, database, login, connection mode, TLS and current deployed Render SHA/environment role. Do not guess a pooler hostname/user format. Keep secrets out of chat, argv, Git, screenshots and logs. Stop for target mismatch.
- Run `sql/security/inspect_access.sql` in a read-only session. It reads only metadata and a count, not identities or payloads. Confirm exact revision 0001, exactly two app_users rows, table/column layout, constraints, owners, policies, grants (including columns), role flags/memberships and both global/schema defaults. Inspect relevant default-ACL grantors and ability to administer them. Account for inheritance and SET-role membership, not just role flags. Stop on drift, additional consumers of public schema or unexpected global client defaults; prepare a revised plan instead of broadly revoking unrelated role access.
- Confirm existing public schemas/functions/extensions have no unrelated consumer depending on the public default ACLs to be changed. No auth, storage, realtime or other Supabase-managed schema is altered. public USAGE is retained; CREATE is narrowed. Confirm no unexpected application-owned sequence exists (the reviewed schema uses UUIDs).
- Verify a usable recovery backup/export and its restore procedure in isolation before the full migration. Record timestamp, integrity, encryption, storage/access owner and a tested restore target. Do not claim a Free-plan backup or PITR entitlement merely because the project is healthy. Backup creation/restore contains private data and needs its own handling approval; this assignment made none. Preserve both existing users without reading their identities in ordinary reporting. Count two before and after; backup/restore validation is the operator's preservation evidence.
- Review whether prompt containment of the exposed E0 tables should precede backup work; containment changes permissions only and is independently authorized. If backup readiness is absent, do not perform the schema upgrade. Arrange a maintenance window and pause API traffic before upgrade/credential cutover. Pausing Render is itself a separately approved operational change.

## 2. Execution authority

Initial 0006 bootstrap needs an administrator that can create the three NOLOGIN roles, administer the current application objects/schema, alter applicable creator defaults, and transfer ownership to event_radar_migrator. PostgreSQL ownership transfer requires membership/SET authority in the destination role (or superuser) and schema CREATE for that destination. Do not assume Supabase's postgres has every supabase_admin capability despite BYPASSRLS.

Review role names for collisions and attributes first. Existing capability roles must be NOLOGIN, non-superuser/non-BYPASSRLS/non-admin, with no parent memberships. If the approved executor is not a superuser, pre-provision the exact reviewed NOLOGIN capability/owner roles through authorized administration where needed. Grant the initial executor temporary migrator membership with **INHERIT TRUE and SET TRUE**: it must retain inherited owner access after ownership transfer so Alembic can update its version row. SET-only membership is insufficient. The executor also needs public-schema ownership/appropriate grant authority and ownership of the existing E0 objects. Authorize that exact temporary membership and remove it when no longer needed. A disposable test performs the full upgrade using a real non-superuser, non-BYPASSRLS, non-CREATEROLE login after these prerequisites and independent provider-default cleanup. Never grant migrator/admin membership to browser/runtime roles. If hosted role administration is not available, stop and ask the platform administrator; do not bypass permission checks.

Future application DDL must run as the dedicated migrator, with explicit SET ROLE using a separately controlled migration login. It owns application tables and seven trigger functions; its default privileges are private. It is not a connection identity for Render. Future migrations that add capabilities require explicit reviewed grants.

## 3. Committed E0 containment

After specific permission-change approval, execute the prepared script privately with a reviewed admin connection, stop-on-error enabled:

```sh
psql service=event_radar_security_admin -X -v ON_ERROR_STOP=1 -f sql/security/quarantine_e0.sql
```

The named libpq service must first be securely configured for the reviewed target with a protected passfile/secret mechanism and verified TLS. Do not put a credential-bearing URL in process arguments or paste it into chat. An equivalent owner-controlled SQL session may execute the exact script. The script uses a transaction, 5-second lock and 60-second statement timeouts; it checks revision 0001, enables RLS, revokes table/column access from PUBLIC/anon/authenticated and checks effective denial. It changes no rows. Recheck both user count and browser effective access. A permission/lock/inheritance failure rolls it back; stop because containment was not achieved. Do not proceed claiming the E0 gap is closed.

Containment commits separately so a subsequent failed upgrade does not reopen browser access. No broad browser policies are added. An old owner-credential backend may still function because owners bypass RLS; that is not least-privilege evidence and is not the desired final runtime.

## 4. Default ACL remediation where separate administration is required

0006 automatically removes dirty schema-local defaults for the executing creator and existing postgres/supabase_admin roles when it has authority. If a required provider creator cannot be administered by that executor, have the authorized administrator execute only that role's block in `sql/security/provider_defaults.sql` before the upgrade. The two role blocks have independent transactions. Inspect defaults afterward. 0006 skips already-clean schema-local defaults, but fails on dirty defaults it cannot modify.

Do not grant supabase_admin to the migration login to evade this limitation. Do not remove global provider PUBLIC function EXECUTE across managed schemas. Unexpected global browser table/sequence grants or direct global browser routine grants require a separately scoped decision. The dedicated application creator removes PUBLIC function execution from its own global defaults; that is safe because it is new and app-only. Future application objects must not be created as postgres/supabase_admin. Global defaults cannot be reliably fixed using only a schema-local REVOKE.

## 5. One atomic schema/security upgrade

Use an approved admin/migration-safe **direct or session-pooler connection**, not transaction pooling. Direct connectivity may be IPv6-dependent; confirm reachability. Use TLS verification supported by the verified target. Never use hosted credentials with disposable tests or the local-only pilot initialization command.

From the reviewed E2 checkout with locked dependencies and secure backend-only DATABASE_URL (`postgresql+psycopg` scheme), run:

```sh
uv sync --frozen
uv run alembic heads
uv run alembic history
uv run alembic current
PGOPTIONS='-c lock_timeout=5000 -c statement_timeout=60000' uv run alembic upgrade 0006_hosted_access_hardening
uv run alembic current
```

Review output privately because driver diagnostics may contain connection details. Do not run revisions individually: Alembic wraps the full 0002→0006 chain in one PostgreSQL transaction; transaction_per_migration is explicitly false. It can also use a caller-owned connection/transaction for an operator wrapper. The new roles, ACLs, RLS, policies, function changes, ownership and version update commit together. New tables are not committed between insecure creation and hardening. No pre-deploy hook, API startup or health check invokes migrations.

An error or timeout rolls back the full upgrade and leaves committed E0 containment in place. Re-inspect revision/table metadata/count before doing anything else. If revision is not exactly 0001 or 0006 after an interrupted connection, treat commit outcome as unknown; reconcile it read-only. Never retry blindly, stamp, disable constraints, or downgrade.

## 6. Security verification before runtime cutover

- Run `sql/security/verify_hardening.sql` read-only: expected revision 0006, all 12 tables present/RLS/migrator-owned, no effective browser access, no runtime administration/bookkeeping access, no client/runtime direct execution of the seven trigger functions, exactly two existing users and seven application triggers.
- Rerun `inspect_access.sql` and compare each grant/column update/policy to the report's matrix. Check role membership closure, no WITH GRANT OPTION or runtime-to-owner SET path, expected function invoker/search paths, FK/unique/check constraints and active immutable/transition triggers. Inspect both provider default ACL sets plus migrator defaults.
- The disposable test proof created future tables/sequences/functions under the reviewed creators. Do not create hosted probe objects without additional approval. Hosted metadata review verifies defaults without DDL.
- Connect with the proposed runtime login and verify `current_user`, role flags/memberships and effective privileges. A successful postgres connection is not sufficient. Verify forbidden app-table administration, bookkeeping and private-role separation through read-only privilege predicates; do not attempt destructive hosted SQL as a test.

## 7. Credentials, pooling and backend compatibility

After independent role/credential approval, create a unique LOGIN role for Render with INHERIT, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE and NOREPLICATION. Grant only event_radar_api, without ADMIN OPTION, using reviewed PostgreSQL membership options. No direct object grants or ownership on the login. Provision a strong generated SCRAM credential through secure administrative tooling and store it only in Render's secret DATABASE_URL. Neither browser keys nor a Supabase service-role API key replace this SQL credential. The capability role itself stays NOLOGIN.

Use the verified Supabase **session pooler** custom-role username/connection format from supported account configuration; actual custom-role authentication, TLS and pooler compatibility must be tested under separate read-only connectivity authority. Do not guess that changing the username of a postgres pooler URL works. Runtime privileges are inherited at login and do not depend on a persistent SET ROLE or custom per-tenant GUC. SQLAlchemy uses bounded pools; no transaction pooler is substituted for E1's session advisory locks. Login roles must not acquire unrelated inherited PUBLIC/database capabilities that permit permanent schema administration. Temporary tables are outside the permanent application schema boundary.

To rotate, provision a second equally restricted login, verify privilege parity, update the authorized Render secret, recycle all connections/deploy the approved compatible SHA, validate, then disable the old login and terminate its sessions only after explicit approval. Never temporarily fall back to postgres to make a smoke test pass. Keep migration credentials separate from runtime secrets and off the API service.

Create a research login only when that separate operation is approved, inheriting only event_radar_research. Worker orchestration/replay has been tested with synthetic inputs under this role. The scheduled CLI's administrative revision-read preflight still needs a reviewed split/attestation before activation; don't grant it alembic_version access or activate E1 under this task.

After explicitly approved runtime cutover/deployment, verify health (connectivity only), 401 unauthenticated routes, matching Supabase JWT authority and normal account-scoped context/packet reads. Private API writes, synthetic-account provisioning, real context editing, packet generation and delivery smoke tests require their own approval; they are not implied by a security migration. Existing two-user synthetic tests supply offline evidence, not permission to use the two retained hosted accounts.

## 8. Failure recovery and stop conditions

Before commit: PostgreSQL rollback, then metadata/count verification. Quarantined E0 remains private. Keep traffic stopped if schema/auth/runtime state is uncertain. After commit: no destructive downgrade. Prefer reviewed forward repair or restore a verified backup into an isolated target, validate integrity/security, then separately approve cutover. Never restore an exposed E0 database to public access without containment. No backup has been verified in this assignment.

Stop on project/host/revision drift, changed user count, unknown table/policy/role ownership, provider-default permission failure, inherited browser access, unsafe runtime membership, missing backup/recovery readiness, unsupported custom-role pooler login, timeout/ambiguous commit, failed runtime security assertions, or unexpected provider cost/plan requirements. Report sanitized metadata only. Do not modify Auth settings or managed schemas as a workaround.

## Specific approval inventory

Execution-lead review is requested for the code/SQL/tests first. Subsequent owner authorization must explicitly cover:

1. Verified backup/private-data handling and maintenance/traffic pause arrangements.
2. E0 table/bookkeeping RLS and table/column grant containment.
3. Applicable postgres/supabase_admin public-schema default ACL remediation, including a separate administrator where required.
4. One atomic upgrade through 0006: create the three NOLOGIN roles, object ownership transfers, role/schema grants, policies and application-function ACL/search-path changes; any necessary narrowly scoped migration-operator membership.
5. Restricted runtime LOGIN creation/credential provisioning, pooler connectivity validation, Render secret change/connection recycling and a separately approved exact-SHA deployment.
6. Precisely bounded authenticated post-change smoke operations; real AI, research, accounts, Telegram, email or scheduler activation remain excluded unless independently authorized.

No hosted SQL, DDL, grants, roles, defaults, data writes, secret reads, deployments, provider calls or deliveries were performed. Neither E1 nor E2 nor Product V1 is complete.
