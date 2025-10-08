"""Mailing lists handler for Odoo MCP."""

from datetime import datetime
from mcp.types import TextContent
from .base import OdooBase


class MailingHandler(OdooBase):
    """Handler for mailing list operations."""

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
        MailingSubscription.write(subscription_ids[0], {
            "opt_out": True,
            "opt_out_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        output = (
            f"# Opt-Out Successful\n\n"
            f"**{contact_name}** ({email}) has been opted out of **{list_name}**."
        )

        return [TextContent(type="text", text=output)]
