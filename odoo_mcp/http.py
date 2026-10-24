"""Single-connection, OAuth-protected Streamable HTTP service."""

import asyncio
import hashlib
import logging
import re
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from urllib.parse import urlsplit

import anyio
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools import Tool, ToolResult
from jsonschema import Draft202012Validator
from mcp.types import TextContent, ToolAnnotations
from pydantic import PrivateAttr
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from .auth import OdooOAuthProvider
from .config import HTTPSettings, required
from .server import OdooMCPServer
from .remote import MAX_RECORDS

logger = logging.getLogger("odoo-mcp.audit")

# Explicit rather than name-prefix inference: new tools are never silently
# classified as read-only. Writes require an operator's exact-name allowlist.
READ_TOOLS = frozenset("""
list_projects get_project get_project_tasks search_tasks_by_tag get_task_messages
list_articles get_article list_helpdesk_teams list_tickets get_ticket get_ticket_messages
list_contacts get_contact search_contacts search_contacts_by_tag
list_mailing_lists get_mailing_list get_contact_subscriptions list_users
list_activities get_activity list_activity_types list_todos get_todo list_todo_stages
list_spreadsheets get_spreadsheet list_dashboard_groups list_dashboards get_dashboard
list_products get_boms get_stock list_locations list_invoices get_invoice list_payments
get_account_balances get_aged_balances list_journal_items list_accounts list_journals list_taxes
""".split())


class SecretRedactor(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = tuple(x for x in secrets if x)

    def clean(self, text):
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", text)
        text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED JWT]", text)
        return text

    def filter(self, record):
        record.msg = self.clean(record.getMessage())
        record.args = ()
        # Legacy RPC exceptions may include request bodies in their traceback.
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def install_redactor(redactor):
    """Sanitize before any current or future handler sees the log record."""
    factory = logging.getLogRecordFactory()
    if hasattr(factory, "odoo_redactor"):
        factory.odoo_redactor = redactor
        return

    def safe_record(*args, **kwargs):
        record = factory(*args, **kwargs)
        safe_record.odoo_redactor.filter(record)
        return record

    safe_record.odoo_redactor = redactor
    logging.setLogRecordFactory(safe_record)


class RequestBoundary:
    """Bound request bodies and reject cross-origin browser mutations."""

    def __init__(self, app, public_url):
        self.app, self.public_url = app, public_url

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin")
        if scope["method"] == "POST" and origin and origin.decode() != self.public_url:
            return await JSONResponse({"error": "Untrusted origin"}, 403)(scope, receive, send)
        limit = 2 * 1024 * 1024 if scope["path"] == "/mcp" else 64 * 1024
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                return await JSONResponse({"error": "Request too large"}, 413)(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        consumed = False

        async def buffered_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    # Preserve Origin on consent form POSTs without leaking
                    # OAuth paths or query strings in the Referer header.
                    (b"referrer-policy", b"strict-origin"),
                ])
            await send(message)

        await self.app(scope, buffered_receive, secure_send)


class OdooHTTPTool(Tool):
    _backend: OdooMCPServer = PrivateAttr()
    _limiter: anyio.CapacityLimiter = PrivateAttr()
    _redactor: SecretRedactor = PrivateAttr()
    _admission: anyio.Semaphore = PrivateAttr()

    async def run(self, arguments):
        identity = get_access_token()
        if identity is None:
            return ToolResult(content="Authentication required", is_error=True)
        validator = Draft202012Validator(self.parameters)
        if not validator.is_valid(arguments):
            return ToolResult(content="Invalid tool arguments; consult the tool schema", is_error=True)
        for name, value in arguments.items():
            if name == "limit" or name.endswith("_limit"):
                if type(value) is not int or not 1 <= value <= MAX_RECORDS:
                    return ToolResult(content=f"{name} must be between 1 and {MAX_RECORDS}", is_error=True)
        # The local contacts helpers can fetch arbitrary image URLs. That is not
        # an appropriate server-side network capability for the remote service.
        if self.name in ("create_contact", "update_contact") and arguments.get("image_url"):
            return ToolResult(content="Remote image URL fetching is disabled over HTTP", is_error=True)
        try:
            self._admission.acquire_nowait()
        except anyio.WouldBlock:
            return ToolResult(content="Service is busy; retry later", is_error=True)
        started = time.monotonic()
        subject = hashlib.sha256(str(identity.claims.get("sub", "")).encode()).hexdigest()[:16]

        def execute():
            # OdooRPC is synchronous and its shared session is not thread-safe.
            # Serialize calls, off the HTTP loop, including a cancelled request
            # until its worker finishes. Never auto-retry a possible write.
            return asyncio.run(self._backend.call_tool(self.name, arguments))

        try:
            content = await anyio.to_thread.run_sync(execute, limiter=self._limiter)
            if sum(len(x.text.encode("utf-8")) for x in content) > 1024 * 1024:
                content = [TextContent(type="text", text="Error: response too large; narrow the filters")]
            failed = any(re.match(r"^\s*(?:\*\*)?Error\b", x.text) for x in content)
            if failed:
                content = [TextContent(type="text", text="Odoo could not complete this operation. Check permissions and connection settings.")]
            else:
                content = [x.model_copy(update={"text": self._redactor.clean(x.text)}) for x in content]
        except Exception:
            failed = True
            content = [TextContent(type="text", text="Odoo operation failed")]
        finally:
            self._admission.release()
        logger.info("tool=%s subject=%s result=%s duration_ms=%d", self.name, subject,
                    "error" if failed else "ok", (time.monotonic() - started) * 1000)
        return ToolResult(content=content, is_error=failed)


async def create_app(config=None, *, backend=None, auth=None):
    """Build the app; injectable collaborators are for offline integration tests."""
    config = config or HTTPSettings.from_env()
    redactor = SecretRedactor((required("ODOO_API_KEY"), config.oidc_client_secret, config.signing_key))
    install_redactor(redactor)
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "odoorpc", "fastmcp.server.auth"):
        logging.getLogger(name).setLevel(logging.WARNING)
    auth = auth or OdooOAuthProvider(config)
    backend = backend or OdooMCPServer()
    backend.projects.remote_limits = True
    limiter = anyio.CapacityLimiter(1)
    admission = anyio.Semaphore(8)

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield
        finally:
            backend.cleanup()

    mcp = FastMCP("Odoo", auth=auth, mask_error_details=True, lifespan=lifespan,
                  instructions="Access to this Odoo connection is controlled by its operator. Write tools require explicit operator enablement.")
    catalogue = await backend.list_tools()
    known = {tool.name for tool in catalogue}
    if config.write_tools - known:
        raise ValueError("MCP_WRITE_TOOLS contains unknown tool names")
    for definition in catalogue:
        if definition.name not in READ_TOOLS | config.write_tools:
            continue
        readonly = definition.name in READ_TOOLS
        parameters = deepcopy(definition.input_schema)
        for name, schema in parameters.get("properties", {}).items():
            if name == "limit" or name.endswith("_limit"):
                schema.update(minimum=1, maximum=MAX_RECORDS)
                if "default" in schema:
                    schema["default"] = min(MAX_RECORDS, max(1, schema["default"]))
        tool = OdooHTTPTool(
            name=definition.name, description=definition.description,
            parameters=parameters,
            annotations=ToolAnnotations(readOnlyHint=readonly, destructiveHint=not readonly,
                                        idempotentHint=readonly, openWorldHint=False),
        )
        tool._backend, tool._limiter, tool._redactor = backend, limiter, redactor
        tool._admission = admission
        mcp.add_tool(tool)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def health(request):
        # Liveness only: never query the ERP for a container health check.
        return JSONResponse({"status": "ok"})

    hostname = urlsplit(config.public_url).hostname
    return mcp.http_app(
        path="/mcp", stateless_http=True, json_response=True,
        allowed_hosts=[hostname, "127.0.0.1", "localhost"],
        allowed_origins=[config.public_url],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=[hostname, "127.0.0.1", "localhost"]),
            Middleware(RequestBoundary, public_url=config.public_url),
        ],
    )


def main():
    async def serve():
        app = await create_app()
        await uvicorn.Server(uvicorn.Config(
            app, host="0.0.0.0", port=8000, workers=1,
            proxy_headers=False, access_log=False, log_level="info", limit_concurrency=64,
        )).serve()
    try:
        asyncio.run(serve())
    except ValueError as exc:
        raise SystemExit(f"Invalid service configuration: {exc}") from None


if __name__ == "__main__":
    main()
