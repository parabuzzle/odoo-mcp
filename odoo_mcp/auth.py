"""OIDC-backed MCP OAuth. User identity is independent of the Odoo API key."""

import base64
import hashlib

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastmcp.server.auth.auth import PrivateKeyJWTClientAuthenticator
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from key_value.aio.stores.filetree import (
    FileTreeStore, FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from mcp.server.auth.provider import RefreshToken, TokenError
from mcp.server.auth.middleware.client_auth import AuthenticationError
from mcp.server.auth.settings import RevocationOptions
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .config import HTTPSettings


def identity_allowed(claims: dict, config: HTTPSettings) -> bool:
    """Only signed subjects or verified, explicitly allowed emails grant access."""
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        return False
    if subject in config.allowed_subjects:
        return True
    email = claims.get("email")
    return (claims.get("email_verified") is True and isinstance(email, str)
            and email.casefold() in config.allowed_emails)


class OdooOAuthProvider(OIDCProxy):
    """Use FastMCP for protocol handling, with local identity and grant policy.

    The small revocation override uses FastMCP's persisted grant stores. Keep the
    dependency pinned and run the OAuth integration tests when upgrading it.
    """

    def __init__(self, config: HTTPSettings):
        self.config = config
        config.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        encryption_key = base64.urlsafe_b64encode(HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=None, info=b"odoo-mcp-oauth-storage-v1",
        ).derive(config.signing_key.encode()))
        storage = FernetEncryptionWrapper(
            key_value=FileTreeStore(
                data_directory=config.state_dir,
                key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(config.state_dir),
                collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(config.state_dir),
            ),
            fernet=Fernet(encryption_key),
        )
        super().__init__(
            config_url=config.oidc_config_url,
            client_id=config.oidc_client_id,
            client_secret=config.oidc_client_secret,
            base_url=config.public_url,
            jwt_signing_key=config.signing_key,
            client_storage=storage,
            verify_id_token=True,
            required_scopes=list(config.scopes),
            extra_authorize_params={"scope": " ".join(config.scopes)},
            token_endpoint_auth_method=config.token_endpoint_auth_method,
            require_authorization_consent=True,
            enable_cimd=True,
            forward_resource=False,
            fastmcp_access_token_expiry_seconds=900,
            fallback_refresh_token_expiry_seconds=86400 * 7,
        )
        # Local revocation must work even if the IdP has no revocation endpoint.
        self.revocation_options = RevocationOptions(enabled=True)
        # profile/email/offline_access request identity information and refresh
        # capability; providers need not echo them in access-token scope claims.
        # Authorization to Odoo is governed by the verified identity allowlist.
        self.required_scopes = ["openid"]

    async def _extract_upstream_claims(self, idp_tokens):
        # The library validates signature, issuer, expiry, and audience against
        # this deployment's OIDC client. Never authorize from unverified JWTs.
        token = idp_tokens.get("id_token")
        identity = await self._token_validator.verify_token(token) if token else None
        if identity is None or not identity_allowed(identity.claims, self.config):
            raise TokenError("invalid_grant", "This account is not authorized for this Odoo connection")
        return None  # Do not copy identity information into client-visible JWTs.

    async def load_access_token(self, token):
        identity = await super().load_access_token(token)
        if identity is None or not identity_allowed(identity.claims, self.config):
            return None
        try:
            payload = self.jwt_issuer.verify_token(token)
        except Exception:
            return None  # Includes a token expiring between the two checks.
        mapping = await self._jti_mapping_store.get(key=payload["jti"])
        if mapping is None or await self._client_storage.get(
            key=mapping.upstream_token_id, collection="odoo_revoked_grants"
        ):
            return None
        # SDK revocation compares against the downstream client's ID. Also keep
        # the upstream access token out of the request authentication context.
        return identity.model_copy(update={
            "token": token, "client_id": payload["client_id"],
            "expires_at": int(payload["exp"]),
            "scopes": payload.get("scope", "").split(),
        })

    async def revoke_token(self, token):
        """Immediately invalidate the whole local grant, including sibling tokens."""
        kind = "refresh" if isinstance(token, RefreshToken) else "access"
        payload = self.jwt_issuer.verify_token(token.token, expected_token_use=kind)
        mapping = await self._jti_mapping_store.get(key=payload["jti"])
        if mapping is not None:
            # Durable tombstone also defeats a refresh already in flight when
            # revocation happens. Do not let that request resurrect the grant.
            await self._client_storage.put(
                key=mapping.upstream_token_id, value={"revoked": True},
                collection="odoo_revoked_grants",
            )
            await self._upstream_token_store.delete(key=mapping.upstream_token_id)
        await self._jti_mapping_store.delete(key=payload["jti"])
        if isinstance(token, RefreshToken):
            await self._refresh_token_store.delete(key=hashlib.sha256(token.token.encode()).hexdigest())

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        payload = self.jwt_issuer.verify_token(refresh_token.token, expected_token_use="refresh")
        mapping = await self._jti_mapping_store.get(key=payload["jti"])
        if mapping is None or await self._client_storage.get(
            key=mapping.upstream_token_id, collection="odoo_revoked_grants"
        ):
            raise TokenError("invalid_grant", "Authorization has been revoked")
        return await super().exchange_refresh_token(client, refresh_token, scopes)

    def get_routes(self, mcp_path=None):
        routes = super().get_routes(mcp_path)
        # The SDK's revocation form requires client_secret even for public
        # clients and its default authenticator doesn't support CIMD assertions.
        # Reuse FastMCP client authentication, accepting RFC 7009 public clients.
        authenticator = PrivateKeyJWTClientAuthenticator(
            provider=self, cimd_manager=self._cimd_manager,
            token_endpoint_url=self.config.public_url + "/revoke",
        )

        async def revoke(request):
            try:
                client = await authenticator.authenticate_request(request)
            except AuthenticationError:
                return JSONResponse({"error": "invalid_client"}, status_code=401)
            form = await request.form()
            value = form.get("token")
            hint = form.get("token_type_hint")
            if not isinstance(value, str) or not value or hint not in (None, "access_token", "refresh_token"):
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            token = await self.load_refresh_token(client, value) if hint == "refresh_token" else None
            token = token or await self.load_access_token(value)
            token = token or await self.load_refresh_token(client, value)
            if token is not None and token.client_id == client.client_id:
                await self.revoke_token(token)
            # RFC 7009: an unknown token is also a successful revocation.
            return Response(status_code=200, headers={"Cache-Control": "no-store"})

        return [Route("/revoke", revoke, methods=["POST"]) if route.path == "/revoke" else route
                for route in routes]
