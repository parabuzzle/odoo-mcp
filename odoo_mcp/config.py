"""Configuration shared by stdio and the optional HTTP service."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def setting(name: str, default: str = "") -> str:
    """Read an environment setting or its mounted NAME_FILE, never both."""
    value, filename = os.environ.get(name), os.environ.get(f"{name}_FILE")
    if value is not None and filename is not None:
        raise ValueError(f"Set only one of {name} and {name}_FILE")
    if filename is not None:
        try:
            return Path(filename).read_text(encoding="utf-8").strip()
        except OSError:
            raise ValueError(f"Cannot read {name}_FILE") from None
    return value.strip() if value is not None else default


def required(name: str) -> str:
    value = setting(name)
    if not value:
        raise ValueError(f"{name} or {name}_FILE is required")
    return value


def https_url(name: str, value: str, *, origin_only: bool = False) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or (origin_only and parsed.path not in ("", "/"))):
        raise ValueError(f"{name} must be an HTTPS {'origin' if origin_only else 'URL'} without credentials, query, or fragment")
    return value.rstrip("/")


def csv_setting(name: str) -> frozenset[str]:
    return frozenset(x.strip() for x in setting(name).split(",") if x.strip())


@dataclass(frozen=True)
class HTTPSettings:
    public_url: str
    oidc_config_url: str
    oidc_client_id: str
    oidc_client_secret: str = field(repr=False)
    signing_key: str = field(repr=False)
    allowed_subjects: frozenset[str]
    allowed_emails: frozenset[str]
    write_tools: frozenset[str]
    state_dir: Path
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    token_endpoint_auth_method: str = "client_secret_basic"

    @classmethod
    def from_env(cls):
        subjects = csv_setting("MCP_ALLOWED_SUBJECTS")
        emails = frozenset(x.casefold() for x in csv_setting("MCP_ALLOWED_EMAILS"))
        if not subjects and not emails:
            raise ValueError("An explicit MCP_ALLOWED_SUBJECTS or MCP_ALLOWED_EMAILS allowlist is required")
        if any("*" in item for item in subjects | emails):
            raise ValueError("Identity allowlists do not accept wildcards")
        key = required("MCP_OAUTH_SIGNING_KEY")
        if len(key.encode()) < 32:
            raise ValueError("MCP_OAUTH_SIGNING_KEY must contain at least 32 bytes; generate a random secret")
        scopes = tuple(setting("MCP_OIDC_SCOPES", "openid profile email").split())
        if "openid" not in scopes:
            raise ValueError("MCP_OIDC_SCOPES must include openid")
        method = setting("MCP_OIDC_TOKEN_AUTH_METHOD", "client_secret_basic")
        if method not in ("client_secret_basic", "client_secret_post"):
            raise ValueError("MCP_OIDC_TOKEN_AUTH_METHOD must be client_secret_basic or client_secret_post")
        # One operator-configured connection. Never accept credentials or an Odoo
        # destination from tool arguments, OAuth registrations, or browser users.
        https_url("ODOO_URL", required("ODOO_URL"), origin_only=True)
        for name in ("ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY"):
            required(name)
        return cls(
            public_url=https_url("MCP_PUBLIC_URL", required("MCP_PUBLIC_URL"), origin_only=True),
            oidc_config_url=https_url("MCP_OIDC_CONFIG_URL", required("MCP_OIDC_CONFIG_URL")),
            oidc_client_id=required("MCP_OIDC_CLIENT_ID"),
            oidc_client_secret=required("MCP_OIDC_CLIENT_SECRET"),
            signing_key=key,
            allowed_subjects=subjects,
            allowed_emails=emails,
            write_tools=csv_setting("MCP_WRITE_TOOLS"),
            state_dir=Path(setting("MCP_STATE_DIR", "/data/oauth")),
            scopes=scopes,
            token_endpoint_auth_method=method,
        )
