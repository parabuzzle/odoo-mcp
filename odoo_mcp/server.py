#!/usr/bin/env python3
"""Odoo MCP Server - Provides MCP interface to Odoo cloud apps."""

import os
import logging
from typing import Any
import asyncio
import base64
import requests

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

    def cleanup(self):
        """Cleanup resources on shutdown."""
        if self.odoo:
            try:
                logger.info("Closing Odoo connection...")
                # OdooRPC doesn't have an explicit close method, just clear the reference
                self.odoo = None
                logger.info("Odoo connection closed")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

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
        ]

    async def call_tool(self, name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if not self.odoo:
                self.connect_odoo()

            if name == "list_projects":
                return await self.list_projects(arguments)
            elif name == "get_project":
                return await self.get_project(arguments)
            elif name == "create_project":
                return await self.create_project(arguments)
            elif name == "update_project":
                return await self.update_project(arguments)
            elif name == "archive_project":
                return await self.archive_project(arguments)
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
            elif name == "send_task_message":
                return await self.send_task_message(arguments)
            elif name == "get_task_messages":
                return await self.get_task_messages(arguments)
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
            elif name == "list_helpdesk_teams":
                return await self.list_helpdesk_teams(arguments)
            elif name == "list_tickets":
                return await self.list_tickets(arguments)
            elif name == "get_ticket":
                return await self.get_ticket(arguments)
            elif name == "create_ticket":
                return await self.create_ticket(arguments)
            elif name == "update_ticket":
                return await self.update_ticket(arguments)
            elif name == "close_ticket":
                return await self.close_ticket(arguments)
            elif name == "send_ticket_message":
                return await self.send_ticket_message(arguments)
            elif name == "get_ticket_messages":
                return await self.get_ticket_messages(arguments)
            elif name == "list_contacts":
                return await self.list_contacts(arguments)
            elif name == "get_contact":
                return await self.get_contact(arguments)
            elif name == "create_contact":
                return await self.create_contact(arguments)
            elif name == "update_contact":
                return await self.update_contact(arguments)
            elif name == "delete_contact":
                return await self.delete_contact(arguments)
            elif name == "archive_contact":
                return await self.archive_contact(arguments)
            elif name == "search_contacts":
                return await self.search_contacts(arguments)
            elif name == "list_mailing_lists":
                return await self.list_mailing_lists(arguments)
            elif name == "get_mailing_list":
                return await self.get_mailing_list(arguments)
            elif name == "create_mailing_list":
                return await self.create_mailing_list(arguments)
            elif name == "update_mailing_list":
                return await self.update_mailing_list(arguments)
            elif name == "delete_mailing_list":
                return await self.delete_mailing_list(arguments)
            elif name == "subscribe_contact":
                return await self.subscribe_contact(arguments)
            elif name == "unsubscribe_contact":
                return await self.unsubscribe_contact(arguments)
            elif name == "get_contact_subscriptions":
                return await self.get_contact_subscriptions(arguments)
            elif name == "opt_in_contact":
                return await self.opt_in_contact(arguments)
            elif name == "opt_out_contact":
                return await self.opt_out_contact(arguments)
            elif name == "list_users":
                return await self.list_users(arguments)
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

    async def get_project(self, arguments: dict) -> list[TextContent]:
        """Get a specific project by ID."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Access project.project model
        Project = self.odoo.env["project.project"]

        # Read project details
        project = Project.read(
            project_id,
            ["name", "id", "user_id", "partner_id", "task_count", "active", "description"]
        )[0]

        user_id = project.get("user_id")
        manager = user_id[1] if user_id else "Unassigned"
        partner_id = project.get("partner_id")
        partner = partner_id[1] if partner_id else "No customer"
        task_count = project.get("task_count", 0)
        active = "Active" if project.get("active", True) else "Archived"
        description = project.get("description") or "No description"

        output = (
            f"# {project['name']}\n\n"
            f"**ID:** {project['id']}  \n"
            f"**Status:** {active}  \n"
            f"**Manager:** {manager}  \n"
            f"**Customer:** {partner}  \n"
            f"**Task Count:** {task_count}  \n\n"
            f"## Description\n\n{description}"
        )

        return [TextContent(type="text", text=output)]

    async def create_project(self, arguments: dict) -> list[TextContent]:
        """Create a new project."""
        name = arguments.get("name")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        # Build project values
        project_values = {"name": name}

        if "description" in arguments and arguments["description"]:
            project_values["description"] = arguments["description"]

        # Create the project
        Project = self.odoo.env["project.project"]
        new_project_id = Project.create(project_values)

        # Read the created project to return details
        project = Project.read(new_project_id, ["name", "id"])[0]

        output = (
            f"# Project Created Successfully\n\n"
            f"**{project['name']}** (ID: {project['id']})"
        )

        return [TextContent(type="text", text=output)]

    async def update_project(self, arguments: dict) -> list[TextContent]:
        """Update an existing project."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "description" in arguments:
            update_values["description"] = arguments["description"]

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the project
        Project = self.odoo.env["project.project"]
        Project.write(project_id, update_values)

        # Read the updated project to return details
        project = Project.read(project_id, ["name", "id"])[0]

        output = (
            f"# Project Updated Successfully\n\n"
            f"**{project['name']}** (ID: {project['id']})"
        )

        return [TextContent(type="text", text=output)]

    async def archive_project(self, arguments: dict) -> list[TextContent]:
        """Archive a project."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Get project details before archiving
        Project = self.odoo.env["project.project"]
        project = Project.read(project_id, ["name", "id"])[0]
        project_name = project["name"]

        # Archive the project
        Project.write(project_id, {"active": False})

        output = (
            f"# Project Archived Successfully\n\n"
            f"Project **{project_name}** (ID: {project_id}) has been archived."
        )

        return [TextContent(type="text", text=output)]

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

    async def send_task_message(self, arguments: dict) -> list[TextContent]:
        """Send a message on a task."""
        task_id = arguments.get("task_id")
        body = arguments.get("body")

        if not task_id or not body:
            return [TextContent(type="text", text="Error: task_id and body are required")]

        message_type = arguments.get("message_type", "comment")

        # Get the task
        Task = self.odoo.env["project.task"]
        task_record = Task.browse(task_id)
        task_data = Task.read(task_id, ["name"])[0]

        # Handle both HTML and plain text:
        # - If body contains HTML tags, use it as-is
        # - If plain text, wrap in <p> tags and convert newlines to <br>
        if '<' not in body or '>' not in body:
            # Plain text - wrap in paragraph and convert newlines
            body = '<p>' + body.replace('\n', '<br>') + '</p>'
        # else: body already contains HTML, use as-is

        # Use message_post() with body_is_html=True to preserve HTML formatting
        # subtype_xmlid: 'mail.mt_comment' for public comments
        #                'mail.mt_note' for internal notes
        subtype_xmlid = 'mail.mt_comment' if message_type == "comment" else 'mail.mt_note'

        task_record.message_post(
            body=body,
            body_is_html=True,
            message_type=message_type,
            subtype_xmlid=subtype_xmlid
        )

        output = (
            f"# Message Sent Successfully\n\n"
            f"Message posted on task **{task_data['name']}** (ID: {task_id})\n"
            f"- Type: {message_type}\n"
        )

        return [TextContent(type="text", text=output)]

    async def get_task_messages(self, arguments: dict) -> list[TextContent]:
        """Get all messages from a task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Get the task to find its message_ids
        Task = self.odoo.env["project.task"]
        task = Task.read(task_id, ["name", "message_ids"])[0]
        task_name = task["name"]
        message_ids = task.get("message_ids", [])

        if not message_ids:
            return [TextContent(type="text", text=f"# Messages for {task_name}\n\nNo messages found.")]

        # Read the messages
        Message = self.odoo.env["mail.message"]
        messages = Message.read(
            message_ids,
            ["id", "author_id", "body", "date", "message_type", "subtype_id"]
        )

        # Sort messages by date (oldest first)
        messages.sort(key=lambda m: m.get("date", ""))

        # Format output
        output_lines = [f"# Messages for {task_name}\n"]
        for msg in messages:
            author_id = msg.get("author_id")
            author = author_id[1] if author_id else "System"

            date = msg.get("date", "Unknown")
            message_type = msg.get("message_type", "notification")
            subtype_id = msg.get("subtype_id")
            subtype = subtype_id[1] if subtype_id else "Note"

            body = msg.get("body") or "No content"

            output_lines.append(
                f"## Message {msg['id']}\n"
                f"- **Author:** {author}\n"
                f"- **Date:** {date}\n"
                f"- **Type:** {message_type} ({subtype})\n\n"
                f"**Content:**\n{body}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

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

    async def list_helpdesk_teams(self, arguments: dict) -> list[TextContent]:
        """List helpdesk teams."""
        limit = arguments.get("limit", 50)

        # Access helpdesk.team model
        Team = self.odoo.env["helpdesk.team"]

        # Search for teams
        team_ids = Team.search([], limit=limit)

        if not team_ids:
            return [TextContent(type="text", text="No helpdesk teams found.")]

        # Read team details
        teams = Team.read(
            team_ids,
            ["name", "id", "use_sla", "use_rating", "ticket_count"]
        )

        # Format output
        output_lines = ["# Helpdesk Teams\n"]
        for team in teams:
            name = team.get("name", "Unknown")
            team_id = team["id"]
            use_sla = "Yes" if team.get("use_sla") else "No"
            use_rating = "Yes" if team.get("use_rating") else "No"
            ticket_count = team.get("ticket_count", 0)

            output_lines.append(
                f"## {name} (ID: {team_id})\n"
                f"- Tickets: {ticket_count}\n"
                f"- Uses SLA: {use_sla}\n"
                f"- Uses Rating: {use_rating}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def list_tickets(self, arguments: dict) -> list[TextContent]:
        """List helpdesk tickets."""
        limit = arguments.get("limit", 50)
        team_id = arguments.get("team_id")

        # Access helpdesk.ticket model
        Ticket = self.odoo.env["helpdesk.ticket"]

        # Build search domain
        domain = []
        if team_id is not None:
            domain.append(("team_id", "=", team_id))

        # Search for tickets
        ticket_ids = Ticket.search(domain, limit=limit)

        if not ticket_ids:
            return [TextContent(type="text", text="No tickets found.")]

        # Read ticket details
        tickets = Ticket.read(
            ticket_ids,
            ["name", "id", "partner_id", "user_id", "stage_id", "priority", "create_date"]
        )

        # Format output
        output_lines = ["# Helpdesk Tickets\n"]
        for ticket in tickets:
            partner_id = ticket.get("partner_id")
            customer = partner_id[1] if partner_id else "No customer"

            user_id = ticket.get("user_id")
            assigned = user_id[1] if user_id else "Unassigned"

            stage_id = ticket.get("stage_id")
            stage = stage_id[1] if stage_id else "No stage"

            priority = ticket.get("priority", "1")
            priority_map = {"0": "Low", "1": "Normal", "2": "High", "3": "Urgent"}
            priority_str = priority_map.get(priority, "Normal")

            create_date = ticket.get("create_date", "Unknown")

            output_lines.append(
                f"## {ticket['name']} (ID: {ticket['id']})\n"
                f"- Customer: {customer}\n"
                f"- Stage: {stage}\n"
                f"- Priority: {priority_str}\n"
                f"- Assigned to: {assigned}\n"
                f"- Created: {create_date}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_ticket(self, arguments: dict) -> list[TextContent]:
        """Get a specific ticket with full details."""
        ticket_id = arguments.get("ticket_id")

        if not ticket_id:
            return [TextContent(type="text", text="Error: ticket_id is required")]

        # Access helpdesk.ticket model
        Ticket = self.odoo.env["helpdesk.ticket"]

        # Read ticket with full details
        ticket = Ticket.read(
            ticket_id,
            ["name", "id", "description", "partner_id", "user_id", "stage_id",
             "priority", "create_date", "team_id"]
        )[0]

        partner_id = ticket.get("partner_id")
        customer = partner_id[1] if partner_id else "No customer"

        user_id = ticket.get("user_id")
        assigned = user_id[1] if user_id else "Unassigned"

        stage_id = ticket.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        team_id = ticket.get("team_id")
        team = team_id[1] if team_id else "No team"

        priority = ticket.get("priority", "1")
        priority_map = {"0": "Low", "1": "Normal", "2": "High", "3": "Urgent"}
        priority_str = priority_map.get(priority, "Normal")

        create_date = ticket.get("create_date", "Unknown")
        description = ticket.get("description") or "No description"

        output = (
            f"# {ticket['name']}\n\n"
            f"**ID:** {ticket['id']}  \n"
            f"**Customer:** {customer}  \n"
            f"**Team:** {team}  \n"
            f"**Stage:** {stage}  \n"
            f"**Priority:** {priority_str}  \n"
            f"**Assigned to:** {assigned}  \n"
            f"**Created:** {create_date}\n\n"
            f"## Description\n\n{description}"
        )

        return [TextContent(type="text", text=output)]

    async def create_ticket(self, arguments: dict) -> list[TextContent]:
        """Create a new helpdesk ticket."""
        name = arguments.get("name")
        team_id = arguments.get("team_id")

        if not name or not team_id:
            return [TextContent(type="text", text="Error: name and team_id are required")]

        # Build ticket values
        ticket_values = {
            "name": name,
            "team_id": team_id,
        }

        # Add optional fields
        if "description" in arguments and arguments["description"]:
            ticket_values["description"] = arguments["description"]

        if "partner_id" in arguments and arguments["partner_id"]:
            ticket_values["partner_id"] = arguments["partner_id"]

        if "priority" in arguments:
            ticket_values["priority"] = arguments["priority"]

        # Create the ticket
        Ticket = self.odoo.env["helpdesk.ticket"]
        new_ticket_id = Ticket.create(ticket_values)

        # Read the created ticket to return details
        ticket = Ticket.read(new_ticket_id, ["name", "id", "team_id", "stage_id"])[0]

        team_id_field = ticket.get("team_id")
        team = team_id_field[1] if team_id_field else "Unknown"

        stage_id = ticket.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        output = (
            f"# Ticket Created Successfully\n\n"
            f"**{ticket['name']}** (ID: {ticket['id']})\n"
            f"- Team: {team}\n"
            f"- Stage: {stage}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_ticket(self, arguments: dict) -> list[TextContent]:
        """Update an existing helpdesk ticket."""
        ticket_id = arguments.get("ticket_id")

        if not ticket_id:
            return [TextContent(type="text", text="Error: ticket_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "description" in arguments:
            update_values["description"] = arguments["description"]

        if "stage_id" in arguments:
            update_values["stage_id"] = arguments["stage_id"]

        if "priority" in arguments:
            update_values["priority"] = arguments["priority"]

        if "user_id" in arguments:
            update_values["user_id"] = arguments["user_id"]

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the ticket
        Ticket = self.odoo.env["helpdesk.ticket"]
        Ticket.write(ticket_id, update_values)

        # Read the updated ticket to return details
        ticket = Ticket.read(ticket_id, ["name", "id", "stage_id", "priority", "user_id"])[0]

        stage_id = ticket.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        priority = ticket.get("priority", "1")
        priority_map = {"0": "Low", "1": "Normal", "2": "High", "3": "Urgent"}
        priority_str = priority_map.get(priority, "Normal")

        user_id = ticket.get("user_id")
        assigned = user_id[1] if user_id else "Unassigned"

        output = (
            f"# Ticket Updated Successfully\n\n"
            f"**{ticket['name']}** (ID: {ticket['id']})\n"
            f"- Stage: {stage}\n"
            f"- Priority: {priority_str}\n"
            f"- Assigned to: {assigned}\n"
        )

        return [TextContent(type="text", text=output)]

    async def close_ticket(self, arguments: dict) -> list[TextContent]:
        """Close a helpdesk ticket."""
        ticket_id = arguments.get("ticket_id")

        if not ticket_id:
            return [TextContent(type="text", text="Error: ticket_id is required")]

        # Get the ticket's team to find the closed stage
        Ticket = self.odoo.env["helpdesk.ticket"]
        ticket = Ticket.read(ticket_id, ["team_id"])[0]
        team_id = ticket["team_id"][0] if ticket["team_id"] else None

        if not team_id:
            return [TextContent(type="text", text="Error: Ticket has no team assigned")]

        # Find the closed/done stage for this team
        Stage = self.odoo.env["helpdesk.stage"]
        stage_ids = Stage.search([
            ("team_ids", "in", [team_id]),
            "|",
            ("name", "ilike", "closed"),
            ("name", "ilike", "done")
        ], limit=1)

        if not stage_ids:
            return [TextContent(type="text", text="Error: Could not find a closed stage for this team")]

        # Update the ticket to closed stage
        Ticket.write(ticket_id, {"stage_id": stage_ids[0]})

        # Read the updated ticket
        ticket = Ticket.read(ticket_id, ["name", "id", "stage_id"])[0]
        stage_id = ticket.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        output = (
            f"# Ticket Closed Successfully\n\n"
            f"**{ticket['name']}** (ID: {ticket['id']})\n"
            f"- Stage: {stage}\n"
        )

        return [TextContent(type="text", text=output)]

    async def send_ticket_message(self, arguments: dict) -> list[TextContent]:
        """Send a message on a helpdesk ticket."""
        ticket_id = arguments.get("ticket_id")
        body = arguments.get("body")

        if not ticket_id or not body:
            return [TextContent(type="text", text="Error: ticket_id and body are required")]

        message_type = arguments.get("message_type", "comment")

        # Get the ticket
        Ticket = self.odoo.env["helpdesk.ticket"]
        ticket_record = Ticket.browse(ticket_id)
        ticket_data = Ticket.read(ticket_id, ["name"])[0]

        # Handle both HTML and plain text:
        # - If body contains HTML tags, use it as-is
        # - If plain text, wrap in <p> tags and convert newlines to <br>
        if '<' not in body or '>' not in body:
            # Plain text - wrap in paragraph and convert newlines
            body = '<p>' + body.replace('\n', '<br>') + '</p>'
        # else: body already contains HTML, use as-is

        # Use message_post() with body_is_html=True to preserve HTML formatting
        # and trigger email notifications
        # subtype_xmlid: 'mail.mt_comment' for public comments (sends email)
        #                'mail.mt_note' for internal notes (no email)
        subtype_xmlid = 'mail.mt_comment' if message_type == "comment" else 'mail.mt_note'

        ticket_record.message_post(
            body=body,
            body_is_html=True,
            message_type=message_type,
            subtype_xmlid=subtype_xmlid
        )

        output = (
            f"# Message Sent Successfully\n\n"
            f"Message posted on ticket **{ticket_data['name']}** (ID: {ticket_id})\n"
            f"- Type: {message_type}\n"
        )

        return [TextContent(type="text", text=output)]

    async def get_ticket_messages(self, arguments: dict) -> list[TextContent]:
        """Get all messages from a helpdesk ticket."""
        ticket_id = arguments.get("ticket_id")

        if not ticket_id:
            return [TextContent(type="text", text="Error: ticket_id is required")]

        # Get the ticket to find its message_ids
        Ticket = self.odoo.env["helpdesk.ticket"]
        ticket = Ticket.read(ticket_id, ["name", "message_ids"])[0]
        ticket_name = ticket["name"]
        message_ids = ticket.get("message_ids", [])

        if not message_ids:
            return [TextContent(type="text", text=f"# Messages for {ticket_name}\n\nNo messages found.")]

        # Read the messages
        Message = self.odoo.env["mail.message"]
        messages = Message.read(
            message_ids,
            ["id", "author_id", "body", "date", "message_type", "subtype_id"]
        )

        # Sort messages by date (oldest first)
        messages.sort(key=lambda m: m.get("date", ""))

        # Format output
        output_lines = [f"# Messages for {ticket_name}\n"]
        for msg in messages:
            author_id = msg.get("author_id")
            author = author_id[1] if author_id else "System"

            date = msg.get("date", "Unknown")
            message_type = msg.get("message_type", "notification")
            subtype_id = msg.get("subtype_id")
            subtype = subtype_id[1] if subtype_id else "Note"

            body = msg.get("body") or "No content"

            output_lines.append(
                f"## Message {msg['id']}\n"
                f"- **Author:** {author}\n"
                f"- **Date:** {date}\n"
                f"- **Type:** {message_type} ({subtype})\n\n"
                f"**Content:**\n{body}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def list_contacts(self, arguments: dict) -> list[TextContent]:
        """List contacts."""
        limit = arguments.get("limit", 50)
        is_company = arguments.get("is_company")

        # Access res.partner model
        Partner = self.odoo.env["res.partner"]

        # Build search domain
        domain = []
        if is_company is not None:
            domain.append(("is_company", "=", is_company))

        # Search for contacts
        contact_ids = Partner.search(domain, limit=limit)

        if not contact_ids:
            return [TextContent(type="text", text="No contacts found.")]

        # Read contact details
        contacts = Partner.read(
            contact_ids,
            ["name", "id", "email", "phone", "mobile", "is_company", "parent_id", "active"]
        )

        # Format output
        output_lines = ["# Contacts\n"]
        for contact in contacts:
            contact_type = "Company" if contact.get("is_company") else "Individual"
            email = contact.get("email") or "No email"
            phone = contact.get("phone") or contact.get("mobile") or "No phone"
            parent_id = contact.get("parent_id")
            parent = parent_id[1] if parent_id else "No parent company"
            active = "Active" if contact.get("active", True) else "Archived"

            output_lines.append(
                f"## {contact['name']} (ID: {contact['id']})\n"
                f"- Type: {contact_type}\n"
                f"- Status: {active}\n"
                f"- Email: {email}\n"
                f"- Phone: {phone}\n"
            )
            if not contact.get("is_company"):
                output_lines.append(f"- Company: {parent}\n")
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_contact(self, arguments: dict) -> list[TextContent]:
        """Get a specific contact with full details."""
        contact_id = arguments.get("contact_id")

        if not contact_id:
            return [TextContent(type="text", text="Error: contact_id is required")]

        # Access res.partner model
        Partner = self.odoo.env["res.partner"]

        # Read contact with full details
        contact = Partner.read(
            contact_id,
            ["name", "id", "email", "phone", "mobile", "is_company", "parent_id",
             "street", "street2", "city", "zip", "country_id", "active"]
        )[0]

        contact_type = "Company" if contact.get("is_company") else "Individual"
        email = contact.get("email") or "No email"
        phone = contact.get("phone") or "No phone"
        mobile = contact.get("mobile") or "No mobile"
        parent_id = contact.get("parent_id")
        parent = parent_id[1] if parent_id else "No parent company"
        active = "Active" if contact.get("active", True) else "Archived"

        # Format address
        address_parts = []
        if contact.get("street"):
            address_parts.append(contact["street"])
        if contact.get("street2"):
            address_parts.append(contact["street2"])
        city_line = []
        if contact.get("city"):
            city_line.append(contact["city"])
        if contact.get("zip"):
            city_line.append(contact["zip"])
        if city_line:
            address_parts.append(", ".join(city_line))
        country_id = contact.get("country_id")
        if country_id:
            address_parts.append(country_id[1])
        address = "\n".join(address_parts) if address_parts else "No address"

        output = (
            f"# {contact['name']}\n\n"
            f"**ID:** {contact['id']}  \n"
            f"**Type:** {contact_type}  \n"
            f"**Status:** {active}  \n"
            f"**Email:** {email}  \n"
            f"**Phone:** {phone}  \n"
            f"**Mobile:** {mobile}  \n"
        )
        if not contact.get("is_company"):
            output += f"**Company:** {parent}  \n"
        output += f"\n## Address\n\n{address}"

        return [TextContent(type="text", text=output)]

    async def create_contact(self, arguments: dict) -> list[TextContent]:
        """Create a new contact."""
        name = arguments.get("name")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        # Build contact values
        contact_values = {
            "name": name,
        }

        # Add optional fields
        if "email" in arguments and arguments["email"]:
            contact_values["email"] = arguments["email"]

        if "phone" in arguments and arguments["phone"]:
            contact_values["phone"] = arguments["phone"]

        if "mobile" in arguments and arguments["mobile"]:
            contact_values["mobile"] = arguments["mobile"]

        if "is_company" in arguments:
            contact_values["is_company"] = arguments["is_company"]

        if "parent_id" in arguments and arguments["parent_id"]:
            contact_values["parent_id"] = arguments["parent_id"]

        if "street" in arguments and arguments["street"]:
            contact_values["street"] = arguments["street"]

        if "street2" in arguments and arguments["street2"]:
            contact_values["street2"] = arguments["street2"]

        if "city" in arguments and arguments["city"]:
            contact_values["city"] = arguments["city"]

        if "zip" in arguments and arguments["zip"]:
            contact_values["zip"] = arguments["zip"]

        if "country_id" in arguments and arguments["country_id"]:
            contact_values["country_id"] = arguments["country_id"]

        # Handle image upload
        if "image_url" in arguments and arguments["image_url"]:
            image_url = arguments["image_url"]
            try:
                # Download the image
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()

                # Convert to base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                contact_values["image_1920"] = image_base64
            except Exception as e:
                return [TextContent(type="text", text=f"Error downloading image: {str(e)}")]

        # Create the contact
        Partner = self.odoo.env["res.partner"]
        new_contact_id = Partner.create(contact_values)

        # Read the created contact to return details
        contact = Partner.read(new_contact_id, ["name", "id", "email", "is_company"])[0]

        contact_type = "Company" if contact.get("is_company") else "Individual"
        email = contact.get("email") or "No email"

        output = (
            f"# Contact Created Successfully\n\n"
            f"**{contact['name']}** (ID: {contact['id']})\n"
            f"- Type: {contact_type}\n"
            f"- Email: {email}\n"
        )

        if "image_1920" in contact_values:
            output += "- Logo: Uploaded\n"

        return [TextContent(type="text", text=output)]

    async def update_contact(self, arguments: dict) -> list[TextContent]:
        """Update an existing contact."""
        contact_id = arguments.get("contact_id")

        if not contact_id:
            return [TextContent(type="text", text="Error: contact_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "email" in arguments:
            update_values["email"] = arguments["email"]

        if "phone" in arguments:
            update_values["phone"] = arguments["phone"]

        if "mobile" in arguments:
            update_values["mobile"] = arguments["mobile"]

        if "street" in arguments:
            update_values["street"] = arguments["street"]

        if "street2" in arguments:
            update_values["street2"] = arguments["street2"]

        if "city" in arguments:
            update_values["city"] = arguments["city"]

        if "zip" in arguments:
            update_values["zip"] = arguments["zip"]

        # Handle image upload
        if "image_url" in arguments and arguments["image_url"]:
            image_url = arguments["image_url"]
            try:
                # Download the image
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()

                # Convert to base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                update_values["image_1920"] = image_base64
            except Exception as e:
                return [TextContent(type="text", text=f"Error downloading image: {str(e)}")]

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the contact
        Partner = self.odoo.env["res.partner"]
        Partner.write(contact_id, update_values)

        # Read the updated contact to return details
        contact = Partner.read(contact_id, ["name", "id", "email", "phone", "mobile"])[0]

        email = contact.get("email") or "No email"
        phone = contact.get("phone") or "No phone"
        mobile = contact.get("mobile") or "No mobile"

        output = (
            f"# Contact Updated Successfully\n\n"
            f"**{contact['name']}** (ID: {contact['id']})\n"
            f"- Email: {email}\n"
            f"- Phone: {phone}\n"
            f"- Mobile: {mobile}\n"
        )

        if "image_1920" in update_values:
            output += "- Logo: Updated\n"

        return [TextContent(type="text", text=output)]

    async def delete_contact(self, arguments: dict) -> list[TextContent]:
        """Delete a contact permanently."""
        contact_id = arguments.get("contact_id")

        if not contact_id:
            return [TextContent(type="text", text="Error: contact_id is required")]

        # Get contact details before deletion
        Partner = self.odoo.env["res.partner"]
        contact = Partner.read(contact_id, ["name", "id"])[0]
        contact_name = contact["name"]

        # Delete the contact
        Partner.unlink(contact_id)

        output = (
            f"# Contact Deleted Successfully\n\n"
            f"Contact **{contact_name}** (ID: {contact_id}) has been permanently deleted."
        )

        return [TextContent(type="text", text=output)]

    async def archive_contact(self, arguments: dict) -> list[TextContent]:
        """Archive a contact."""
        contact_id = arguments.get("contact_id")

        if not contact_id:
            return [TextContent(type="text", text="Error: contact_id is required")]

        # Archive the contact by setting active=False
        Partner = self.odoo.env["res.partner"]
        Partner.write(contact_id, {"active": False})

        # Read the archived contact to return details
        contact = Partner.read(contact_id, ["name", "id"])[0]

        output = (
            f"# Contact Archived Successfully\n\n"
            f"Contact **{contact['name']}** (ID: {contact['id']}) has been archived."
        )

        return [TextContent(type="text", text=output)]

    async def search_contacts(self, arguments: dict) -> list[TextContent]:
        """Search contacts by name, email, or company."""
        query = arguments.get("query")
        limit = arguments.get("limit", 50)

        if not query:
            return [TextContent(type="text", text="Error: query is required")]

        # Access res.partner model
        Partner = self.odoo.env["res.partner"]

        # Build search domain using OR conditions
        # Search in name, email, and parent company name
        domain = [
            '|', '|',
            ('name', 'ilike', query),
            ('email', 'ilike', query),
            ('parent_id.name', 'ilike', query)
        ]

        # Search for contacts
        contact_ids = Partner.search(domain, limit=limit)

        if not contact_ids:
            return [TextContent(type="text", text=f"No contacts found matching '{query}'.")]

        # Read contact details
        contacts = Partner.read(
            contact_ids,
            ["name", "id", "email", "phone", "mobile", "is_company", "parent_id", "active"]
        )

        # Format output
        output_lines = [f"# Search Results for '{query}'\n\nFound {len(contacts)} contact(s):\n"]
        for contact in contacts:
            contact_type = "Company" if contact.get("is_company") else "Individual"
            email = contact.get("email") or "No email"
            phone = contact.get("phone") or contact.get("mobile") or "No phone"
            parent_id = contact.get("parent_id")
            parent = parent_id[1] if parent_id else "No parent company"
            active = "Active" if contact.get("active", True) else "Archived"

            output_lines.append(
                f"## {contact['name']} (ID: {contact['id']})\n"
                f"- Type: {contact_type}\n"
                f"- Status: {active}\n"
                f"- Email: {email}\n"
                f"- Phone: {phone}\n"
            )
            if not contact.get("is_company"):
                output_lines.append(f"- Company: {parent}\n")
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def list_mailing_lists(self, arguments: dict) -> list[TextContent]:
        """List all mailing lists."""
        limit = arguments.get("limit", 50)

        # Access mailing.list model
        MailingList = self.odoo.env["mailing.list"]

        # Search for mailing lists
        list_ids = MailingList.search([], limit=limit)

        if not list_ids:
            return [TextContent(type="text", text="No mailing lists found.")]

        # Read mailing list details
        lists = MailingList.read(
            list_ids,
            ["name", "id", "contact_count"]
        )

        # Format output
        output_lines = ["# Mailing Lists\n"]
        for ml in lists:
            contact_count = ml.get("contact_count", 0)

            output_lines.append(
                f"## {ml['name']} (ID: {ml['id']})\n"
                f"- Subscribers: {contact_count}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_mailing_list(self, arguments: dict) -> list[TextContent]:
        """Get a specific mailing list with all subscribers."""
        list_id = arguments.get("list_id")

        if not list_id:
            return [TextContent(type="text", text="Error: list_id is required")]

        # Access mailing.list model
        MailingList = self.odoo.env["mailing.list"]

        # Read mailing list with details
        ml = MailingList.read(
            list_id,
            ["name", "id", "contact_count"]
        )[0]

        contact_count = ml.get("contact_count", 0)

        output = (
            f"# {ml['name']}\n\n"
            f"**ID:** {ml['id']}  \n"
            f"**Total Subscribers:** {contact_count}\n\n"
        )

        # Get subscriptions for this list
        MailingSubscription = self.odoo.env["mailing.subscription"]
        subscription_ids = MailingSubscription.search([("list_id", "=", list_id)])

        if subscription_ids:
            subscriptions = MailingSubscription.read(
                subscription_ids,
                ["contact_id", "opt_out", "opt_out_datetime"]
            )

            # Separate active and opted-out subscribers
            active_subs = [s for s in subscriptions if not s.get("opt_out")]
            opted_out_subs = [s for s in subscriptions if s.get("opt_out")]

            # Show active subscribers
            if active_subs:
                output += "## Active Subscribers\n\n"
                for sub in active_subs:
                    contact_info = sub.get("contact_id")
                    if contact_info:
                        output += f"- {contact_info[1]}\n"
                output += "\n"

            # Show opted-out subscribers
            if opted_out_subs:
                output += "## Opted Out\n\n"
                for sub in opted_out_subs:
                    contact_info = sub.get("contact_id")
                    opt_out_datetime = sub.get("opt_out_datetime", "Unknown")
                    if contact_info:
                        output += f"- {contact_info[1]} (opted out: {opt_out_datetime})\n"
                output += "\n"

            if not active_subs and not opted_out_subs:
                output += "## Subscribers\n\nNo subscribers yet."
        else:
            output += "## Subscribers\n\nNo subscribers yet."

        return [TextContent(type="text", text=output)]

    async def create_mailing_list(self, arguments: dict) -> list[TextContent]:
        """Create a new mailing list."""
        name = arguments.get("name")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        # Create the mailing list
        MailingList = self.odoo.env["mailing.list"]
        new_list_id = MailingList.create({"name": name})

        # Read the created list to return details
        ml = MailingList.read(new_list_id, ["name", "id"])[0]

        output = (
            f"# Mailing List Created Successfully\n\n"
            f"**{ml['name']}** (ID: {ml['id']})\n"
            f"- Subscribers: 0\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_mailing_list(self, arguments: dict) -> list[TextContent]:
        """Update an existing mailing list."""
        list_id = arguments.get("list_id")
        name = arguments.get("name")

        if not list_id or not name:
            return [TextContent(type="text", text="Error: list_id and name are required")]

        # Update the mailing list
        MailingList = self.odoo.env["mailing.list"]
        MailingList.write(list_id, {"name": name})

        # Read the updated list to return details
        ml = MailingList.read(list_id, ["name", "id", "contact_count"])[0]

        contact_count = ml.get("contact_count", 0)

        output = (
            f"# Mailing List Updated Successfully\n\n"
            f"**{ml['name']}** (ID: {ml['id']})\n"
            f"- Subscribers: {contact_count}\n"
        )

        return [TextContent(type="text", text=output)]

    async def delete_mailing_list(self, arguments: dict) -> list[TextContent]:
        """Delete a mailing list permanently."""
        list_id = arguments.get("list_id")

        if not list_id:
            return [TextContent(type="text", text="Error: list_id is required")]

        # Get list details before deletion
        MailingList = self.odoo.env["mailing.list"]
        ml = MailingList.read(list_id, ["name", "id"])[0]
        list_name = ml["name"]

        # Delete the mailing list
        MailingList.unlink(list_id)

        output = (
            f"# Mailing List Deleted Successfully\n\n"
            f"Mailing list **{list_name}** (ID: {list_id}) has been permanently deleted."
        )

        return [TextContent(type="text", text=output)]

    async def subscribe_contact(self, arguments: dict) -> list[TextContent]:
        """Subscribe a contact to a mailing list."""
        list_id = arguments.get("list_id")
        email = arguments.get("email")
        name = arguments.get("name")

        if not list_id or not email:
            return [TextContent(type="text", text="Error: list_id and email are required")]

        # Get the mailing list name
        MailingList = self.odoo.env["mailing.list"]
        ml = MailingList.read(list_id, ["name"])[0]
        list_name = ml["name"]

        # Check if contact already exists
        MailingContact = self.odoo.env["mailing.contact"]
        existing_contacts = MailingContact.search([
            ("email", "=", email),
            ("list_ids", "in", [list_id])
        ])

        if existing_contacts:
            return [TextContent(type="text", text=f"Contact {email} is already subscribed to {list_name}.")]

        # Find or create mailing contact
        contact_ids = MailingContact.search([("email", "=", email)])

        if contact_ids:
            # Contact exists, add to list
            contact = MailingContact.browse(contact_ids[0])
            contact.write({"list_ids": [(4, list_id)]})
            contact_name = MailingContact.read(contact_ids[0], ["name"])[0]["name"]
        else:
            # Create new contact
            contact_name = name if name else email.split("@")[0]
            MailingContact.create({
                "name": contact_name,
                "email": email,
                "list_ids": [(4, list_id)]
            })

        output = (
            f"# Subscription Successful\n\n"
            f"**{contact_name}** ({email}) has been subscribed to **{list_name}**."
        )

        return [TextContent(type="text", text=output)]

    async def unsubscribe_contact(self, arguments: dict) -> list[TextContent]:
        """Unsubscribe a contact from a mailing list."""
        list_id = arguments.get("list_id")
        email = arguments.get("email")

        if not list_id or not email:
            return [TextContent(type="text", text="Error: list_id and email are required")]

        # Get the mailing list name
        MailingList = self.odoo.env["mailing.list"]
        ml = MailingList.read(list_id, ["name"])[0]
        list_name = ml["name"]

        # Find the mailing contact
        MailingContact = self.odoo.env["mailing.contact"]
        contact_ids = MailingContact.search([
            ("email", "=", email),
            ("list_ids", "in", [list_id])
        ])

        if not contact_ids:
            return [TextContent(type="text", text=f"Contact {email} is not subscribed to {list_name}.")]

        # Remove from list
        contact = MailingContact.browse(contact_ids[0])
        contact.write({"list_ids": [(3, list_id)]})
        contact_name = MailingContact.read(contact_ids[0], ["name"])[0]["name"]

        output = (
            f"# Unsubscription Successful\n\n"
            f"**{contact_name}** ({email}) has been unsubscribed from **{list_name}**."
        )

        return [TextContent(type="text", text=output)]

    async def get_contact_subscriptions(self, arguments: dict) -> list[TextContent]:
        """Get all mailing lists a contact is subscribed to."""
        email = arguments.get("email")

        if not email:
            return [TextContent(type="text", text="Error: email is required")]

        # Search for mailing contact with this email
        MailingContact = self.odoo.env["mailing.contact"]
        contact_ids = MailingContact.search([("email", "=", email)])

        if not contact_ids:
            return [TextContent(type="text", text=f"No mailing contact found with email: {email}")]

        # Get the contact and their lists
        contacts = MailingContact.read(contact_ids, ["name", "email", "list_ids"])
        contact = contacts[0]
        contact_name = contact["name"]
        list_ids = contact.get("list_ids", [])

        output = f"# Mailing List Subscriptions\n\n**{contact_name}** ({email})\n\n"

        if list_ids:
            MailingList = self.odoo.env["mailing.list"]
            lists = MailingList.read(list_ids, ["name", "id"])
            output += f"Subscribed to {len(lists)} mailing list(s):\n\n"
            for ml in lists:
                output += f"- {ml['name']} (ID: {ml['id']})\n"
        else:
            output += "Not subscribed to any mailing lists."

        return [TextContent(type="text", text=output)]

    async def opt_in_contact(self, arguments: dict) -> list[TextContent]:
        """Opt a contact back into a mailing list."""
        list_id = arguments.get("list_id")
        email = arguments.get("email")

        if not list_id or not email:
            return [TextContent(type="text", text="Error: list_id and email are required")]

        # Get the mailing list name
        MailingList = self.odoo.env["mailing.list"]
        ml = MailingList.read(list_id, ["name"])[0]
        list_name = ml["name"]

        # Find the mailing contact
        MailingContact = self.odoo.env["mailing.contact"]
        contact_ids = MailingContact.search([("email", "=", email)])

        if not contact_ids:
            return [TextContent(type="text", text=f"No mailing contact found with email: {email}")]

        contact = MailingContact.read(contact_ids[0], ["name"])[0]
        contact_name = contact["name"]

        # Find the subscription
        MailingSubscription = self.odoo.env["mailing.subscription"]
        subscription_ids = MailingSubscription.search([
            ("contact_id", "=", contact_ids[0]),
            ("list_id", "=", list_id)
        ])

        if not subscription_ids:
            return [TextContent(type="text", text=f"No subscription found for {email} on {list_name}.")]

        # Update subscription to opt back in
        MailingSubscription.write(subscription_ids[0], {
            "opt_out": False,
            "opt_out_datetime": False
        })

        output = (
            f"# Opt-In Successful\n\n"
            f"**{contact_name}** ({email}) has been opted back into **{list_name}**."
        )

        return [TextContent(type="text", text=output)]

    async def opt_out_contact(self, arguments: dict) -> list[TextContent]:
        """Opt a contact out of a mailing list."""
        list_id = arguments.get("list_id")
        email = arguments.get("email")

        if not list_id or not email:
            return [TextContent(type="text", text="Error: list_id and email are required")]

        # Get the mailing list name
        MailingList = self.odoo.env["mailing.list"]
        ml = MailingList.read(list_id, ["name"])[0]
        list_name = ml["name"]

        # Find the mailing contact
        MailingContact = self.odoo.env["mailing.contact"]
        contact_ids = MailingContact.search([("email", "=", email)])

        if not contact_ids:
            return [TextContent(type="text", text=f"No mailing contact found with email: {email}")]

        contact = MailingContact.read(contact_ids[0], ["name"])[0]
        contact_name = contact["name"]

        # Find the subscription
        MailingSubscription = self.odoo.env["mailing.subscription"]
        subscription_ids = MailingSubscription.search([
            ("contact_id", "=", contact_ids[0]),
            ("list_id", "=", list_id)
        ])

        if not subscription_ids:
            return [TextContent(type="text", text=f"No subscription found for {email} on {list_name}.")]

        # Update subscription to opt out
        from datetime import datetime
        MailingSubscription.write(subscription_ids[0], {
            "opt_out": True,
            "opt_out_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        output = (
            f"# Opt-Out Successful\n\n"
            f"**{contact_name}** ({email}) has been opted out of **{list_name}**."
        )

        return [TextContent(type="text", text=output)]

    async def list_users(self, arguments: dict) -> list[TextContent]:
        """List Odoo users."""
        limit = arguments.get("limit", 50)

        # Access res.users model
        User = self.odoo.env["res.users"]

        # Search for active users
        user_ids = User.search([("active", "=", True)], limit=limit)

        if not user_ids:
            return [TextContent(type="text", text="No users found.")]

        # Read user details
        users = User.read(
            user_ids,
            ["name", "id", "login", "email", "partner_id"]
        )

        # Format output
        output_lines = ["# Odoo Users\n"]
        for user in users:
            name = user.get("name", "Unknown")
            user_id = user["id"]
            login = user.get("login", "N/A")
            email = user.get("email", "No email")

            output_lines.append(
                f"## {name} (ID: {user_id})\n"
                f"- Login: {login}\n"
                f"- Email: {email}\n"
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
    import signal
    import sys

    server = None

    # Handle shutdown signals gracefully
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal, exiting gracefully...")
        if server:
            server.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server = OdooMCPServer()
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        if server:
            server.cleanup()
    except Exception as e:
        logger.error(f"Server error: {e}")
        if server:
            server.cleanup()
        sys.exit(1)
    finally:
        if server:
            server.cleanup()


if __name__ == "__main__":
    main()
