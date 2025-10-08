# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server for integrating Odoo cloud apps with LLMs. The MCP allows AI assistants to interact with Odoo's SaaS platform through a standardized protocol.

**Currently Implemented:**
- Projects: List projects and read project tasks

**Roadmap:**
- Knowledge (documents)
- Helpdesk (tickets and customer messages)
- Contacts (CRM)

## Commands

### Development
```bash
# Test Odoo connection
python test_connection.py

# Run the MCP server
python -m odoo_mcp.server

# Install in development mode
pip install -e .
```

### Testing
The server uses stdio transport, so manual testing requires an MCP client like Claude Desktop or Claude Code.

## Project Structure

```
odoo-mcp/
├── odoo_mcp/
│   ├── __init__.py
│   └── server.py          # Main MCP server implementation
├── test_connection.py     # Test script for Odoo connectivity
├── pyproject.toml        # Project dependencies
├── .env                  # Environment variables (gitignored)
└── README.md
```

## Architecture

### MCP Server (`odoo_mcp/server.py`)

The server follows this pattern:
1. **OdooMCPServer class** - Main server implementation
2. **Connection management** - `connect_odoo()` initializes the Odoo connection using odoorpc
3. **Tool registration** - Tools are registered via `@server.list_tools()` and `@server.call_tool()` decorators
4. **Tool handlers** - Each tool is an async method that:
   - Connects to Odoo if not already connected
   - Uses odoorpc to access Odoo models
   - Searches/reads data from Odoo
   - Formats results as TextContent
   - Returns formatted markdown output

### Adding New Tools

To add a new tool:

1. **Add tool definition** in `list_tools()`:
```python
Tool(
    name="tool_name",
    description="What the tool does",
    inputSchema={
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string",
                "description": "Parameter description"
            }
        },
        "required": ["param_name"]
    }
)
```

2. **Add handler** in `call_tool()`:
```python
elif name == "tool_name":
    return await self.tool_name(arguments)
```

3. **Implement method**:
```python
async def tool_name(self, arguments: dict) -> list[TextContent]:
    """Tool implementation."""
    # Access Odoo model
    Model = self.odoo.env["model.name"]

    # Search for records
    record_ids = Model.search([('field', 'operator', 'value')])

    # Read fields
    records = Model.read(record_ids, ['field1', 'field2'])

    # Format and return
    return [TextContent(type="text", text="formatted output")]
```

## Odoo API Patterns

### Authentication
- Uses JSON-RPC over SSL (port 443)
- Authenticates with API key (not password)
- Connection is initialized once and reused

### Common Operations

**Search:**
```python
Model = self.odoo.env["model.name"]
ids = Model.search([('field', '=', 'value')], limit=50)
```

**Read:**
```python
records = Model.read(ids, ['field1', 'field2', 'field3'])
```

**Relational Fields:**
- `many2one`: Returns `[id, "Display Name"]` or `False`
- `one2many`/`many2many`: Returns list of IDs
- Access display name: `field[1]` for many2one

**Domain Filters:**
```python
[('field', '=', 'value')]           # Equals
[('field', '!=', 'value')]          # Not equals
[('field', 'in', [1, 2, 3])]        # In list
[('field', 'like', 'pattern')]      # Pattern match
['|', ('a', '=', 1), ('b', '=', 2)] # OR (Polish notation)
```

## Environment Variables

Required in `.env` file:
- `ODOO_URL` - Your Odoo instance URL
- `ODOO_DB` - Database name
- `ODOO_USERNAME` - User email
- `ODOO_API_KEY` - API key for authentication
- `ODOO_COMPANY_ID` - (Optional) For multi-company setups

## Common Odoo Models

- `project.project` - Projects
- `project.task` - Tasks/tickets
- `helpdesk.ticket` - Helpdesk tickets
- `res.partner` - Contacts/customers
- `res.users` - Users
- `knowledge.article` - Knowledge base articles

## Key Dependencies

- **mcp** (>=1.0.0) - Model Context Protocol SDK
- **odoorpc** (>=0.10.0) - Odoo RPC client library
- **python-dotenv** (>=1.0.0) - Environment variable management
