"""Offline HTTP/OAuth integration tests: no live Odoo or identity provider."""

import asyncio
import base64
import hashlib
import json
import re
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from authlib.integrations.httpx_client import AsyncOAuth2Client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration, OIDCProxy
from fastmcp.server.auth.cimd import CIMDDocument, CIMDFetcher
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp.types import TextContent
from starlette.testclient import TestClient

from odoo_mcp.auth import OdooOAuthProvider, identity_allowed
from odoo_mcp.config import HTTPSettings, setting
from odoo_mcp.http import READ_TOOLS, create_app
from odoo_mcp.server import OdooMCPServer

PUBLIC = "https://mcp.example.com"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "a" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


class FakeOdoo(OdooMCPServer):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return [TextContent(type="text", text="fake Odoo response")]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # Never load the project's .env or contact its database.
    monkeypatch.setenv("ODOO_API_KEY", "test-odoo-secret-never-send-to-clients")
    monkeypatch.delenv("ODOO_API_KEY_FILE", raising=False)
    config = HTTPSettings(
        public_url=PUBLIC, oidc_config_url="https://id.example.com/.well-known/openid-configuration",
        oidc_client_id="bridge-client", oidc_client_secret="test-oidc-secret",
        signing_key="test-signing-secret-" * 4,
        allowed_subjects=frozenset({"allowed-person"}), allowed_emails=frozenset(),
        write_tools=frozenset(), state_dir=tmp_path / "oauth",
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    discovery = OIDCConfiguration(
        issuer="https://id.example.com", authorization_endpoint="https://id.example.com/authorize",
        token_endpoint="https://id.example.com/token", jwks_uri="https://id.example.com/jwks",
        response_types_supported=["code"], subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
    )
    monkeypatch.setattr(OIDCProxy, "get_oidc_configuration", lambda *args, **kwargs: discovery)
    monkeypatch.setattr(OIDCProxy, "get_token_verifier", lambda self, **kwargs: JWTVerifier(
        public_key=public_key, issuer="https://id.example.com", audience="bridge-client", algorithm="RS256",
    ))
    user = {"sub": "allowed-person"}

    async def fake_tokens(*args, **kwargs):
        now = int(time.time())
        id_token = jwt.encode({"iss": "https://id.example.com", "aud": "bridge-client",
                               "iat": now, "exp": now + 3600, **user}, key, algorithm="RS256")
        return {"access_token": "upstream-access-secret", "refresh_token": "upstream-refresh-secret",
                "id_token": id_token, "token_type": "Bearer", "expires_in": 3600,
                "scope": "openid profile email"}

    monkeypatch.setattr(AsyncOAuth2Client, "fetch_token", fake_tokens)
    monkeypatch.setattr(AsyncOAuth2Client, "refresh_token", fake_tokens)
    return config, user


def make_client(config):
    backend = FakeOdoo()
    auth = OdooOAuthProvider(config)
    app = asyncio.run(create_app(config, backend=backend, auth=auth))
    return TestClient(app, base_url=PUBLIC, follow_redirects=False), backend, auth


def register(client):
    response = client.post("/register", json={
        "client_name": "Offline test client", "redirect_uris": [CALLBACK],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none",
        "scope": "openid profile email",
    })
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def authorization_code(client, client_id, **overrides):
    params = {"client_id": client_id, "redirect_uri": CALLBACK,
              "response_type": "code", "scope": "openid profile email", "state": "test-state",
              "code_challenge": CHALLENGE, "code_challenge_method": "S256", "resource": PUBLIC + "/mcp"}
    params.update(overrides)
    response = client.get("/authorize", params=params)
    assert response.status_code == 302, response.text
    consent_url = response.headers["location"]
    consent = client.get(consent_url)
    assert consent.status_code == 200, consent.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', consent.text).group(1)
    txn = re.search(r'name="txn_id" value="([^"]+)"', consent.text).group(1)
    approved = client.post(urlsplit(consent_url).path, data={"txn_id": txn, "csrf_token": csrf, "action": "approve"})
    assert approved.status_code == 302, approved.text
    upstream_state = parse_qs(urlsplit(approved.headers["location"]).query)["state"][0]
    callback = client.get("/auth/callback", params={"code": "fake-provider-code", "state": upstream_state})
    assert callback.status_code == 302, callback.text
    return parse_qs(urlsplit(callback.headers["location"]).query)["code"][0]


def exchange(client, client_id, code, verifier=VERIFIER, **extra):
    return client.post("/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "redirect_uri": CALLBACK, "code_verifier": verifier, "resource": PUBLIC + "/mcp",
        **extra,
    })


def login(client):
    client_id = register(client)
    response = exchange(client, client_id, authorization_code(client, client_id))
    assert response.status_code == 200, response.text
    return client_id, response.json()


def rpc(client, token, method="tools/list", params=None):
    return client.post("/mcp", headers={"Authorization": f"Bearer {token}",
                                      "Accept": "application/json, text/event-stream"},
                       json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def test_discovery_auth_required_and_host_boundaries(setup):
    config, _ = setup
    with make_client(config)[0] as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        metadata = client.get("/.well-known/oauth-authorization-server").json()
        assert metadata["registration_endpoint"] == PUBLIC + "/register"
        assert "S256" in metadata["code_challenge_methods_supported"]
        assert metadata["client_id_metadata_document_supported"] is True
        resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert resource["resource"] == PUBLIC + "/mcp"
        assert rpc(client, "bogus").status_code == 401
        unauth = client.post("/mcp")
        assert unauth.status_code == 401
        assert "resource_metadata" in unauth.headers["www-authenticate"]
        assert client.get("/healthz", headers={"Host": "attacker.example"}).status_code == 400
        assert client.post("/register", headers={"Origin": "https://evil.example"}, json={}).status_code == 403
        assert client.post("/register", content=b"x" * 65537).status_code == 413


def test_oauth_read_tool_write_denial_restart_and_revocation(setup):
    config, _ = setup
    client, backend, _ = make_client(config)
    with client:
        client_id, tokens = login(client)
        access = tokens["access_token"]
        listed = rpc(client, access)
        assert listed.status_code == 200, listed.text
        names = {x["name"] for x in listed.json()["result"]["tools"]}
        assert names == READ_TOOLS
        assert "create_task" not in names
        called = rpc(client, access, "tools/call", {"name": "list_projects", "arguments": {}})
        assert called.json()["result"]["content"][0]["text"] == "fake Odoo response"
        denied = rpc(client, access, "tools/call", {"name": "create_task", "arguments": {"name": "should not run"}})
        assert denied.json()["result"]["isError"] is True
        assert backend.calls == [("list_projects", {})]
        decoded = jwt.decode(access, options={"verify_signature": False})
        assert decoded["aud"] == PUBLIC + "/mcp"
        assert decoded["exp"] - decoded["iat"] <= 900
        assert "upstream-access-secret" not in str(tokens)
    # Actual encrypted file store is reused by a new provider/app instance.
    with make_client(config)[0] as restarted:
        assert rpc(restarted, access).status_code == 200
        refreshed = restarted.post("/token", data={"grant_type": "refresh_token",
                                   "client_id": client_id, "refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text
        revoked = restarted.post("/revoke", data={"client_id": client_id,
                                 "token": refreshed.json()["refresh_token"], "token_type_hint": "refresh_token"})
        assert revoked.status_code == 200, revoked.text
        assert rpc(restarted, access).status_code == 401
        assert rpc(restarted, refreshed.json()["access_token"]).status_code == 401
    for file in config.state_dir.rglob("*"):
        if file.is_file():
            data = file.read_bytes()
            assert b"upstream-refresh-secret" not in data
            assert b"upstream-access-secret" not in data


def test_pkce_code_replay_and_unapproved_identity(setup):
    config, user = setup
    with make_client(config)[0] as client:
        client_id = register(client)
        code = authorization_code(client, client_id)
        assert exchange(client, client_id, code, verifier="b" * 64).status_code in (400, 401)
        code = authorization_code(client, client_id)
        assert exchange(client, client_id, code).status_code == 200
        assert exchange(client, client_id, code).status_code in (400, 401)
        user["sub"] = "unapproved-person"
        code = authorization_code(client, client_id)
        denied = exchange(client, client_id, code)
        assert denied.status_code in (400, 401), denied.text


def test_identity_removed_on_restart(setup):
    config, _ = setup
    with make_client(config)[0] as client:
        _, tokens = login(client)
    restricted = replace(config, allowed_subjects=frozenset({"someone-else"}))
    with make_client(restricted)[0] as client:
        assert rpc(client, tokens["access_token"]).status_code == 401


def test_explicit_writes_and_image_fetch_disabled(setup):
    config, _ = setup
    config = replace(config, write_tools=frozenset({"create_task", "create_contact"}))
    client, backend, _ = make_client(config)
    with client:
        _, tokens = login(client)
        token = tokens["access_token"]
        tools = rpc(client, token).json()["result"]["tools"]
        assert next(t for t in tools if t["name"] == "create_task")["annotations"]["readOnlyHint"] is False
        result = rpc(client, token, "tools/call", {"name": "create_contact", "arguments": {
            "name": "Example", "image_url": "http://169.254.169.254/latest/meta-data/"}})
        assert result.json()["result"]["isError"] is True
        assert backend.calls == []


def test_verified_email_and_subject_rules(setup):
    config, _ = setup
    config = replace(config, allowed_subjects=frozenset(), allowed_emails=frozenset({"person@example.com"}))
    assert identity_allowed({"sub": "person", "email": "Person@Example.com", "email_verified": True}, config)
    assert not identity_allowed({"sub": "person", "email": "person@example.com", "email_verified": "true"}, config)
    assert not identity_allowed({"email": "person@example.com", "email_verified": True}, config)


def test_secret_file_conflict_and_fail_closed_config(monkeypatch, tmp_path):
    secret = tmp_path / "key"
    secret.write_text("fake-key\n")
    monkeypatch.delenv("TEST_SECRET", raising=False)
    monkeypatch.setenv("TEST_SECRET_FILE", str(secret))
    assert setting("TEST_SECRET") == "fake-key"
    monkeypatch.setenv("TEST_SECRET", "other")
    with pytest.raises(ValueError, match="only one"):
        setting("TEST_SECRET")
    monkeypatch.setenv("MCP_ALLOWED_SUBJECTS", "")
    monkeypatch.setenv("MCP_ALLOWED_EMAILS", "")
    with pytest.raises(ValueError, match="allowlist"):
        HTTPSettings.from_env()


def test_schema_cache_isolation():
    first, second = OdooMCPServer(), OdooMCPServer()
    assert first.projects._fields_cache is first.contacts._fields_cache
    assert first.projects._fields_cache is not second.projects._fields_cache


@pytest.mark.parametrize("method", ["none", "private_key_jwt"])
def test_cimd_without_registration_and_revocation(setup, monkeypatch, method):
    config, _ = setup
    client_id = "https://chatgpt.com/oauth/test-callback/client.json"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", alg="RS256", use="sig")
    doc = CIMDDocument(client_id=client_id, client_name="ChatGPT test",
                       redirect_uris=[CALLBACK], token_endpoint_auth_method=method,
                       grant_types=["authorization_code", "refresh_token"],
                       scope="openid profile email", jwks={"keys": [jwk]})

    async def fetch(self, url):
        assert url == client_id
        return doc

    monkeypatch.setattr(CIMDFetcher, "fetch", fetch)

    def assertion(endpoint):
        if method == "none":
            return {}
        now = int(time.time())
        return {"client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": jwt.encode({"iss": client_id, "sub": client_id,
                    "aud": PUBLIC + endpoint, "iat": now, "exp": now + 60,
                    "jti": endpoint + str(time.time_ns())}, key, algorithm="RS256", headers={"kid": "test-key"})}

    with make_client(config)[0] as client:
        code = authorization_code(client, client_id)
        token = exchange(client, client_id, code, **assertion("/token"))
        assert token.status_code == 200, token.text
        access = token.json()["access_token"]
        assert rpc(client, access).status_code == 200
        revoke = client.post("/revoke", data={"client_id": client_id, "token": access, **assertion("/revoke")})
        assert revoke.status_code == 200, revoke.text
        assert rpc(client, access).status_code == 401


@pytest.mark.parametrize("changes", [{"aud": "wrong-app"}, {"iss": "https://wrong-issuer.example"}, {"exp": 1}])
def test_invalid_upstream_identity_tokens_rejected(setup, changes):
    config, user = setup
    user.update(changes)
    with make_client(config)[0] as client:
        client_id = register(client)
        code = authorization_code(client, client_id)
        assert exchange(client, client_id, code).status_code in (400, 401)


def test_access_token_binding_expiry_and_revocation_client_ownership(setup):
    config, _ = setup
    client, _, auth = make_client(config)
    with client:
        client_id, tokens = login(client)
        access = tokens["access_token"]
        payload = jwt.decode(access, options={"verify_signature": False})
        for changes in ({"aud": "https://other.example/mcp"}, {"iss": "https://other.example"}, {"exp": 1}):
            invalid = jwt.encode({**payload, **changes}, auth._jwt_signing_key, algorithm="HS256")
            assert rpc(client, invalid).status_code == 401
        forged = jwt.encode(payload, b"untrusted-key" * 4, algorithm="HS256")
        assert rpc(client, forged).status_code == 401
        other = register(client)
        assert client.post("/revoke", data={"client_id": other, "token": access}).status_code == 200
        assert rpc(client, access).status_code == 200
        assert client.post("/revoke", data={"client_id": client_id, "token": access}).status_code == 200
        assert rpc(client, access).status_code == 401
        assert client.post("/token", data={"client_id": client_id, "grant_type": "refresh_token",
                                           "refresh_token": tokens["refresh_token"]}).status_code in (400, 401)


def test_oidc_offline_access_need_not_be_echoed_in_provider_token_scope(setup):
    config, _ = setup
    config = replace(config, scopes=("openid", "profile", "email", "offline_access"))
    with make_client(config)[0] as client:
        _, tokens = login(client)
        assert rpc(client, tokens["access_token"]).status_code == 200


def test_remote_results_redact_secrets_and_mask_legacy_rpc_errors(setup):
    config, _ = setup
    client, backend, _ = make_client(config)

    async def secret_result(name, arguments):
        return [TextContent(type="text", text="accidental test-odoo-secret-never-send-to-clients")]

    async def error_result(name, arguments):
        return [TextContent(type="text", text="Error reading record: raw-private-rpc-details")]

    with client:
        _, tokens = login(client)
        backend.call_tool = secret_result
        response = rpc(client, tokens["access_token"], "tools/call", {"name": "list_projects", "arguments": {}})
        assert "test-odoo-secret" not in response.text
        assert "[REDACTED]" in response.text
        backend.call_tool = error_result
        response = rpc(client, tokens["access_token"], "tools/call", {"name": "list_projects", "arguments": {}})
        assert response.json()["result"]["isError"] is True
        assert "raw-private-rpc-details" not in response.text
