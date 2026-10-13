"""Run INSIDE the built image; test its real entry point with a local TLS IdP.

No live Odoo or external identity provider is contacted, and no extra packages
are installed. Mount this script read-only at /tests/container_smoke.py.
"""

import datetime
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    assert os.getuid() == 10001, "Image must run as its non-root user"
    assert shutil.which("odoo-mcp-http"), "Missing HTTP console entry point"
    assert shutil.which("odoo-mcp"), "Missing stdio console entry point"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(minutes=1))
                .not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        cert_file, key_file = root / "cert.pem", root / "key.pem"
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))

        class IdP(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                base = f"https://localhost:{self.server.server_port}"
                document = {"issuer": base, "authorization_endpoint": base + "/authorize",
                            "token_endpoint": base + "/token", "jwks_uri": base + "/jwks",
                            "response_types_supported": ["code"], "subject_types_supported": ["public"],
                            "id_token_signing_alg_values_supported": ["RS256"]}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(document).encode())

        idp = ThreadingHTTPServer(("127.0.0.1", 0), IdP)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert_file, key_file)
        idp.socket = tls.wrap_socket(idp.socket, server_side=True)
        threading.Thread(target=idp.serve_forever, daemon=True).start()
        for name, value in {"odoo_key": "fake-odoo-key", "client_secret": "fake-client-secret",
                            "signing_key": "fake-signing-key-for-container-smoke-only-" * 2}.items():
            (root / name).write_text(value)
        env = {**os.environ,
               "SSL_CERT_FILE": str(cert_file),
               "MCP_PUBLIC_URL": "https://mcp.example.com",
               "MCP_OIDC_CONFIG_URL": f"https://localhost:{idp.server_port}/.well-known/openid-configuration",
               "MCP_OIDC_CLIENT_ID": "smoke-test", "MCP_ALLOWED_SUBJECTS": "smoke-user",
               "MCP_OIDC_CLIENT_SECRET_FILE": str(root / "client_secret"),
               "MCP_OAUTH_SIGNING_KEY_FILE": str(root / "signing_key"),
               "ODOO_API_KEY_FILE": str(root / "odoo_key"),
               "ODOO_URL": "https://unused-odoo.invalid", "ODOO_DB": "fake", "ODOO_USERNAME": "fake"}
        # Intentionally use /data/oauth, the image's persistent, owned directory.
        proc = subprocess.Popen(["odoo-mcp-http"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise AssertionError(proc.stdout.read().decode())
                try:
                    with urlopen("http://127.0.0.1:8000/healthz", timeout=1) as response:
                        assert json.load(response) == {"status": "ok"}
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("Container service did not become healthy")
            with urlopen("http://127.0.0.1:8000/.well-known/oauth-authorization-server") as response:
                metadata = json.load(response)
                assert metadata["issuer"].rstrip("/") == "https://mcp.example.com"
                assert metadata["client_id_metadata_document_supported"] is True
                assert metadata["registration_endpoint"].endswith("/register")
            try:
                urlopen(Request("http://127.0.0.1:8000/mcp", data=b"{}", method="POST"))
                raise AssertionError("Unauthenticated MCP request was accepted")
            except HTTPError as response:
                assert response.code == 401
            assert Path("/data/oauth").is_dir()
        finally:
            proc.terminate()
            try:
                output, _ = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
            idp.shutdown()
            idp.server_close()
        assert proc.returncode in (0, -15), output.decode()
        assert b"fake-odoo-key" not in output
        assert b"fake-client-secret" not in output
        # Exercise the actual stdio console script without calling Odoo.
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "container-smoke", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        stdio = subprocess.run(["odoo-mcp"], env=env,
                               input="".join(json.dumps(r) + "\n" for r in requests),
                               text=True, capture_output=True, timeout=15)
        assert stdio.returncode == 0, stdio.stderr
        responses = [json.loads(line) for line in stdio.stdout.splitlines() if line]
        catalogue = next(r for r in responses if r.get("id") == 2)
        assert "list_projects" in {t["name"] for t in catalogue["result"]["tools"]}
        print("PASS: non-root read-only container, secret files, OIDC discovery, health, protected MCP, graceful shutdown, stdio catalogue")


if __name__ == "__main__":
    main()
