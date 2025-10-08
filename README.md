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

Add to your Claude Code MCP settings (`~/.config/claude-code/mcp_settings.json`):

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

### Cursor

Add to your Cursor MCP settings.

## Available Tools

### Projects

- **list_projects**: List all projects in Odoo with names, IDs, managers, customers, and task counts
- **get_project_tasks**: Get all tasks/tickets for a specific project with details like assignees, stages, priorities, and descriptions

## Supported Apps (Roadmap)

- [x] Projects - interact with projects. Read projects and tasks.
- [ ] Knowledge - interact with knowledge base. Read and update documents.
- [ ] Helpdesk - interact with help desk projects. Read and update tickets. Read and send messages with customers.
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
