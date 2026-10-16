# E2 independent backup and recovery gate

Prepared procedure; **no authorization to extract hosted data**. Target supplied by
the lead: event-radar / fbjwxfkzbxhkwixwypsa,
Free organization, PostgreSQL 17.11, approximately 11 MB, revision 0001_app_users,
two application users. Exact project ID: **fbjwxfkzbxhkwixwypsa**.
No actual hosted backup or recovery has been performed. The security runbook's
maintenance, containment, authority and deployment gates still apply.

| Evidence | Status |
| --- | --- |
| Procedure and private integrity utility implemented | Yes |
| Synthetic E0 and hardened E2 logical backup/restore | Tested locally; mandatory CI |
| Real hosted backup completed | No; private extraction/storage approval required |
| Real hosted recovery verified | No; approved isolated recovery target required |

## Method and coverage

Supabase recommends CLI `db dump` exports for Free projects. Its supported transfer
recipe separates roles, schema and COPY data and uses the **session pooler** by
default (direct connection is suitable where IPv6/network connectivity permits).
Do not use transaction pooling. See [Free backup policy](https://supabase.com/docs/guides/platform/backups),
[Supabase transfer procedure](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
and [CLI dump behavior](https://supabase.com/docs/reference/cli/supabase-db-dump).
A default CLI dump is schema-only and excludes managed schema definitions; it is
not a complete identity/data backup.

Use a reviewed PostgreSQL **17** client for the supplemental narrow archive below.
Supabase also documents direct [pg_dump logical backup](https://supabase.com/docs/guides/troubleshooting/pg_dump-fails-with-query-would-be-affected-by-row-level-security-policy-1d5783).
Do not add a BYPASSRLS runtime or backup role to evade a permission failure: use
the separately authorized existing backup administrator and stop on denied reads.
The proposed operator must prove read access to all required Auth tables.

`scripts/database_recovery.py capture` uses one exported repeatable-read snapshot
for both dumps and all private row comparisons. Capture and restoration
verification open an autocommit connection, set Psycopg's REPEATABLE_READ/read_only
characteristics, and enter an explicit `connection.transaction()` context before
any recovery queries. Both paths fail closed unless PostgreSQL reports
`transaction_isolation = repeatable read` and `transaction_read_only = on`.
Capture keeps that transaction open through both pg_dump calls, passing the same
exported snapshot to each. Verification's catalog, row and revision reads share
one transaction too. See [Psycopg transaction contexts and characteristics](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

The deterministic PostgreSQL regression commits synthetic app/Auth changes from
a second connection before capture inventory, between archives, and between
verification catalog/row reads. It checks server characteristics, read-only write
rejection, matching dump snapshot arguments, restored pre-change data, fresh-reader
change detection and absence of an already-active-transaction warning. The earlier
raw-BEGIN path still produced consistent results on the tested PostgreSQL 17.11,
but issued that warning; this correction removes reliance on nested BEGIN handling.
No prior hosted backup inconsistency is claimed.

The capture bundle contains:

- `public.dump`: application schema/data, Alembic revision, constraints, policies,
  triggers, functions, ownership, ACLs and applicable public default privileges.
  Preflight must confirm public contains only the reviewed application objects.
- `auth.dump`: **data only**, all current Auth tables, including users, identities,
  password hashes, and any sessions/MFA rows present. Not just app_users IDs.
- `roles.json`: app-prefixed role flags, membership options and global/schema default ACLs, without passwords.
  Operators must inventory any non-prefixed application login separately.
- `manifest.json`: required filenames and SHA-256 checksums, revision, every
  public/Auth table's count and private canonical full-row hash, application
  columns/constraints/triggers/policies/owners/ACL/function definitions.

Checksums detect damage, not malicious replacement of both files and manifest.
Keep the encrypted bundle and its signed receipt/checksum in independently
controlled storage. No identities or row hashes belong in the public handoff.
This helper is small-project tooling: it reads rows into memory; reassess for a
substantially larger database. It never restores or writes to the source.

## Private operator preparation (after approval)

1. Approve extraction purpose, operator, storage location/key custodian, recovery
   target and retention first. Use an encrypted volume outside Git/cloud-sync
   folders, mode 0700 directory/0600 files. Disable shell tracing, session capture,
   debug logs, core dumps and any automated transcript upload. Do not paste secrets.
2. Confirm the exact Connect-dialog endpoint/user, TLS CA and `sslmode=verify-full`.
   Use a protected libpq service file and passfile; obtain credentials through the
   authorized secret channel only. No password in URL/argv/environment dumps.
   Example service (placeholders only):

   ```ini
   [event_radar_backup]
   host=APPROVED_SESSION_POOLER_HOST
   port=5432
   dbname=postgres
   user=APPROVED_ADMIN_POOLER_USERNAME
   sslmode=verify-full
   sslrootcert=/private/approved-ca.pem
   passfile=/private/event-radar.pass
   ```

   Passfile format is `host:port:database:user:password`; write via a secure editor
   or secret-manager file injection, escape colon/backslash per libpq, chmod 0600.
   Set PGSERVICEFILE to the private service file. Clear unrelated PGHOSTADDR,
   PGPASSWORD, PGOPTIONS and other libpq overrides in the operator environment.
3. Record PG client/server and Supabase CLI versions. Run `supabase --help`,
   `supabase db --help`, `supabase db dump --help` before using CLI flags. In a
   private offline workspace, configure a compatible Supabase/Postgres version.
   The supported CLI triplet is role-only, schema, then data-only/use-copy.
   Use the CLI's protected password prompt with a **password-free** `--db-url`;
   never put a secret in `--password` or `--db-url`. If the installed version
   cannot prompt safely, stop and use the named-service PG17 capture below.
   Do not use debug/dry-run output that could reveal credential-bearing commands.
   Keep all CLI output files private and encrypted, including error logs.
4. Freeze application writes, Auth signups/account changes and application DDL
   for the recovery baseline; a CLI triplet otherwise has separate snapshots.
   The supplemental helper shares a snapshot but cannot freeze external Auth
   configuration. Recheck revision=0001 and count=2 privately. If containment is
   done first, record that fact; containment is independently approved/committed.
5. Securely record recovery dependencies separately: exact Auth migration/service
   version and trusted schema bootstrap, extensions/versions, project Auth/JWT
   settings, redirect/SMTP/OAuth configuration, signing/encryption-key handling,
   application-role/login definitions, database settings and approved source SHA.
   SQL-login passwords are not in these dumps; regenerate on recovery. Auth password
   hashes are sensitive and are in Auth data. OAuth/SMTP/Render secrets, JWT signing
   keys and Supabase encryption root keys are not supplied by a logical dump.
   Encrypted MFA/Vault/column data may require the original encryption root key:
   follow the Supabase transfer guide's key-copy procedure under separate approval.
   Storage object bytes and Edge Function code are not covered; if used, inventory
   and back them up separately or declare recovery blocked. Do not silently omit them.

## Capture and protect (templates; not executed on hosted Supabase)

Use an approved PG17 binary directory on PATH and locked Python dependencies.
`PRIVATE_ROOT` is an approved encrypted, non-repository directory; `BUNDLE` must
not already exist. No hosted credentials are embedded in these commands.

```sh
set +x
set -euo pipefail
umask 077
export PGSERVICEFILE=/private/event-radar-services.conf
BUNDLE="$PRIVATE_ROOT/e2-pre-migration"
pg_dump --version
uv run python scripts/database_recovery.py capture "$BUNDLE" --service event_radar_backup
uv run python scripts/database_recovery.py check "$BUNDLE"
tar -C "$PRIVATE_ROOT" -cf - e2-pre-migration | age -R /private/approved-recipients.txt -o "$PRIVATE_ROOT/e2-pre-migration.tar.age"
sha256sum "$PRIVATE_ROOT/e2-pre-migration.tar.age" > "$PRIVATE_ROOT/e2-pre-migration.tar.age.sha256"
```

A failed capture leaves no valid manifest; treat the directory as incomplete,
quarantine it privately and start a new destination after investigating. Do not
publish subprocess stderr, SQL or failing rows. A successful capture/check is
**not** a recovery success. Verify decryption using an independently held key,
copy ciphertext to access-controlled off-site storage, verify retrieved ciphertext
checksum and authenticate the receipt. Owner-approved proposed retention: retain
the pre-migration bundle for 30 days and until recovery/cutover is accepted,
whichever is longer; review deletion after that. Restrict access to the named
operator/key custodian, record accesses and securely remove decrypted working
copies after validation. Do not promise secure file shredding on SSDs; use encrypted
scratch-volume/key disposal and documented retention controls.

## Isolated restoration and validation

Never execute a whole public archive, roles dump, or Auth DDL against an active
Supabase project. It may contain provider default ACLs/owners that the hosted
postgres role cannot restore. Restoring those defaults is not a migration need.
Use a new, private recovery target with outbound network/providers disabled.

For a bare disposable PG17 drill, create only needed owner/grantee role stubs and
then reviewed app role attributes/membership and global defaults from roles.json, without secrets or
privileged provider memberships. Provision the exact trusted Auth schema version
from the matched Supabase distribution, not invented table definitions. Synthetic
tests use a small users/identities analogue and existing isolated cluster roles;
they do **not** prove actual GoTrue recovery or cross-cluster role provisioning.
Schema-filtered pg_dump does not preserve global default ACLs. After recreating
the dedicated owner on a fresh cluster, reinstate its reviewed global defaults:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE event_radar_migrator
  REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, event_radar_api, event_radar_research;
ALTER DEFAULT PRIVILEGES FOR ROLE event_radar_migrator
  REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated, event_radar_api, event_radar_research;
ALTER DEFAULT PRIVILEGES FOR ROLE event_radar_migrator
  REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated, event_radar_api, event_radar_research;
```

Only use this block when the bundle contains the hardened roles; E0 need not have
them. Compare against roles.json and explicitly review any additional defaults.
No provider-global defaults are restored. The row/schema helper intentionally does
not provision roles or certify membership/global-default parity; that is a separate
mandatory operator check, not a successful helper exit implication.

On a new real Supabase recovery project, let the platform provision managed schemas
and roles, use the supported filtered CLI transfer, and review the application
archive TOC for app-only restoration instead of replaying provider ACL entries.
If matching Auth schema/key compatibility cannot be established, stop.

For the bare isolated drill only, `event_radar_restore` must resolve to the approved
new loopback target. Confirm current_database/server_addr/port and that public is
empty before removing its empty default schema; never use CASCADE to clear an
unknown target. Do not use these bare-cluster commands on hosted Supabase:

```sh
# After verified isolated target, trusted Auth bootstrap and reviewed role setup:
psql service=event_radar_restore -X -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public'
pg_restore --exit-on-error --single-transaction --dbname=service=event_radar_restore "$BUNDLE/public.dump"
pg_restore --exit-on-error --single-transaction --dbname=service=event_radar_restore "$BUNDLE/auth.dump"
uv run python scripts/database_recovery.py verify "$BUNDLE" --service event_radar_restore
```

Auth foreign-key cycles/triggers may require the supported Supabase restore recipe
and scoped replica-mode authority on the **isolated** target. Do not globally
disable security or blindly ignore errors. Both phases must succeed; a failed
second phase means the whole recovery is unverified. Recreate the disposable target
for a fresh attempt. Never continue from a partially restored target as if complete.

Validation must include exact private app_users canonical comparison (all columns,
not only IDs/count), all other public/Auth row comparisons and revision, plus
catalog/security comparison. Verify role flags/membership and schema/default ACLs
against the private inventory, then run quarantine or verify_hardening as appropriate
on the isolated target. Compare counts privately including users/identities links,
seven active triggers at E2, all twelve protected tables, API/research grants and
browser/runtime denial. Where provider-specific restore legitimately changes
ownership, require an explicitly reviewed mapping and equivalent privilege checks;
do not suppress a failed comparator. Test actual Auth login/session behavior on the
isolated compatible Supabase stack only with separately approved accounts/secrets.
Do not send email, AI or Telegram requests. Public evidence: counts and PASS/FAIL
only; store hashes, identities and diagnostics privately.

Before full migration, require a real bundle that decrypts and restores with these
checks, and an approved recovery/cutover decision. Restore to a new target and
separately approve switching services; never overwrite the live project on a hunch.
A failure after upgrade commit calls for reviewed forward repair or this isolated
recovery path. Transaction rollback remains the first response before commit.

Public documentation review included the [17.11 compatibility changelog](https://supabase.com/changelog/postgres-15-19-17-11-breaking-changes).
Event Radar migrations do not introduce the affected custom operators/ltree/GiST
features. The actual recovery target still needs extension/version inventory;
no hosted extension assessment or repair was performed here.
