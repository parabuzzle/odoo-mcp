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
- **get_project_tasks**: Get all tasks/tickets for a specific project with details like assignees, stages, priorities, and descriptions
- **create_task**: Create a new task in a project with optional fields like description, assignees (by name or email), stage, priority, deadline, and parent task (for subtasks)
- **update_task**: Update an existing task - modify name, description, assignees, stage, priority, or deadline
- **delete_task**: Permanently delete a task and all its subtasks
- **archive_task**: Archive a task (hidden from default views but can be restored later)

### Knowledge

- **list_articles**: List knowledge articles with optional filtering by parent ID for hierarchical navigation
- **get_article**: Get a specific article by ID with full content, metadata, and hierarchy information
- **create_article**: Create a new knowledge article with optional body content and parent article for organization
- **update_article**: Update an existing article - modify name, body content, or parent article
- **delete_article**: Permanently delete a knowledge article
- **archive_article**: Archive an article (hidden from default views but can be restored later)

### Helpdesk

- **list_tickets**: List helpdesk tickets with optional filtering by team ID
- **get_ticket**: Get a specific ticket by ID with full details including description and customer information
- **get_ticket_messages**: Get all messages from a ticket's message thread with authors and content
- **create_ticket**: Create a new helpdesk ticket with subject, description, customer, and priority
- **update_ticket**: Update an existing ticket - modify subject, description, stage, priority, or assignment
- **close_ticket**: Close a ticket by moving it to the closed/done stage
- **send_ticket_message**: Send a message on a ticket for customer communication or internal notes. **Supports full HTML formatting** including bold (`<strong>`), italic (`<em>`), lists (`<ul>`, `<li>`), links (`<a href="">`), and line breaks (`<br>`). Plain text with newlines will be automatically converted to HTML.

## Supported Apps (Roadmap)

- [x] Projects - interact with projects. Read, create, update, delete, and archive tasks.
- [x] Knowledge - interact with knowledge base. Read, create, update, delete, and archive articles.
- [x] Helpdesk - interact with helpdesk. Read, create, update, close tickets. Send messages for customer communication.
- [ ] Contacts - read and update contacts

... more to come (or you can open a PR and add what you need!)

## Development

The MCP server is built with:
- `mcp` - Model Context Protocol SDK
- `odoorpc` - Odoo XML-RPC/JSON-RPC client
- `python-dotenv` - Environment variable management

Architecture:
- `odoo_mcp/server.py` - Main MCP server implementation
- Tools are defined as async methods in the `OdooMCPServer` class
- Each tool connects to Odoo via `odoorpc` and returns formatted results

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
