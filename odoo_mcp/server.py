#!/usr/bin/env python3
"""Odoo MCP Server - Provides MCP interface to Odoo cloud apps."""

import logging
from typing import Any
import asyncio

from mcp.server import Server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# Import handlers
from .projects import ProjectsHandler
from .knowledge import KnowledgeHandler
from .helpdesk import HelpdeskHandler
from .contacts import ContactsHandler
from .mailing import MailingHandler
from .users import UsersHandler
from .activities import ActivitiesHandler
from .todos import TodosHandler
from .spreadsheets import SpreadsheetsHandler
from .dashboards import DashboardsHandler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odoo-mcp")


class OdooMCPServer:
    """MCP Server for Odoo integration."""

    def __init__(self):
        """Initialize the Odoo MCP server."""
        self.server = Server("odoo-mcp")

        # Initialize handlers
        self.projects = ProjectsHandler()
        self.knowledge = KnowledgeHandler()
        self.helpdesk = HelpdeskHandler()
        self.contacts = ContactsHandler()
        self.mailing = MailingHandler()
        self.users = UsersHandler()
        self.activities = ActivitiesHandler()
        self.todos = TodosHandler()
        self.spreadsheets = SpreadsheetsHandler()
        self.dashboards = DashboardsHandler()
        # Let the inventory dashboard builder also create Documents spreadsheets.
        self.dashboards.spreadsheets = self.spreadsheets

        # Register handlers
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    def connect_odoo(self):
        """Connect to Odoo instance and share with handlers."""
        # Connect via projects handler (they all inherit from OdooBase)
        self.projects.connect_odoo()

        # Share the connection with all handlers
        self.knowledge.odoo = self.projects.odoo
        self.helpdesk.odoo = self.projects.odoo
        self.contacts.odoo = self.projects.odoo
        self.mailing.odoo = self.projects.odoo
        self.users.odoo = self.projects.odoo
        self.activities.odoo = self.projects.odoo
        self.todos.odoo = self.projects.odoo
        self.spreadsheets.odoo = self.projects.odoo
        self.dashboards.odoo = self.projects.odoo

    def cleanup(self):
        """Cleanup resources on shutdown."""
        self.projects.cleanup()

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
                name="get_project",
                description="Get a specific project by ID. Returns full project details including name, description, and task count.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "The ID of the project to retrieve"
                        }
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="create_project",
                description="Create a new project. Returns the created project ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The project name (required)"
                        },
                        "description": {
                            "type": "string",
                            "description": "The project description (optional)"
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_project",
                description="Update an existing project. Can update name and description.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "The ID of the project to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New project name (optional)"
                        },
                        "description": {
                            "type": "string",
                            "description": "New project description (optional)"
                        }
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="archive_project",
                description="Archive a project. Archived projects are hidden from default views but can be restored later.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "The ID of the project to archive"
                        }
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="get_project_tasks",
                description="Get tasks/tickets for a specific project. Returns task details including name, status, assignee, tags, and description.",
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
                name="search_tasks_by_tag",
                description="Search for tasks by tag name across all projects. Returns all tasks that have the specified tag.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tag_name": {
                            "type": "string",
                            "description": "The name of the tag to search for (case-insensitive)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of tasks to return (default: 50)",
                            "default": 50
                        }
                    },
                    "required": ["tag_name"]
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
                        },
                        "partner_id": {
                            "type": "integer",
                            "description": "Customer/partner contact ID (optional)"
                        },
                        "kanban_state": {
                            "type": "string",
                            "enum": ["normal", "blocked", "done"],
                            "description": "Kanban state: normal=Ready, blocked=Blocked, done=Done (optional, default: normal)"
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
                        },
                        "partner_id": {
                            "type": "integer",
                            "description": "New customer/partner contact ID (optional). Pass 0 or null to clear."
                        },
                        "kanban_state": {
                            "type": "string",
                            "enum": ["normal", "blocked", "done"],
                            "description": "New kanban state: normal=Ready, blocked=Blocked, done=Done (optional)"
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
                name="send_task_message",
                description="Send a message on a task. This can be used for task comments, discussions, or internal notes. Supports HTML formatting including bold, italic, lists, and links.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to send a message on"
                        },
                        "body": {
                            "type": "string",
                            "description": "The message content. Supports HTML formatting: <strong>bold</strong>, <em>italic</em>, <ul><li>lists</li></ul>, <a href='url'>links</a>, <br> for line breaks. Plain text with newlines will be automatically converted to HTML with <br> tags."
                        },
                        "message_type": {
                            "type": "string",
                            "enum": ["comment", "notification"],
                            "description": "Type of message: 'comment' for general communication, 'notification' for internal notes (default: comment)"
                        }
                    },
                    "required": ["task_id", "body"]
                }
            ),
            Tool(
                name="get_task_messages",
                description="Get all messages from a task. Returns the message thread with authors and content.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to get messages from"
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
            Tool(
                name="list_helpdesk_teams",
                description="List all helpdesk teams. Returns team names, IDs, and basic information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of teams to return (default: 50)",
                            "default": 50
                        }
                    }
                }
            ),
            Tool(
                name="list_tickets",
                description="List helpdesk tickets. Returns ticket details including subject, status, priority, and customer.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "team_id": {
                            "type": "integer",
                            "description": "Filter tickets by helpdesk team ID (optional)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of tickets to return (default: 50)",
                            "default": 50
                        }
                    }
                }
            ),
            Tool(
                name="get_ticket",
                description="Get a specific helpdesk ticket by ID. Returns full ticket details including description, messages, and customer information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "The ID of the ticket to retrieve"
                        }
                    },
                    "required": ["ticket_id"]
                }
            ),
            Tool(
                name="create_ticket",
                description="Create a new helpdesk ticket. Returns the created ticket ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The ticket subject/title"
                        },
                        "team_id": {
                            "type": "integer",
                            "description": "The helpdesk team ID to assign the ticket to"
                        },
                        "description": {
                            "type": "string",
                            "description": "The ticket description/content (optional)"
                        },
                        "partner_id": {
                            "type": "integer",
                            "description": "The customer/partner ID (optional)"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["0", "1", "2", "3"],
                            "description": "Ticket priority: 0=Low, 1=Normal, 2=High, 3=Urgent (optional, default: 1)"
                        },
                        "tag_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of tag IDs to assign to the ticket (optional)"
                        },
                        "ticket_type_id": {
                            "type": "integer",
                            "description": "Ticket type/category ID (optional)"
                        },
                        "kanban_state": {
                            "type": "string",
                            "enum": ["normal", "blocked", "done"],
                            "description": "Kanban state: normal=Ready, blocked=Blocked, done=Done (optional, default: normal)"
                        }
                    },
                    "required": ["name", "team_id"]
                }
            ),
            Tool(
                name="update_ticket",
                description="Update an existing helpdesk ticket. Can update subject, description, stage, priority, or assignment.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "The ID of the ticket to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New ticket subject/title (optional)"
                        },
                        "description": {
                            "type": "string",
                            "description": "New ticket description (optional)"
                        },
                        "stage_id": {
                            "type": "integer",
                            "description": "New stage ID (optional)"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["0", "1", "2", "3"],
                            "description": "New priority: 0=Low, 1=Normal, 2=High, 3=Urgent (optional)"
                        },
                        "user_id": {
                            "type": "integer",
                            "description": "New assigned user ID (optional)"
                        },
                        "partner_id": {
                            "type": "integer",
                            "description": "New customer/partner ID (optional). Pass 0 or null to clear."
                        },
                        "tag_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of tag IDs to assign to the ticket (optional). Pass empty array to clear all tags."
                        },
                        "ticket_type_id": {
                            "type": "integer",
                            "description": "New ticket type/category ID (optional). Pass 0 or null to clear."
                        },
                        "kanban_state": {
                            "type": "string",
                            "enum": ["normal", "blocked", "done"],
                            "description": "New kanban state: normal=Ready, blocked=Blocked, done=Done (optional)"
                        }
                    },
                    "required": ["ticket_id"]
                }
            ),
            Tool(
                name="close_ticket",
                description="Close a helpdesk ticket by moving it to the closed stage.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "The ID of the ticket to close"
                        }
                    },
                    "required": ["ticket_id"]
                }
            ),
            Tool(
                name="send_ticket_message",
                description="Send a message on a helpdesk ticket. This can be used to communicate with customers or add internal notes. Supports HTML formatting including bold, italic, lists, and links.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "The ID of the ticket to send a message on"
                        },
                        "body": {
                            "type": "string",
                            "description": "The message content. Supports HTML formatting: <strong>bold</strong>, <em>italic</em>, <ul><li>lists</li></ul>, <a href='url'>links</a>, <br> for line breaks. Plain text with newlines will be automatically converted to HTML with <br> tags."
                        },
                        "message_type": {
                            "type": "string",
                            "enum": ["comment", "notification"],
                            "description": "Type of message: 'comment' for customer communication, 'notification' for internal notes (default: comment)"
                        }
                    },
                    "required": ["ticket_id", "body"]
                }
            ),
            Tool(
                name="get_ticket_messages",
                description="Get all messages from a helpdesk ticket. Returns the message thread with authors and content.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "The ID of the ticket to get messages from"
                        }
                    },
                    "required": ["ticket_id"]
                }
            ),
            Tool(
                name="list_contacts",
                description="List contacts in Odoo. Returns contact names, IDs, emails, phones, and company information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of contacts to return (default: 50)",
                            "default": 50
                        },
                        "is_company": {
                            "type": "boolean",
                            "description": "Filter by contact type: true for companies, false for individuals (optional)"
                        }
                    }
                }
            ),
            Tool(
                name="get_contact",
                description="Get a specific contact by ID. Returns full contact details including address, email, phone, and related information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "contact_id": {
                            "type": "integer",
                            "description": "The ID of the contact to retrieve"
                        }
                    },
                    "required": ["contact_id"]
                }
            ),
            Tool(
                name="create_contact",
                description="Create a new contact. Returns the created contact ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The contact name (required)"
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address (optional)"
                        },
                        "phone": {
                            "type": "string",
                            "description": "Phone number (optional)"
                        },
                        "mobile": {
                            "type": "string",
                            "description": "Mobile number (optional)"
                        },
                        "is_company": {
                            "type": "boolean",
                            "description": "True if this is a company, false if individual (default: false)"
                        },
                        "parent_id": {
                            "type": "integer",
                            "description": "Parent company ID for individuals associated with a company (optional)"
                        },
                        "street": {
                            "type": "string",
                            "description": "Street address (optional)"
                        },
                        "street2": {
                            "type": "string",
                            "description": "Street address line 2 (optional)"
                        },
                        "city": {
                            "type": "string",
                            "description": "City (optional)"
                        },
                        "zip": {
                            "type": "string",
                            "description": "Zip/postal code (optional)"
                        },
                        "country_id": {
                            "type": "integer",
                            "description": "Country ID (optional)"
                        },
                        "state_id": {
                            "type": "integer",
                            "description": "State/Province ID (optional)"
                        },
                        "website": {
                            "type": "string",
                            "description": "Website URL (optional)"
                        },
                        "vat": {
                            "type": "string",
                            "description": "Tax ID/VAT number (optional)"
                        },
                        "title": {
                            "type": "integer",
                            "description": "Title ID (Mr/Ms/Dr, etc.) (optional)"
                        },
                        "function": {
                            "type": "string",
                            "description": "Job position/function (optional)"
                        },
                        "ref": {
                            "type": "string",
                            "description": "Internal reference (optional)"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tag names to assign to the contact (optional). Tags will be created if they don't exist."
                        },
                        "notes": {
                            "type": "string",
                            "description": "Internal notes about the contact (optional)"
                        },
                        "image_url": {
                            "type": "string",
                            "description": "URL of the image/logo to upload (optional). Will be downloaded and converted to base64."
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_contact",
                description="Update an existing contact. Can update any field including name, email, phone, address, etc.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "contact_id": {
                            "type": "integer",
                            "description": "The ID of the contact to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New contact name (optional)"
                        },
                        "email": {
                            "type": "string",
                            "description": "New email address (optional)"
                        },
                        "phone": {
                            "type": "string",
                            "description": "New phone number (optional)"
                        },
                        "mobile": {
                            "type": "string",
                            "description": "New mobile number (optional)"
                        },
                        "street": {
                            "type": "string",
                            "description": "New street address (optional)"
                        },
                        "street2": {
                            "type": "string",
                            "description": "New street address line 2 (optional)"
                        },
                        "city": {
                            "type": "string",
                            "description": "New city (optional)"
                        },
                        "zip": {
                            "type": "string",
                            "description": "New zip/postal code (optional)"
                        },
                        "state_id": {
                            "type": "integer",
                            "description": "New state/province ID (optional)"
                        },
                        "country_id": {
                            "type": "integer",
                            "description": "New country ID (optional)"
                        },
                        "website": {
                            "type": "string",
                            "description": "New website URL (optional)"
                        },
                        "vat": {
                            "type": "string",
                            "description": "New tax ID/VAT number (optional)"
                        },
                        "title": {
                            "type": "integer",
                            "description": "New title ID (Mr/Ms/Dr, etc.) (optional)"
                        },
                        "function": {
                            "type": "string",
                            "description": "New job position/function (optional)"
                        },
                        "ref": {
                            "type": "string",
                            "description": "New internal reference (optional)"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tag names to assign to the contact (optional). Tags will be created if they don't exist. Pass empty array to clear all tags."
                        },
                        "notes": {
                            "type": "string",
                            "description": "Internal notes about the contact (optional). Pass empty string to clear notes."
                        },
                        "image_url": {
                            "type": "string",
                            "description": "URL of the image/logo to upload (optional). Will be downloaded and converted to base64."
                        }
                    },
                    "required": ["contact_id"]
                }
            ),
            Tool(
                name="delete_contact",
                description="Delete a contact. This will permanently remove the contact.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "contact_id": {
                            "type": "integer",
                            "description": "The ID of the contact to delete"
                        }
                    },
                    "required": ["contact_id"]
                }
            ),
            Tool(
                name="archive_contact",
                description="Archive a contact. Archived contacts are hidden from default views but can be restored later.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "contact_id": {
                            "type": "integer",
                            "description": "The ID of the contact to archive"
                        }
                    },
                    "required": ["contact_id"]
                }
            ),
            Tool(
                name="search_contacts",
                description="Search contacts by name, email, or company. Returns matching contacts with basic information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - will search across name, email, and company fields"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of contacts to return (default: 50)",
                            "default": 50
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="search_contacts_by_tag",
                description="Search contacts by tag name. Returns all contacts that have the specified tag.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tag_name": {
                            "type": "string",
                            "description": "The name of the tag to search for"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of contacts to return (default: 50)",
                            "default": 50
                        }
                    },
                    "required": ["tag_name"]
                }
            ),
            Tool(
                name="list_mailing_lists",
                description="List all mailing lists. Returns list names, IDs, and subscriber counts.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of mailing lists to return (default: 50)",
                            "default": 50
                        }
                    }
                }
            ),
            Tool(
                name="get_mailing_list",
                description="Get a specific mailing list by ID with full details including all subscribers.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list to retrieve"
                        }
                    },
                    "required": ["list_id"]
                }
            ),
            Tool(
                name="create_mailing_list",
                description="Create a new mailing list. Returns the created list ID and details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The mailing list name (required)"
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_mailing_list",
                description="Update an existing mailing list name.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New mailing list name"
                        }
                    },
                    "required": ["list_id", "name"]
                }
            ),
            Tool(
                name="delete_mailing_list",
                description="Delete a mailing list. This will permanently remove the list and all its subscriptions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list to delete"
                        }
                    },
                    "required": ["list_id"]
                }
            ),
            Tool(
                name="subscribe_contact",
                description="Subscribe a contact to a mailing list. Creates a mailing contact if one doesn't exist.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list"
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address of the contact to subscribe"
                        },
                        "name": {
                            "type": "string",
                            "description": "Name of the contact (optional, will be inferred from email if not provided)"
                        }
                    },
                    "required": ["list_id", "email"]
                }
            ),
            Tool(
                name="unsubscribe_contact",
                description="Unsubscribe a contact from a mailing list.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list"
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address of the contact to unsubscribe"
                        }
                    },
                    "required": ["list_id", "email"]
                }
            ),
            Tool(
                name="get_contact_subscriptions",
                description="Get all mailing lists a contact is subscribed to by email address.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Email address of the contact"
                        }
                    },
                    "required": ["email"]
                }
            ),
            Tool(
                name="opt_in_contact",
                description="Opt a contact back into a mailing list (reverses opt-out).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list"
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address of the contact to opt back in"
                        }
                    },
                    "required": ["list_id", "email"]
                }
            ),
            Tool(
                name="opt_out_contact",
                description="Opt a contact out of a mailing list (manual opt-out).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_id": {
                            "type": "integer",
                            "description": "The ID of the mailing list"
                        },
                        "email": {
                            "type": "string",
                            "description": "Email address of the contact to opt out"
                        }
                    },
                    "required": ["list_id", "email"]
                }
            ),
            Tool(
                name="list_users",
                description="List Odoo users. Returns user names, IDs, emails, and login information. Useful for assigning tasks and tickets.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of users to return (default: 50)",
                            "default": 50
                        }
                    }
                }
            ),

            # Activities tools
            Tool(
                name="list_activities",
                description="List activities (to-dos). Returns all activities with optional filtering by user, state, or type.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of activities to return (default: 50)",
                            "default": 50
                        },
                        "user_id": {
                            "type": "integer",
                            "description": "Filter by assigned user ID (optional)"
                        },
                        "state": {
                            "type": "string",
                            "description": "Filter by state: overdue, today, planned, done (optional)"
                        },
                        "activity_type": {
                            "type": "string",
                            "description": "Filter by activity type name, e.g. 'To-do', 'Call', 'Email', 'Meeting' (optional)"
                        }
                    }
                }
            ),
            Tool(
                name="get_activity",
                description="Get a specific activity by ID with full details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "activity_id": {
                            "type": "integer",
                            "description": "The ID of the activity to retrieve"
                        }
                    },
                    "required": ["activity_id"]
                }
            ),
            Tool(
                name="create_activity",
                description="Create a new activity/to-do. Can be linked to any record or created as a standalone to-do.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "The activity summary/title"
                        },
                        "note": {
                            "type": "string",
                            "description": "Detailed description (optional)"
                        },
                        "date_deadline": {
                            "type": "string",
                            "description": "Deadline in YYYY-MM-DD format (optional)"
                        },
                        "user_id": {
                            "type": "integer",
                            "description": "ID of user to assign to (optional, defaults to current user)"
                        },
                        "activity_type": {
                            "type": "string",
                            "description": "Type of activity: 'To-do', 'Call', 'Email', 'Meeting', etc. (optional, defaults to 'To-do')",
                            "default": "To-do"
                        },
                        "res_model": {
                            "type": "string",
                            "description": "Model to link to, e.g. 'res.users', 'project.task', 'res.partner' (optional, defaults to 'res.users')",
                            "default": "res.users"
                        },
                        "res_id": {
                            "type": "integer",
                            "description": "ID of record to link to (optional, defaults to assigned user ID)"
                        }
                    },
                    "required": ["summary"]
                }
            ),
            Tool(
                name="update_activity",
                description="Update an existing activity. Can modify summary, description, deadline, assignee, or type.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "activity_id": {
                            "type": "integer",
                            "description": "The ID of the activity to update"
                        },
                        "summary": {
                            "type": "string",
                            "description": "New activity summary/title (optional)"
                        },
                        "note": {
                            "type": "string",
                            "description": "New description (optional)"
                        },
                        "date_deadline": {
                            "type": "string",
                            "description": "New deadline in YYYY-MM-DD format (optional)"
                        },
                        "user_id": {
                            "type": "integer",
                            "description": "New assigned user ID (optional)"
                        },
                        "activity_type": {
                            "type": "string",
                            "description": "New activity type name (optional)"
                        }
                    },
                    "required": ["activity_id"]
                }
            ),
            Tool(
                name="mark_activity_done",
                description="Mark an activity as done/completed.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "activity_id": {
                            "type": "integer",
                            "description": "The ID of the activity to mark as done"
                        },
                        "feedback": {
                            "type": "string",
                            "description": "Optional feedback/note when completing the activity"
                        }
                    },
                    "required": ["activity_id"]
                }
            ),
            Tool(
                name="delete_activity",
                description="Delete an activity permanently.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "activity_id": {
                            "type": "integer",
                            "description": "The ID of the activity to delete"
                        }
                    },
                    "required": ["activity_id"]
                }
            ),
            Tool(
                name="list_activity_types",
                description="List all available activity types (To-do, Call, Email, Meeting, etc.).",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),

            # To-Do app tools
            Tool(
                name="list_todos",
                description="List to-dos from the To-Do app (personal tasks without a project). Returns to-dos with optional filtering by stage or user.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of to-dos to return (default: 50)",
                            "default": 50
                        },
                        "stage": {
                            "type": "string",
                            "description": "Filter by stage name, e.g. 'Today', 'This Week', 'Inbox', 'Later' (optional)"
                        },
                        "user_id": {
                            "type": "integer",
                            "description": "Filter by user ID (optional, defaults to current user)"
                        }
                    }
                }
            ),
            Tool(
                name="get_todo",
                description="Get a specific to-do by ID with full details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "todo_id": {
                            "type": "integer",
                            "description": "The ID of the to-do to retrieve"
                        }
                    },
                    "required": ["todo_id"]
                }
            ),
            Tool(
                name="create_todo",
                description="Create a new to-do in the To-Do app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The to-do name/title"
                        },
                        "description": {
                            "type": "string",
                            "description": "The to-do description (optional)"
                        },
                        "date_deadline": {
                            "type": "string",
                            "description": "Deadline in YYYY-MM-DD format (optional)"
                        },
                        "stage": {
                            "type": "string",
                            "description": "Stage name, e.g. 'Today', 'This Week', 'Inbox' (optional, defaults to 'Today')",
                            "default": "Today"
                        },
                        "priority": {
                            "type": "string",
                            "description": "Priority: '0' for Normal, '1' for High (optional, default: '0')",
                            "default": "0"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tag names (optional)"
                        }
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_todo",
                description="Update an existing to-do.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "todo_id": {
                            "type": "integer",
                            "description": "The ID of the to-do to update"
                        },
                        "name": {
                            "type": "string",
                            "description": "New to-do name/title (optional)"
                        },
                        "description": {
                            "type": "string",
                            "description": "New description (optional)"
                        },
                        "date_deadline": {
                            "type": "string",
                            "description": "New deadline in YYYY-MM-DD format (optional)"
                        },
                        "stage": {
                            "type": "string",
                            "description": "New stage name, e.g. 'Today', 'This Week' (optional)"
                        },
                        "priority": {
                            "type": "string",
                            "description": "New priority: '0' or '1' (optional)"
                        }
                    },
                    "required": ["todo_id"]
                }
            ),
            Tool(
                name="mark_todo_done",
                description="Mark a to-do as done by moving it to the 'Done' stage.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "todo_id": {
                            "type": "integer",
                            "description": "The ID of the to-do to mark as done"
                        }
                    },
                    "required": ["todo_id"]
                }
            ),
            Tool(
                name="delete_todo",
                description="Delete a to-do permanently.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "todo_id": {
                            "type": "integer",
                            "description": "The ID of the to-do to delete"
                        }
                    },
                    "required": ["todo_id"]
                }
            ),
            Tool(
                name="list_todo_stages",
                description="List all available to-do stages (Inbox, Today, This Week, This Month, Later, Done, etc.).",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),

            # Spreadsheets (Documents app)
            Tool(
                name="list_spreadsheets",
                description="List spreadsheets in the Odoo Documents app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max spreadsheets to return (default: 50)", "default": 50},
                        "name": {"type": "string", "description": "Optional case-insensitive name filter"}
                    }
                }
            ),
            Tool(
                name="get_spreadsheet",
                description="Get a spreadsheet's metadata and a summary of its content (sheets, cell/figure counts). Set include_data to also return the raw o-spreadsheet JSON.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "integer", "description": "The ID of the spreadsheet (documents.document)"},
                        "include_data": {"type": "boolean", "description": "Include the raw spreadsheet_data JSON (default: false)", "default": False}
                    },
                    "required": ["spreadsheet_id"]
                }
            ),
            Tool(
                name="create_spreadsheet",
                description="Create a new spreadsheet in the Documents app. Creates an empty spreadsheet unless data_json (o-spreadsheet JSON) is provided. Requires a Documents folder/workspace.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The spreadsheet name (required)"},
                        "folder": {"type": "string", "description": "Documents folder/workspace name or numeric ID to create it in. If omitted, a default folder is auto-detected."},
                        "data_json": {"type": "string", "description": "Optional o-spreadsheet JSON content (string). If omitted, an empty spreadsheet is created."}
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_spreadsheet",
                description="Update a spreadsheet's name and/or o-spreadsheet content (data_json).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "integer", "description": "The ID of the spreadsheet to update"},
                        "name": {"type": "string", "description": "New name (optional)"},
                        "data_json": {"type": "string", "description": "New o-spreadsheet JSON content, as a string (optional)"}
                    },
                    "required": ["spreadsheet_id"]
                }
            ),
            Tool(
                name="delete_spreadsheet",
                description="Delete a spreadsheet from the Documents app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "integer", "description": "The ID of the spreadsheet to delete"}
                    },
                    "required": ["spreadsheet_id"]
                }
            ),

            # Dashboards (Dashboards app)
            Tool(
                name="list_dashboard_groups",
                description="List dashboard groups (sections) in the Odoo Dashboards app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max groups to return (default: 50)", "default": 50}
                    }
                }
            ),
            Tool(
                name="create_dashboard_group",
                description="Create a new dashboard group (section) in the Dashboards app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The dashboard group name (required)"}
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="list_dashboards",
                description="List dashboards in the Dashboards app, optionally filtered by group name or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max dashboards to return (default: 50)", "default": 50},
                        "group": {"type": "string", "description": "Optional dashboard group name or numeric ID to filter by"}
                    }
                }
            ),
            Tool(
                name="get_dashboard",
                description="Get a dashboard's metadata and a summary of its content. Set include_data to also return the raw o-spreadsheet JSON.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dashboard_id": {"type": "integer", "description": "The ID of the dashboard (spreadsheet.dashboard)"},
                        "include_data": {"type": "boolean", "description": "Include the raw spreadsheet_data JSON (default: false)", "default": False}
                    },
                    "required": ["dashboard_id"]
                }
            ),
            Tool(
                name="create_dashboard",
                description="Create a new dashboard from raw o-spreadsheet JSON (or empty). To build an inventory dashboard from live stock data, use create_inventory_dashboard instead.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The dashboard name (required)"},
                        "group": {"type": "string", "description": "Dashboard group name or numeric ID. Created if it doesn't exist; a default group is used if omitted."},
                        "data_json": {"type": "string", "description": "Optional o-spreadsheet JSON content (string). If omitted, an empty dashboard is created."}
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="update_dashboard",
                description="Update a dashboard's name, group, and/or o-spreadsheet content (data_json).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dashboard_id": {"type": "integer", "description": "The ID of the dashboard to update"},
                        "name": {"type": "string", "description": "New name (optional)"},
                        "group": {"type": "string", "description": "New dashboard group name or numeric ID (optional)"},
                        "data_json": {"type": "string", "description": "New o-spreadsheet JSON content, as a string (optional)"}
                    },
                    "required": ["dashboard_id"]
                }
            ),
            Tool(
                name="delete_dashboard",
                description="Delete a dashboard from the Dashboards app.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dashboard_id": {"type": "integer", "description": "The ID of the dashboard to delete"}
                    },
                    "required": ["dashboard_id"]
                }
            ),
            Tool(
                name="create_inventory_dashboard",
                description=(
                    "Build a custom inventory dashboard from live stock data. Queries on-hand stock "
                    "(stock.quant, internal locations), aggregates by product/location/warehouse/category, "
                    "and writes a data table plus a chart into a new dashboard (or Documents spreadsheet). "
                    "The data is a point-in-time snapshot written as plain values (robust across Odoo versions); "
                    "re-run to refresh. Requires the Inventory app, plus the Dashboards or Documents app depending on target."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Dashboard/spreadsheet name (default: 'Inventory Dashboard')"},
                        "group_by": {"type": "string", "enum": ["product", "location", "warehouse", "category"], "description": "How to group the inventory (default: product)"},
                        "measure": {"type": "string", "enum": ["quantity", "value"], "description": "'quantity' for on-hand units, 'value' for on-hand value (default: quantity)"},
                        "limit": {"type": "integer", "description": "Number of top groups to show in the table/chart (default: 30)", "default": 30},
                        "include_chart": {"type": "boolean", "description": "Include a chart figure (default: true)", "default": True},
                        "chart_type": {"type": "string", "enum": ["bar", "line", "pie"], "description": "Chart type (default: bar)"},
                        "target": {"type": "string", "enum": ["dashboard", "spreadsheet"], "description": "Create a Dashboards-app dashboard or a Documents spreadsheet (default: dashboard)"},
                        "group": {"type": "string", "description": "Dashboard group name or ID (when target=dashboard). Created if missing."},
                        "folder": {"type": "string", "description": "Documents folder name or ID (when target=spreadsheet)."},
                        "product": {"type": "string", "description": "Optional product name filter (case-insensitive)"},
                        "location": {"type": "string", "description": "Optional location name filter (case-insensitive)"},
                        "scan_limit": {"type": "integer", "description": "Max stock records to scan when aggregating (default: 5000)", "default": 5000}
                    }
                }
            ),
        ]

    async def call_tool(self, name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if not self.projects.odoo:
                self.connect_odoo()

            # Projects tools
            if name == "list_projects":
                return await self.projects.list_projects(arguments)
            elif name == "get_project":
                return await self.projects.get_project(arguments)
            elif name == "create_project":
                return await self.projects.create_project(arguments)
            elif name == "update_project":
                return await self.projects.update_project(arguments)
            elif name == "archive_project":
                return await self.projects.archive_project(arguments)
            elif name == "get_project_tasks":
                return await self.projects.get_project_tasks(arguments)
            elif name == "search_tasks_by_tag":
                return await self.projects.search_tasks_by_tag(arguments)
            elif name == "create_task":
                return await self.projects.create_task(arguments)
            elif name == "update_task":
                return await self.projects.update_task(arguments)
            elif name == "delete_task":
                return await self.projects.delete_task(arguments)
            elif name == "archive_task":
                return await self.projects.archive_task(arguments)
            elif name == "send_task_message":
                return await self.projects.send_task_message(arguments)
            elif name == "get_task_messages":
                return await self.projects.get_task_messages(arguments)

            # Knowledge tools
            elif name == "list_articles":
                return await self.knowledge.list_articles(arguments)
            elif name == "get_article":
                return await self.knowledge.get_article(arguments)
            elif name == "create_article":
                return await self.knowledge.create_article(arguments)
            elif name == "update_article":
                return await self.knowledge.update_article(arguments)
            elif name == "delete_article":
                return await self.knowledge.delete_article(arguments)
            elif name == "archive_article":
                return await self.knowledge.archive_article(arguments)

            # Helpdesk tools
            elif name == "list_helpdesk_teams":
                return await self.helpdesk.list_helpdesk_teams(arguments)
            elif name == "list_tickets":
                return await self.helpdesk.list_tickets(arguments)
            elif name == "get_ticket":
                return await self.helpdesk.get_ticket(arguments)
            elif name == "create_ticket":
                return await self.helpdesk.create_ticket(arguments)
            elif name == "update_ticket":
                return await self.helpdesk.update_ticket(arguments)
            elif name == "close_ticket":
                return await self.helpdesk.close_ticket(arguments)
            elif name == "send_ticket_message":
                return await self.helpdesk.send_ticket_message(arguments)
            elif name == "get_ticket_messages":
                return await self.helpdesk.get_ticket_messages(arguments)

            # Contacts tools
            elif name == "list_contacts":
                return await self.contacts.list_contacts(arguments)
            elif name == "get_contact":
                return await self.contacts.get_contact(arguments)
            elif name == "create_contact":
                return await self.contacts.create_contact(arguments)
            elif name == "update_contact":
                return await self.contacts.update_contact(arguments)
            elif name == "delete_contact":
                return await self.contacts.delete_contact(arguments)
            elif name == "archive_contact":
                return await self.contacts.archive_contact(arguments)
            elif name == "search_contacts":
                return await self.contacts.search_contacts(arguments)
            elif name == "search_contacts_by_tag":
                return await self.contacts.search_contacts_by_tag(arguments)

            # Mailing tools
            elif name == "list_mailing_lists":
                return await self.mailing.list_mailing_lists(arguments)
            elif name == "get_mailing_list":
                return await self.mailing.get_mailing_list(arguments)
            elif name == "create_mailing_list":
                return await self.mailing.create_mailing_list(arguments)
            elif name == "update_mailing_list":
                return await self.mailing.update_mailing_list(arguments)
            elif name == "delete_mailing_list":
                return await self.mailing.delete_mailing_list(arguments)
            elif name == "subscribe_contact":
                return await self.mailing.subscribe_contact(arguments)
            elif name == "unsubscribe_contact":
                return await self.mailing.unsubscribe_contact(arguments)
            elif name == "get_contact_subscriptions":
                return await self.mailing.get_contact_subscriptions(arguments)
            elif name == "opt_in_contact":
                return await self.mailing.opt_in_contact(arguments)
            elif name == "opt_out_contact":
                return await self.mailing.opt_out_contact(arguments)

            # Users tools
            elif name == "list_users":
                return await self.users.list_users(arguments)

            # Activities tools
            elif name == "list_activities":
                return await self.activities.list_activities(arguments)
            elif name == "get_activity":
                return await self.activities.get_activity(arguments)
            elif name == "create_activity":
                return await self.activities.create_activity(arguments)
            elif name == "update_activity":
                return await self.activities.update_activity(arguments)
            elif name == "mark_activity_done":
                return await self.activities.mark_activity_done(arguments)
            elif name == "delete_activity":
                return await self.activities.delete_activity(arguments)
            elif name == "list_activity_types":
                return await self.activities.list_activity_types(arguments)

            # To-Do app tools
            elif name == "list_todos":
                return await self.todos.list_todos(arguments)
            elif name == "get_todo":
                return await self.todos.get_todo(arguments)
            elif name == "create_todo":
                return await self.todos.create_todo(arguments)
            elif name == "update_todo":
                return await self.todos.update_todo(arguments)
            elif name == "mark_todo_done":
                return await self.todos.mark_todo_done(arguments)
            elif name == "delete_todo":
                return await self.todos.delete_todo(arguments)
            elif name == "list_todo_stages":
                return await self.todos.list_todo_stages(arguments)

            # Spreadsheets tools
            elif name == "list_spreadsheets":
                return await self.spreadsheets.list_spreadsheets(arguments)
            elif name == "get_spreadsheet":
                return await self.spreadsheets.get_spreadsheet(arguments)
            elif name == "create_spreadsheet":
                return await self.spreadsheets.create_spreadsheet(arguments)
            elif name == "update_spreadsheet":
                return await self.spreadsheets.update_spreadsheet(arguments)
            elif name == "delete_spreadsheet":
                return await self.spreadsheets.delete_spreadsheet(arguments)

            # Dashboards tools
            elif name == "list_dashboard_groups":
                return await self.dashboards.list_dashboard_groups(arguments)
            elif name == "create_dashboard_group":
                return await self.dashboards.create_dashboard_group(arguments)
            elif name == "list_dashboards":
                return await self.dashboards.list_dashboards(arguments)
            elif name == "get_dashboard":
                return await self.dashboards.get_dashboard(arguments)
            elif name == "create_dashboard":
                return await self.dashboards.create_dashboard(arguments)
            elif name == "update_dashboard":
                return await self.dashboards.update_dashboard(arguments)
            elif name == "delete_dashboard":
                return await self.dashboards.delete_dashboard(arguments)
            elif name == "create_inventory_dashboard":
                return await self.dashboards.create_inventory_dashboard(arguments)

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def run(self):
        """Run the MCP server."""
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            logger.info("Odoo MCP server starting...")
            try:
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
            finally:
                self.cleanup()


async def main():
    """Main entry point."""
    server = OdooMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
