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
            Tool(
                name="create_task",
                description="Create a new task in a project. Returns the created task ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "The ID of the project to create the task in"
                        },
                        "name": {
                            "type": "string",
                            "description": "The task name/title"
                        },
                        "description": {
                            "type": "string",
                            "description": "The task description (optional)"
                        },
                        "assignee_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of user names to assign to the task (optional)"
                        },
                        "stage_name": {
                            "type": "string",
                            "description": "The stage/status name (e.g., 'Todo', 'In Progress', 'Done'). If not provided, uses the first stage."
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["normal", "high"],
                            "description": "Task priority (optional, default: normal)"
                        },
                        "deadline": {
                            "type": "string",
                            "description": "Deadline in YYYY-MM-DD format (optional)"
                        },
                        "parent_id": {
                            "type": "integer",
                            "description": "Parent task ID to create this as a subtask (optional)"
                        }
                    },
                    "required": ["project_id", "name"]
                }
            ),
            Tool(
                name="update_task",
                description="Update an existing task. Can update any field including transitioning to a different stage.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New task name/title (optional)"
                        },
                        "description": {
                            "type": "string",
                            "description": "New task description (optional)"
                        },
                        "assignee_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New list of user names to assign (optional). This replaces all existing assignees."
                        },
                        "stage_name": {
                            "type": "string",
                            "description": "New stage/status name to transition to (e.g., 'Todo', 'In Progress', 'Done', 'Closed')"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["normal", "high"],
                            "description": "New task priority (optional)"
                        },
                        "deadline": {
                            "type": "string",
                            "description": "New deadline in YYYY-MM-DD format (optional)"
                        }
                    },
                    "required": ["task_id"]
                }
            ),
            Tool(
                name="delete_task",
                description="Delete a task. This will permanently remove the task and all its subtasks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to delete"
                        }
                    },
                    "required": ["task_id"]
                }
            ),
            Tool(
                name="archive_task",
                description="Archive a task. Archived tasks are hidden from default views but can be restored later.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to archive"
                        }
                    },
                    "required": ["task_id"]
                }
            ),
            Tool(
                name="list_articles",
                description="List knowledge articles in Odoo. Returns article names, IDs, and basic information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of articles to return (default: 50)",
                            "default": 50
                        },
                        "parent_id": {
                            "type": "integer",
                            "description": "Filter articles by parent ID (optional, for hierarchical articles)"
                        }
                    }
                }
            ),
            Tool(
                name="get_article",
                description="Get a specific knowledge article by ID. Returns full article content including body, metadata, and hierarchy.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The ID of the article to retrieve"
                        }
                    },
                    "required": ["article_id"]
                }
            ),
            Tool(
                name="create_article",
                description="Create a new knowledge article. Returns the created article ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The article title/name"
                        },
                        "body": {
                            "type": "string",
                            "description": "The article content (HTML format, optional)"
                        },
                        "parent_id": {
                            "type": "integer",
                            "description": "Parent article ID for hierarchical structure (optional)"
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_article",
                description="Update an existing knowledge article. Can update name, body, or parent.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The ID of the article to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New article title/name (optional)"
                        },
                        "body": {
                            "type": "string",
                            "description": "New article content (HTML format, optional)"
                        },
                        "parent_id": {
                            "type": "integer",
                            "description": "New parent article ID (optional)"
                        }
                    },
                    "required": ["article_id"]
                }
            ),
            Tool(
                name="delete_article",
                description="Delete a knowledge article. This will permanently remove the article.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The ID of the article to delete"
                        }
                    },
                    "required": ["article_id"]
                }
            ),
            Tool(
                name="archive_article",
                description="Archive a knowledge article. Archived articles are hidden from default views but can be restored later.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The ID of the article to archive"
                        }
                    },
                    "required": ["article_id"]
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
            elif name == "create_task":
                return await self.create_task(arguments)
            elif name == "update_task":
                return await self.update_task(arguments)
            elif name == "delete_task":
                return await self.delete_task(arguments)
            elif name == "archive_task":
                return await self.archive_task(arguments)
            elif name == "list_articles":
                return await self.list_articles(arguments)
            elif name == "get_article":
                return await self.get_article(arguments)
            elif name == "create_article":
                return await self.create_article(arguments)
            elif name == "update_article":
                return await self.update_article(arguments)
            elif name == "delete_article":
                return await self.delete_article(arguments)
            elif name == "archive_article":
                return await self.archive_article(arguments)
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
            user_id = project.get("user_id")
            manager = user_id[1] if user_id else "Unassigned"
            partner_id = project.get("partner_id")
            partner = partner_id[1] if partner_id else "No customer"
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

            stage_id = task.get("stage_id")
            stage = stage_id[1] if stage_id else "No stage"
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

    def _find_user_ids(self, user_names: list[str]) -> list[int]:
        """Find user IDs by name or email."""
        if not user_names:
            return []

        User = self.odoo.env["res.users"]
        user_ids = []

        for name in user_names:
            # Search for user by name or login (email) (case-insensitive)
            found_ids = User.search([
                "|",
                ("name", "ilike", name),
                ("login", "ilike", name)
            ], limit=1)
            if found_ids:
                user_ids.append(found_ids[0])
            else:
                logger.warning(f"User not found: {name}")

        return user_ids

    def _find_stage_id(self, project_id: int, stage_name: str) -> int:
        """Find stage ID by name for a specific project."""
        Stage = self.odoo.env["project.task.type"]

        # Search for stage by name in this project
        stage_ids = Stage.search([
            ("name", "ilike", stage_name),
            "|",
            ("project_ids", "=", project_id),
            ("project_ids", "=", False)  # Stages available to all projects
        ], limit=1)

        if not stage_ids:
            raise ValueError(f"Stage '{stage_name}' not found for project {project_id}")

        return stage_ids[0]

    async def create_task(self, arguments: dict) -> list[TextContent]:
        """Create a new task in a project."""
        project_id = arguments.get("project_id")
        name = arguments.get("name")

        if not project_id or not name:
            return [TextContent(type="text", text="Error: project_id and name are required")]

        # Build task values
        task_values = {
            "project_id": project_id,
            "name": name,
        }

        # Add optional fields
        if "description" in arguments and arguments["description"]:
            task_values["description"] = arguments["description"]

        # Handle assignees
        if "assignee_names" in arguments and arguments["assignee_names"]:
            user_ids = self._find_user_ids(arguments["assignee_names"])
            if user_ids:
                task_values["user_ids"] = [(6, 0, user_ids)]  # Odoo many2many replace syntax

        # Handle stage
        if "stage_name" in arguments and arguments["stage_name"]:
            stage_id = self._find_stage_id(project_id, arguments["stage_name"])
            task_values["stage_id"] = stage_id

        # Handle priority
        if "priority" in arguments:
            priority_map = {"normal": "0", "high": "1"}
            task_values["priority"] = priority_map.get(arguments["priority"], "0")

        # Handle deadline
        if "deadline" in arguments and arguments["deadline"]:
            task_values["date_deadline"] = arguments["deadline"]

        # Handle parent task (for subtasks)
        if "parent_id" in arguments and arguments["parent_id"]:
            task_values["parent_id"] = arguments["parent_id"]

        # Create the task
        Task = self.odoo.env["project.task"]
        new_task_id = Task.create(task_values)

        # Read the created task to return details
        task = Task.read(new_task_id, ["name", "id", "stage_id", "user_ids", "project_id"])[0]

        # Format output
        stage_id = task.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        project_id_field = task.get("project_id")
        project_name = project_id_field[1] if project_id_field else "Unknown"

        assignees = task.get("user_ids", [])
        if assignees and len(assignees) > 0:
            User = self.odoo.env["res.users"]
            user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
            assignee_str = ", ".join(user_names)
        else:
            assignee_str = "Unassigned"

        output = (
            f"# Task Created Successfully\n\n"
            f"**{task['name']}** (ID: {task['id']})\n"
            f"- Project: {project_name}\n"
            f"- Stage: {stage}\n"
            f"- Assigned to: {assignee_str}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_task(self, arguments: dict) -> list[TextContent]:
        """Update an existing task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "description" in arguments:
            update_values["description"] = arguments["description"]

        # Handle assignees
        if "assignee_names" in arguments:
            user_ids = self._find_user_ids(arguments["assignee_names"])
            update_values["user_ids"] = [(6, 0, user_ids)]  # Replace all assignees

        # Handle stage transition
        if "stage_name" in arguments and arguments["stage_name"]:
            # Get the task's project to find the right stage
            Task = self.odoo.env["project.task"]
            task = Task.read(task_id, ["project_id"])[0]
            project_id = task["project_id"][0] if task["project_id"] else None

            if project_id:
                stage_id = self._find_stage_id(project_id, arguments["stage_name"])
                update_values["stage_id"] = stage_id

        # Handle priority
        if "priority" in arguments:
            priority_map = {"normal": "0", "high": "1"}
            update_values["priority"] = priority_map.get(arguments["priority"], "0")

        # Handle deadline
        if "deadline" in arguments:
            update_values["date_deadline"] = arguments["deadline"] if arguments["deadline"] else False

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the task
        Task = self.odoo.env["project.task"]
        Task.write(task_id, update_values)

        # Read the updated task to return details
        task = Task.read(task_id, ["name", "id", "stage_id", "user_ids", "project_id", "priority", "date_deadline"])[0]

        # Format output
        stage_id = task.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        project_id_field = task.get("project_id")
        project_name = project_id_field[1] if project_id_field else "Unknown"

        assignees = task.get("user_ids", [])
        if assignees and len(assignees) > 0:
            User = self.odoo.env["res.users"]
            user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
            assignee_str = ", ".join(user_names)
        else:
            assignee_str = "Unassigned"

        priority = task.get("priority", "0")
        priority_map = {"0": "Normal", "1": "High"}
        priority_str = priority_map.get(priority, priority)

        deadline = task.get("date_deadline", "No deadline")

        output = (
            f"# Task Updated Successfully\n\n"
            f"**{task['name']}** (ID: {task['id']})\n"
            f"- Project: {project_name}\n"
            f"- Stage: {stage}\n"
            f"- Priority: {priority_str}\n"
            f"- Assigned to: {assignee_str}\n"
            f"- Deadline: {deadline}\n"
        )

        return [TextContent(type="text", text=output)]

    async def delete_task(self, arguments: dict) -> list[TextContent]:
        """Delete a task permanently."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Get task details before deletion
        Task = self.odoo.env["project.task"]
        task = Task.read(task_id, ["name", "id"])[0]
        task_name = task["name"]

        # Delete the task
        Task.unlink(task_id)

        output = (
            f"# Task Deleted Successfully\n\n"
            f"Task **{task_name}** (ID: {task_id}) has been permanently deleted."
        )

        return [TextContent(type="text", text=output)]

    async def archive_task(self, arguments: dict) -> list[TextContent]:
        """Archive a task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Archive the task by setting active=False
        Task = self.odoo.env["project.task"]
        Task.write(task_id, {"active": False})

        # Read the archived task to return details
        task = Task.read(task_id, ["name", "id"])[0]

        output = (
            f"# Task Archived Successfully\n\n"
            f"Task **{task['name']}** (ID: {task['id']}) has been archived."
        )

        return [TextContent(type="text", text=output)]

    async def list_articles(self, arguments: dict) -> list[TextContent]:
        """List knowledge articles."""
        limit = arguments.get("limit", 50)
        parent_id = arguments.get("parent_id")

        # Access knowledge.article model
        Article = self.odoo.env["knowledge.article"]

        # Build search domain
        domain = []
        if parent_id is not None:
            domain.append(("parent_id", "=", parent_id))

        # Search for articles
        article_ids = Article.search(domain, limit=limit)

        if not article_ids:
            return [TextContent(type="text", text="No articles found.")]

        # Read article details
        articles = Article.read(
            article_ids,
            ["name", "id", "parent_id", "write_date", "active"]
        )

        # Format output
        output_lines = ["# Knowledge Articles\n"]
        for article in articles:
            parent_id_field = article.get("parent_id")
            parent = parent_id_field[1] if parent_id_field else "No parent"
            write_date = article.get("write_date", "Unknown")
            active = "Active" if article.get("active", True) else "Archived"

            output_lines.append(
                f"## {article['name']} (ID: {article['id']})\n"
                f"- Status: {active}\n"
                f"- Parent: {parent}\n"
                f"- Last modified: {write_date}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_article(self, arguments: dict) -> list[TextContent]:
        """Get a specific article with full content."""
        article_id = arguments.get("article_id")

        if not article_id:
            return [TextContent(type="text", text="Error: article_id is required")]

        # Access knowledge.article model
        Article = self.odoo.env["knowledge.article"]

        # Read article with full details
        article = Article.read(
            article_id,
            ["name", "id", "body", "parent_id", "write_date", "active"]
        )[0]

        parent_id_field = article.get("parent_id")
        parent = parent_id_field[1] if parent_id_field else "No parent"
        write_date = article.get("write_date", "Unknown")
        active = "Active" if article.get("active", True) else "Archived"
        body = article.get("body") or "No content"

        output = (
            f"# {article['name']}\n\n"
            f"**ID:** {article['id']}  \n"
            f"**Status:** {active}  \n"
            f"**Parent:** {parent}  \n"
            f"**Last modified:** {write_date}\n\n"
            f"## Content\n\n{body}"
        )

        return [TextContent(type="text", text=output)]

    async def create_article(self, arguments: dict) -> list[TextContent]:
        """Create a new knowledge article."""
        name = arguments.get("name")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        # Build article values
        article_values = {
            "name": name,
        }

        # Add optional fields
        if "body" in arguments and arguments["body"]:
            article_values["body"] = arguments["body"]

        if "parent_id" in arguments and arguments["parent_id"]:
            article_values["parent_id"] = arguments["parent_id"]

        # Create the article
        Article = self.odoo.env["knowledge.article"]
        new_article_id = Article.create(article_values)

        # Read the created article to return details
        article = Article.read(new_article_id, ["name", "id", "parent_id"])[0]

        parent_id_field = article.get("parent_id")
        parent = parent_id_field[1] if parent_id_field else "No parent"

        output = (
            f"# Article Created Successfully\n\n"
            f"**{article['name']}** (ID: {article['id']})\n"
            f"- Parent: {parent}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_article(self, arguments: dict) -> list[TextContent]:
        """Update an existing knowledge article."""
        article_id = arguments.get("article_id")

        if not article_id:
            return [TextContent(type="text", text="Error: article_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "body" in arguments:
            update_values["body"] = arguments["body"]

        if "parent_id" in arguments:
            update_values["parent_id"] = arguments["parent_id"]

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the article
        Article = self.odoo.env["knowledge.article"]
        Article.write(article_id, update_values)

        # Read the updated article to return details
        article = Article.read(article_id, ["name", "id", "parent_id"])[0]

        parent_id_field = article.get("parent_id")
        parent = parent_id_field[1] if parent_id_field else "No parent"

        output = (
            f"# Article Updated Successfully\n\n"
            f"**{article['name']}** (ID: {article['id']})\n"
            f"- Parent: {parent}\n"
        )

        return [TextContent(type="text", text=output)]

    async def delete_article(self, arguments: dict) -> list[TextContent]:
        """Delete a knowledge article permanently."""
        article_id = arguments.get("article_id")

        if not article_id:
            return [TextContent(type="text", text="Error: article_id is required")]

        # Get article details before deletion
        Article = self.odoo.env["knowledge.article"]
        article = Article.read(article_id, ["name", "id"])[0]
        article_name = article["name"]

        # Delete the article
        Article.unlink(article_id)

        output = (
            f"# Article Deleted Successfully\n\n"
            f"Article **{article_name}** (ID: {article_id}) has been permanently deleted."
        )

        return [TextContent(type="text", text=output)]

    async def archive_article(self, arguments: dict) -> list[TextContent]:
        """Archive a knowledge article."""
        article_id = arguments.get("article_id")

        if not article_id:
            return [TextContent(type="text", text="Error: article_id is required")]

        # Archive the article by setting active=False
        Article = self.odoo.env["knowledge.article"]
        Article.write(article_id, {"active": False})

        # Read the archived article to return details
        article = Article.read(article_id, ["name", "id"])[0]

        output = (
            f"# Article Archived Successfully\n\n"
            f"Article **{article['name']}** (ID: {article['id']}) has been archived."
        )

        return [TextContent(type="text", text=output)]

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
