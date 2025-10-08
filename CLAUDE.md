# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server for integrating Odoo cloud apps with LLMs. The MCP allows AI assistants to interact with Odoo's SaaS platform through a standardized protocol.

**Currently Implemented:**
- **Projects** (13 tools): Full CRUD on projects and tasks. Create, read, update, archive projects. Create, read, update, delete, archive tasks. Send and read task messages. Search tasks by tag across all projects. Task details include tags.
- **Knowledge** (6 tools): Full CRUD on knowledge articles. Create, read, update, delete, archive articles with hierarchical organization.
- **Helpdesk** (8 tools): List teams. Full CRUD on tickets. Create, read, update, close tickets. Send and read ticket messages with HTML support.
- **Contacts** (7 tools): Full CRUD on contacts (companies and individuals). List, search, create, read, update, delete, archive contacts. Upload logos from URLs.
- **Mailing Lists** (10 tools): Manage email marketing lists. Create, update, delete lists. Subscribe/unsubscribe contacts. Manage opt-in/opt-out status.
- **Users** (1 tool): List Odoo users for task and ticket assignments.
- **Activities** (7 tools): Manage scheduled follow-ups and activities. List, create, update, mark done, delete activities. List activity types. Activities can be linked to any Odoo record.
- **To-Do App** (7 tools): Manage personal to-do list. List, create, update, mark done, delete to-dos. List stages. Organize by stages (Inbox, Today, This Week, This Month, Later).

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
│   ├── server.py          # Main MCP server (tool registration and routing)
│   ├── base.py            # Base class with shared Odoo connection logic
│   ├── projects.py        # Projects and tasks operations (13 tools)
│   ├── knowledge.py       # Knowledge articles operations (6 tools)
│   ├── helpdesk.py        # Helpdesk tickets operations (8 tools)
│   ├── contacts.py        # Contacts/partners operations (7 tools)
│   ├── mailing.py         # Mailing lists operations (10 tools)
│   ├── users.py           # Users operations (1 tool)
│   ├── activities.py      # Activities/scheduled follow-ups (7 tools)
│   └── todos.py           # To-Do app/personal tasks (7 tools)
├── test_connection.py     # Test script for Odoo connectivity
├── pyproject.toml        # Project dependencies
├── .env                  # Environment variables (gitignored)
└── README.md
```

## Architecture

The codebase follows a modular architecture with separate handler modules for each Odoo app:

### Base Class (`odoo_mcp/base.py`)

- **OdooBase** - Base class providing shared Odoo connection logic
- `connect_odoo()` - Initializes the Odoo connection using odoorpc with JSON-RPC over SSL
- `cleanup()` - Cleanup resources on shutdown
- All handler classes inherit from OdooBase

### Handler Modules

Each Odoo app has its own handler module inheriting from OdooBase:
- **ProjectsHandler** (`projects.py`) - 13 tools for projects and tasks
- **KnowledgeHandler** (`knowledge.py`) - 6 tools for knowledge articles
- **HelpdeskHandler** (`helpdesk.py`) - 8 tools for helpdesk tickets
- **ContactsHandler** (`contacts.py`) - 7 tools for contacts/partners
- **MailingHandler** (`mailing.py`) - 10 tools for mailing lists
- **UsersHandler** (`users.py`) - 1 tool for users
- **ActivitiesHandler** (`activities.py`) - 7 tools for activities/scheduled follow-ups
- **TodosHandler** (`todos.py`) - 7 tools for personal to-do list

Each handler:
- Implements tools as async methods
- Connects to Odoo via shared odoorpc connection
- Searches/reads data from Odoo models
- Formats results as TextContent
- Returns formatted markdown output

### Main Server (`odoo_mcp/server.py`)

The OdooMCPServer class:
1. **Initialization** - Creates handler instances for each Odoo app
2. **Connection sharing** - Establishes Odoo connection and shares it among all handlers
3. **Tool registration** - Registers all 59 tools via `@server.list_tools()` decorator
4. **Tool routing** - Routes tool calls to appropriate handlers via `@server.call_tool()` decorator
5. **Graceful shutdown** - Handles SIGINT/SIGTERM signals and cleans up resources

### Adding New Tools

To add a new tool to an existing handler:

1. **Add tool definition** in `server.py` `list_tools()`:
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

2. **Add handler routing** in `server.py` `call_tool()`:
```python
elif name == "tool_name":
    return await self.handler_name.tool_name(arguments)
```

3. **Implement method** in appropriate handler file (e.g., `projects.py`):
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
- `project.tags` - Task tags (for categorization and filtering)
- `helpdesk.ticket` - Helpdesk tickets
- `helpdesk.team` - Helpdesk teams
- `res.partner` - Contacts/customers
- `res.users` - Users
- `knowledge.article` - Knowledge base articles
- `mailing.list` - Mailing lists
- `mailing.contact` - Mailing contacts
- `mailing.subscription` - List subscriptions (tracks opt-in/opt-out)
- `mail.message` - Messages/chatter entries
- `mail.activity` - Activities/to-dos (scheduled tasks and follow-ups)
- `mail.activity.type` - Activity types (To-do, Call, Email, Meeting, etc.)

## Message Handling

For tasks and tickets, use `message_post()` to send messages:

```python
# Get the record
Task = self.odoo.env["project.task"]
task_record = Task.browse(task_id)

# Convert plain text to HTML
if '<' not in body or '>' not in body:
    body = '<p>' + body.replace('\n', '<br>') + '</p>'

# Post message
task_record.message_post(
    body=body,
    body_is_html=True,
    message_type="comment",  # or "notification" for internal notes
    subtype_xmlid='mail.mt_comment'  # or 'mail.mt_note' for internal
)
```

**Key points:**
- `message_post()` automatically handles signatures and email notifications
- Use `body_is_html=True` to preserve HTML formatting
- `mail.mt_comment` sends emails, `mail.mt_note` is internal only
- Read messages via the `message_ids` field on records

## Image Handling

For uploading images/logos to contacts:

```python
import base64
import requests

# Download image from URL
response = requests.get(image_url, timeout=10)
response.raise_for_status()

# Convert to base64
image_base64 = base64.b64encode(response.content).decode('utf-8')

# Update contact
Partner = self.odoo.env["res.partner"]
Partner.write(contact_id, {"image_1920": image_base64})
```

**Key points:**
- `image_1920` is the full resolution image field
- Images must be base64 encoded strings
- Odoo automatically creates smaller variants (image_512, image_256, etc.)

## Mailing Lists

The mailing list system maintains separate `mailing.contact` records from the main `res.partner` contacts:

**Contact Management:**
- `mailing.contact` - Mailing list subscribers (separate from res.partner)
- `mailing.subscription` - Links mailing contacts to lists, tracks opt-in/opt-out
- The `subscribe_contact` function automatically searches for matching `res.partner` contacts by email and uses the partner's name for the mailing contact

**Key points:**
- Mailing contacts are separate records from regular contacts (res.partner)
- When subscribing an email, the system searches for a res.partner with that email and uses the partner's name
- This ensures consistent naming across mailing lists and the contact database
- The `get_mailing_list` function shows both names and email addresses for clarity

## To-Do App (Personal Tasks)

The To-Do app uses `project.task` records without a project (`project_id = False`) and has special handling:

**Personal Stages:**
- To-Do tasks use `personal_stage_type_id` field (NOT `stage_id`)
- Personal stages include: Inbox, Today, This Week, This Month, Later, Done
- Stages are from `project.task.type` model

**Marking Tasks as Done:**
To properly mark a to-do as complete, you must set BOTH:
1. `personal_stage_type_id` to a Done stage (with `fold=True`)
2. `state` to `"1_done"`

```python
Task = self.odoo.env["project.task"]
Stage = self.odoo.env["project.task.type"]

# Find a Done stage with fold=True
done_stage_ids = Stage.search([("name", "ilike", "done"), ("fold", "=", True)])
done_stages = Stage.read(done_stage_ids, ["id", "sequence", "fold"])

# Prefer Done stage with sequence 5-7 (typical for personal tasks)
preferred_stage = None
for stage in done_stages:
    if stage.get("fold") and 5 <= stage.get("sequence", 0) <= 7:
        preferred_stage = stage["id"]
        break

# Update task
Task.write(todo_id, {
    "personal_stage_type_id": preferred_stage,
    "state": "1_done"
})
```

**Key points:**
- `is_closed` is a computed field based on the stage's `fold` attribute
- Setting only `state="1_done"` marks it complete but doesn't move it to Done column
- Setting only the stage doesn't mark it as complete (state remains in progress)
- Both fields are required for proper "done" behavior in the UI

## Key Dependencies

- **mcp** (>=1.0.0) - Model Context Protocol SDK
- **odoorpc** (>=0.10.0) - Odoo RPC client library
- **python-dotenv** (>=1.0.0) - Environment variable management
- **requests** - HTTP library for downloading images from URLs
