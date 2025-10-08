#!/usr/bin/env python3
"""Odoo MCP Server - Provides MCP interface to Odoo cloud apps."""

import os
import logging
from typing import Any
import asyncio

import odoorpc
from mcp.server import Server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odoo-mcp")


class OdooMCPServer:
    """MCP Server for Odoo integration."""

    def __init__(self):
        """Initialize the Odoo MCP server."""
        self.odoo = None
        self.server = Server("odoo-mcp")

        # Register handlers
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    def connect_odoo(self):
        """Connect to Odoo instance."""
        odoo_url = os.getenv("ODOO_URL", "").replace("https://", "").replace("http://", "")
        odoo_db = os.getenv("ODOO_DB")
        odoo_username = os.getenv("ODOO_USERNAME")
        odoo_api_key = os.getenv("ODOO_API_KEY")

        if not all([odoo_url, odoo_db, odoo_username, odoo_api_key]):
            raise ValueError(
                "Missing required environment variables. "
                "Please set ODOO_URL, ODOO_DB, ODOO_USERNAME, and ODOO_API_KEY"
            )

        logger.info(f"Connecting to Odoo at {odoo_url}...")

        # Create Odoo connection
        self.odoo = odoorpc.ODOO(odoo_url, protocol="jsonrpc+ssl", port=443)

        # Login with API key
        self.odoo.login(odoo_db, odoo_username, odoo_api_key)

        logger.info(f"Connected to Odoo as {odoo_username}")

    async def list_tools(self) -> list[Tool]:
        """List available MCP tools."""
        return [
            Tool(
                name="list_projects",
                description="List all projects in Odoo. Returns project names, IDs, and basic information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of projects to return (default: 20)",
                            "default": 20
                        }
                    }
                }
            ),
            Tool(
                name="get_project_tasks",
                description="Get tasks/tickets for a specific project. Returns task details including name, status, assignee, and description.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "The ID of the project to get tasks from"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of tasks to return (default: 50)",
                            "default": 50
                        }
                    },
                    "required": ["project_id"]
                }
            ),
        ]

    async def call_tool(self, name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if not self.odoo:
                self.connect_odoo()

            if name == "list_projects":
                return await self.list_projects(arguments)
            elif name == "get_project_tasks":
                return await self.get_project_tasks(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Error calling tool {name}: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def list_projects(self, arguments: dict) -> list[TextContent]:
        """List all projects."""
        limit = arguments.get("limit", 20)

        # Access project.project model
        Project = self.odoo.env["project.project"]

        # Search for projects
        project_ids = Project.search([], limit=limit)

        if not project_ids:
            return [TextContent(type="text", text="No projects found.")]

        # Read project details
        projects = Project.read(
            project_ids,
            ["name", "id", "user_id", "partner_id", "task_count", "active"]
        )

        # Format output
        output_lines = ["# Odoo Projects\n"]
        for project in projects:
            manager = project.get("user_id", [False, "Unassigned"])[1]
            partner = project.get("partner_id", [False, "No customer"])[1]
            task_count = project.get("task_count", 0)
            active = "Active" if project.get("active", True) else "Archived"

            output_lines.append(
                f"## {project['name']} (ID: {project['id']})\n"
                f"- Status: {active}\n"
                f"- Manager: {manager}\n"
                f"- Customer: {partner}\n"
                f"- Tasks: {task_count}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_project_tasks(self, arguments: dict) -> list[TextContent]:
        """Get tasks for a specific project."""
        project_id = arguments.get("project_id")
        limit = arguments.get("limit", 50)

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Access project.task model
        Task = self.odoo.env["project.task"]

        # Search for tasks in this project
        task_ids = Task.search([("project_id", "=", project_id)], limit=limit)

        if not task_ids:
            return [TextContent(type="text", text=f"No tasks found in project {project_id}.")]

        # Read task details
        tasks = Task.read(
            task_ids,
            ["name", "id", "user_ids", "stage_id", "priority", "description", "date_deadline"]
        )

        # Get project name
        Project = self.odoo.env["project.project"]
        project = Project.read(project_id, ["name"])[0]

        # Format output
        output_lines = [f"# Tasks in {project['name']}\n"]
        for task in tasks:
            assignees = task.get("user_ids", [])
            if assignees and len(assignees) > 0:
                # user_ids returns list of IDs, need to fetch names
                User = self.odoo.env["res.users"]
                user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
                assignee_str = ", ".join(user_names)
            else:
                assignee_str = "Unassigned"

            stage = task.get("stage_id", [False, "No stage"])[1]
            priority = task.get("priority", "0")
            priority_map = {"0": "Normal", "1": "High"}
            priority_str = priority_map.get(priority, priority)
            deadline = task.get("date_deadline", "No deadline")
            description = task.get("description") or "No description"

            output_lines.append(
                f"## {task['name']} (ID: {task['id']})\n"
                f"- Stage: {stage}\n"
                f"- Priority: {priority_str}\n"
                f"- Assigned to: {assignee_str}\n"
                f"- Deadline: {deadline}\n"
                f"- Description: {description}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def run(self):
        """Run the MCP server."""
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Main entry point."""
    server = OdooMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
