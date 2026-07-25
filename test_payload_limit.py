#!/usr/bin/env python3
"""Regression test: round-trip a >=100 KB data_json through update_dashboard.

Verifies the server's request/response path handles large o-spreadsheet
payloads, both by calling the handler directly and through the real MCP
stdio transport (initialize -> tools/call). Creates a clearly-named test
dashboard on the live instance and deletes it (and its group) afterward.

Run: python test_payload_limit.py

Background: on 2026-07-25 a ~46 KB create_dashboard(data_json=...) call was
observed to abort mid-request. This test shows 120 KB round-trips byte-perfect
through the handler, the stdio transport, and Odoo itself — the abort was the
MCP *client* failing to emit the large tool-call arguments, not a limit in
this server. Keep large payload generation server-side (or retry client-side)
rather than hunting for a server limit.
"""
import asyncio
import json
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from odoo_mcp.dashboards import DashboardsHandler
from odoo_mcp import spreadsheet_utils as su

TEST_NAME = "MCP TEST payload limit - safe to delete"
TEST_GROUP = "MCP TEST group - safe to delete"
TARGET_BYTES = 120_000


def big_payload(target_bytes: int) -> str:
    """A valid o-spreadsheet doc padded with filler cells to >= target_bytes."""
    data = su.empty_spreadsheet("PayloadTest")
    cells = data["sheets"][0]["cells"]
    i = 0
    while len(json.dumps(data, separators=(",", ":"))) < target_bytes:
        cells[f"{chr(65 + i % 10)}{i // 10 + 1}"] = {"content": f"filler cell {i} " + "x" * 40}
        i += 1
    data["sheets"][0]["rowNumber"] = max(200, i // 10 + 10)
    return json.dumps(data, separators=(",", ":"))


def rpc(proc, msg):
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()


def read_response(proc, want_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == want_id:
            return msg
    raise RuntimeError(f"timeout waiting for response id={want_id}")


async def main():
    failures = []

    h = DashboardsHandler()
    h.connect_odoo()
    Dashboard = h.odoo.env["spreadsheet.dashboard"]

    payload = big_payload(TARGET_BYTES)
    print(f"payload bytes: {len(payload)}")

    r = await h.create_dashboard({"name": TEST_NAME, "group": TEST_GROUP})
    dash_id = int(r[0].text.split("**ID:** ")[1].split("\n")[0])
    print(f"created test dashboard {dash_id}")

    try:
        # 1) Handler-level round trip.
        r = await h.update_dashboard({"dashboard_id": dash_id, "data_json": payload})
        stored = Dashboard.read(dash_id, ["spreadsheet_data"])[0]["spreadsheet_data"]
        ok = "Updated" in r[0].text and stored == payload
        print(f"handler round-trip: {'OK' if ok else 'FAILED'} ({len(stored)} bytes)")
        if not ok:
            failures.append("handler round-trip")

        # 2) Same payload through the real MCP stdio transport.
        proc = subprocess.Popen(
            [sys.executable, "-m", "odoo_mcp.server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "payload-test", "version": "0"}}})
            read_response(proc, 1)
            rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            marker_payload = payload.replace("filler cell 0 ", "filler STDIO 0 ", 1)
            rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "update_dashboard",
                                  "arguments": {"dashboard_id": dash_id,
                                                "data_json": marker_payload}}})
            resp = read_response(proc, 2)
            stored = Dashboard.read(dash_id, ["spreadsheet_data"])[0]["spreadsheet_data"]
            ok = not resp["result"].get("isError") and stored == marker_payload
            print(f"stdio round-trip: {'OK' if ok else 'FAILED'} ({len(stored)} bytes)")
            if not ok:
                failures.append("stdio round-trip")

            # 3) Large tool RESULT: get_dashboard include_data returns the doc.
            rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "get_dashboard",
                                  "arguments": {"dashboard_id": dash_id, "include_data": True}}})
            resp = read_response(proc, 3)
            rtext = resp["result"]["content"][0]["text"]
            ok = len(rtext) >= TARGET_BYTES and marker_payload[:2000] in rtext
            print(f"stdio large response: {'OK' if ok else 'FAILED'} ({len(rtext)} bytes)")
            if not ok:
                failures.append("stdio large response")
        finally:
            proc.kill()
    finally:
        await h.delete_dashboard({"dashboard_id": dash_id})
        Group = h.odoo.env["spreadsheet.dashboard.group"]
        gids = Group.search([("name", "=", TEST_GROUP)])
        if gids:
            Group.unlink(gids)
        leftovers = Dashboard.search([("name", "ilike", "MCP TEST%")])
        print(f"cleanup done, leftover test dashboards: {leftovers}")
        if leftovers:
            failures.append("cleanup")

    if failures:
        print(f"FAILED: {failures}")
        sys.exit(1)
    print("All payload-limit checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
