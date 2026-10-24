"""Run seed with the old checkout/environment, then verify with the new one.

Set PYTHONPATH to each checkout and its tests directory. All keys and tokens
are synthetic, stored only in the supplied temporary directory. No real IdP
or Odoo connection is used.
"""
import argparse
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from test_http_service import setup, make_client, login, rpc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["seed", "verify"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_file = root / "fake-idp-key.pem"
    if args.mode == "seed":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(rsa, "generate_private_key", lambda **kwargs: key)
        config, _ = setup.__wrapped__(root, monkeypatch)
        with make_client(config)[0] as client:
            if args.mode == "seed":
                client_id, tokens = login(client)
                revoked_id, revoked = login(client)
                assert client.post("/revoke", data={"client_id": revoked_id,
                    "token": revoked["refresh_token"], "token_type_hint": "refresh_token"}).status_code == 200
                (root / "fake-grants.json").write_text(json.dumps({
                    "client_id": client_id, "tokens": tokens, "revoked": revoked,
                }))
            else:
                saved = json.loads((root / "fake-grants.json").read_text())
                tokens = saved["tokens"]
                assert rpc(client, tokens["access_token"]).status_code == 200
                assert rpc(client, saved["revoked"]["access_token"]).status_code == 401
                refreshed = client.post("/token", data={"grant_type": "refresh_token",
                    "client_id": saved["client_id"], "refresh_token": tokens["refresh_token"]})
                assert refreshed.status_code == 200, refreshed.text
                fresh = refreshed.json()
                assert rpc(client, fresh["access_token"]).status_code == 200
                assert client.post("/revoke", data={"client_id": saved["client_id"],
                    "token": fresh["refresh_token"], "token_type_hint": "refresh_token"}).status_code == 200
                assert rpc(client, tokens["access_token"]).status_code == 401
                assert rpc(client, fresh["access_token"]).status_code == 401
    print("PASS: OAuth upgrade " + args.mode)


if __name__ == "__main__":
    main()
