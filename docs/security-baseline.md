# E0 secrets and security baseline (WP9)

Scope: accepted WP8 source plus bounded WP9 ignore/static-check changes. This note
records configuration locations and regression protections; it is not proof that
all historical commits, hosted artifacts, accounts or provider logs are secret-free.
No provider settings, hosted database, deployment or personal runtime was changed.

## Configuration locations (names and classifications only)

| Location | Names | Purpose / classification |
| --- | --- | --- |
| GitHub personal production workflow secrets | EVENT_RADAR_STATE_TOKEN | Privileged private-state repository access; personal workflow only |
| GitHub personal production workflow secrets | OPENAI_API_KEY | Privileged research provider credential; personal workflow only |
| GitHub personal production workflow secrets | TELEGRAM_BOT_TOKEN | Privileged bot credential; personal workflow only |
| GitHub personal production workflow secrets | TELEGRAM_CHAT_ID, TELEGRAM_OWNER_USER_ID | Private recipient/owner identifiers; personal workflow only |
| GitHub Product Foundation CI | TEST_DATABASE_URL | Explicit disposable local test infrastructure; no hosted credentials; never copied to browser |
| Compose development/test services | POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD | Deliberately synthetic local development/test values; not Supabase access |
| Render API environment | DATABASE_URL | Secret-bearing backend connection configuration; exact Supabase session-pooler configuration, never browser-visible |
| Render API environment | SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY | Public project/application identifiers; publishable key is not user identity or a privileged credential |
| Render API environment | SUPABASE_JWT_AUDIENCE, WEB_ORIGINS | Non-secret authentication policy and exact-origin CORS allowlist |
| Render API environment | PYTHON_VERSION, UV_VERSION, PORT | Non-secret runtime configuration |
| Vercel web build environment | VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY, VITE_API_URL | Only intended public browser configuration; assume every VITE value is publicly readable |
| Supabase provider / authorized owner environment | Database password; staging-user passwords | Privileged connection/user credentials; secure provider/local entry only, never Git, chat, screenshots, Vercel or ordinary CI |
| Supabase provider | Signing keys and Auth policy | Provider-owned; no JWT shared signing secret or service-role/secret key is needed by this backend/browser authentication implementation |

SUPABASE_SECRET_KEY, SUPABASE_SERVICE_ROLE_KEY, JWT signing secrets, DATABASE_URL,
TEST_DATABASE_URL, OPENAI_API_KEY and TELEGRAM_BOT_TOKEN are prohibited browser inputs.
Do not rename privileged credentials with VITE_ to make them available. Public
publishable keys identify the application/project; only validated user access tokens
identify a user. Tokens/passwords are never acceptable log or fixture data.

The root .env.example intentionally contains personal-runtime names and backend
foundation names together for reference. Do not import that file wholesale into
Render. Render does not need personal OpenAI/Telegram credentials. Backend product
configuration reads process variables independently of legacy personal .env loading.
web/.env.example contains only the three public names with empty values.

## Git and local-file protection

Tracked root ignore rules cover .env and environment overrides, virtual environments,
node_modules, web build/coverage output, the two private personal config files,
.private-state, state JSON, generated packets/output and audit artifacts. WP9 adds
.vercel/ at all directory levels so provider metadata does not depend on one owner's
untracked web/.gitignore. No provider metadata or environment file was opened/copied.

The pre-existing web/.gitignore remains unchanged and untracked. Its .env* rule can
mask even web/.env.example in local check-ignore --no-index output; that example is
already intentionally tracked and remains so. A clean clone uses the tracked root
exception for examples. Do not overwrite the owner's local file to simplify status.
Tracked .env.example, web/.env.example and data/hikes.json remain intentional inputs.
Ignore rules do not untrack accidentally committed files: tracked-path auditing is
also required. Never copy personal state into browser public assets or test fixtures.

Private runtime paths remain config/user_context.json,
config/personal_experience_preference_context.md, state/telegram_offset.json,
state/permanent_directions.json, state/temporary_directions.json and .private-state/.
See e1-core-coexistence-technical-note.md for import-time legacy settings and audit
artifact sensitivity. No personal contents were needed for this audit.

## Bounded static checks

```bash
uv run python scripts/check_security.py
uv run python scripts/check_security.py --dist /path/to/isolated/web/dist
uv run pytest tests/test_security_baseline.py
```

The source check uses git ls-files, including staged additions. It never enumerates
ignored private files. Prohibited tracked paths fail before their contents are read.
It detects selected privileged credential formats, service-role JWTs, private keys,
and credential-bearing PostgreSQL URLs. Only the exact existing disposable/local
connection examples are allowed in source; PostgreSQL URLs are prohibited in dist.
It checks explicit browser import.meta.env access against the three VITE names and
Vite built-ins, rejecting dynamic access and custom exposure mechanisms for review.
Browser examples must contain only allowed names and empty values.

Artifact checking rejects those credential indicators and personal runtime filenames.
Failures report category/path only, never matched values. Synthetic regression tests
prove unsafe credentials, service-role JWTs, private paths and browser accesses fail;
a deliberately unsafe artifact makes the CLI exit nonzero without echoing its value.
Public publishable-key examples, names and approved local-only examples do not fail.

This is a bounded regression aid, not entropy scanning or proof against arbitrary
encodings, unknown password formats, copied private prose without recognizable
markers, historical exposure, or malicious code. Review remains necessary. Do not
weaken findings with broad exclusions. If a genuine secret is found, report only
category/path and stop for the execution lead before account actions/history rewriting.

## Frontend artifact proof without reading provider files

WP9 built the actual tracked web sources/lockfile in a disposable directory, without
local .env overrides, .vercel files or provider configuration. Unit tests ran with
no live configuration. Build-only public inputs were synthetic; eight backend-only
variables carried unique synthetic sentinels. Public configuration was present in
the built JavaScript; every backend sentinel was absent. All three generated files
passed the artifact scanner. The temporary build was removed afterward.

This avoids Vite implicitly reading local provider environment files during a normal
in-place build. It is not an inspection or exposure claim about the existing hosted
Vercel bundle. In clean GitHub CI, the ordinary npm build is followed by artifact
checking; no provider environment values are supplied.

## Authorization and runtime isolation

Existing auth/identity.py obtains one Bearer header and constructs AuthenticatedUser
only after verifier success. Asymmetric signature/issuer/audience/expiry/subject and
legacy authoritative Auth-server behavior remain unchanged. API get_session resolves
get_current_user before user-specific engine/session access. Query/body/custom-header
IDs cannot select an app_users row. Test dependency overrides live in tests; there is
no deployed bypass configuration.

Existing deterministic tests cover invalid/missing tokens, malformed/unsupported
algorithms, claim/signature failures, request manipulation, auth-before-database,
sanitized errors/logs and exact-origin CORS. The accepted startup guard blocks private
runtime imports/files, network and writes, including DB/migration/provider activity.
No verifier rewrite or duplicate auth test suite was introduced.

## CI isolation and evidence

Product Foundation CI retains contents:read, pinned actions, separate concurrency,
all five required live PostgreSQL checks, always-run test-container cleanup, and
all Python/web gates. WP9 adds tracked-source scanning to Python and built-artifact
scanning after the web build. No production secrets, private-state checkout, hosted
migration, personal pipeline command, deployment or write permissions are added.
The original event-radar.yml production workflow is unchanged.

WP9 push alone does not trigger this workflow (the temporary branch trigger names
WP7). No new GitHub run is implied. Accepted WP7 live PostgreSQL evidence remains
run 37156432123. A future authorized PR/main run executes the additional checks.

## Safe future configuration changes

1. Classify each value before adding it: public build configuration, backend secret,
   personal private state, or disposable local fixture. Keep names/examples in Git;
   keep values in the designated secure provider/environment boundary.
2. Enter provider values directly using authorized owner/provider tooling; never
   paste secrets in chat, command logs, commits or screenshots. Do not inspect/copy
   provider-generated local files to obtain evidence.
3. Review the staged diff and run source/artifact checks plus auth/isolation tests.
   Use synthetic sentinels in an isolated build, never live credentials for leak tests.
4. Provider changes/deployments require their own authorized package. Preserve email
   confirmation, exact-origin CORS and backend token validation. A VITE change requires
   a rebuild, but WP9 does not perform one on hosted infrastructure.
5. Rotate exposed staging passwords before live reuse through the owner-controlled
   process. This audit did not use old credentials or claim that rotation occurred.
