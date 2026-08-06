"""Manufacturing read tools for Odoo MCP.

Read-only access to products, bills of materials, on-hand stock, and stock
locations so callers (e.g. a clear-to-build spreadsheet generator) can pull
BoM structures and stock levels directly instead of driving a browser
session against ``/web/dataset/call_kw``.

Deliberately scoped: no generic ``read_records(model, domain, fields)``
passthrough, and no writes to product/BoM/stock/location models. All calls
execute as the authenticated user, so Odoo record rules apply.

Archived-record handling: Odoo's ``search`` silently excludes ``active=False``
records unless the domain mentions ``active`` explicitly (equivalent to
``context={'active_test': False}``). Archived components can still sit on
active BoM lines, so these tools surface them on request. ``read`` by id is
not filtered by ``active`` and always sees archived records.

Requires the Manufacturing app (``mrp.bom``) for ``get_boms``/``has_bom`` and
the Inventory app (``stock.quant``, ``stock.location``) for stock tools.
"""

import json
import logging

from mcp.types import TextContent

from .base import OdooBase

logger = logging.getLogger("odoo-mcp")

# Domain term that disables Odoo's implicit active=True filter on search().
_INCLUDE_ARCHIVED = ("active", "in", [True, False])


def _json_block(payload) -> str:
    """Render structured rows as a fenced JSON block for machine consumption."""
    return "```json\n" + json.dumps(payload, indent=2) + "\n```\n"


def _m2o_id(value):
    """Return the id of a many2one read value ([id, name] or False)."""
    return value[0] if value else None


def _m2o_name(value):
    """Return the display name of a many2one read value ([id, name] or False)."""
    return value[1] if value else None


def _clean(value):
    """Map Odoo's False-for-unset scalars to None for JSON output."""
    return None if value is False else value


class ManufacturingHandler(OdooBase):
    """Handler for read-only manufacturing/inventory data access."""

    def __init__(self):
        super().__init__()
        self._field_cache = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _has_field(self, model: str, field: str) -> bool:
        key = (model, field)
        if key not in self._field_cache:
            try:
                self._field_cache[key] = field in self.odoo.env[model].fields_get([field])
            except Exception:
                self._field_cache[key] = False
        return self._field_cache[key]

    def _read_products(self, product_ids: list[int]) -> list[dict]:
        """Read product identity fields, deriving is_storable on older Odoo.

        Odoo 18 uses type='consu' plus a boolean ``is_storable``; Odoo 17 and
        earlier encode storability as type='product'. Both are load-bearing
        for CTB math (non-storable products have no quants and are treated as
        always available), so both are returned, deriving is_storable when
        the field doesn't exist.
        """
        if not product_ids:
            return []
        Product = self.odoo.env["product.product"]
        fields = ["id", "default_code", "name", "product_tmpl_id", "active", "type"]
        native_storable = self._has_field("product.product", "is_storable")
        if native_storable:
            fields.append("is_storable")
        records = Product.read(product_ids, fields)
        for rec in records:
            if not native_storable:
                rec["is_storable"] = rec.get("type") == "product"
        return records

    def _bom_map_for_templates(self, tmpl_ids: list[int]):
        """Return (template_level, variant_level) BoM ownership sets.

        template_level: template ids with at least one template-wide BoM
        (applies to all variants). variant_level: product.product ids that a
        variant-bound BoM targets.
        """
        template_level, variant_level = set(), set()
        if not tmpl_ids:
            return template_level, variant_level
        Bom = self.odoo.env["mrp.bom"]
        bom_ids = Bom.search([("product_tmpl_id", "in", tmpl_ids)])
        if bom_ids:
            for bom in self.safe_read_records("mrp.bom", bom_ids, ["product_tmpl_id", "product_id"]):
                if bom.get("product_id"):
                    variant_level.add(bom["product_id"][0])
                else:
                    template_level.add(bom["product_tmpl_id"][0])
        return template_level, variant_level

    # ------------------------------------------------------------------
    # Tool 1: list_products
    # ------------------------------------------------------------------
    async def list_products(self, arguments: dict) -> list[TextContent]:
        """Enumerate products by internal-reference prefix or explicit ids."""
        code_prefix = arguments.get("code_prefix")
        ids = arguments.get("ids")
        include_archived = arguments.get("include_archived", False)
        limit = arguments.get("limit", 200)

        if bool(code_prefix) == bool(ids):
            return [TextContent(type="text", text=(
                "Error: provide exactly one of code_prefix or ids"
            ))]

        Product = self.odoo.env["product.product"]
        domain = []
        if code_prefix:
            domain.append(("default_code", "=like", f"{code_prefix}%"))
        else:
            domain.append(("id", "in", list(ids)))
        if include_archived:
            domain.append(_INCLUDE_ARCHIVED)

        product_ids = Product.search(domain, limit=limit, order="default_code")
        records = self._read_products(product_ids)

        bom_note = None
        try:
            tmpl_ids = list({rec["product_tmpl_id"][0] for rec in records})
            template_level, variant_level = self._bom_map_for_templates(tmpl_ids)
        except Exception as e:
            template_level, variant_level = set(), set()
            bom_note = (
                "Warning: could not read mrp.bom (Manufacturing app may not be "
                f"installed); has_bom is null. Details: {e}"
            )

        rows = []
        for rec in records:
            tmpl_id = _m2o_id(rec.get("product_tmpl_id"))
            has_bom = (
                None if bom_note
                else (tmpl_id in template_level or rec["id"] in variant_level)
            )
            rows.append({
                "id": rec["id"],
                "default_code": _clean(rec.get("default_code")),
                "name": rec.get("name"),
                "product_tmpl_id": tmpl_id,
                "active": rec.get("active", True),
                "type": rec.get("type"),
                "is_storable": rec.get("is_storable"),
                "has_bom": has_bom,
            })

        header = f"# Products ({len(rows)})\n\n"
        if bom_note:
            header += bom_note + "\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 2: get_boms
    # ------------------------------------------------------------------
    async def get_boms(self, arguments: dict) -> list[TextContent]:
        """Return complete BoM structures with lines resolved to components."""
        product_ids = arguments.get("product_ids")
        code_prefix = arguments.get("code_prefix")
        include_archived_components = arguments.get("include_archived_components", True)

        if bool(product_ids) == bool(code_prefix):
            return [TextContent(type="text", text=(
                "Error: provide exactly one of product_ids or code_prefix"
            ))]

        Product = self.odoo.env["product.product"]
        if code_prefix:
            product_ids = Product.search([
                ("default_code", "=like", f"{code_prefix}%"),
                _INCLUDE_ARCHIVED,
            ])
        else:
            product_ids = list(product_ids)

        if not product_ids:
            return [TextContent(type="text", text=(
                "# BoMs (0)\n\nNo products matched.\n\n" + _json_block([])
            ))]

        products = self.safe_read_records("product.product", product_ids, ["id", "default_code", "product_tmpl_id"])
        requested = {p["id"] for p in products}
        tmpl_ids = list({p["product_tmpl_id"][0] for p in products})
        tmpl_code = {}
        for p in products:
            # Any variant's code works as a template fallback; single-variant
            # templates share the variant's default_code anyway.
            tmpl_code.setdefault(p["product_tmpl_id"][0], _clean(p.get("default_code")))

        Bom = self.odoo.env["mrp.bom"]
        try:
            bom_ids = Bom.search([("product_tmpl_id", "in", tmpl_ids)])
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching mrp.bom. The Manufacturing app may not be "
                f"installed on this Odoo instance. Details: {e}"
            ))]

        boms = self.safe_read_records(
            "mrp.bom", bom_ids, ["id", "product_tmpl_id", "product_id", "product_qty", "type", "bom_line_ids"]
        ) if bom_ids else []
        # A variant-bound BoM only applies to that variant; keep it only when
        # the bound variant was requested. Template-level BoMs cover all
        # requested variants of the template.
        boms = [
            b for b in boms
            if not b.get("product_id") or b["product_id"][0] in requested
        ]

        # Resolve product_code for variant-bound BoMs (the variant may be
        # archived or outside the requested set's read above).
        variant_ids = list({b["product_id"][0] for b in boms if b.get("product_id")})
        variant_code = {}
        if variant_ids:
            for v in self.safe_read_records("product.product", variant_ids, ["id", "default_code"]):
                variant_code[v["id"]] = _clean(v.get("default_code"))

        # Batch-read all lines, then all components (read by id sees archived
        # components, so they appear with active=false instead of vanishing).
        line_ids = [lid for b in boms for lid in b.get("bom_line_ids", [])]
        BomLine = self.odoo.env["mrp.bom.line"]
        lines_by_bom = {}
        component_ids = set()
        if line_ids:
            for line in self.safe_read_records("mrp.bom.line", line_ids, ["id", "bom_id", "product_id", "product_qty", "product_uom_id"]):
                lines_by_bom.setdefault(_m2o_id(line["bom_id"]), []).append(line)
                component_ids.add(_m2o_id(line["product_id"]))
        components = {c["id"]: c for c in self._read_products(list(component_ids))}

        rows = []
        total_lines = 0
        for b in boms:
            out_lines = []
            for line in lines_by_bom.get(b["id"], []):
                comp = components.get(_m2o_id(line["product_id"]), {})
                if not include_archived_components and not comp.get("active", True):
                    continue
                out_lines.append({
                    "component_id": _m2o_id(line["product_id"]),
                    "default_code": _clean(comp.get("default_code")),
                    "name": comp.get("name"),
                    "qty": line.get("product_qty"),
                    "uom": _m2o_name(line.get("product_uom_id")),
                    "active": comp.get("active", True),
                    "is_storable": comp.get("is_storable"),
                })
            total_lines += len(out_lines)
            variant_id = _m2o_id(b.get("product_id"))
            rows.append({
                "id": b["id"],
                "product_tmpl_id": _m2o_id(b["product_tmpl_id"]),
                "product_id": variant_id,
                "product_code": (
                    variant_code.get(variant_id) if variant_id
                    else tmpl_code.get(_m2o_id(b["product_tmpl_id"]))
                ),
                "product_qty": b.get("product_qty"),
                "type": b.get("type"),
                "lines": out_lines,
            })

        header = f"# BoMs ({len(rows)}, {total_lines} lines)\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 3: get_stock
    # ------------------------------------------------------------------
    async def get_stock(self, arguments: dict) -> list[TextContent]:
        """On-hand quantity/value aggregates for a product set."""
        product_ids = arguments.get("product_ids")
        group_by = arguments.get("group_by", "product")
        exclude_location_ids = arguments.get("exclude_location_ids")
        include_location_ids = arguments.get("include_location_ids")
        usage = arguments.get("usage", "internal")

        if not product_ids:
            return [TextContent(type="text", text="Error: product_ids is required")]
        if group_by not in ("product", "product_location"):
            return [TextContent(type="text", text=(
                "Error: group_by must be 'product' or 'product_location'"
            ))]
        if exclude_location_ids and include_location_ids:
            return [TextContent(type="text", text=(
                "Error: exclude_location_ids and include_location_ids are mutually exclusive"
            ))]

        domain = [("product_id", "in", list(product_ids))]
        if usage:
            domain.append(("location_id.usage", "=", usage))
        if include_location_ids:
            domain.append(("location_id", "in", list(include_location_ids)))
        elif exclude_location_ids:
            domain.append(("location_id", "not in", list(exclude_location_ids)))

        groupby = ["product_id"] if group_by == "product" else ["product_id", "location_id"]

        Quant = self.odoo.env["stock.quant"]
        have_value = True
        try:
            groups = Quant.read_group(domain, ["quantity:sum", "value:sum"], groupby, lazy=False)
        except Exception:
            have_value = False
            try:
                groups = Quant.read_group(domain, ["quantity:sum"], groupby, lazy=False)
            except Exception as e:
                return [TextContent(type="text", text=(
                    "Error aggregating stock.quant. The Inventory app may not "
                    f"be installed on this Odoo instance. Details: {e}"
                ))]

        # Resolve default_code (and standard_price when the instance has no
        # quant value field) for the products that actually have quants.
        seen_product_ids = list({_m2o_id(g["product_id"]) for g in groups if g.get("product_id")})
        code_map, cost_map = {}, {}
        if seen_product_ids:
            Product = self.odoo.env["product.product"]
            pfields = ["id", "default_code"] + ([] if have_value else ["standard_price"])
            for p in Product.read(seen_product_ids, pfields):
                code_map[p["id"]] = _clean(p.get("default_code"))
                if not have_value:
                    cost_map[p["id"]] = p.get("standard_price") or 0.0

        # complete_name reads better than display_name for nested locations.
        loc_name = {}
        if group_by == "product_location":
            loc_ids = list({_m2o_id(g["location_id"]) for g in groups if g.get("location_id")})
            if loc_ids:
                Location = self.odoo.env["stock.location"]
                for loc in self.safe_read_records("stock.location", loc_ids, ["id", "complete_name"]):
                    loc_name[loc["id"]] = loc.get("complete_name")

        rows = []
        for g in groups:
            pid = _m2o_id(g.get("product_id"))
            qty = g.get("quantity") or 0.0
            if have_value:
                value = g.get("value") or 0.0
            else:
                value = qty * cost_map.get(pid, 0.0)
            row = {
                "product_id": pid,
                "default_code": code_map.get(pid),
                "quantity": round(qty, 4),
                "value": round(value, 2),
            }
            if group_by == "product_location":
                lid = _m2o_id(g.get("location_id"))
                row["location_id"] = lid
                row["location_name"] = loc_name.get(lid) or _m2o_name(g.get("location_id"))
            rows.append(row)

        rows.sort(key=lambda r: (r["default_code"] or "", r.get("location_id") or 0))
        header = f"# Stock ({len(rows)} rows)\n\n"
        if not have_value:
            header += ("Note: stock.quant has no 'value' field on this instance; "
                       "value = quantity x standard_price.\n\n")
        if not rows:
            header += "No quants matched (absence means zero on hand).\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 4: list_locations
    # ------------------------------------------------------------------
    async def list_locations(self, arguments: dict) -> list[TextContent]:
        """Enumerate stock locations so callers stop hardcoding ids."""
        usage = arguments.get("usage")
        include_archived = arguments.get("include_archived", False)

        Location = self.odoo.env["stock.location"]
        domain = []
        if usage:
            domain.append(("usage", "=", usage))
        if include_archived:
            domain.append(_INCLUDE_ARCHIVED)

        try:
            location_ids = Location.search(domain, order="complete_name")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error listing stock.location. The Inventory app may not be "
                f"installed on this Odoo instance. Details: {e}"
            ))]

        rows = []
        if location_ids:
            for loc in self.safe_read_records("stock.location", location_ids, ["id", "complete_name", "usage", "active"]):
                rows.append({
                    "id": loc["id"],
                    "complete_name": loc.get("complete_name"),
                    "usage": loc.get("usage"),
                    "active": loc.get("active", True),
                })

        header = f"# Stock Locations ({len(rows)})\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]
