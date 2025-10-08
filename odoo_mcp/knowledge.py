"""Knowledge articles handler for Odoo MCP."""

from mcp.types import TextContent
from .base import OdooBase


class KnowledgeHandler(OdooBase):
    """Handler for knowledge article operations."""

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
