"""Spreadsheets handler for Odoo MCP.

Manages spreadsheets stored in the Odoo Documents app. These are
``documents.document`` records with ``handler='spreadsheet'`` whose content is
an o-spreadsheet JSON payload kept in the ``spreadsheet_data`` field.

Note: this requires the Documents app (and its Spreadsheet feature) to be
installed on the Odoo instance. Documents live inside a folder/workspace; the
folder model changed between Odoo versions, so folder handling here is
defensive and a clear error is returned when a folder cannot be resolved.
"""

import json
import logging

from mcp.types import TextContent

from .base import OdooBase
from . import spreadsheet_utils as su

logger = logging.getLogger("odoo-mcp")

SPREADSHEET_MODEL = "documents.document"


class SpreadsheetsHandler(OdooBase):
    """Handler for Odoo Documents spreadsheet operations."""

    def _resolve_folder_id(self, folder=None):
        """Resolve a Documents folder/workspace id.

        Accepts an int id or a name string. When nothing is provided, tries to
        auto-detect a usable folder. Returns an int id or None if none found.
        Handles both the older ``documents.folder`` model and the newer
        Odoo 18 approach where folders are ``documents.document`` of
        ``type='folder'``.
        """
        # Explicit numeric id
        if isinstance(folder, int):
            return folder
        if isinstance(folder, str) and folder.isdigit():
            return int(folder)

        # Try the classic documents.folder model first.
        try:
            Folder = self.odoo.env["documents.folder"]
            domain = [("name", "ilike", folder)] if folder else []
            ids = Folder.search(domain, limit=1)
            if ids:
                return ids[0]
        except Exception:
            pass

        # Fall back to Odoo 18 folders (documents.document type='folder').
        try:
            Doc = self.odoo.env[SPREADSHEET_MODEL]
            domain = [("type", "=", "folder")]
            if folder:
                domain.append(("name", "ilike", folder))
            ids = Doc.search(domain, limit=1)
            if ids:
                return ids[0]
        except Exception:
            pass

        return None

    async def list_spreadsheets(self, arguments: dict) -> list[TextContent]:
        """List spreadsheets in the Documents app."""
        limit = arguments.get("limit", 50)
        name_filter = arguments.get("name")

        Doc = self.odoo.env[SPREADSHEET_MODEL]

        domain = [("handler", "=", "spreadsheet")]
        if name_filter:
            domain.append(("name", "ilike", name_filter))

        try:
            doc_ids = Doc.search(domain, limit=limit)
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error listing spreadsheets. The Documents app may not be "
                f"installed on this Odoo instance. Details: {e}"
            ))]

        if not doc_ids:
            return [TextContent(type="text", text="No spreadsheets found.")]

        docs = self.safe_read_records(SPREADSHEET_MODEL, doc_ids, ["id", "name", "folder_id", "create_date", "write_date"])

        lines = ["# Spreadsheets\n"]
        for doc in docs:
            folder = doc.get("folder_id")
            folder_str = folder[1] if folder else "No folder"
            lines.append(
                f"## {doc['name']} (ID: {doc['id']})\n"
                f"- Folder: {folder_str}\n"
                f"- Created: {doc.get('create_date', 'Unknown')}\n"
                f"- Last Updated: {doc.get('write_date', 'Unknown')}\n"
            )

        return [TextContent(type="text", text="\n".join(lines))]

    async def get_spreadsheet(self, arguments: dict) -> list[TextContent]:
        """Get a spreadsheet's metadata and a summary of its content."""
        spreadsheet_id = arguments.get("spreadsheet_id")
        include_data = arguments.get("include_data", False)

        if not spreadsheet_id:
            return [TextContent(type="text", text="Error: spreadsheet_id is required")]

        Doc = self.odoo.env[SPREADSHEET_MODEL]

        try:
            doc = self.safe_read_records(
                SPREADSHEET_MODEL,
                spreadsheet_id,
                ["id", "name", "handler", "folder_id", "spreadsheet_data",
                 "create_date", "write_date"],
            )[0]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Spreadsheet {spreadsheet_id} not found. {e}")]

        folder = doc.get("folder_id")
        folder_str = folder[1] if folder else "No folder"

        # Summarize the o-spreadsheet payload.
        raw = doc.get("spreadsheet_data") or ""
        summary_lines = []
        if raw:
            try:
                data = json.loads(raw)
                sheets = data.get("sheets", [])
                summary_lines.append(f"- Sheets: {len(sheets)}")
                for sheet in sheets:
                    n_cells = len(sheet.get("cells", {}))
                    n_figs = len(sheet.get("figures", []))
                    summary_lines.append(
                        f"  - {sheet.get('name', 'Sheet')}: {n_cells} cells, {n_figs} figure(s)"
                    )
            except (ValueError, TypeError):
                summary_lines.append("- Content: (unable to parse spreadsheet data)")
        else:
            summary_lines.append("- Content: (empty)")

        output = (
            f"# Spreadsheet: {doc['name']}\n\n"
            f"**ID:** {doc['id']}\n\n"
            f"**Folder:** {folder_str}\n\n"
            f"**Created:** {doc.get('create_date', 'Unknown')}\n\n"
            f"**Last Updated:** {doc.get('write_date', 'Unknown')}\n\n"
            + "\n".join(summary_lines)
            + "\n"
        )

        if include_data and raw:
            output += f"\n**Raw spreadsheet_data:**\n```json\n{raw}\n```\n"

        return [TextContent(type="text", text=output)]

    async def create_spreadsheet(self, arguments: dict) -> list[TextContent]:
        """Create a new spreadsheet in the Documents app."""
        name = arguments.get("name")
        folder = arguments.get("folder")
        data_json = arguments.get("data_json")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        Doc = self.odoo.env[SPREADSHEET_MODEL]

        folder_id = self._resolve_folder_id(folder)
        if not folder_id:
            return [TextContent(type="text", text=(
                "Error: Could not resolve a Documents folder/workspace. "
                "Pass 'folder' with the name or numeric ID of an existing "
                "Documents folder to create the spreadsheet in."
            ))]

        # Determine the o-spreadsheet payload.
        if data_json:
            if isinstance(data_json, (dict, list)):
                spreadsheet_data = su.dumps(data_json)
            else:
                # Validate it is JSON; store as-is.
                try:
                    json.loads(data_json)
                except ValueError as e:
                    return [TextContent(type="text", text=f"Error: data_json is not valid JSON. {e}")]
                spreadsheet_data = data_json
        else:
            spreadsheet_data = su.dumps(su.empty_spreadsheet(name[:31] or "Sheet1"))

        values = {
            "name": name,
            "handler": "spreadsheet",
            "folder_id": folder_id,
            "spreadsheet_data": spreadsheet_data,
        }

        try:
            doc_id = Doc.create(values)
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating spreadsheet: {e}")]

        output = (
            f"# Spreadsheet Created\n\n"
            f"**ID:** {doc_id}\n\n"
            f"**Name:** {name}\n\n"
            f"**Folder ID:** {folder_id}\n"
        )
        return [TextContent(type="text", text=output)]

    async def update_spreadsheet(self, arguments: dict) -> list[TextContent]:
        """Update a spreadsheet's name and/or content."""
        spreadsheet_id = arguments.get("spreadsheet_id")
        name = arguments.get("name")
        data_json = arguments.get("data_json")

        if not spreadsheet_id:
            return [TextContent(type="text", text="Error: spreadsheet_id is required")]

        values = {}
        if name:
            values["name"] = name

        if data_json is not None:
            if isinstance(data_json, (dict, list)):
                values["spreadsheet_data"] = su.dumps(data_json)
            else:
                try:
                    json.loads(data_json)
                except ValueError as e:
                    return [TextContent(type="text", text=f"Error: data_json is not valid JSON. {e}")]
                values["spreadsheet_data"] = data_json

        if not values:
            return [TextContent(type="text", text="Error: Nothing to update (provide name and/or data_json)")]

        Doc = self.odoo.env[SPREADSHEET_MODEL]
        try:
            Doc.write(spreadsheet_id, values)
        except Exception as e:
            return [TextContent(type="text", text=f"Error updating spreadsheet: {e}")]

        return [TextContent(type="text", text=(
            f"# Spreadsheet Updated\n\n**ID:** {spreadsheet_id}\n\n"
            f"**Fields updated:** {', '.join(values.keys())}\n"
        ))]

    async def delete_spreadsheet(self, arguments: dict) -> list[TextContent]:
        """Delete a spreadsheet."""
        spreadsheet_id = arguments.get("spreadsheet_id")

        if not spreadsheet_id:
            return [TextContent(type="text", text="Error: spreadsheet_id is required")]

        Doc = self.odoo.env[SPREADSHEET_MODEL]

        try:
            doc = Doc.read(spreadsheet_id, ["name"])[0]
            doc_name = doc["name"]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Spreadsheet {spreadsheet_id} not found. {e}")]

        try:
            Doc.unlink(spreadsheet_id)
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting spreadsheet: {e}")]

        return [TextContent(type="text", text=(
            f"# Spreadsheet Deleted\n\nSpreadsheet **{doc_name}** (ID: {spreadsheet_id}) has been deleted."
        ))]
