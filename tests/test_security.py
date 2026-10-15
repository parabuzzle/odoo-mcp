"""Regression tests for the pre-deployment security review."""

import asyncio
import logging
import time
import re
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import odoorpc
import pytest
from authlib.integrations.httpx_client import AsyncOAuth2Client
from mcp.server.auth.provider import TokenError

from test_http_service import (
    setup, make_client, login, register, authorization_code, exchange, rpc,
)
from odoo_mcp.auth import valid_identity_claims
from odoo_mcp.remote import RemoteOdoo, RemoteLimitError, MAX_RECORDS


def test_google_authorization_and_callback_failure(setup, monkeypatch, capsys, caplog):
    from test_http_service import CALLBACK, CHALLENGE
    config, _ = setup
    config = replace(config, oidc_provider="google", workspace_domain="example.com")
    with make_client(config)[0] as client:
        client_id = register(client)
        started = client.get("/authorize", params={"client_id": client_id,
            "redirect_uri": CALLBACK, "response_type": "code", "scope": "openid profile email",
            "state": "test-state", "code_challenge": CHALLENGE, "code_challenge_method": "S256"})
        consent_url = started.headers["location"]
        consent = client.get(consent_url)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', consent.text).group(1)
        txn = re.search(r'name="txn_id" value="([^"]+)"', consent.text).group(1)
        approved = client.post(urlsplit(consent_url).path,
            data={"txn_id": txn, "csrf_token": csrf, "action": "approve"})
        parameters = parse_qs(urlsplit(approved.headers["location"]).query)
        assert parameters["access_type"] == ["offline"]
        assert parameters["prompt"] == ["consent"]
        assert parameters["hd"] == ["example.com"]
        assert set(parameters["scope"][0].split()) == {"openid", "profile", "email"}

        async def fail(*args, **kwargs):
            raise RuntimeError("callback diagnostic " + config.oidc_client_secret)

        monkeypatch.setattr(AsyncOAuth2Client, "fetch_token", fail)
        response = client.get("/auth/callback", params={"code": "fake-code", "state": parameters["state"][0]})
        assert response.status_code == 500
        assert config.oidc_client_secret not in response.text + capsys.readouterr().err + caplog.text


def test_parallel_refresh_single_use_and_family_revoked(setup, monkeypatch):
    config, _ = setup
    client, _, auth = make_client(config)
    with client:
        client_id, tokens = login(client)
        original = AsyncOAuth2Client.refresh_token
        calls = []

        async def slow(*args, **kwargs):
            calls.append(True)
            await asyncio.sleep(0.05)
            return await original(*args, **kwargs)

        monkeypatch.setattr(AsyncOAuth2Client, "refresh_token", slow)

        async def scenario():
            registered = await auth.get_client(client_id)
            refresh = await auth.load_refresh_token(registered, tokens["refresh_token"])
            results = await asyncio.gather(
                auth.exchange_refresh_token(registered, refresh, refresh.scopes),
                auth.exchange_refresh_token(registered, refresh, refresh.scopes),
                return_exceptions=True,
            )
            assert sum(not isinstance(r, Exception) for r in results) == 1
            assert sum(isinstance(r, TokenError) for r in results) == 1
            assert len(calls) == 1
            return next(r.access_token for r in results if not isinstance(r, Exception))

        new_access = client.portal.call(scenario)
        assert rpc(client, new_access).status_code == 401
        assert rpc(client, tokens["access_token"]).status_code == 401
    with make_client(config)[0] as restarted:
        assert rpc(restarted, new_access).status_code == 401


def test_parallel_code_exchange_single_use(setup):
    config, _ = setup
    client, _, auth = make_client(config)
    with client:
        client_id = register(client)
        code = authorization_code(client, client_id)

        async def scenario():
            registered = await auth.get_client(client_id)
            authorization = await auth.load_authorization_code(registered, code)
            results = await asyncio.gather(
                auth.exchange_authorization_code(registered, authorization),
                auth.exchange_authorization_code(registered, authorization),
                return_exceptions=True,
            )
            assert sum(not isinstance(r, Exception) for r in results) == 1
            assert sum(isinstance(r, TokenError) for r in results) == 1

        client.portal.call(scenario)


def test_refresh_exception_redacted_from_response_and_all_logs(setup, monkeypatch, capsys, caplog):
    config, _ = setup
    with make_client(config)[0] as client:
        client_id, tokens = login(client)

        async def fail(*args, **kwargs):
            # Also check logging from a library handler configured after startup.
            logging.getLogger("fastmcp.server.auth.audit-test").error("diagnostic %s", config.oidc_client_secret)
            raise RuntimeError("provider diagnostic " + config.oidc_client_secret)

        monkeypatch.setattr(AsyncOAuth2Client, "refresh_token", fail)
        response = client.post("/token", data={"grant_type": "refresh_token",
            "client_id": client_id, "refresh_token": tokens["refresh_token"]})
        assert response.status_code in (400, 401)
        assert config.oidc_client_secret not in response.text + capsys.readouterr().err + caplog.text
        assert rpc(client, tokens["access_token"]).status_code == 401


@pytest.mark.parametrize("change", [
    {"exp": None}, {"iat": None}, {"exp": True}, {"iat": True},
    {"exp": "9999999999"}, {"iat": 9999999999},
    {"aud": ["bridge-client", "another-client"]}, {"azp": "another-client"},
])
def test_strict_id_token_claims(setup, change):
    config, user = setup
    user.update(change)
    with make_client(config)[0] as client:
        client_id = register(client)
        code = authorization_code(client, client_id)
        assert exchange(client, client_id, code).status_code in (400, 401)


def test_missing_exp_and_nonfinite_claims(setup):
    config, _ = setup
    now = time.time()
    claims = {"sub": "allowed-person", "aud": "bridge-client", "iat": now, "exp": now + 60}
    assert valid_identity_claims(claims, config)
    for name in ("exp", "iat"):
        without = dict(claims)
        del without[name]
        assert not valid_identity_claims(without, config)
        assert not valid_identity_claims({**claims, name: float("inf")}, config)
        assert not valid_identity_claims({**claims, name: float("nan")}, config)


@pytest.mark.parametrize("domain", [None, "other.example", "example.com"])
def test_google_domain_is_enforced_on_signed_identity(setup, domain):
    config, user = setup
    config = replace(config, oidc_provider="google", workspace_domain="example.com")
    user["hd"] = domain
    with make_client(config)[0] as client:
        client_id = register(client)
        code = authorization_code(client, client_id)
        response = exchange(client, client_id, code)
        assert (response.status_code == 200) is (domain == "example.com")


@pytest.mark.parametrize("limit", [0, -1, MAX_RECORDS + 1, True])
def test_bad_limits_never_reach_backend(setup, limit):
    config, _ = setup
    client, backend, _ = make_client(config)
    with client:
        _, tokens = login(client)
        response = rpc(client, tokens["access_token"], "tools/call",
                       {"name": "list_projects", "arguments": {"limit": limit}})
        assert response.json()["result"]["isError"] is True
        assert not backend.calls


def test_rpc_bounds_internal_searches_without_silent_truncation(monkeypatch):
    calls = []

    def execute(self, model, method, args, kwargs):
        calls.append((method, args, kwargs))
        return list(range(MAX_RECORDS + 1))

    monkeypatch.setattr(odoorpc.ODOO, "execute_kw", execute)
    connection = object.__new__(RemoteOdoo)  # No network or credentials.
    for method, args in (("search", [[]]), ("read_group", [[], ["amount:sum"], ["partner_id"]])):
        with pytest.raises(RemoteLimitError):
            connection.execute_kw("example.model", method, args)
        assert calls[-1][2]["limit"] == MAX_RECORDS + 1
    calls.clear()
    with pytest.raises(RemoteLimitError):
        connection.execute_kw("example.model", "read", [list(range(MAX_RECORDS + 1))])
    assert not calls
