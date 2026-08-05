#!/usr/bin/env python3
"""Read-only smoke test for the accounting tools against the live instance.

Calls every AccountingHandler tool directly (no MCP transport), parses the
fenced JSON block each returns, and checks shapes plus two invariants:
the double-entry invariant (sum of balances over any date range ~ 0, since
all lines of a posted move share the move date) and per-partner aging
bucket sums matching partner totals. Writes nothing — no teardown needed.

Run: python test_accounting.py
"""
import asyncio
import json
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from odoo_mcp.accounting import AccountingHandler


def parse(r):
    """Return (full text, parsed payload) from a tool result."""
    text = r[0].text
    payload = json.loads(text.split("```json\n")[1].split("\n```")[0])
    return text, payload


async def main():
    failures = []

    def check(label, ok, detail=""):
        print(f"{label}: {'OK' if ok else 'FAILED'}{' - ' + detail if detail else ''}")
        if not ok:
            failures.append(label)

    h = AccountingHandler()
    h.connect_odoo()

    # 1) Journals — any instance with Invoicing has at least one.
    r = await h.list_journals({})
    if "may not be installed" in r[0].text:
        print("SKIP: Accounting/Invoicing app not available on this instance.")
        print(r[0].text)
        sys.exit(1)
    text, journals = parse(r)
    check("list_journals", text.startswith("# Journals") and len(journals) >= 1,
          f"{len(journals)} journals")

    # 2) Chart of accounts.
    text, accounts = parse(await h.list_accounts({}))
    check("list_accounts", len(accounts) >= 1
          and all("code" in a and "account_type" in a for a in accounts),
          f"{len(accounts)} accounts")

    # 3) Taxes.
    text, taxes = parse(await h.list_taxes({}))
    check("list_taxes", all("amount" in t and "type_tax_use" in t for t in taxes),
          f"{len(taxes)} taxes")

    # 4) Invoices (all kinds/states so even a quiet instance returns rows).
    text, invoices = parse(await h.list_invoices({"kind": "all", "state": "all", "limit": 5}))
    kinds = {"customer_invoice", "vendor_bill", "customer_credit_note", "vendor_credit_note"}
    check("list_invoices", all(
        i["kind"] in kinds and "amount_total" in i and "amount_total_signed" in i
        for i in invoices), f"{len(invoices)} documents")

    # 5) Invoice detail on the first result.
    if invoices:
        text, inv = parse(await h.get_invoice({"invoice_id": invoices[0]["id"]}))
        check("get_invoice", isinstance(inv, dict) and isinstance(inv.get("lines"), list)
              and all("price_subtotal" in l for l in inv["lines"]),
              f"id {inv.get('id')}, {len(inv.get('lines', []))} lines")
    else:
        print("get_invoice: skipped (no invoices on instance)")

    # 6) Payments — memo key proves the ref/memo probe shaped the output.
    text, payments = parse(await h.list_payments({"limit": 5}))
    check("list_payments", all("memo" in p and "amount" in p for p in payments),
          f"{len(payments)} payments")

    # 7) Account balances: double-entry invariant, then grouping variants.
    today = date.today().isoformat()
    ytd = {"date_from": f"{date.today().year}-01-01", "date_to": today}
    text, balances = parse(await h.get_account_balances({**ytd, "group_by": "account"}))
    total = sum(row["balance"] for row in balances)
    check("get_account_balances invariant", abs(total) < 0.05,
          f"{len(balances)} accounts, sum(balance)={total:.4f}")
    text, by_type = parse(await h.get_account_balances({**ytd, "group_by": "account_type"}))
    check("get_account_balances by type", all("account_type" in row for row in by_type),
          f"{len(by_type)} types")
    text, pnl = parse(await h.get_account_balances(
        {**ytd, "account_types": ["income", "expense"]}))
    check("get_account_balances P&L filter", all(
        row["account_type"] in ("income", "income_other", "expense",
                                "expense_direct_cost", "expense_depreciation")
        for row in pnl if row["account_type"]), f"{len(pnl)} P&L accounts")

    # 8) Aged balances, both sides: bucket sums must equal partner totals.
    buckets = ["not_due", "days_1_30", "days_31_60", "days_61_90", "days_90_plus"]
    for side in ("receivable", "payable"):
        text, aged = parse(await h.get_aged_balances({"side": side}))
        ok = "totals" in aged and "partners" in aged and all(
            abs(sum(p[b] for b in buckets) - p["total"]) < 0.05
            for p in aged["partners"])
        check(f"get_aged_balances {side}", ok,
              f"{len(aged.get('partners', []))} partners, total={aged['totals']['total']}")

    # 9) Raw journal items: shape, then two filter invariants.
    text, items = parse(await h.list_journal_items({"limit": 5}))
    check("list_journal_items", all(
        "debit" in i and "credit" in i and "matching_number" in i and "move" in i
        for i in items), f"{len(items)} lines")
    if items:
        # All lines of one move must balance to ~0 (double entry per move).
        text, move_lines = parse(await h.list_journal_items({"move_id": items[0]["move_id"]}))
        total = sum(l["balance"] for l in move_lines)
        check("list_journal_items move balance", abs(total) < 0.05,
              f"move {items[0]['move']}: {len(move_lines)} lines, sum={total:.4f}")
        # Account filter returns only that account's lines.
        acct_id = items[0]["account_id"]
        text, acct_lines = parse(await h.list_journal_items({"account_id": acct_id, "limit": 20}))
        check("list_journal_items account filter",
              all(l["account_id"] == acct_id for l in acct_lines),
              f"{len(acct_lines)} lines on account {items[0]['account']}")
        code = next((a["code"] for a in accounts if a["id"] == acct_id), None)
        if code:
            text, code_lines = parse(await h.list_journal_items(
                {"account_code": code, "limit": 20}))
            check("list_journal_items code filter",
                  all(str(l["account"]).startswith(code) for l in code_lines),
                  f"{len(code_lines)} lines for code {code}")
    else:
        print("list_journal_items filters: skipped (no posted journal items)")

    # 10) Input validation returns Error: text without raising.
    for label, coro in [
        ("bad kind", h.list_invoices({"kind": "bogus"})),
        ("missing side", h.get_aged_balances({})),
        ("missing invoice_id", h.get_invoice({})),
        ("account_id + account_code", h.list_journal_items(
            {"account_id": 1, "account_code": "1"})),
    ]:
        r = await coro
        check(f"validation ({label})", r[0].text.startswith("Error:"), r[0].text[:60])

    if failures:
        print(f"\nFAILED: {failures}")
        sys.exit(1)
    print("\nAll accounting smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
