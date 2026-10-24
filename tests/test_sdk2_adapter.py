"""The low-level SDK must reject invalid arguments before reaching Odoo."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolRequestParams, TextContent
from odoo_mcp.server import OdooMCPServer


@pytest.mark.parametrize("name,arguments", [
    ("missing_tool", {}), ("get_project", {}),
    ("get_project", {"project_id": "not-an-integer"}),
])
def test_invalid_stdio_request_never_calls_odoo(name, arguments):
    server = OdooMCPServer()
    server.call_tool = AsyncMock()
    result = asyncio.run(server._call_tool_request(None, CallToolRequestParams(name=name, arguments=arguments)))
    assert result.is_error
    server.call_tool.assert_not_called()


def test_stdio_adapter_returns_typed_results():
    server = OdooMCPServer()
    server.call_tool = AsyncMock(return_value=[TextContent(type="text", text="ok")])
    result = asyncio.run(server._call_tool_request(None, CallToolRequestParams(name="list_projects", arguments={})))
    assert not result.is_error
    assert result.content[0].text == "ok"
    server.call_tool.assert_awaited_once_with("list_projects", {})
