"""Base class for Odoo MCP handlers."""

import os
import logging
import odoorpc
from mcp.types import TextContent

logger = logging.getLogger("odoo-mcp")


class OdooBase:
    """Base class with shared Odoo connection logic."""

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
