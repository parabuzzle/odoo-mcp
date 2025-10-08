"""Helpdesk handler for Odoo MCP."""

from mcp.types import TextContent
from .base import OdooBase


class HelpdeskHandler(OdooBase):
    """Handler for helpdesk operations."""

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
