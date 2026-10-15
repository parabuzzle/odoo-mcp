# Security

Report suspected vulnerabilities privately through the repository's GitHub
Security tab when private vulnerability reporting is enabled. Do not put keys,
OAuth tokens, customer records, or exploit details in public issues. If private
reporting is unavailable, ask the maintainer for a private reporting channel
without including sensitive details. Maintainers must enable private reporting
before publishing a supported release.

Only a specifically tested release image should be deployed. Development
branches are not supported production releases. The HTTP service is a
single-instance, single-Odoo-account deployment; see [the deployment
contract](docs/http-service.md). Every approved identity receives the configured
integration user's Odoo permissions. Keep HTTP write tools disabled unless
explicitly needed, and restrict the integration account independently in Odoo.

The supported deployment requires HTTPS, proxy rate and connection limits,
restricted container networking, runtime secrets, resource limits, and one
worker. Never expose port 8000 directly. OAuth registration is intentionally
public; it does not authorize access to Odoo. Protect OAuth storage and backups,
and keep it separate from its signing/encryption secret.

Security checks include offline OAuth regression tests, container smoke tests,
Git-history secret scanning, and image vulnerability scanning. Passing these
checks does not replace validation of Google Workspace, Odoo ACLs, and the actual
reverse proxy. Unfixed distribution advisories require ongoing review even when
the fixable-advisory CI gate passes.
