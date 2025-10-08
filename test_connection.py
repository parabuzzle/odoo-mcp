#!/usr/bin/env python3
"""Test Odoo connection."""

import os
import odoorpc
from dotenv import load_dotenv

load_dotenv()

odoo_url = os.getenv("ODOO_URL", "").replace("https://", "").replace("http://", "")
odoo_db = os.getenv("ODOO_DB")
odoo_username = os.getenv("ODOO_USERNAME")
odoo_api_key = os.getenv("ODOO_API_KEY")

print(f"Connecting to {odoo_url}...")
print(f"Database: {odoo_db}")
print(f"Username: {odoo_username}")

odoo = odoorpc.ODOO(odoo_url, protocol="jsonrpc+ssl", port=443)
odoo.login(odoo_db, odoo_username, odoo_api_key)

print(f"✓ Connected successfully as {odoo_username}")
print(f"✓ User ID: {odoo.env.uid}")

# Test listing projects
Project = odoo.env["project.project"]
project_ids = Project.search([], limit=5)
projects = Project.read(project_ids, ["name", "id"])

print(f"\nFound {len(projects)} projects:")
for project in projects:
    print(f"  - {project['name']} (ID: {project['id']})")
