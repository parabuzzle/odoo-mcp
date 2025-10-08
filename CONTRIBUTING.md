# Contributing to Odoo MCP

Thank you for your interest in contributing to Odoo MCP! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Your Odoo version and environment details

### Suggesting Features

We welcome feature suggestions! Please open an issue with:
- A clear description of the feature
- The Odoo app it relates to
- Use cases and examples
- Why this would be valuable

### Adding New Odoo App Support

The main goal of this project is to support as many Odoo apps as possible. To add support for a new app:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/add-helpdesk-support`
3. **Add new tools** in `odoo_mcp/server.py`:
   - Define the tool in the `list_tools()` method
   - Implement the handler method
   - Follow the existing pattern for Projects tools
4. **Update documentation**:
   - Add the tool to README.md under "Available Tools"
   - Update the roadmap checkboxes
   - Document any Odoo-specific requirements
5. **Test your changes**:
   - Verify the tool works with your Odoo instance
   - Test error handling
   - Ensure it works with both Claude Desktop and Claude Code
6. **Submit a pull request**

### Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and readable

### Pull Request Process

1. Update the README.md with details of changes (new tools, configuration changes, etc.)
2. Update CLAUDE.md if architectural changes are made
3. Ensure your code works with the latest Odoo SaaS version
4. Your PR will be reviewed and merged once approved

## Development Setup

1. Clone the repository
2. Create a `.env` file with your Odoo credentials
3. Install dependencies: `pip install -e .`
4. Test the connection: `python test_connection.py`
5. Make your changes
6. Test with: `python -m odoo_mcp.server`

## Odoo App Priority

We're particularly interested in support for these Odoo apps:
- **Helpdesk** - Ticket management and customer communication
- **Knowledge** - Document management
- **Contacts** - CRM contact management
- **Sales** - Sales orders and quotations
- **Inventory** - Stock and warehouse management
- **Accounting** - Financial operations
- **HR** - Human resources management

## Questions?

Feel free to open an issue for any questions about contributing!

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
