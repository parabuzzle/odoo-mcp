# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server for integrating Odoo cloud apps with LLMs. The MCP allows AI assistants to interact with Odoo's SaaS platform through a standardized protocol.

**Currently Implemented:**
- **Projects** (13 tools): Full CRUD on projects and tasks. Create, read, update, archive projects. Create, read, update, delete, archive tasks. Send and read task messages. Search tasks by tag across all projects. Task details include comprehensive fields: assignees, customer/partner, stage, kanban state, priority, tags, deadlines, date assigned, subtask count, and descriptions.
- **Knowledge** (6 tools): Full CRUD on knowledge articles. Create, read, update, delete, archive articles with hierarchical organization.
- **Helpdesk** (8 tools): List teams. Full CRUD on tickets. Create, read, update, close tickets. Send and read ticket messages with HTML support. Ticket details include comprehensive fields: customer contact info (name, email, phone), stage, kanban state, priority, ticket type, tags, SLA deadline, and assignment.
- **Contacts** (8 tools): Full CRUD on contacts (companies and individuals). List, search by name/email/company, search by tag, create, read, update, delete, archive contacts. Upload logos from URLs. Comprehensive field support including website, VAT/tax ID, title, job function, internal reference, address, state/province, country, tags, and internal notes.
- **Mailing Lists** (10 tools): Manage email marketing lists. Create, update, delete lists. Subscribe/unsubscribe contacts. Manage opt-in/opt-out status.
- **Users** (1 tool): List Odoo users for task and ticket assignments.
- **Activities** (7 tools): Manage scheduled follow-ups and activities. List, create, update, mark done, delete activities. List activity types. Activities can be linked to any Odoo record.
- **To-Do App** (7 tools): Manage personal to-do list. List, create, update, mark done, delete to-dos. List stages. Organize by stages (Inbox, Today, This Week, This Month, Later).
- **Spreadsheets** (5 tools): Manage spreadsheets in the Documents app (`documents.document`, `handler='spreadsheet'`). List, read, create, update, delete spreadsheets. Content is stored as o-spreadsheet JSON in `spreadsheet_data`.
- **Dashboards** (8 tools): Manage spreadsheet dashboards (`spreadsheet.dashboard`, `spreadsheet.dashboard.group`). Full CRUD on dashboards and groups. Includes `create_inventory_dashboard`, which builds an on-hand inventory dashboard from `stock.quant` grouped by product/location/warehouse/category — either as a snapshot data table + chart (`mode='snapshot'`, re-run to refresh) or as a self-refreshing live pivot + Odoo-bound chart (`mode='live'`, supports two-level grouping via `sub_group_by`). Can create a new dashboard/spreadsheet or overwrite an existing dashboard via `dashboard_id`.
- **Manufacturing** (4 tools, read-only): `list_products` (by internal-reference prefix or ids, with archived-record support and a variant-aware `has_bom` flag), `get_boms` (complete BoM structures with lines resolved to component identity), `get_stock` (on-hand quantity/value aggregates with location scoping), `list_locations` (stock locations with usage filter). Deliberately scoped — no generic model passthrough, no writes to product/BoM/stock/location models. Built to support clear-to-build (CTB) spreadsheet regeneration from live BoM data.
- **Accounting** (9 tools, read-only): `list_invoices`/`get_invoice` (customer invoices, vendor bills, credit notes with line detail), `list_payments`, `get_account_balances` (trial-balance/P&L aggregates from `account.move.line`), `get_aged_balances` (AR/AP aging by partner), `list_journal_items` (raw line-level general ledger with `matching_number` for reconciliation pairing), `list_accounts`, `list_journals`, `list_taxes`. Deliberately scoped — no writes to any accounting model, no generic passthrough. Document-currency amounts plus company-currency `*_signed` fields on documents; balance/aging tools are company currency only.

## Commands

### Development
```bash
# Test Odoo connection
python test_connection.py

# Regression test: round-trip a 120KB data_json through update_dashboard,
# both handler-level and over MCP stdio (creates + deletes a test dashboard)
python test_payload_limit.py

# Read-only smoke test for all 8 accounting tools against the live instance
python test_accounting.py

# Offline (no live connection) regression tests for the defensive schema layer:
# missing-field drops, write-payload validation, kanban_state->state remap,
# and mobile->phone aliasing. Uses a fake odoo.env.
python test_schema_layer.py

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
│   ├── todos.py           # To-Do app/personal tasks (7 tools)
│   ├── spreadsheets.py    # Documents spreadsheets (5 tools)
│   ├── dashboards.py      # Spreadsheet dashboards + inventory builder (8 tools)
│   ├── manufacturing.py   # Read-only products/BoMs/stock/locations (4 tools)
│   ├── accounting.py      # Read-only invoices/payments/balances/journal items/reference data (9 tools)
│   └── spreadsheet_utils.py  # o-spreadsheet JSON builder helpers
├── test_connection.py     # Test script for Odoo connectivity
├── test_payload_limit.py  # Regression test: 100KB+ payload round-trip
├── test_accounting.py     # Read-only smoke test for accounting tools
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

**Defensive schema layer (Odoo version compatibility).** Odoo removes/renames
model fields between major versions, and hardcoded field lists in `read()`/
`write()` calls 500 the moment a referenced field disappears. `OdooBase` provides
a caching `fields_get()`-based layer so this degrades gracefully:
- `get_model_fields(model)` - cached `fields_get()` per model. The cache is a
  **class attribute** shared across every handler instance (they share one
  connection), so it costs one `fields_get` RPC per model for the whole process,
  not one per call. On RPC failure it caches `{}` and the helpers **fail open**
  (drop nothing) so hardening never makes things worse than before.
- `safe_read(model, ids, fields)` -> `(records, warnings)`: `read()` with the
  field list intersected against the live schema; missing fields are dropped and
  reported. Used by the affected-model read tools, which surface the warnings in
  a trailing `## Warnings` section (`warnings_section(...)`).
- `safe_read_records(model, ids, fields)` -> `records`: drop-in replacement for
  `Model.read()` (same return shape) that filters missing fields and **logs**
  the drops instead of returning them. Used across the other read tools whose
  output isn't structured to carry a warnings section.
- `invalid_write_fields(model, values)` -> list of payload keys not on the live
  schema. Write tools call this and fail fast with a clear message naming the
  offending field instead of surfacing a raw Odoo RPC error.
- `field_selection(model, field)` -> the live `[(value, label), ...]` for a
  selection field (used for the kanban_state->state remap and friendly labels).

**Odoo 18 -> 19 field changes handled (Aug 2026 upgrade):**
- `res.partner.mobile` removed (merged into `phone`). Reads return `phone` only.
  The `mobile` create/update param is kept and aliased onto `phone` (an explicit
  `phone` wins). See `contacts.py`.
- `helpdesk.ticket.ticket_type_id` removed (types converted to tags). Dropped
  from reads; the create/update `ticket_type_id` param is merged into `tag_ids`.
  `helpdesk.ticket.kanban_state` also removed - dropped from reads, ignored on
  writes (both emit a response warning). See `helpdesk.py`.
- `project.task.kanban_state` removed (replaced by the `state` selection). Reads
  return `state` (shown as "Status"); the create/update `kanban_state` param is
  remapped to a live `state` key via `_map_kanban_to_state` (normal->
  `01_in_progress`, blocked->`02_changes_requested`, done->`03_approved`),
  resolved against the actual selection at runtime with a warning if unmappable.
  See `projects.py`.

**Deprecation note:** Odoo 19 deprecates the XML-RPC/JSON-RPC endpoints this
server uses (via odoorpc, `jsonrpc+ssl`). They keep working through Odoo 21.0 but
are slated for removal in SaaS 21.1 (winter 2027) / on-prem 22.0 (fall 2028), in
favor of the new JSON-2 API. A transport migration will be needed before then.

### Handler Modules

Each Odoo app has its own handler module inheriting from OdooBase:
- **ProjectsHandler** (`projects.py`) - 13 tools for projects and tasks
- **KnowledgeHandler** (`knowledge.py`) - 6 tools for knowledge articles
- **HelpdeskHandler** (`helpdesk.py`) - 8 tools for helpdesk tickets
- **ContactsHandler** (`contacts.py`) - 8 tools for contacts/partners
- **MailingHandler** (`mailing.py`) - 10 tools for mailing lists
- **UsersHandler** (`users.py`) - 1 tool for users
- **ActivitiesHandler** (`activities.py`) - 7 tools for activities/scheduled follow-ups
- **TodosHandler** (`todos.py`) - 7 tools for personal to-do list
- **SpreadsheetsHandler** (`spreadsheets.py`) - 5 tools for Documents spreadsheets
- **DashboardsHandler** (`dashboards.py`) - 8 tools for spreadsheet dashboards and the inventory dashboard builder
- **ManufacturingHandler** (`manufacturing.py`) - 4 read-only tools for products, BoMs, stock, and locations
- **AccountingHandler** (`accounting.py`) - 9 read-only tools for invoices/bills, payments, balances, aging, journal items, and accounting reference data

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
3. **Tool registration** - Registers all 86 tools via `@server.list_tools()` decorator
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
- `documents.document` - Documents, including spreadsheets (`handler='spreadsheet'`)
- `spreadsheet.dashboard` - Spreadsheet dashboards (Dashboards app)
- `spreadsheet.dashboard.group` - Dashboard groups/sections
- `stock.quant` - On-hand stock levels (quantity per product per location)
- `stock.location` - Stock locations (has `usage`, `warehouse_id`, `complete_name`)
- `product.product` - Product variants (has `categ_id`, `standard_price`)
- `product.template` - Product templates (BoMs bind here; variants share a template)
- `mrp.bom` - Bills of materials (binds to `product_tmpl_id`; `product_id` optionally selects a variant)
- `mrp.bom.line` - BoM lines (`product_id`, `product_qty`, `product_uom_id`)
- `account.move` - Invoices, bills, credit notes, journal entries (`move_type` distinguishes them; `state`, `payment_state`)
- `account.move.line` - Journal items (`debit`/`credit`/`balance` in company currency; `parent_state` mirrors the move's state)
- `account.payment` - Payments (`payment_type` inbound/outbound; `ref` renamed to `memo` in Odoo 18)
- `account.account` - Chart of accounts (`code`, `account_type` selection since Odoo 16)
- `account.journal` - Accounting journals (`type`: sale, purchase, cash, bank, general)
- `account.tax` - Taxes (`amount`, `amount_type`, `type_tax_use`)

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

## Contacts (res.partner)

Contacts support tags and internal notes for better organization and tracking:

**Tags:**
- Field: `category_id` (many2many to `res.partner.category`)
- Tags are automatically created if they don't exist when assigning to contacts
- Used for categorization and filtering (e.g., "Customer", "Supplier", "VIP")
- Multiple tags can be assigned to a single contact

**Internal Notes:**
- Field: `comment` (text field)
- Private notes about the contact, not visible to the contact
- Useful for tracking relationship details, preferences, or history

```python
# Create contact with tags and notes
Partner = self.odoo.env["res.partner"]
Category = self.odoo.env["res.partner.category"]

# Find or create tags
tag_ids = []
for tag_name in ["Customer", "VIP"]:
    tag = Category.search([("name", "=", tag_name)], limit=1)
    if tag:
        tag_ids.append(tag[0])
    else:
        tag_ids.append(Category.create({"name": tag_name}))

# Create contact with tags and notes
Partner.create({
    "name": "John Doe",
    "email": "john@example.com",
    "category_id": [(6, 0, tag_ids)],  # Set tags
    "comment": "Met at trade show, interested in product line A"
})
```

**Key points:**
- Tags are shared across all contacts and can be reused
- Use `(6, 0, [ids])` to replace all tags on a contact
- Use `(5, 0, 0)` to clear all tags
- Internal notes are plain text, not HTML

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

## Spreadsheets and Dashboards

Odoo spreadsheets and spreadsheet dashboards both store their content as an
**o-spreadsheet JSON** document (a text field named `spreadsheet_data`).

**Where content lives:**
- Spreadsheets: `documents.document` records with `handler='spreadsheet'`. They live inside a Documents folder/workspace (`folder_id`). The folder model differs by version — `documents.folder` (Odoo 16/17) vs. `documents.document` with `type='folder'` (Odoo 18) — so `SpreadsheetsHandler._resolve_folder_id` tries both.
- Dashboards: `spreadsheet.dashboard` records, grouped by `spreadsheet.dashboard.group` (`dashboard_group_id`).

**Building o-spreadsheet JSON (`spreadsheet_utils.py`):**
- `build_table_spreadsheet(...)` turns a simple `headers` + `rows` table into a valid o-spreadsheet payload, with an optional bold title, totals row, and a chart figure. It sticks to the long-stable core of the format (`sheets[].cells` as `{content, style}` maps, top-level `styles`, and `figures`) so snapshots load across versions.
- `empty_spreadsheet(...)` returns a minimal blank document.
- `dumps(data)` serializes to the compact JSON string Odoo stores.
- Cell addresses are A1-style; `col_letter(i)` converts a 0-based column index to a letter.

**Inventory dashboard builder (`create_inventory_dashboard`):**
- Reads on-hand stock from `stock.quant` filtered to internal locations (`location_id.usage = 'internal'`), with optional `product`/`location` name filters and a `location_ids` list for exact locations.
- `mode='snapshot'` (default): aggregates in Python by `group_by` (product/location/warehouse/category) and `measure` (`quantity`, or `value`). For `warehouse`/`category`, it reads `stock.location.warehouse_id` / `product.product.categ_id` to map records to labels. For `value`, it uses the quant's `value` field when present, otherwise falls back to `quantity × product.standard_price`. Writes the result as plain values; re-run to refresh.
- `mode='live'`: writes a **self-refreshing** dashboard — an ODOO-type pivot data source on `stock.quant` (measures `quantity:sum` + `value:sum`, rows from `group_by` and optional `sub_group_by`, rendered by a spilled `=PIVOT(1)` formula) plus an `odoo_bar`/`odoo_line`/`odoo_pie` chart bound to the model. Both re-query Odoo on every dashboard open. `spreadsheet_utils.build_live_pivot_spreadsheet` builds this newer-schema (v21) payload; `DashboardsHandler._reference_schema` clones the schema version, `odooVersion`, and locale settings from an existing dashboard on the instance so the payload matches what the web client expects (falls back to 21/12). Grouping fields map via `_GROUP_FIELDS` to real `stock.quant` fields (`product_id`, `location_id`, `warehouse_id`, `product_categ_id`); the handler probes `read_group` first and returns a clear error if the instance can't group/aggregate that way.
- Targets: `target='dashboard'` creates a `spreadsheet.dashboard`; `target='spreadsheet'` delegates to `SpreadsheetsHandler.create_spreadsheet` (wired via `self.dashboards.spreadsheets` in the server); `dashboard_id` overwrites an existing dashboard's content instead (keeps its name unless `name` is passed).

**Advanced / live content:**
- For live content beyond what the inventory builder generates (other models, lists, global filters), build the o-spreadsheet JSON yourself and pass it through the `data_json` argument of `create_spreadsheet` / `create_dashboard` (or `update_*`). The reliable recipe: read a working dashboard's `spreadsheet_data` from the same instance and mirror its schema `version`, `odooVersion`, sheet skeleton, and pivot/list/figure structures. Odoo's server-side loader (`spreadsheet.dashboard.get_readonly_dashboard()`) is a useful smoke test that a hand-built payload parses.

**Requirements:** the Documents app for spreadsheets, the Dashboards app for dashboards, and the Inventory app (`stock.quant`) for the inventory builder. Each handler returns a clear error if the relevant app/model is unavailable.

## Manufacturing Read Tools

`ManufacturingHandler` (`manufacturing.py`) provides four read-only tools (`list_products`, `get_boms`, `get_stock`, `list_locations`) built to support clear-to-build (CTB) spreadsheet regeneration from live BoM data. Deliberately scoped: no generic `read_records(model, domain, fields)` passthrough (this server fronts an ERP), no writes to product/BoM/stock/location models, no `sudo()` — record rules apply. Each tool returns a markdown header plus a fenced JSON block with the structured rows for machine consumption.

Implementation notes the tools must respect (and that future changes must preserve):

- **Archived records**: `search` silently excludes `active=False` records. Instead of `context={'active_test': False}`, the handler adds `("active", "in", [True, False])` to the domain — mentioning `active` in a domain disables the implicit filter, and this is version-safe over RPC. `read` by id is never filtered by `active`, which is why archived components on active BoM lines appear (with `active: false`) in `get_boms` output rather than vanishing.
- **Storable vs consumable**: Odoo 18 uses `type='consu'` + boolean `is_storable`. The handler probes `fields_get` and, on older instances without `is_storable`, derives it as `type == 'product'`. Both fields are returned; non-storable products have no quants and are treated as always-available in CTB math.
- **BoM variant binding**: `mrp.bom` binds to `product_tmpl_id`; `mrp.bom.product_id` (nullable) selects a variant. `has_bom` in `list_products` and BoM filtering in `get_boms` are variant-aware: a template-level BoM counts for all variants, a variant-bound BoM only for its variant. `product_code` on a BoM is the bound variant's `default_code` when set, else the template's.
- **Quant aggregation**: `get_stock` uses `read_group` with `lazy=False` (required when grouping by multiple fields). Negative quantities pass through unfiltered. If the instance's `stock.quant` has no `value` field, value falls back to `quantity × standard_price`.

**Payload limits (verified 2026-07-25):** the server comfortably handles ≥100 KB tool arguments and results. `test_payload_limit.py` round-trips a 120 KB `data_json` through `update_dashboard` byte-perfect, both handler-level and through the real MCP stdio transport (129 KB request line), and reads it back via `get_dashboard(include_data=true)` (120 KB response). The ~46 KB `create_dashboard` abort observed earlier that day was the MCP *client* failing while emitting large tool-call arguments (LLM output limits), not a server or Odoo limit — which is the argument for generating large payloads server-side (Phase 2 `sync_ctb_dashboard`) rather than streaming them through an LLM.

## Accounting Read Tools

`AccountingHandler` (`accounting.py`) provides nine read-only tools (`list_invoices`, `get_invoice`, `list_payments`, `get_account_balances`, `get_aged_balances`, `list_journal_items`, `list_accounts`, `list_journals`, `list_taxes`). Deliberately scoped: no writes to any accounting model, no generic passthrough, no `sudo()` — record rules apply. Each tool returns a markdown header plus a fenced JSON block. `python test_accounting.py` smoke-tests all nine against the live instance (read-only, no teardown).

Invariants the tools rely on (and that future changes must preserve):

- **Journal entries excluded**: invoice tools cover only the four document types in `_KIND_TO_MOVE_TYPE` (friendly `kind` values mapping to `move_type`); `move_type='entry'` never appears. Entry-level data is reachable only in aggregate via `get_account_balances`.
- **Currency policy**: `account.move` amount fields (`amount_total`, `amount_residual`, ...) are document currency; the `*_signed` variants are company currency with direction sign (credit notes negative). Rows return both plus the `currency` name. `debit`/`credit`/`balance`/`amount_residual` on `account.move.line` are company currency, so balance/aging tools are company-currency only.
- **Sign conventions**: `balance = debit - credit`, so income accounts show negative (credit) balances — stated in output headers. `get_aged_balances` multiplies payable residuals by −1 so amounts owed to vendors read positive (a negative payable total means net vendor prepayment/debit balance, which is legitimate).
- **read_group grouping**: `get_account_balances` always groups by `account_id` (dotted paths are not valid `read_group` groupby values over RPC) and rolls up to `account_type` in Python after batch-reading `account.account`. Dotted **domains** (`account_id.account_type`) are attempted first with a fallback that resolves account ids via `account.account.search` — a failure degrades to a second query, not an error.
- **Double-entry invariant**: all lines of a move share the move's `date`, so summing `balance` across all accounts for any date range of posted entries is ~0. `test_accounting.py` asserts this (and per-move via `list_journal_items(move_id=...)`).
- **Raw journal items**: `list_journal_items` filters by `account_code` prefix by resolving ids via `account.account.search([("code", "=like", prefix%)])` first (never a dotted domain), errors if both `account_code` and `account_id` are passed, and treats the `reconciled` filter as tri-state (applied only when the key is present in arguments, since `False` is a meaningful filter value). `matching_number` is probed and null on instances without it. When the row count hits `limit`, the header says so — callers must not treat a truncated page as the full ledger.
- **Version probes** (via the `_has_field` fields_get cache): `account.payment.ref` → `memo` rename in Odoo 18 (output key is always `memo`); `account.payment.is_reconciled`; `account.account.deprecated` (16/17) vs `active` (18) — both emitted, null when absent; `account.account.account_type` requires Odoo 16+ (tools return a clear error on older instances); `account.journal.default_account_id`; `account.tax.price_include`. Payment `state` values also drift by version (16/17: draft/posted/cancel; 18 adds in_process/paid) and are passed through unvalidated.
- **Aging limitation**: `get_aged_balances` buckets **current** open (unreconciled, residual ≠ 0) items by days overdue vs `date_maturity` (falling back to the move date). A historical `as_of_date` re-buckets those current items; it does not reconstruct historical reconciliation state. Disclosed in the tool description and output header. Open items are read unbatched — fine at small-business scale; this is the scaling point if volumes grow.
- **Multi-company**: no company plumbing (consistent with the rest of the codebase; `ODOO_COMPANY_ID` remains documented-but-unused). Record rules scope results to the user's companies; cross-company totals mix company currencies only if the instance actually runs multiple currencies. `company` is shown in `get_invoice` output only.

## Key Dependencies

- **mcp** (>=1.0.0) - Model Context Protocol SDK
- **odoorpc** (>=0.10.0) - Odoo RPC client library
- **python-dotenv** (>=1.0.0) - Environment variable management
- **requests** - HTTP library for downloading images from URLs
