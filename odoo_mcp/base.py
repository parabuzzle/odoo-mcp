"""Base class for Odoo MCP handlers."""

import os
import logging
import odoorpc
from mcp.types import TextContent

logger = logging.getLogger("odoo-mcp")


class OdooBase:
    """Base class with shared Odoo connection logic."""

    # Per-model schema cache (fields_get results), shared across ALL handler
    # instances because they all talk to the same Odoo connection. This keeps
    # the cost of the defensive schema layer at one fields_get RPC per model for
    # the whole process lifetime, not one per tool call.
    _fields_cache: dict = {}

    def __init__(self):
        """Initialize with no connection."""
        self.odoo = None

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

    # ------------------------------------------------------------------
    # Defensive schema layer
    #
    # Odoo removes/renames model fields between major versions (e.g. the 18->19
    # upgrade dropped res.partner.mobile, helpdesk.ticket.ticket_type_id and
    # project.task.kanban_state). Hardcoded field lists in read()/write() calls
    # 500 the moment a referenced field disappears. These helpers intersect the
    # requested fields against the live schema so a missing field degrades to a
    # warning instead of crashing the tool.
    # ------------------------------------------------------------------

    def get_model_fields(self, model_name: str) -> dict:
        """Return the cached fields_get() dict for a model.

        One fields_get RPC per model for the process lifetime. On failure the
        result is cached as an empty dict, which makes the filtering helpers
        "fail open" (they don't drop anything) so we never make things worse
        than the un-hardened behaviour.
        """
        cache = OdooBase._fields_cache
        if model_name not in cache:
            try:
                Model = self.odoo.env[model_name]
                cache[model_name] = Model.fields_get(
                    [], attributes=["type", "string", "selection"]
                )
            except Exception as e:  # pragma: no cover - network/permission edge
                logger.warning(f"fields_get failed for {model_name}: {e}")
                cache[model_name] = {}
        return cache[model_name]

    def split_fields(self, model_name: str, requested: list) -> tuple:
        """Split requested fields into (kept, dropped) against the live schema.

        If the schema is unknown (fields_get failed), nothing is dropped.
        """
        schema = self.get_model_fields(model_name)
        if not schema:
            return list(requested), []
        kept = [f for f in requested if f in schema]
        dropped = [f for f in requested if f not in schema]
        return kept, dropped

    def _dropped_warnings(self, model_name: str, dropped: list) -> list:
        return [
            f"field '{f}' not present on {model_name}, omitted" for f in dropped
        ]

    def safe_read(self, model_name: str, ids, fields: list) -> tuple:
        """read() with the field list intersected against the live schema.

        Returns (records, warnings). Never raises because a requested field is
        missing from this Odoo version.
        """
        kept, dropped = self.split_fields(model_name, fields)
        Model = self.odoo.env[model_name]
        records = Model.read(ids, kept)
        return records, self._dropped_warnings(model_name, dropped)

    def safe_read_records(self, model_name: str, ids, fields: list) -> list:
        """Drop-in replacement for Model.read() that never crashes on a missing field.

        Same signature/return shape as read() (a list of dicts), so it can replace
        a `Model.read(ids, fields)` call verbatim. Fields absent from the live
        schema are dropped and logged (rather than surfaced in the tool response).
        Used by read tools whose output isn't structured to carry a warnings
        section; the affected-model tools use safe_read() to surface warnings inline.
        """
        records, warnings = self.safe_read(model_name, ids, fields)
        for w in warnings:
            logger.warning(f"{model_name}: {w}")
        return records

    def invalid_write_fields(self, model_name: str, values: dict) -> list:
        """Return payload keys that don't exist on the model (empty if schema unknown)."""
        schema = self.get_model_fields(model_name)
        if not schema:
            return []
        return [k for k in values if k not in schema]

    def field_selection(self, model_name: str, field_name: str) -> list:
        """Return the [(value, label), ...] selection for a field, or []."""
        schema = self.get_model_fields(model_name)
        info = schema.get(field_name) or {}
        return info.get("selection") or []

    @staticmethod
    def warnings_section(warnings: list) -> str:
        """Render dropped-field warnings as a trailing markdown section."""
        if not warnings:
            return ""
        lines = ["\n\n## Warnings\n"]
        lines.extend(f"- {w}" for w in warnings)
        return "\n".join(lines)

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
