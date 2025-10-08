# Odoo MCP

A Model Context Protocol server for Odoo cloud apps.

## Overview

Odoo provides lots of functionality through its various apps. The goal of this repository is provide an MCP that supports as many of these apps as possible for using with various LLMs.

_note: This MCP supports the Odoo SaaS product._

## Setup

You need some environment variables set in a `.env` file:

```shell
ODOO_URL=https://yourcompany.odoo.com
ODOO_DB=yourcompany
ODOO_USERNAME=you@yourcompany.com
ODOO_API_KEY=<your api key>
# ODOO_COMPANY_ID=1  # optional, required in multi-company setups
```

### Installation

Install dependencies:

```bash
pip install mcp odoorpc python-dotenv
```

Or install the package in development mode:

```bash
pip install -e .
```

### Testing the Connection

Test your Odoo connection:

```bash
python test_connection.py
```

### Running the MCP Server

Run the server directly:

```bash
python -m odoo_mcp.server
```

Or if installed:

```bash
odoo-mcp
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "odoo": {
      "command": "python",
      "args": ["-m", "odoo_mcp.server"],
      "cwd": "/path/to/odoo-mcp"
    }
  }
}
```

### Claude Code

A `.mcp.json` file is included at the project root. When you open this project in Claude Code, it will automatically detect the MCP server configuration and prompt you to approve it.

Alternatively, you can manually add the server using:

```bash
claude mcp add odoo --scope project python -m odoo_mcp.server
```

### Cursor

Add to your Cursor MCP settings.

## Available Tools

### Projects

- **list_projects**: List all projects in Odoo with names, IDs, managers, customers, and task counts
- **get_project**: Get a specific project by ID with full details including name, description, manager, customer, and task count
- **create_project**: Create a new project with name and optional description
- **update_project**: Update an existing project - modify name or description
- **archive_project**: Archive a project (hidden from default views but can be restored later)
- **get_project_tasks**: Get all tasks/tickets for a specific project with details like assignees, stages, priorities, tags, and descriptions
- **search_tasks_by_tag**: Search for tasks by tag name across all projects. Returns all tasks with the specified tag regardless of project
- **create_task**: Create a new task in a project with optional fields like description, assignees (by name or email), stage, priority, deadline, and parent task (for subtasks)
- **update_task**: Update an existing task - modify name, description, assignees, stage, priority, or deadline
- **delete_task**: Permanently delete a task and all its subtasks
- **archive_task**: Archive a task (hidden from default views but can be restored later)
- **send_task_message**: Send a message on a task for comments, discussions, or internal notes. **Supports full HTML formatting** including bold (`<strong>`), italic (`<em>`), lists (`<ul>`, `<li>`), links (`<a href="">`), and line breaks (`<br>`). Plain text with newlines will be automatically converted to HTML.
- **get_task_messages**: Get all messages from a task's message thread with authors, dates, and content

### Knowledge

- **list_articles**: List knowledge articles with optional filtering by parent ID for hierarchical navigation
- **get_article**: Get a specific article by ID with full content, metadata, and hierarchy information
- **create_article**: Create a new knowledge article with optional body content and parent article for organization
- **update_article**: Update an existing article - modify name, body content, or parent article
- **delete_article**: Permanently delete a knowledge article
- **archive_article**: Archive an article (hidden from default views but can be restored later)

### Helpdesk

- **list_helpdesk_teams**: List all helpdesk teams with names, IDs, ticket counts, and configuration details
- **list_tickets**: List helpdesk tickets with optional filtering by team ID
- **get_ticket**: Get a specific ticket by ID with full details including description and customer information
- **get_ticket_messages**: Get all messages from a ticket's message thread with authors and content
- **create_ticket**: Create a new helpdesk ticket with subject, description, customer, and priority
- **update_ticket**: Update an existing ticket - modify subject, description, stage, priority, or assignment
- **close_ticket**: Close a ticket by moving it to the closed/done stage
- **send_ticket_message**: Send a message on a ticket for customer communication or internal notes. **Supports full HTML formatting** including bold (`<strong>`), italic (`<em>`), lists (`<ul>`, `<li>`), links (`<a href="">`), and line breaks (`<br>`). Plain text with newlines will be automatically converted to HTML.

### Contacts

- **list_contacts**: List contacts in Odoo with optional filtering by type (company or individual). Returns names, IDs, emails, phones, tags, and company information
- **get_contact**: Get a specific contact by ID with comprehensive details including address, email, phone, mobile, website, VAT/tax ID, title, job function, internal reference, tags, internal notes, and related company
- **search_contacts**: Search contacts by name, email, or company name. Returns matching contacts with basic information including tags
- **search_contacts_by_tag**: Search contacts by tag name. Returns all contacts that have the specified tag
- **create_contact**: Create a new contact with comprehensive support for all res.partner fields including email, phone, mobile, website, VAT/tax ID, title, job function, internal reference, address, state/province, country, parent company, tags, internal notes, and logo/image from URL. Supports both company and individual contacts
- **update_contact**: Update an existing contact - modify any field including name, email, phone, mobile, website, VAT/tax ID, title, job function, internal reference, address, state/province, country, tags, internal notes, or upload logo/image from URL
- **delete_contact**: Permanently delete a contact
- **archive_contact**: Archive a contact (hidden from default views but can be restored later)

### Mailing Lists

- **list_mailing_lists**: List all mailing lists with subscriber counts
- **get_mailing_list**: Get a specific mailing list by ID with full details, subscriber list, and opt-out status with timestamps
- **create_mailing_list**: Create a new mailing list
- **update_mailing_list**: Update mailing list name
- **delete_mailing_list**: Permanently delete a mailing list and all its subscriptions
- **subscribe_contact**: Subscribe a contact to a mailing list by email (creates mailing contact if needed)
- **unsubscribe_contact**: Unsubscribe a contact from a mailing list
- **get_contact_subscriptions**: Get all mailing lists a contact is subscribed to by email
- **opt_in_contact**: Opt a contact back into a mailing list (reverses opt-out)
- **opt_out_contact**: Opt a contact out of a mailing list (manual opt-out with timestamp)

### Users

- **list_users**: List Odoo users with names, IDs, logins, and email addresses. Useful for assigning tasks and tickets to team members

### Activities (Scheduled Follow-ups)

- **list_activities**: List activities/to-dos with optional filtering by user, state (overdue, today, planned, done), or activity type. Returns all scheduled activities with details
- **get_activity**: Get a specific activity by ID with full details including type, assignee, deadline, state, and linked record
- **create_activity**: Create a new activity/to-do with summary, description, deadline, and assignee. Can be linked to any Odoo record or created as standalone
- **update_activity**: Update an existing activity - modify summary, description, deadline, assignee, or activity type
- **mark_activity_done**: Mark an activity as done/completed with optional feedback note
- **delete_activity**: Permanently delete an activity
- **list_activity_types**: List all available activity types (To-do, Call, Email, Meeting, etc.) with their default settings

### To-Do App (Personal Tasks)

- **list_todos**: List personal to-dos from the To-Do app with optional filtering by stage (Today, This Week, Inbox, Later) or user. Returns tasks without a project assignment
- **get_todo**: Get a specific to-do by ID with full details including stage, priority, deadline, tags, and description
- **create_todo**: Create a new personal to-do with name, description, deadline, stage, priority, and tags. Defaults to "Today" stage
- **update_todo**: Update an existing to-do - modify name, description, deadline, stage (move between Today/This Week/etc.), or priority
- **mark_todo_done**: Mark a to-do as done by moving it to the "Done" stage. Quick way to complete personal tasks
- **delete_todo**: Permanently delete a to-do from the To-Do app
- **list_todo_stages**: List all available to-do stages (Inbox, Today, This Week, This Month, Later, Done, etc.) with their sequence and fold status

## Supported Apps (Roadmap)

- [x] Projects - interact with projects. Read, create, update, delete, and archive tasks.
- [x] Knowledge - interact with knowledge base. Read, create, update, delete, and archive articles.
- [x] Helpdesk - interact with helpdesk. Read, create, update, close tickets. Send messages for customer communication.
- [x] Contacts - full CRUD operations on contacts. Read, create, update, delete, and archive contacts (companies and individuals).
- [x] Mailing Lists - manage email marketing lists. Create, update, delete lists. Subscribe/unsubscribe contacts. Query subscriptions.
- [x] Activities - manage scheduled follow-ups and activities. List, create, update, mark done, and delete activities. Link activities to any record.
- [x] To-Do App - manage personal to-do list. List, create, update, mark done, and delete to-dos. Organize by stages (Today, This Week, etc.).

... more to come (or you can open a PR and add what you need!)

## Development

The MCP server is built with:
- `mcp` - Model Context Protocol SDK
- `odoorpc` - Odoo XML-RPC/JSON-RPC client
- `python-dotenv` - Environment variable management
- `requests` - HTTP library for downloading images

### Architecture

The codebase follows a modular architecture with separate handler modules for each Odoo app:

```
odoo-mcp/
├── odoo_mcp/
│   ├── __init__.py
│   ├── server.py          # Main MCP server (tool registration and routing)
│   ├── base.py            # Base class with shared Odoo connection logic
│   ├── projects.py        # Projects and tasks operations (13 tools)
│   ├── knowledge.py       # Knowledge articles operations (6 tools)
│   ├── helpdesk.py        # Helpdesk tickets operations (8 tools)
│   ├── contacts.py        # Contacts/partners operations (8 tools)
│   ├── mailing.py         # Mailing lists operations (10 tools)
│   ├── users.py           # Users operations (1 tool)
│   ├── activities.py      # Activities/scheduled follow-ups (7 tools)
│   └── todos.py           # To-Do app/personal tasks (7 tools)
├── test_connection.py     # Test script for Odoo connectivity
├── pyproject.toml        # Project dependencies
├── .env                  # Environment variables (gitignored)
└── README.md
```

**Design Pattern:**
- `OdooBase` - Base class providing Odoo connection management and cleanup
- Handler classes inherit from `OdooBase` and implement operations for each Odoo app
- `OdooMCPServer` - Main server class that initializes all handlers and routes tool calls
- Tools are defined as async methods in handler classes
- Each tool connects to Odoo via `odoorpc` and returns formatted results

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
