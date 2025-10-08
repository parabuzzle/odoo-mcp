"""Users handler for Odoo MCP."""

from mcp.types import TextContent
from .base import OdooBase


class UsersHandler(OdooBase):
    """Handler for user operations."""

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
