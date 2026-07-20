"""Dashboards handler for Odoo MCP.

Manages spreadsheet dashboards from the Odoo Dashboards app:
- ``spreadsheet.dashboard.group`` -- sections that group dashboards
- ``spreadsheet.dashboard``       -- an individual dashboard (o-spreadsheet JSON
                                     stored in ``spreadsheet_data``)

Also provides a dedicated builder, ``create_inventory_dashboard``, that queries
live ``stock.quant`` data, aggregates on-hand quantity or value by
product/location/warehouse/category, and writes a self-contained data table +
chart into a new dashboard (or spreadsheet). Because the data is written as
plain values (a snapshot), the result is robust across Odoo versions; re-run
the tool to refresh it.

Requires the Dashboards app (``spreadsheet.dashboard``) and the Inventory app
(``stock.quant``) to be installed on the Odoo instance.
"""

import json
import logging

from mcp.types import TextContent

from .base import OdooBase
from . import spreadsheet_utils as su

logger = logging.getLogger("odoo-mcp")

DASHBOARD_MODEL = "spreadsheet.dashboard"
DASHBOARD_GROUP_MODEL = "spreadsheet.dashboard.group"

# group_by option -> (human label for the first column)
_GROUP_LABELS = {
    "product": "Product",
    "location": "Location",
    "warehouse": "Warehouse",
    "category": "Category",
}


class DashboardsHandler(OdooBase):
    """Handler for Odoo spreadsheet dashboard operations."""

    def __init__(self):
        super().__init__()
        # Set by the server so the inventory builder can also target a
        # Documents spreadsheet (reuses folder resolution + creation).
        self.spreadsheets = None

    # ------------------------------------------------------------------
    # Dashboard groups
    # ------------------------------------------------------------------
    def _resolve_group_id(self, group=None, create=True):
        """Resolve a spreadsheet.dashboard.group id from a name or id."""
        Group = self.odoo.env[DASHBOARD_GROUP_MODEL]

        if isinstance(group, int):
            return group
        if isinstance(group, str) and group.isdigit():
            return int(group)

        if group:  # name provided
            ids = Group.search([("name", "ilike", group)], limit=1)
            if ids:
                return ids[0]
            if create:
                return Group.create({"name": group})
            return None

        # No group given: use the first existing one, or create a default.
        ids = Group.search([], limit=1)
        if ids:
            return ids[0]
        if create:
            return Group.create({"name": "Dashboards"})
        return None

    async def list_dashboard_groups(self, arguments: dict) -> list[TextContent]:
        """List dashboard groups (sections)."""
        Group = self.odoo.env[DASHBOARD_GROUP_MODEL]

        try:
            ids = Group.search([], limit=arguments.get("limit", 50))
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error listing dashboard groups. The Dashboards app may not be "
                f"installed on this Odoo instance. Details: {e}"
            ))]

        if not ids:
            return [TextContent(type="text", text="No dashboard groups found.")]

        groups = Group.read(ids, ["id", "name", "sequence", "dashboard_ids"])
        lines = ["# Dashboard Groups\n"]
        for g in sorted(groups, key=lambda x: x.get("sequence", 0)):
            lines.append(
                f"## {g['name']} (ID: {g['id']})\n"
                f"- Dashboards: {len(g.get('dashboard_ids', []))}\n"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def create_dashboard_group(self, arguments: dict) -> list[TextContent]:
        """Create a new dashboard group (section)."""
        name = arguments.get("name")
        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        Group = self.odoo.env[DASHBOARD_GROUP_MODEL]
        try:
            group_id = Group.create({"name": name})
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating dashboard group: {e}")]

        return [TextContent(type="text", text=(
            f"# Dashboard Group Created\n\n**ID:** {group_id}\n\n**Name:** {name}\n"
        ))]

    # ------------------------------------------------------------------
    # Dashboards
    # ------------------------------------------------------------------
    async def list_dashboards(self, arguments: dict) -> list[TextContent]:
        """List dashboards, optionally filtered by group."""
        limit = arguments.get("limit", 50)
        group = arguments.get("group")

        Dashboard = self.odoo.env[DASHBOARD_MODEL]

        domain = []
        if group is not None:
            group_id = self._resolve_group_id(group, create=False)
            if not group_id:
                return [TextContent(type="text", text=f"No dashboard group matching '{group}' found.")]
            domain.append(("dashboard_group_id", "=", group_id))

        try:
            ids = Dashboard.search(domain, limit=limit)
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error listing dashboards. The Dashboards app may not be "
                f"installed on this Odoo instance. Details: {e}"
            ))]

        if not ids:
            return [TextContent(type="text", text="No dashboards found.")]

        dashboards = Dashboard.read(ids, ["id", "name", "dashboard_group_id", "sequence"])
        lines = ["# Dashboards\n"]
        for d in dashboards:
            grp = d.get("dashboard_group_id")
            grp_str = grp[1] if grp else "No group"
            lines.append(
                f"## {d['name']} (ID: {d['id']})\n"
                f"- Group: {grp_str}\n"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def get_dashboard(self, arguments: dict) -> list[TextContent]:
        """Get a dashboard's metadata and a summary of its content."""
        dashboard_id = arguments.get("dashboard_id")
        include_data = arguments.get("include_data", False)

        if not dashboard_id:
            return [TextContent(type="text", text="Error: dashboard_id is required")]

        Dashboard = self.odoo.env[DASHBOARD_MODEL]
        try:
            d = Dashboard.read(
                dashboard_id,
                ["id", "name", "dashboard_group_id", "spreadsheet_data"],
            )[0]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Dashboard {dashboard_id} not found. {e}")]

        grp = d.get("dashboard_group_id")
        grp_str = grp[1] if grp else "No group"

        raw = d.get("spreadsheet_data") or ""
        summary_lines = []
        if raw:
            try:
                data = json.loads(raw)
                sheets = data.get("sheets", [])
                summary_lines.append(f"- Sheets: {len(sheets)}")
                for sheet in sheets:
                    summary_lines.append(
                        f"  - {sheet.get('name', 'Sheet')}: "
                        f"{len(sheet.get('cells', {}))} cells, "
                        f"{len(sheet.get('figures', []))} figure(s)"
                    )
            except (ValueError, TypeError):
                summary_lines.append("- Content: (unable to parse spreadsheet data)")
        else:
            summary_lines.append("- Content: (empty)")

        output = (
            f"# Dashboard: {d['name']}\n\n"
            f"**ID:** {d['id']}\n\n"
            f"**Group:** {grp_str}\n\n"
            + "\n".join(summary_lines)
            + "\n"
        )
        if include_data and raw:
            output += f"\n**Raw spreadsheet_data:**\n```json\n{raw}\n```\n"

        return [TextContent(type="text", text=output)]

    async def create_dashboard(self, arguments: dict) -> list[TextContent]:
        """Create a new dashboard from raw o-spreadsheet JSON (or empty)."""
        name = arguments.get("name")
        group = arguments.get("group")
        data_json = arguments.get("data_json")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        group_id = self._resolve_group_id(group)
        if not group_id:
            return [TextContent(type="text", text="Error: Could not resolve or create a dashboard group.")]

        if data_json:
            if isinstance(data_json, (dict, list)):
                spreadsheet_data = su.dumps(data_json)
            else:
                try:
                    json.loads(data_json)
                except ValueError as e:
                    return [TextContent(type="text", text=f"Error: data_json is not valid JSON. {e}")]
                spreadsheet_data = data_json
        else:
            spreadsheet_data = su.dumps(su.empty_spreadsheet(name[:31] or "Sheet1"))

        Dashboard = self.odoo.env[DASHBOARD_MODEL]
        try:
            dashboard_id = Dashboard.create({
                "name": name,
                "dashboard_group_id": group_id,
                "spreadsheet_data": spreadsheet_data,
            })
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating dashboard: {e}")]

        return [TextContent(type="text", text=(
            f"# Dashboard Created\n\n**ID:** {dashboard_id}\n\n"
            f"**Name:** {name}\n\n**Group ID:** {group_id}\n"
        ))]

    async def update_dashboard(self, arguments: dict) -> list[TextContent]:
        """Update a dashboard's name, group, and/or content."""
        dashboard_id = arguments.get("dashboard_id")
        name = arguments.get("name")
        group = arguments.get("group")
        data_json = arguments.get("data_json")

        if not dashboard_id:
            return [TextContent(type="text", text="Error: dashboard_id is required")]

        values = {}
        if name:
            values["name"] = name
        if group is not None:
            group_id = self._resolve_group_id(group)
            if group_id:
                values["dashboard_group_id"] = group_id
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
            return [TextContent(type="text", text="Error: Nothing to update (provide name, group, and/or data_json)")]

        Dashboard = self.odoo.env[DASHBOARD_MODEL]
        try:
            Dashboard.write(dashboard_id, values)
        except Exception as e:
            return [TextContent(type="text", text=f"Error updating dashboard: {e}")]

        return [TextContent(type="text", text=(
            f"# Dashboard Updated\n\n**ID:** {dashboard_id}\n\n"
            f"**Fields updated:** {', '.join(values.keys())}\n"
        ))]

    async def delete_dashboard(self, arguments: dict) -> list[TextContent]:
        """Delete a dashboard."""
        dashboard_id = arguments.get("dashboard_id")
        if not dashboard_id:
            return [TextContent(type="text", text="Error: dashboard_id is required")]

        Dashboard = self.odoo.env[DASHBOARD_MODEL]
        try:
            d = Dashboard.read(dashboard_id, ["name"])[0]
            name = d["name"]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Dashboard {dashboard_id} not found. {e}")]

        try:
            Dashboard.unlink(dashboard_id)
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting dashboard: {e}")]

        return [TextContent(type="text", text=(
            f"# Dashboard Deleted\n\nDashboard **{name}** (ID: {dashboard_id}) has been deleted."
        ))]

    # ------------------------------------------------------------------
    # Inventory dashboard builder
    # ------------------------------------------------------------------
    def _aggregate_inventory(self, group_by, measure, scan_limit,
                             product_filter, location_filter):
        """Aggregate on-hand stock into a sorted list of (label, value) plus total.

        Returns (rows, total, note) where rows is a list of [label, value]
        sorted descending by value, total is the sum over ALL groups, and note
        is an optional warning string (e.g. when the scan was truncated).
        """
        Quant = self.odoo.env["stock.quant"]

        # On-hand = quantity physically in internal locations.
        domain = [("location_id.usage", "=", "internal")]
        if product_filter:
            domain.append(("product_id.name", "ilike", product_filter))
        if location_filter:
            domain.append(("location_id.complete_name", "ilike", location_filter))

        quant_ids = Quant.search(domain, limit=scan_limit)
        if not quant_ids:
            return [], 0.0, None

        note = None
        if len(quant_ids) >= scan_limit:
            note = (f"Only the first {scan_limit} stock records were scanned "
                    f"(scan_limit). Totals may be partial; raise scan_limit to include more.")

        read_fields = ["product_id", "location_id", "quantity"]
        have_value = False
        if measure == "value":
            try:
                if "value" in Quant.fields_get(["value"]):
                    read_fields.append("value")
                    have_value = True
            except Exception:
                have_value = False

        records = Quant.read(quant_ids, read_fields)

        # Build label maps for groupings not directly on the quant.
        loc_to_wh = {}
        prod_to_categ = {}
        prod_to_cost = {}

        if group_by == "warehouse":
            loc_ids = list({r["location_id"][0] for r in records if r.get("location_id")})
            if loc_ids:
                Location = self.odoo.env["stock.location"]
                for loc in Location.read(loc_ids, ["id", "warehouse_id"]):
                    wh = loc.get("warehouse_id")
                    loc_to_wh[loc["id"]] = tuple(wh) if wh else None

        if group_by == "category" or (measure == "value" and not have_value):
            prod_ids = list({r["product_id"][0] for r in records if r.get("product_id")})
            if prod_ids:
                Product = self.odoo.env["product.product"]
                pfields = ["id"]
                if group_by == "category":
                    pfields.append("categ_id")
                if measure == "value" and not have_value:
                    pfields.append("standard_price")
                for p in Product.read(prod_ids, pfields):
                    if "categ_id" in pfields:
                        categ = p.get("categ_id")
                        prod_to_categ[p["id"]] = tuple(categ) if categ else None
                    if "standard_price" in pfields:
                        prod_to_cost[p["id"]] = p.get("standard_price") or 0.0

        totals = {}
        for r in records:
            qty = r.get("quantity") or 0.0

            # Determine the measured amount for this quant.
            if measure == "value":
                if have_value:
                    amount = r.get("value") or 0.0
                else:
                    prod = r.get("product_id")
                    cost = prod_to_cost.get(prod[0], 0.0) if prod else 0.0
                    amount = qty * cost
            else:
                amount = qty

            # Determine the group key + label.
            if group_by == "location":
                key = tuple(r["location_id"]) if r.get("location_id") else ("none", "No location")
            elif group_by == "warehouse":
                wh = loc_to_wh.get(r["location_id"][0]) if r.get("location_id") else None
                key = wh if wh else ("none", "No warehouse")
            elif group_by == "category":
                categ = prod_to_categ.get(r["product_id"][0]) if r.get("product_id") else None
                key = categ if categ else ("none", "No category")
            else:  # product
                key = tuple(r["product_id"]) if r.get("product_id") else ("none", "No product")

            totals[key] = totals.get(key, 0.0) + amount

        grand_total = round(sum(totals.values()), 2)
        rows = sorted(
            ([label, round(val, 2)] for (_id, label), val in totals.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        return rows, grand_total, note

    async def create_inventory_dashboard(self, arguments: dict) -> list[TextContent]:
        """Build an inventory dashboard (snapshot) from live stock.quant data."""
        name = arguments.get("name", "Inventory Dashboard")
        group_by = arguments.get("group_by", "product")
        measure = arguments.get("measure", "quantity")
        limit = arguments.get("limit", 30)
        include_chart = arguments.get("include_chart", True)
        chart_type = arguments.get("chart_type", "bar")
        target = arguments.get("target", "dashboard")
        group = arguments.get("group")
        folder = arguments.get("folder")
        scan_limit = arguments.get("scan_limit", 5000)
        product_filter = arguments.get("product")
        location_filter = arguments.get("location")

        if group_by not in _GROUP_LABELS:
            return [TextContent(type="text", text=(
                f"Error: group_by must be one of {', '.join(_GROUP_LABELS)}."
            ))]
        if measure not in ("quantity", "value"):
            return [TextContent(type="text", text="Error: measure must be 'quantity' or 'value'.")]
        if chart_type not in ("bar", "line", "pie"):
            return [TextContent(type="text", text="Error: chart_type must be 'bar', 'line', or 'pie'.")]

        # Aggregate the data.
        try:
            rows, grand_total, note = self._aggregate_inventory(
                group_by, measure, scan_limit, product_filter, location_filter
            )
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error aggregating inventory data. The Inventory app "
                f"(stock.quant) may not be installed. Details: {e}"
            ))]

        if not rows:
            return [TextContent(type="text", text=(
                "No on-hand stock found for the given filters, so no dashboard was created."
            ))]

        measure_label = "On-hand Qty" if measure == "quantity" else "On-hand Value"
        group_label = _GROUP_LABELS[group_by]

        # Keep the top-N groups for the table/chart; note if truncated.
        truncated = len(rows) > limit
        display_rows = rows[:limit]

        headers = [group_label, measure_label]
        totals_row = ["TOTAL (all groups)", grand_total]

        data = su.build_table_spreadsheet(
            sheet_name="Inventory",
            headers=headers,
            rows=display_rows,
            title=name,
            totals_row=totals_row,
            chart_type=chart_type if include_chart else None,
            chart_title=f"{measure_label} by {group_label}",
            chart_label_col=0,
            chart_value_cols=[1],
        )
        spreadsheet_data = su.dumps(data)

        # Persist to the chosen target.
        if target == "spreadsheet":
            if not self.spreadsheets:
                return [TextContent(type="text", text=(
                    "Error: spreadsheet target is unavailable in this configuration."
                ))]
            result = await self.spreadsheets.create_spreadsheet({
                "name": name,
                "folder": folder,
                "data_json": spreadsheet_data,
            })
            location_desc = "Documents spreadsheet"
        else:
            group_id = self._resolve_group_id(group)
            if not group_id:
                return [TextContent(type="text", text="Error: Could not resolve or create a dashboard group.")]
            Dashboard = self.odoo.env[DASHBOARD_MODEL]
            try:
                dashboard_id = Dashboard.create({
                    "name": name,
                    "dashboard_group_id": group_id,
                    "spreadsheet_data": spreadsheet_data,
                })
            except Exception as e:
                return [TextContent(type="text", text=f"Error creating dashboard: {e}")]
            result = [TextContent(type="text", text=(
                f"# Inventory Dashboard Created\n\n**ID:** {dashboard_id}\n\n"
                f"**Name:** {name}\n\n**Group ID:** {group_id}\n"
            ))]
            location_desc = "dashboard"

        # Append a summary of what was built to the result text.
        summary = [
            f"\n---\n## Inventory snapshot ({location_desc})\n",
            f"- Grouped by: **{group_label}**",
            f"- Measure: **{measure_label}**",
            f"- Groups shown: **{len(display_rows)}**" + (f" of {len(rows)} (top {limit})" if truncated else ""),
            f"- Grand total ({measure_label}): **{grand_total}**",
            f"- Chart: {'yes (' + chart_type + ')' if include_chart else 'no'}",
        ]
        if note:
            summary.append(f"- ⚠️ {note}")
        summary.append("\n_This is a point-in-time snapshot. Re-run this tool to refresh the numbers._")

        result_text = result[0].text + "\n" + "\n".join(summary)
        return [TextContent(type="text", text=result_text)]
