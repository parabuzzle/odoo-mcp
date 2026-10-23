# Docker HTTP service

This service exposes the existing Odoo tools at `/mcp` using Streamable HTTP.
It serves **one operator-configured Odoo connection**. Every approved person acts
through that same Odoo user, with that user's Odoo permissions. It is not a
multi-tenant credential vault or per-user Odoo impersonation service.

ChatGPT authenticates to the bridge through OAuth. The bridge authenticates to
Odoo using a separately mounted API key. Odoo credentials never belong in client
registration, OAuth tokens, tool arguments, or chat. Use a restricted Odoo
integration account; bridge read-only policy adds a second boundary.

All ORM calls pin the selected company through `allowed_company_ids`,
`company_id`, and `force_company`. `ODOO_COMPANY_ID` defaults to `1` and is
operator-configured, not a tool argument. Odoo ACLs and record rules still apply;
company-neutral records can remain visible. Stock and location queries also
filter explicitly by company, and location results identify their owner.

## Sign-in and dynamic registration

The HTTP extra uses the pinned FastMCP OIDC proxy for discovery, authorization
code + S256 PKCE, consent, CIMD, dynamic client registration, and token storage.
No local password database or unauthenticated HTTP mode is provided.

For Google Workspace set `MCP_OIDC_PROVIDER=google`,
`MCP_OIDC_CONFIG_URL=https://accounts.google.com/.well-known/openid-configuration`,
and `MCP_GOOGLE_WORKSPACE_DOMAIN` to the exact Workspace domain. Register a Google
OAuth web client with an **Internal** audience. Google mode requests
`access_type=offline` and `prompt=consent`, and verifies the signed `hd` claim
against that domain in addition to the explicit user allowlist. The `hd` request
parameter is only a sign-in hint; the signed claim is the enforcement boundary.
Keep scopes as `openid profile email`; Google's offline flow does not use an
`offline_access` scope. See [Google's server-side OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server#offline).

Before deploying, register one confidential web application with your chosen
OIDC provider. Configure this exact callback:

```
https://odoo-mcp.example.com/auth/callback
```

The provider must issue signed ID tokens with an issuer, subject, audience, and
expiry, and publish its JWKS. We verify ID tokens against the registered client
ID, including for providers with opaque access tokens. For email allowlists,
the provider must emit `email_verified: true`; otherwise use subject IDs.
Restrict the provider application to the intended organization/users and enable
MFA there. The local allowlist is enforced again on every authenticated request.

Refresh requires the provider to return refresh tokens. Some providers require
`offline_access` in `MCP_OIDC_SCOPES` or provider-side offline-access settings.
Without refresh, users must reconnect when the upstream authorization expires.

Once deployed, add `https://odoo-mcp.example.com/mcp` to ChatGPT and select OAuth.
Use CIMD or DCR without manually supplying client credentials. Complete sign-in
and the consent screen. Registration alone never grants Odoo access. Discovery
and protocol endpoints live at the origin root; do not mount behind a URL prefix.

## Configuration contract for the deployment repository

All settings support either `NAME` or a UTF-8 mounted `NAME_FILE`, never both.
Use `_FILE` for secrets so they do not appear in container environment inspection.
The HTTP service deliberately does not load a repository `.env` file.

| Setting | Meaning |
| --- | --- |
| `MCP_PUBLIC_URL` | Required public HTTPS origin, without `/mcp` |
| `MCP_OIDC_CONFIG_URL` | Required HTTPS OIDC discovery URL |
| `MCP_OIDC_CLIENT_ID` | Application registered once at the identity provider |
| `MCP_OIDC_PROVIDER` | `generic` (default) or `google` |
| `MCP_GOOGLE_WORKSPACE_DOMAIN` | Required exact domain for Google; matched against signed `hd` |
| `MCP_OIDC_CLIENT_SECRET_FILE` | Mounted OIDC application secret |
| `MCP_OAUTH_SIGNING_KEY_FILE` | Mounted high-entropy secret, at least 32 bytes; generate with `secrets.token_urlsafe(48)` |
| `MCP_ALLOWED_SUBJECTS` | Comma-separated exact OIDC subject IDs (preferred) |
| `MCP_ALLOWED_EMAILS` | Alternatively, comma-separated exact verified emails; case-insensitive |
| `MCP_OIDC_SCOPES` | Default `openid profile email`; add `offline_access` if your provider needs it |
| `MCP_OIDC_TOKEN_AUTH_METHOD` | `client_secret_basic` (default) or `client_secret_post`, per provider |
| `ODOO_URL` | Required HTTPS Odoo origin |
| `ODOO_DB` | Required Odoo database name |
| `ODOO_USERNAME` | Required restricted integration user |
| `ODOO_COMPANY_ID` | Single company for all tools; positive integer, default `1` |
| `ODOO_API_KEY_FILE` | Mounted Odoo API key |
| `MCP_STATE_DIR` | OAuth storage path; default `/data/oauth` |
| `MCP_WRITE_TOOLS` | Empty by default. Comma-separated exact write tool names, e.g. `create_task,update_task` |

At least one non-empty identity allowlist is mandatory. If both are supplied,
either can authorize the user. Wildcards are rejected. New tools are not
automatically classified as read-only. Disabled tools are absent from discovery
and cannot be called directly. Write annotations describe the enabled tools;
they are not a substitute for the backend allowlist or Odoo permissions.

Contact `image_url` fetching is disabled in HTTP mode to avoid exposing an
arbitrary server-side fetch facility. Existing stdio behavior is retained.

HTTP list limits must be between 1 and 500. Remote RPC searches and group queries
also have a 500-record/group bound, including internal searches without an
explicit limit. An operation needing a larger complete set fails rather than
silently truncating accounting totals. Narrow its filters. Tool responses are
capped at 1 MiB. Eight tool requests may be admitted at once; their Odoo execution
is serialized. Excess requests fail with a busy response. Use container memory
and CPU limits as well; bounded results do not eliminate database query costs.

## Image and runtime

Build locally:

```sh
docker build -t odoo-mcp:local .
```

The CI workflow tests and builds PRs without publishing. Each push to `main`
publishes `main` and `sha-<full-commit>` tags to `ghcr.io/<owner>/<repository>`
after all checks pass. Pushing a `v*` release tag also publishes a versioned image.
Manual workflow runs only validate. Registry package visibility must be configured
by the repository owner; public GHCR packages allow anonymous pulls. Private
packages require registry credentials on the Ansible-managed Docker host.
CI publishes the exact image that passed the smoke test and vulnerability gate,
without rebuilding it. Python dependencies and build tooling use hash-locked
requirements. The runtime excludes pip and build tooling and includes package
and license inventories under `/usr/share/odoo-mcp`.
The publishing job writes the pullable image digest to its GitHub Actions summary.
Your deployment repository should pin that reference, for example
`ghcr.io/parabuzzle/odoo-mcp@sha256:<digest>`, rather than the moving `main` tag.
No Ansible or production
deployment inventory lives in this repository.

Runtime requirements:

- One container / one worker. Odoo RPC calls are serialized off the HTTP event
  loop because the shared Odoo session is not thread-safe. Do not scale this
  file-backed service to multiple replicas without replacing the storage and
  revisiting concurrency.
- Container port `8000`, listening on all container interfaces. Expose it only to
  the HTTPS reverse proxy, not directly to the internet.
- Run as UID/GID `10001:10001`. Mount a writable persistent volume at `/data`.
  Pre-create bind mounts with matching ownership and mode `0700`.
- Mount secret files read-only, readable by UID 10001. Use a read-only root
  filesystem, a `/tmp` tmpfs, drop capabilities, and enable no-new-privileges.
- The reverse proxy must preserve the public `Host`, terminate TLS, limit
  request rates (especially `/register`, `/authorize`, and `/token`), and allow
  requests up to 2 MiB at `/mcp`. OAuth requests are capped at 64 KiB in the app.
  Set an appropriate tool timeout (for example 180 seconds); **do not retry
  POSTs automatically**, since a write may have completed despite a timeout.
- Do not log Authorization headers, request/response bodies, or OAuth callback
  query strings at the proxy. Application HTTP access logs are disabled.
- Egress is needed to Odoo, your OIDC provider/JWKS, and public CIMD documents.
  The service does not trust incoming forwarded headers.

Example runtime shape (the referenced files belong in private deployment
configuration, not this repo):

```sh
docker run --name odoo-mcp --restart unless-stopped \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --env-file /etc/odoo-mcp/service.env \
  --mount type=bind,src=/etc/odoo-mcp/secrets,dst=/run/secrets,readonly \
  --mount type=volume,src=odoo-mcp-data,dst=/data \
  -p 127.0.0.1:8000:8000 \
  odoo-mcp:local
```

Use a private Docker network instead of a loopback port when the reverse proxy
is also containerized. Configure `*_FILE` paths beneath `/run/secrets` in the
private env file. TLS certificates belong to your existing reverse proxy.

## Storage, revocation, and operations

OAuth grants and provider tokens are encrypted on the persistent volume with
a key derived from the separately mounted signing secret. Keep the volume and
secret stable across restarts. Backups of the volume are sensitive; encryption
does not protect against an attacker controlling the running container.

Issued bridge access tokens last 15 minutes. `/revoke` invalidates the entire
local grant, including related access and refresh tokens; it does not revoke
the shared Odoo key or the user's identity-provider account. To remove a person,
remove them from the configured allowlist and restart. For a full emergency
reset, stop the service, replace the signing secret and replace the OAuth state
volume; all clients must register/connect again. Treat restoration of old OAuth
state as potentially restoring revoked grants, and rotate the signing key when
restoring backups. Rotate the Odoo key independently by replacing its secret
file and restarting the container.

Refresh tokens are single-use. Reusing a consumed token revokes its whole local
grant, including newly issued sibling tokens, and requires reconnection. Grant
operations (including transparent refresh, code exchange, and revocation) are
serialized in this single-process deployment. In-flight tool calls already
authorized before revocation may finish. Upstream errors are replaced with
generic messages before the OAuth library can expose their diagnostics.

`GET /healthz` is unauthenticated **liveness only**. It does not log into Odoo or
prove the OIDC/Odoo services are reachable. Invalid configuration prevents
startup. Deployment acceptance should include a real ChatGPT authorization and
one read tool, followed by reconnect/revocation checks. Offline tests use fake
OIDC/Odoo services and do not establish compatibility with your chosen provider.

Audit logs contain tool names, a hash of the authenticated subject, outcome, and
elapsed time. They omit tool arguments/results. Secrets are redacted from legacy
logs, and raw RPC exceptions are not returned through HTTP tool results.

## Development

```sh
pip install -e '.[http,test]'
python -m pytest tests -q
python test_schema_layer.py
```

The original `odoo-mcp` / `python -m odoo_mcp.server` commands continue to use
stdio and load local `.env` settings. `odoo-mcp-http` starts the HTTP service.

For release validation on Python 3.12, install `requirements-build.lock` and
`requirements-test.lock` with `pip install --require-hashes -r ...`, then install
the project with `pip install --no-deps --no-build-isolation .`.
Regenerate locks deliberately with uv 0.13.1:

```sh
uv pip compile pyproject.toml --extra http --python-version 3.12 --universal --generate-hashes -o requirements-http.lock
uv pip compile pyproject.toml --extra http --extra test --python-version 3.12 --universal --generate-hashes -c requirements-http.lock -o requirements-test.lock
uv pip compile requirements-build.in --python-version 3.12 --universal --generate-hashes -o requirements-build.lock
```

Run the security suite and rebuild/scan after dependency updates. Dependabot
updates still need lock regeneration and review. See
[`deployment-handoff.txt`](deployment-handoff.txt) for the private Ansible repo's
deployment instructions; no Ansible inventory or secrets belong here.
