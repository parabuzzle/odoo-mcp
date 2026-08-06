"""Contacts handler for Odoo MCP."""

import base64
import requests
from mcp.types import TextContent
from .base import OdooBase


class ContactsHandler(OdooBase):
    """Handler for contact operations."""

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

        # Read contact details (mobile was merged into phone in Odoo 19)
        contacts, warnings = self.safe_read(
            "res.partner",
            contact_ids,
            ["name", "id", "email", "phone", "is_company", "parent_id", "active", "category_id"]
        )

        # Format output
        output_lines = ["# Contacts\n"]
        for contact in contacts:
            contact_type = "Company" if contact.get("is_company") else "Individual"
            email = contact.get("email") or "No email"
            phone = contact.get("phone") or "No phone"
            parent_id = contact.get("parent_id")
            parent = parent_id[1] if parent_id else "No parent company"
            active = "Active" if contact.get("active", True) else "Archived"

            # Get tags
            category_ids = contact.get("category_id", [])
            if category_ids:
                Category = self.odoo.env["res.partner.category"]
                categories = Category.read(category_ids, ["name"])
                tags = ", ".join([cat["name"] for cat in categories])
            else:
                tags = None

            output_lines.append(
                f"## {contact['name']} (ID: {contact['id']})\n"
                f"- Type: {contact_type}\n"
                f"- Status: {active}\n"
                f"- Email: {email}\n"
                f"- Phone: {phone}\n"
            )
            if not contact.get("is_company"):
                output_lines.append(f"- Company: {parent}\n")
            if tags:
                output_lines.append(f"- Tags: {tags}\n")
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines) + self.warnings_section(warnings))]

    async def get_contact(self, arguments: dict) -> list[TextContent]:
        """Get a specific contact with full details."""
        contact_id = arguments.get("contact_id")

        if not contact_id:
            return [TextContent(type="text", text="Error: contact_id is required")]

        # Access res.partner model
        Partner = self.odoo.env["res.partner"]

        # Read contact with full details (mobile was merged into phone in Odoo 19)
        contacts, warnings = self.safe_read(
            "res.partner",
            contact_id,
            ["name", "id", "email", "phone", "website", "is_company", "parent_id",
             "street", "street2", "city", "state_id", "zip", "country_id", "active",
             "category_id", "comment", "vat", "title", "function", "ref"]
        )
        contact = contacts[0]

        contact_type = "Company" if contact.get("is_company") else "Individual"
        email = contact.get("email") or "No email"
        phone = contact.get("phone") or "No phone"
        website = contact.get("website") or "No website"
        parent_id = contact.get("parent_id")
        parent = parent_id[1] if parent_id else "No parent company"
        active = "Active" if contact.get("active", True) else "Archived"
        vat = contact.get("vat") or "No tax ID"
        title_id = contact.get("title")
        title = title_id[1] if title_id else "No title"
        function = contact.get("function") or "No job position"
        ref = contact.get("ref") or "No reference"

        # Get tags
        category_ids = contact.get("category_id", [])
        if category_ids:
            Category = self.odoo.env["res.partner.category"]
            categories = Category.read(category_ids, ["name"])
            tags = ", ".join([cat["name"] for cat in categories])
        else:
            tags = "No tags"

        # Get internal notes
        notes = contact.get("comment") or "No notes"

        # Format address
        address_parts = []
        if contact.get("street"):
            address_parts.append(contact["street"])
        if contact.get("street2"):
            address_parts.append(contact["street2"])
        city_line = []
        if contact.get("city"):
            city_line.append(contact["city"])
        state_id = contact.get("state_id")
        if state_id:
            city_line.append(state_id[1])
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
            f"**Website:** {website}  \n"
        )
        if not contact.get("is_company"):
            output += f"**Title:** {title}  \n"
            output += f"**Job Position:** {function}  \n"
            output += f"**Company:** {parent}  \n"
        else:
            output += f"**Tax ID:** {vat}  \n"
        output += f"**Reference:** {ref}  \n"
        output += f"**Tags:** {tags}  \n"
        output += f"\n## Address\n\n{address}\n\n"
        output += f"## Internal Notes\n\n{notes}"

        return [TextContent(type="text", text=output + self.warnings_section(warnings))]

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

        # Read contact details (mobile was merged into phone in Odoo 19)
        contacts, warnings = self.safe_read(
            "res.partner",
            contact_ids,
            ["name", "id", "email", "phone", "is_company", "parent_id", "active", "category_id"]
        )

        # Format output
        output_lines = [f"# Search Results for '{query}'\n\nFound {len(contacts)} contact(s):\n"]
        for contact in contacts:
            contact_type = "Company" if contact.get("is_company") else "Individual"
            email = contact.get("email") or "No email"
            phone = contact.get("phone") or "No phone"
            parent_id = contact.get("parent_id")
            parent = parent_id[1] if parent_id else "No parent company"
            active = "Active" if contact.get("active", True) else "Archived"

            # Get tags
            category_ids = contact.get("category_id", [])
            if category_ids:
                Category = self.odoo.env["res.partner.category"]
                categories = Category.read(category_ids, ["name"])
                tags = ", ".join([cat["name"] for cat in categories])
            else:
                tags = None

            output_lines.append(
                f"## {contact['name']} (ID: {contact['id']})\n"
                f"- Type: {contact_type}\n"
                f"- Status: {active}\n"
                f"- Email: {email}\n"
                f"- Phone: {phone}\n"
            )
            if not contact.get("is_company"):
                output_lines.append(f"- Company: {parent}\n")
            if tags:
                output_lines.append(f"- Tags: {tags}\n")
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines) + self.warnings_section(warnings))]

    async def search_contacts_by_tag(self, arguments: dict) -> list[TextContent]:
        """Search contacts by tag name."""
        tag_name = arguments.get("tag_name")
        limit = arguments.get("limit", 50)

        if not tag_name:
            return [TextContent(type="text", text="Error: tag_name is required")]

        # Access res.partner.category model
        Category = self.odoo.env["res.partner.category"]

        # Search for tag
        tag_ids = Category.search([("name", "ilike", tag_name)], limit=1)

        if not tag_ids:
            return [TextContent(type="text", text=f"No tag found matching '{tag_name}'.")]

        tag_id = tag_ids[0]
        tag = Category.read(tag_id, ["name"])[0]
        tag_name_actual = tag["name"]

        # Access res.partner model
        Partner = self.odoo.env["res.partner"]

        # Search for contacts with this tag
        contact_ids = Partner.search([("category_id", "in", [tag_id])], limit=limit)

        if not contact_ids:
            return [TextContent(type="text", text=f"No contacts found with tag '{tag_name_actual}'.")]

        # Read contact details (mobile was merged into phone in Odoo 19)
        contacts, warnings = self.safe_read(
            "res.partner",
            contact_ids,
            ["name", "id", "email", "phone", "is_company", "parent_id", "active", "category_id"]
        )

        # Format output
        output_lines = [f"# Contacts with Tag '{tag_name_actual}'\n\nFound {len(contacts)} contact(s):\n"]
        for contact in contacts:
            contact_type = "Company" if contact.get("is_company") else "Individual"
            email = contact.get("email") or "No email"
            phone = contact.get("phone") or "No phone"
            parent_id = contact.get("parent_id")
            parent = parent_id[1] if parent_id else "No parent company"
            active = "Active" if contact.get("active", True) else "Archived"

            # Get all tags
            category_ids = contact.get("category_id", [])
            if category_ids:
                categories = Category.read(category_ids, ["name"])
                tags = ", ".join([cat["name"] for cat in categories])
            else:
                tags = None

            output_lines.append(
                f"## {contact['name']} (ID: {contact['id']})\n"
                f"- Type: {contact_type}\n"
                f"- Status: {active}\n"
                f"- Email: {email}\n"
                f"- Phone: {phone}\n"
            )
            if not contact.get("is_company"):
                output_lines.append(f"- Company: {parent}\n")
            if tags:
                output_lines.append(f"- Tags: {tags}\n")
            output_lines.append("")

        return [TextContent(type="text", text="\n".join(output_lines) + self.warnings_section(warnings))]

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

        # Odoo 19 removed res.partner.mobile (merged into phone). The 'mobile'
        # param is kept for backward compatibility and aliased onto phone, but
        # an explicitly-provided phone always wins.
        if "mobile" in arguments and arguments["mobile"] and "phone" not in contact_values:
            contact_values["phone"] = arguments["mobile"]

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

        if "state_id" in arguments and arguments["state_id"]:
            contact_values["state_id"] = arguments["state_id"]

        if "website" in arguments and arguments["website"]:
            contact_values["website"] = arguments["website"]

        if "vat" in arguments and arguments["vat"]:
            contact_values["vat"] = arguments["vat"]

        if "title" in arguments and arguments["title"]:
            contact_values["title"] = arguments["title"]

        if "function" in arguments and arguments["function"]:
            contact_values["function"] = arguments["function"]

        if "ref" in arguments and arguments["ref"]:
            contact_values["ref"] = arguments["ref"]

        # Handle tags
        if "tags" in arguments and arguments["tags"]:
            tag_names = arguments["tags"]
            Category = self.odoo.env["res.partner.category"]
            tag_ids = []
            for tag_name in tag_names:
                # Search for existing tag
                existing_tag = Category.search([("name", "=", tag_name)], limit=1)
                if existing_tag:
                    tag_ids.append(existing_tag[0])
                else:
                    # Create new tag
                    new_tag_id = Category.create({"name": tag_name})
                    tag_ids.append(new_tag_id)
            contact_values["category_id"] = [(6, 0, tag_ids)]

        # Handle internal notes
        if "notes" in arguments and arguments["notes"]:
            contact_values["comment"] = arguments["notes"]

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

        # Validate payload against the live schema before writing so a removed
        # field fails fast with a clear message instead of a raw RPC error.
        invalid = self.invalid_write_fields("res.partner", contact_values)
        if invalid:
            return [TextContent(type="text", text=(
                f"Error: unknown field(s) for res.partner: {', '.join(invalid)}. "
                "They may have been removed in this Odoo version."
            ))]

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

        # Odoo 19 removed res.partner.mobile (merged into phone). Alias the
        # deprecated 'mobile' param onto phone unless phone was also provided.
        if "mobile" in arguments and "phone" not in arguments:
            update_values["phone"] = arguments["mobile"]

        if "street" in arguments:
            update_values["street"] = arguments["street"]

        if "street2" in arguments:
            update_values["street2"] = arguments["street2"]

        if "city" in arguments:
            update_values["city"] = arguments["city"]

        if "zip" in arguments:
            update_values["zip"] = arguments["zip"]

        if "state_id" in arguments:
            update_values["state_id"] = arguments["state_id"]

        if "country_id" in arguments:
            update_values["country_id"] = arguments["country_id"]

        if "website" in arguments:
            update_values["website"] = arguments["website"]

        if "vat" in arguments:
            update_values["vat"] = arguments["vat"]

        if "title" in arguments:
            update_values["title"] = arguments["title"]

        if "function" in arguments:
            update_values["function"] = arguments["function"]

        if "ref" in arguments:
            update_values["ref"] = arguments["ref"]

        # Handle tags
        if "tags" in arguments:
            if arguments["tags"]:
                tag_names = arguments["tags"]
                Category = self.odoo.env["res.partner.category"]
                tag_ids = []
                for tag_name in tag_names:
                    # Search for existing tag
                    existing_tag = Category.search([("name", "=", tag_name)], limit=1)
                    if existing_tag:
                        tag_ids.append(existing_tag[0])
                    else:
                        # Create new tag
                        new_tag_id = Category.create({"name": tag_name})
                        tag_ids.append(new_tag_id)
                update_values["category_id"] = [(6, 0, tag_ids)]
            else:
                # Empty list means clear all tags
                update_values["category_id"] = [(5, 0, 0)]

        # Handle internal notes
        if "notes" in arguments:
            update_values["comment"] = arguments["notes"]

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

        # Validate payload against the live schema before writing.
        invalid = self.invalid_write_fields("res.partner", update_values)
        if invalid:
            return [TextContent(type="text", text=(
                f"Error: unknown field(s) for res.partner: {', '.join(invalid)}. "
                "They may have been removed in this Odoo version."
            ))]

        # Update the contact
        Partner = self.odoo.env["res.partner"]
        Partner.write(contact_id, update_values)

        # Read the updated contact to return details (mobile merged into phone in Odoo 19)
        contact = Partner.read(contact_id, ["name", "id", "email", "phone"])[0]

        email = contact.get("email") or "No email"
        phone = contact.get("phone") or "No phone"

        output = (
            f"# Contact Updated Successfully\n\n"
            f"**{contact['name']}** (ID: {contact['id']})\n"
            f"- Email: {email}\n"
            f"- Phone: {phone}\n"
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
