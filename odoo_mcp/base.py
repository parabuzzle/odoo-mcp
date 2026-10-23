"""Base class for Odoo MCP handlers."""

import logging
import odoorpc
from mcp.types import TextContent
from urllib.parse import urlsplit
from .config import setting
from .connection import CompanyOdoo

logger = logging.getLogger("odoo-mcp")


class OdooBase:
    """Base class with shared Odoo connection logic."""

    def __init__(self):
        """Initialize with no connection."""
        self.odoo = None
        self._fields_cache = {}

    def connect_odoo(self):
        """Connect to Odoo instance."""
        odoo_url = setting("ODOO_URL")
        odoo_db = setting("ODOO_DB")
        odoo_username = setting("ODOO_USERNAME")
        odoo_api_key = setting("ODOO_API_KEY")

        if not all([odoo_url, odoo_db, odoo_username, odoo_api_key]):
            raise ValueError(
                "Missing required environment variables. "
                "Please set ODOO_URL, ODOO_DB, ODOO_USERNAME, and ODOO_API_KEY"
            )

        parsed = urlsplit(odoo_url if "://" in odoo_url else f"https://{odoo_url}")
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
            raise ValueError("ODOO_URL must identify an HTTPS Odoo origin")
        logger.info("Connecting to Odoo")

        # Create Odoo connection
        company_id = int(setting("ODOO_COMPANY_ID", "1"))
        if company_id <= 0:
            raise ValueError("ODOO_COMPANY_ID must be a positive integer")
        connection_type = CompanyOdoo
        if getattr(self, "remote_limits", False):
            from .remote import RemoteOdoo
            connection_type = RemoteOdoo
        connection = connection_type(parsed.hostname, protocol="jsonrpc+ssl", port=parsed.port or 443, timeout=30)
        connection.company_id = company_id

        # Login with API key
        connection.login(odoo_db, odoo_username, odoo_api_key)
        connection.env.context.update(allowed_company_ids=[company_id],
                                      company_id=company_id, force_company=company_id)
        self.odoo = connection

        logger.info("Connected to Odoo")

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
        cache = self._fields_cache
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
