# E2 database security remediation — prepared, not applied

Baseline E2 SHA: `51355c7fad3cfc0b60241b1a88cb660cd41f683b`. Target revision: `0006_hosted_access_hardening`, additive after unchanged revisions 0001–0005. Final implementation SHA and exact-head CI are in the handoff. E1 remains at `26b454f41c3513de29f8e3a2bdada5f82185e421`, draft/unmerged, with weekly activation pending. Accepted governance and product scope are unchanged. No hosted operation was executed in this assignment.

## Observed risk and authority

The execution lead's October 13, 2026 metadata inspection is the supplied baseline: project `event-radar`, ID `fbjwxfkzbxhkwixwypsa`, ACTIVE_HEALTHY, revision 0001, two app_users rows. app_users and alembic_version lack RLS and give anon/authenticated effective CRUD; postgres/supabase_admin public-schema defaults grant broad browser table privileges. No dedicated API/research role exists; postgres has BYPASSRLS. These are lead-observed facts, not independently revalidated here. No user identities or payloads were inspected. No backup or current deployed security state is claimed.

A browser key plus direct Data API access can bypass FastAPI ownership checks under that baseline. Migration bookkeeping exposure also permits tampering. Upgrading table structure alone does not prove secure runtime access: passing tests as postgres masks missing grants/RLS policies. See [hosted execution runbook](e2-database-security-runbook.md).

## Selected model

Supabase Auth → verified ordinary-account JWT → account-scoped FastAPI/services → trusted SQL role. Three NOLOGIN capability/ownership roles:

- `event_radar_api`: trusted cross-account backend capabilities, no ownership, SUPERUSER, BYPASSRLS, CREATEROLE, CREATEDB, replication or parent-role membership. A separately provisioned LOGIN inherits only this role. Browser identities are never mapped to SQL login roles.
- `event_radar_research`: independent regional-only capabilities; no private user/context/packet/delivery access. Separate credential, no activation implied.
- `event_radar_migrator`: separately controlled application object owner, NOLOGIN and no superuser/BYPASSRLS flag. Ownership deliberately permits administrative RLS bypass and DDL. It is never granted to runtime/browser roles. A migration operator may assume it only through reviewed administrative membership. Initial hardening additionally needs existing-owner/role/default-ACL administrative authority.

API RLS policies intentionally allow its trusted role across account rows; SQL privileges narrow operations/columns. **Database-enforced tenant isolation is not claimed.** JWT verification plus backend account predicates provide tenant isolation. Compromise of a runtime credential can expose multiple accounts within its permitted objects. There is no broad browser policy, SECURITY DEFINER helper, or new auth bypass.

## Privilege matrix

S = SELECT; I = INSERT; U(columns) = listed column updates only. No runtime DELETE, TRUNCATE, REFERENCES, TRIGGER, ownership or grant option. All 12 tables have RLS enabled. Every row below grants **nothing** to anon/authenticated (including inherited effective access checks) and nothing through PUBLIC. Migrator owns all listed tables, retaining administrative DDL/DML, except immutable/transition triggers still reject ordinary invalid DML. Administrators can intentionally alter protections; runtime cannot.

| Table | API role | Research role | Migrator/operator |
| --- | --- | --- | --- |
| alembic_version | None | None | Owner/admin bookkeeping |
| app_users | S, I, U(updated_at) | None | Owner |
| regional_universes | S | S, I, U(current_snapshot_id, updated_at) | Owner |
| regional_universe_snapshots | S | S, I | Owner |
| regional_research_runs | None | S, I, U(status, finished_at, snapshot_id, failure_code, diagnostics_payload, discovery_summary) | Owner |
| user_context_revisions | S, I | None | Owner, immutable DML trigger |
| curation_jobs | S, I, U(status, finished_at, failure_code, usage_payload) | None | Owner, transition trigger |
| weekend_packets | S, I | None | Owner, completed-claim/immutable trigger |
| delivery_bindings | S, I, U(status, consent, revoked_at) | None | Owner, transition trigger |
| delivery_challenges | S, I, U(consumed_at) | None | Owner, single-use trigger |
| delivery_intents | S, I, U(status, attempts, failure_code, updated_at) | None | Owner, transition trigger |
| delivery_attempts | S, I, U(status, failure_code, finished_at) | None | Owner, transition trigger |

The app_users UPDATE grant exists because context/challenge/curation serialization uses SELECT FOR UPDATE; PostgreSQL requires UPDATE permission on at least one column. It does not grant identity/timestamp-creation modification. ORM UPDATE grants match actual transition assignments. API gets no regional writes; public-export import is an operator/research-capability task, not API runtime work. Worker snapshots are insert/read only; it cannot edit research history or user data. No existing table columns, user rows, constraints or payloads are rewritten.

Application-defined functions: `reject_user_context_mutation()`, `protect_curation_job()`, `protect_weekend_packet()`, `protect_delivery_binding()`, `protect_delivery_attempt()`, `protect_delivery_challenge()`, `protect_delivery_intent()`. All stay invoker functions, become migrator-owned, get fixed `pg_catalog, public` search paths and have client/runtime EXECUTE revoked. Existing seven triggers remain attached and active. PostgreSQL invokes established triggers without needing runtime direct EXECUTE; restricted-login insert/transition tests prove this. No trigger creation right is given to runtime.

No application sequences exist: IDs are application-generated UUIDs. No runtime sequence grant is required. Future sequences created by the dedicated migrator have private defaults and require explicit grants if a later reviewed schema uses them. Unrelated provider sequences/functions are not altered.

Schema public: runtime gets USAGE only; CREATE is revoked from PUBLIC, browser and runtime roles, with effective inheritance checks. USAGE for existing provider/browser roles is retained because schema reachability alone grants no object data access and public may contain provider extensions. Migrator receives USAGE/CREATE. Database owner, provider roles and pg_catalog built-ins are not reconfigured; default TEMP capability is not administration of permanent application objects.

## Individual migration review

- 0001 creates identity rows/table with no RLS/ACL boundary. Existing records must be retained. Alembic's bookkeeping is outside model metadata and also needs explicit protection.
- 0002 creates regional identities, immutable-by-service snapshots and research attempts without RLS/ACLs. New ACLs prevent API writes and worker snapshot mutation; no E1 schema/history rewrite.
- 0003 enables context RLS and revokes PUBLIC, but direct/inherited client grants and trigger function EXECUTE need comprehensive review. Append-only trigger remains.
- 0004 protects curation/packet tables and direct browser ACLs, with immutable/claim triggers, but gives no non-owner runtime policy. Existing immutable behavior is retained.
- 0005 does similarly for binding/challenge/outbox/audit tables. New column grants permit only existing lifecycle transitions; triggers remain decisive.
- 0006 revokes table and column ACLs (table revocation alone does not remove column grants), enables RLS on all tables, installs role-specific policies, narrows grants, hardens application functions/defaults and transfers ownership to the dedicated migrator. Unknown policies, unsafe existing role attributes/parent memberships, global client defaults or effective inherited client access fail the transaction. Historical migrations remain byte-for-byte unchanged.

## Defaults and transaction decisions

Contain E0 first with separately approved `sql/security/quarantine_e0.sql`. It protects only the two existing tables, checks effective client denial, changes no data and commits independently. If full upgrade later fails, the original security gap does not reopen. If containment cannot acquire locks or inherited grants remain, it rolls back and the original exposure remains: keep services paused and stop for operator remediation.

Then upgrade 0001 → 0006 in one PostgreSQL transaction, not one invocation per intermediate revision. `alembic/env.py` explicitly disables per-revision transactions and accepts an operator/test-owned outer connection. 0002–0005's intermediate broad defaults cannot become externally visible before 0006 hardens them. Injected late failures prove rollback of tables, ACLs, ownership, role/default changes and revision advancement, with the committed quarantine and both user rows preserved. Initial migration holds locks: schedule maintenance and bound lock/statement timeouts.

Schema-level table/sequence/function defaults for current migration executor, postgres and supabase_admin are stripped of PUBLIC/browser/runtime grants where present. If the executor cannot change a provider role's ACL, stop; the specifically authorized administrator can run the relevant block of `provider_defaults.sql` separately. The migration skips an already-clean schema ACL, allowing independent administration without granting supabase_admin membership. It never silently ignores a dirty inaccessible ACL.

Per-schema revocation cannot cancel global defaults. Unexpected global browser table/sequence grants or direct global browser routine grants stop the migration for review. PostgreSQL's normal global PUBLIC EXECUTE for provider-created functions is not revoked globally because that could affect managed schemas. Existing application functions are explicitly private; **future Event Radar DDL must run as event_radar_migrator**, whose global defaults are private for tables, sequences and functions. That new role is application-only; changing its global defaults does not change provider-owned schema behavior. Public-schema default changes necessarily affect future objects by those creators in public; confirm this project has no unrelated public-schema consumers before approval. Do not extrapolate that this secures every provider function or schema.

## Verification and compatibility

The guarded port-55432 PostgreSQL fixture simulates anon/authenticated, postgres/supabase_admin defaults, E0 state, two synthetic users and column-level exposure. It checks all twelve tables, seven triggers, constraints, RLS, owner identities, effective table/column privileges, client read/insert/update/delete/truncate rejection and migration/DDL denial. Future table/sequence defaults are checked under both provider creator roles; dedicated-migrator table/sequence/function defaults are checked separately.

A separate real LOGIN inherits the API capability with no privileged memberships; it creates/readbacks contexts, runs fake AI #3 claims and packet persistence, verifies signed-JWT two-account API isolation, binds a synthetic private destination, queues/sends through a fake transport and revokes it. It cannot SET ROLE to the migrator or test administrator. Immutable context/packet triggers are also tested with the owner. A separate research LOGIN performs regional persistence and the actual E1 worker orchestration/replay with synthetic dependencies. No upstream/live collection or provider calls occur. Tests fail if run against a hosted URL; every destructive fixture retains the existing database identity/URL guards.

E1 worker service compatibility is tested, but its **scheduled deployment remains pending**. The existing scheduler database preflight reads alembic_version. It now recognizes 0006 for administrative compatibility checks, but the restricted worker cannot read bookkeeping; a future reviewed split between administrative schema attestation and worker execution is needed before configuring that role in the scheduler CLI. We did not grant bookkeeping access, change E1's branch, or activate anything.

Downgrade does not restore insecure grants. Crossing 0006 is refused except the explicitly flagged, identity-checked disposable test teardown. Hosted recovery is transaction rollback before commit, forward repair, or verified isolated backup restore after commit—not an automatic destructive downgrade.

See the final handoff for focused/full counts and exact-head CI. Existing connected pilot architecture, provisional AI #3 policy, private-only Telegram scope, and public V1 email requirement are unchanged.

## Local verification result

Nine focused security cases pass, including the real non-superuser migration executor. Full Python/PostgreSQL suite: **869 passed, one expected hosted-Supabase opt-in skip**. Frontend: **57 passed**. Ruff format/lint, mypy (111 source files), frontend lint/typecheck/build/security baseline and isolated E1 evidence restart pass. The new nine cases are mandatory non-skipped evidence in Product Foundation CI. The final handoff records the pushed SHA and exact-head CI result. No hosted data preservation result is claimed; the two unchanged rows in the migration proof are synthetic.
