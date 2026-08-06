"""Accounting read tools for Odoo MCP.

Read-only visibility into Odoo accounting: customer invoices, vendor bills
and credit notes (``account.move``), payments (``account.payment``),
account balances and aged receivables/payables (aggregated from
``account.move.line``), and reference data (chart of accounts, journals,
taxes).

Deliberately scoped: no writes to any accounting model, no generic
``read_records(model, domain, fields)`` passthrough, and no ``sudo()`` —
all calls execute as the authenticated user, so Odoo record rules apply.

Currency policy: invoice and payment rows carry document-currency amounts
plus a ``currency`` name, and company-currency ``*_signed`` variants for
cross-currency aggregation. Balance and aging tools are company-currency
only (``debit``/``credit``/``balance``/``amount_residual`` on
``account.move.line`` are company-currency fields). ``balance = debit -
credit``, so income accounts show negative (credit) balances; aged
payables are sign-flipped so amounts owed to vendors read positive.

Archived-record handling: Odoo's ``search`` silently excludes
``active=False`` records unless the domain mentions ``active`` explicitly
(equivalent to ``context={'active_test': False}``), so listing tools add
``("active", "in", [True, False])`` when archived records are requested.

Requires the Invoicing/Accounting app (``account.move``). Each tool wraps
its first Odoo call and returns a clear error if the app is unavailable.
"""

import json
import logging
from datetime import date

from mcp.types import TextContent

from .base import OdooBase

logger = logging.getLogger("odoo-mcp")

# Domain term that disables Odoo's implicit active=True filter on search().
_INCLUDE_ARCHIVED = ("active", "in", [True, False])

# Friendly document kinds <-> account.move.move_type. Journal entries
# (move_type='entry') are deliberately excluded from invoice tools.
_KIND_TO_MOVE_TYPE = {
    "customer_invoice": "out_invoice",
    "vendor_bill": "in_invoice",
    "customer_credit_note": "out_refund",
    "vendor_credit_note": "in_refund",
}
_MOVE_TYPE_TO_KIND = {v: k for k, v in _KIND_TO_MOVE_TYPE.items()}
_DOC_MOVE_TYPES = list(_KIND_TO_MOVE_TYPE.values())

_AGED_ACCOUNT_TYPE = {
    "receivable": "asset_receivable",
    "payable": "liability_payable",
}

_MOVE_HEADER_FIELDS = [
    "id", "name", "move_type", "state", "payment_state", "partner_id",
    "invoice_date", "invoice_date_due", "currency_id",
    "amount_untaxed", "amount_tax", "amount_total", "amount_residual",
    "amount_total_signed", "amount_residual_signed",
    "ref", "invoice_origin",
]

_AGING_BUCKETS = ["not_due", "days_1_30", "days_31_60", "days_61_90", "days_90_plus"]


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


def _round2(value) -> float:
    return round(value or 0.0, 2)


class AccountingHandler(OdooBase):
    """Handler for read-only accounting data access."""

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

    def _payment_memo_field(self) -> str:
        """Odoo 18 renamed account.payment.ref to memo."""
        return "memo" if self._has_field("account.payment", "memo") else "ref"

    def _move_row(self, rec: dict) -> dict:
        """Shape an account.move read record into an output row."""
        return {
            "id": rec["id"],
            "number": _clean(rec.get("name")),
            "kind": _MOVE_TYPE_TO_KIND.get(rec.get("move_type")),
            "state": rec.get("state"),
            "payment_state": _clean(rec.get("payment_state")),
            "partner_id": _m2o_id(rec.get("partner_id")),
            "partner": _m2o_name(rec.get("partner_id")),
            "invoice_date": _clean(rec.get("invoice_date")),
            "due_date": _clean(rec.get("invoice_date_due")),
            "currency": _m2o_name(rec.get("currency_id")),
            "amount_untaxed": _round2(rec.get("amount_untaxed")),
            "amount_tax": _round2(rec.get("amount_tax")),
            "amount_total": _round2(rec.get("amount_total")),
            "amount_residual": _round2(rec.get("amount_residual")),
            "amount_total_signed": _round2(rec.get("amount_total_signed")),
            "amount_residual_signed": _round2(rec.get("amount_residual_signed")),
            "ref": _clean(rec.get("ref")),
            "origin": _clean(rec.get("invoice_origin")),
        }

    def _resolve_account_ids(self, account_types: list) -> list[int]:
        """Fallback for instances that reject dotted account_type domains."""
        Account = self.odoo.env["account.account"]
        return Account.search([("account_type", "in", list(account_types))])

    # ------------------------------------------------------------------
    # Tool 1: list_invoices
    # ------------------------------------------------------------------
    async def list_invoices(self, arguments: dict) -> list[TextContent]:
        """List invoices, bills, and credit notes with filters."""
        kind = arguments.get("kind", "all")
        state = arguments.get("state", "posted")
        payment_state = arguments.get("payment_state")
        partner_id = arguments.get("partner_id")
        partner_name = arguments.get("partner_name")
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")
        limit = arguments.get("limit", 80)

        if kind != "all" and kind not in _KIND_TO_MOVE_TYPE:
            return [TextContent(type="text", text=(
                "Error: kind must be one of "
                + ", ".join(list(_KIND_TO_MOVE_TYPE) + ["all"])
            ))]
        if state not in ("draft", "posted", "cancel", "all"):
            return [TextContent(type="text", text=(
                "Error: state must be one of draft, posted, cancel, all"
            ))]
        valid_payment_states = (
            "not_paid", "partial", "in_payment", "paid", "reversed", "unpaid"
        )
        if payment_state and payment_state not in valid_payment_states:
            return [TextContent(type="text", text=(
                "Error: payment_state must be one of " + ", ".join(valid_payment_states)
            ))]

        if kind == "all":
            domain = [("move_type", "in", _DOC_MOVE_TYPES)]
        else:
            domain = [("move_type", "=", _KIND_TO_MOVE_TYPE[kind])]
        if state != "all":
            domain.append(("state", "=", state))
        if payment_state == "unpaid":
            domain.append(("payment_state", "in", ["not_paid", "partial"]))
        elif payment_state:
            domain.append(("payment_state", "=", payment_state))
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        if partner_name:
            domain.append(("partner_id.name", "ilike", partner_name))
        if date_from:
            domain.append(("invoice_date", ">=", date_from))
        if date_to:
            domain.append(("invoice_date", "<=", date_to))

        Move = self.odoo.env["account.move"]
        try:
            move_ids = Move.search(domain, limit=limit, order="invoice_date desc, id desc")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.move. The Accounting/Invoicing app may "
                f"not be installed on this Odoo instance. Details: {e}"
            ))]

        rows = []
        if move_ids:
            for rec in Move.read(move_ids, _MOVE_HEADER_FIELDS):
                rows.append(self._move_row(rec))

        header = (
            f"# Invoices & Bills ({len(rows)})\n\n"
            "Amounts are in each document's currency (see `currency`); credit "
            "notes show positive amounts. `*_signed` fields are company "
            "currency with direction sign.\n\n"
        )
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 2: get_invoice
    # ------------------------------------------------------------------
    async def get_invoice(self, arguments: dict) -> list[TextContent]:
        """Read a single invoice/bill/credit note with its line items."""
        invoice_id = arguments.get("invoice_id")
        include_sections = arguments.get("include_sections", False)

        if not invoice_id:
            return [TextContent(type="text", text="Error: invoice_id is required")]

        Move = self.odoo.env["account.move"]
        fields = _MOVE_HEADER_FIELDS + ["journal_id", "company_id", "invoice_line_ids"]
        try:
            recs = Move.read([invoice_id], fields)
        except Exception as e:
            return [TextContent(type="text", text=(
                f"Error reading account.move {invoice_id}. Check the ID, or the "
                "Accounting/Invoicing app may not be installed on this Odoo "
                f"instance. Details: {e}"
            ))]
        if not recs:
            return [TextContent(type="text", text=f"Error: invoice {invoice_id} not found")]
        rec = recs[0]

        payload = self._move_row(rec)
        payload["journal"] = _m2o_name(rec.get("journal_id"))
        payload["company"] = _m2o_name(rec.get("company_id"))

        line_ids = rec.get("invoice_line_ids") or []
        lines = []
        tax_names = {}
        if line_ids:
            MoveLine = self.odoo.env["account.move.line"]
            line_recs = self.safe_read_records("account.move.line", line_ids, [
                "id", "display_type", "product_id", "name", "quantity",
                "product_uom_id", "price_unit", "discount",
                "price_subtotal", "price_total", "tax_ids", "account_id",
            ])
            tax_ids = sorted({tid for lr in line_recs for tid in (lr.get("tax_ids") or [])})
            if tax_ids:
                Tax = self.odoo.env["account.tax"]
                for t in self.safe_read_records("account.tax", tax_ids, ["id", "name"]):
                    tax_names[t["id"]] = t["name"]
            for lr in line_recs:
                display_type = _clean(lr.get("display_type"))
                is_product_line = display_type in (None, "product")
                if not is_product_line and not (
                    include_sections and display_type in ("line_section", "line_note")
                ):
                    continue
                lines.append({
                    "id": lr["id"],
                    "display_type": display_type or "product",
                    "product_id": _m2o_id(lr.get("product_id")),
                    "product": _m2o_name(lr.get("product_id")),
                    "description": _clean(lr.get("name")),
                    "quantity": lr.get("quantity"),
                    "uom": _m2o_name(lr.get("product_uom_id")),
                    "price_unit": lr.get("price_unit"),
                    "discount": lr.get("discount"),
                    "taxes": [tax_names.get(tid, str(tid)) for tid in (lr.get("tax_ids") or [])],
                    "price_subtotal": _round2(lr.get("price_subtotal")),
                    "price_total": _round2(lr.get("price_total")),
                    "account_id": _m2o_id(lr.get("account_id")),
                    "account": _m2o_name(lr.get("account_id")),
                })
        payload["lines"] = lines

        header = (
            f"# {payload['number'] or 'Draft'} — "
            f"{(payload['kind'] or 'document').replace('_', ' ')} ({payload['state']})\n\n"
        )
        return [TextContent(type="text", text=header + _json_block(payload))]

    # ------------------------------------------------------------------
    # Tool 3: list_payments
    # ------------------------------------------------------------------
    async def list_payments(self, arguments: dict) -> list[TextContent]:
        """List customer/vendor payments with filters."""
        payment_type = arguments.get("payment_type")
        partner_id = arguments.get("partner_id")
        partner_name = arguments.get("partner_name")
        state = arguments.get("state")
        journal_id = arguments.get("journal_id")
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")
        limit = arguments.get("limit", 80)

        if payment_type and payment_type not in ("inbound", "outbound"):
            return [TextContent(type="text", text=(
                "Error: payment_type must be 'inbound' or 'outbound'"
            ))]

        domain = []
        if payment_type:
            domain.append(("payment_type", "=", payment_type))
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        if partner_name:
            domain.append(("partner_id.name", "ilike", partner_name))
        if state:
            domain.append(("state", "=", state))
        if journal_id:
            domain.append(("journal_id", "=", journal_id))
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        Payment = self.odoo.env["account.payment"]
        try:
            payment_ids = Payment.search(domain, limit=limit, order="date desc, id desc")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.payment. The Accounting/Invoicing app "
                f"may not be installed on this Odoo instance. Details: {e}"
            ))]

        memo_field = self._payment_memo_field()
        have_reconciled = self._has_field("account.payment", "is_reconciled")
        fields = [
            "id", "name", "payment_type", "partner_type", "partner_id",
            "amount", "currency_id", "date", "journal_id", "state", memo_field,
        ]
        if have_reconciled:
            fields.append("is_reconciled")

        rows = []
        if payment_ids:
            for rec in Payment.read(payment_ids, fields):
                rows.append({
                    "id": rec["id"],
                    "name": _clean(rec.get("name")),
                    "payment_type": rec.get("payment_type"),
                    "partner_type": _clean(rec.get("partner_type")),
                    "partner_id": _m2o_id(rec.get("partner_id")),
                    "partner": _m2o_name(rec.get("partner_id")),
                    "amount": _round2(rec.get("amount")),
                    "currency": _m2o_name(rec.get("currency_id")),
                    "date": _clean(rec.get("date")),
                    "journal": _m2o_name(rec.get("journal_id")),
                    "state": rec.get("state"),
                    "is_reconciled": rec.get("is_reconciled") if have_reconciled else None,
                    "memo": _clean(rec.get(memo_field)),
                })

        header = f"# Payments ({len(rows)})\n\nAmounts are in each payment's currency.\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 4: get_account_balances
    # ------------------------------------------------------------------
    async def get_account_balances(self, arguments: dict) -> list[TextContent]:
        """Trial-balance style aggregates from posted journal items."""
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")
        account_types = arguments.get("account_types")
        group_by = arguments.get("group_by", "account")
        include_draft = arguments.get("include_draft", False)

        if group_by not in ("account", "account_type"):
            return [TextContent(type="text", text=(
                "Error: group_by must be 'account' or 'account_type'"
            ))]

        domain_base = []
        if include_draft:
            domain_base.append(("parent_state", "in", ["draft", "posted"]))
        else:
            domain_base.append(("parent_state", "=", "posted"))
        if date_from:
            domain_base.append(("date", ">=", date_from))
        if date_to:
            domain_base.append(("date", "<=", date_to))

        domain = list(domain_base)
        if account_types:
            domain.append(("account_id.account_type", "in", list(account_types)))

        Line = self.odoo.env["account.move.line"]
        agg_fields = ["debit:sum", "credit:sum", "balance:sum"]
        try:
            groups = Line.read_group(domain, agg_fields, ["account_id"], lazy=False)
        except Exception as first_err:
            if not account_types:
                return [TextContent(type="text", text=(
                    "Error aggregating account.move.line. The Accounting/"
                    "Invoicing app may not be installed on this Odoo instance. "
                    f"Details: {first_err}"
                ))]
            # Some instances reject dotted domains over RPC; resolve the
            # account ids first and retry with a plain domain.
            try:
                account_ids = self._resolve_account_ids(account_types)
            except Exception as e:
                return [TextContent(type="text", text=(
                    "Error: account_types filtering requires "
                    "account.account.account_type (Odoo 16+). "
                    f"Details: {e}"
                ))]
            try:
                groups = Line.read_group(
                    domain_base + [("account_id", "in", account_ids)],
                    agg_fields, ["account_id"], lazy=False,
                )
            except Exception as e:
                return [TextContent(type="text", text=(
                    "Error aggregating account.move.line. The Accounting/"
                    "Invoicing app may not be installed on this Odoo instance. "
                    f"Details: {e}"
                ))]

        # Resolve code/name/type for the accounts that actually have activity.
        acc_info = {}
        acc_ids = [_m2o_id(g["account_id"]) for g in groups if g.get("account_id")]
        have_account_type = self._has_field("account.account", "account_type")
        if group_by == "account_type" and not have_account_type:
            return [TextContent(type="text", text=(
                "Error: group_by='account_type' requires "
                "account.account.account_type (Odoo 16+)."
            ))]
        if acc_ids:
            Account = self.odoo.env["account.account"]
            acc_fields = ["id", "code", "name"] + (
                ["account_type"] if have_account_type else []
            )
            for a in Account.read(acc_ids, acc_fields):
                acc_info[a["id"]] = a

        if group_by == "account":
            rows = []
            for g in groups:
                aid = _m2o_id(g.get("account_id"))
                info = acc_info.get(aid, {})
                rows.append({
                    "account_id": aid,
                    "code": _clean(info.get("code")),
                    "name": info.get("name") or _m2o_name(g.get("account_id")),
                    "account_type": info.get("account_type") if have_account_type else None,
                    "debit": _round2(g.get("debit")),
                    "credit": _round2(g.get("credit")),
                    "balance": _round2(g.get("balance")),
                })
            rows.sort(key=lambda r: r["code"] or "")
        else:
            by_type = {}
            for g in groups:
                aid = _m2o_id(g.get("account_id"))
                acct_type = acc_info.get(aid, {}).get("account_type") or "(unknown)"
                agg = by_type.setdefault(acct_type, {
                    "account_type": acct_type,
                    "debit": 0.0, "credit": 0.0, "balance": 0.0, "account_count": 0,
                })
                agg["debit"] += g.get("debit") or 0.0
                agg["credit"] += g.get("credit") or 0.0
                agg["balance"] += g.get("balance") or 0.0
                agg["account_count"] += 1
            rows = sorted(by_type.values(), key=lambda r: r["account_type"])
            for r in rows:
                r["debit"], r["credit"], r["balance"] = (
                    _round2(r["debit"]), _round2(r["credit"]), _round2(r["balance"]),
                )

        period = f"{date_from or 'beginning'} to {date_to or 'today'}"
        header = (
            f"# Account Balances ({len(rows)} rows, {period})\n\n"
            "Company currency. balance = debit - credit, so income accounts "
            "show negative (credit) balances. "
            + ("Includes draft entries.\n\n" if include_draft else "Posted entries only.\n\n")
        )
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 5: get_aged_balances
    # ------------------------------------------------------------------
    async def get_aged_balances(self, arguments: dict) -> list[TextContent]:
        """Aged receivables/payables by partner with standard buckets."""
        side = arguments.get("side")
        as_of_arg = arguments.get("as_of_date")
        partner_id = arguments.get("partner_id")
        limit = arguments.get("limit", 100)

        if side not in _AGED_ACCOUNT_TYPE:
            return [TextContent(type="text", text=(
                "Error: side must be 'receivable' or 'payable'"
            ))]
        try:
            as_of = date.fromisoformat(as_of_arg) if as_of_arg else date.today()
        except ValueError:
            return [TextContent(type="text", text=(
                "Error: as_of_date must be YYYY-MM-DD"
            ))]

        acct_type = _AGED_ACCOUNT_TYPE[side]
        domain_base = [
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("amount_residual", "!=", 0),
            ("date", "<=", as_of.isoformat()),
        ]
        if partner_id:
            domain_base.append(("partner_id", "=", partner_id))

        Line = self.odoo.env["account.move.line"]
        try:
            line_ids = Line.search(
                domain_base + [("account_id.account_type", "=", acct_type)]
            )
        except Exception as first_err:
            # Dotted-domain fallback: resolve receivable/payable accounts first.
            try:
                account_ids = self._resolve_account_ids([acct_type])
                line_ids = Line.search(
                    domain_base + [("account_id", "in", account_ids)]
                )
            except Exception:
                return [TextContent(type="text", text=(
                    "Error searching account.move.line. The Accounting/"
                    "Invoicing app may not be installed on this Odoo instance. "
                    f"Details: {first_err}"
                ))]

        # Bucket in Python: residuals are company currency; payables flipped
        # so amounts owed to vendors read positive.
        sign = -1.0 if side == "payable" else 1.0
        partners = {}
        totals = {"total": 0.0, **{b: 0.0 for b in _AGING_BUCKETS}}
        lines = self.safe_read_records(
            "account.move.line", line_ids, ["partner_id", "amount_residual", "date_maturity", "date"]
        ) if line_ids else []
        for line in lines:
            amount = (line.get("amount_residual") or 0.0) * sign
            due = line.get("date_maturity") or line.get("date")
            days_overdue = (as_of - date.fromisoformat(due)).days if due else 0
            if days_overdue <= 0:
                bucket = "not_due"
            elif days_overdue <= 30:
                bucket = "days_1_30"
            elif days_overdue <= 60:
                bucket = "days_31_60"
            elif days_overdue <= 90:
                bucket = "days_61_90"
            else:
                bucket = "days_90_plus"

            pid = _m2o_id(line.get("partner_id"))
            entry = partners.setdefault(pid, {
                "partner_id": pid,
                "partner": _m2o_name(line.get("partner_id")) or "(no partner)",
                "total": 0.0, **{b: 0.0 for b in _AGING_BUCKETS},
            })
            entry[bucket] += amount
            entry["total"] += amount
            totals[bucket] += amount
            totals["total"] += amount

        partner_rows = sorted(partners.values(), key=lambda p: -abs(p["total"]))
        shown = partner_rows[:limit]
        for row in shown:
            for key in ["total"] + _AGING_BUCKETS:
                row[key] = _round2(row[key])
        payload = {
            "side": side,
            "as_of_date": as_of.isoformat(),
            "currency_note": (
                "company currency"
                + ("; payables shown positive" if side == "payable" else "")
            ),
            "totals": {k: _round2(v) for k, v in totals.items()},
            "partners": shown,
        }

        header = f"# Aged {side.capitalize()}s as of {as_of.isoformat()}\n\n"
        header += (
            "Buckets are days overdue vs due date (falls back to move date). "
            "Note: a historical as_of_date re-buckets *current* open items; "
            "it does not reconstruct historical reconciliation state.\n\n"
        )
        if len(partner_rows) > len(shown):
            header += (
                f"Showing top {len(shown)} of {len(partner_rows)} partners by "
                "absolute total; `totals` covers all partners.\n\n"
            )
        return [TextContent(type="text", text=header + _json_block(payload))]

    # ------------------------------------------------------------------
    # Tool 6: list_journal_items
    # ------------------------------------------------------------------
    async def list_journal_items(self, arguments: dict) -> list[TextContent]:
        """Raw journal items (account.move.line) for ledger/reconciliation work.

        Matched lines share a matching_number, which is what move-by-move
        pairing on a reconcilable account needs.
        """
        account_id = arguments.get("account_id")
        account_code = arguments.get("account_code")
        move_id = arguments.get("move_id")
        journal_id = arguments.get("journal_id")
        partner_id = arguments.get("partner_id")
        partner_name = arguments.get("partner_name")
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")
        include_draft = arguments.get("include_draft", False)
        limit = arguments.get("limit", 200)

        if account_id and account_code:
            return [TextContent(type="text", text=(
                "Error: account_id and account_code are mutually exclusive"
            ))]

        if include_draft:
            domain = [("parent_state", "in", ["draft", "posted"])]
        else:
            domain = [("parent_state", "=", "posted")]
        header_notes = []

        if account_code:
            Account = self.odoo.env["account.account"]
            try:
                matched = Account.search([("code", "=like", f"{account_code}%")])
            except Exception as e:
                return [TextContent(type="text", text=(
                    "Error searching account.account. The Accounting/Invoicing "
                    f"app may not be installed on this Odoo instance. Details: {e}"
                ))]
            if not matched:
                return [TextContent(type="text", text=(
                    f"# Journal Items (0)\n\nNo account code starts with "
                    f"'{account_code}'.\n\n" + _json_block([])
                ))]
            domain.append(("account_id", "in", matched))
        elif account_id:
            domain.append(("account_id", "=", account_id))
        if move_id:
            domain.append(("move_id", "=", move_id))
        if journal_id:
            domain.append(("journal_id", "=", journal_id))
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        if partner_name:
            domain.append(("partner_id.name", "ilike", partner_name))
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if "reconciled" in arguments:
            domain.append(("reconciled", "=", bool(arguments["reconciled"])))

        Line = self.odoo.env["account.move.line"]
        try:
            line_ids = Line.search(domain, limit=limit, order="date desc, id desc")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.move.line. The Accounting/Invoicing "
                f"app may not be installed on this Odoo instance. Details: {e}"
            ))]

        have_matching = self._has_field("account.move.line", "matching_number")
        fields = [
            "id", "date", "move_id", "journal_id", "account_id", "partner_id",
            "name", "ref", "debit", "credit", "balance", "amount_residual",
            "amount_currency", "currency_id", "reconciled", "parent_state",
        ]
        if have_matching:
            fields.append("matching_number")

        rows = []
        if line_ids:
            for rec in Line.read(line_ids, fields):
                rows.append({
                    "id": rec["id"],
                    "date": _clean(rec.get("date")),
                    "move_id": _m2o_id(rec.get("move_id")),
                    "move": _m2o_name(rec.get("move_id")),
                    "journal": _m2o_name(rec.get("journal_id")),
                    "account_id": _m2o_id(rec.get("account_id")),
                    "account": _m2o_name(rec.get("account_id")),
                    "partner_id": _m2o_id(rec.get("partner_id")),
                    "partner": _m2o_name(rec.get("partner_id")),
                    "label": _clean(rec.get("name")),
                    "ref": _clean(rec.get("ref")),
                    "debit": _round2(rec.get("debit")),
                    "credit": _round2(rec.get("credit")),
                    "balance": _round2(rec.get("balance")),
                    "amount_residual": _round2(rec.get("amount_residual")),
                    "amount_currency": _round2(rec.get("amount_currency")),
                    "currency": _m2o_name(rec.get("currency_id")),
                    "reconciled": rec.get("reconciled"),
                    "matching_number": (
                        _clean(rec.get("matching_number")) if have_matching else None
                    ),
                    "state": rec.get("parent_state"),
                })

        header = (
            f"# Journal Items ({len(rows)})\n\n"
            "debit/credit/balance/amount_residual are company currency; "
            "amount_currency is the line's own currency. Reconciled lines "
            "share a matching_number.\n\n"
        )
        if len(rows) == limit:
            header += (
                f"Result hit the limit ({limit}); narrow the filters or raise "
                "`limit` for a complete set.\n\n"
            )
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 7: list_accounts
    # ------------------------------------------------------------------
    async def list_accounts(self, arguments: dict) -> list[TextContent]:
        """Chart of accounts. Balances live in get_account_balances."""
        account_type = arguments.get("account_type")
        code_prefix = arguments.get("code_prefix")
        name = arguments.get("name")
        limit = arguments.get("limit", 500)

        have_account_type = self._has_field("account.account", "account_type")
        have_deprecated = self._has_field("account.account", "deprecated")
        have_active = self._has_field("account.account", "active")

        if account_type and not have_account_type:
            return [TextContent(type="text", text=(
                "Error: account_type filtering requires "
                "account.account.account_type (Odoo 16+)."
            ))]

        domain = []
        if account_type:
            domain.append(("account_type", "=", account_type))
        if code_prefix:
            domain.append(("code", "=like", f"{code_prefix}%"))
        if name:
            domain.append(("name", "ilike", name))
        if have_active:
            # Show archived accounts with their flag rather than hiding them.
            domain.append(_INCLUDE_ARCHIVED)

        Account = self.odoo.env["account.account"]
        try:
            account_ids = Account.search(domain, limit=limit, order="code")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.account. The Accounting/Invoicing app "
                f"may not be installed on this Odoo instance. Details: {e}"
            ))]

        fields = ["id", "code", "name", "reconcile"]
        if have_account_type:
            fields.append("account_type")
        if have_deprecated:
            fields.append("deprecated")
        if have_active:
            fields.append("active")

        rows = []
        if account_ids:
            for rec in Account.read(account_ids, fields):
                rows.append({
                    "id": rec["id"],
                    "code": _clean(rec.get("code")),
                    "name": rec.get("name"),
                    "account_type": rec.get("account_type") if have_account_type else None,
                    "reconcile": rec.get("reconcile"),
                    "deprecated": rec.get("deprecated") if have_deprecated else None,
                    "active": rec.get("active") if have_active else None,
                })

        header = f"# Chart of Accounts ({len(rows)})\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 8: list_journals
    # ------------------------------------------------------------------
    async def list_journals(self, arguments: dict) -> list[TextContent]:
        """Enumerate accounting journals."""
        journal_type = arguments.get("journal_type")
        include_archived = arguments.get("include_archived", False)

        domain = []
        if journal_type:
            domain.append(("type", "=", journal_type))
        if include_archived:
            domain.append(_INCLUDE_ARCHIVED)

        Journal = self.odoo.env["account.journal"]
        try:
            journal_ids = Journal.search(domain, order="type, code")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.journal. The Accounting/Invoicing app "
                f"may not be installed on this Odoo instance. Details: {e}"
            ))]

        have_default_account = self._has_field("account.journal", "default_account_id")
        fields = ["id", "name", "code", "type", "currency_id", "active"]
        if have_default_account:
            fields.append("default_account_id")

        rows = []
        if journal_ids:
            for rec in Journal.read(journal_ids, fields):
                rows.append({
                    "id": rec["id"],
                    "name": rec.get("name"),
                    "code": rec.get("code"),
                    "type": rec.get("type"),
                    "currency": _m2o_name(rec.get("currency_id")),
                    "default_account": (
                        _m2o_name(rec.get("default_account_id"))
                        if have_default_account else None
                    ),
                    "active": rec.get("active", True),
                })

        header = f"# Journals ({len(rows)})\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]

    # ------------------------------------------------------------------
    # Tool 9: list_taxes
    # ------------------------------------------------------------------
    async def list_taxes(self, arguments: dict) -> list[TextContent]:
        """Enumerate taxes."""
        type_tax_use = arguments.get("type_tax_use")
        include_archived = arguments.get("include_archived", False)

        if type_tax_use and type_tax_use not in ("sale", "purchase", "none"):
            return [TextContent(type="text", text=(
                "Error: type_tax_use must be 'sale', 'purchase', or 'none'"
            ))]

        domain = []
        if type_tax_use:
            domain.append(("type_tax_use", "=", type_tax_use))
        if include_archived:
            domain.append(_INCLUDE_ARCHIVED)

        Tax = self.odoo.env["account.tax"]
        try:
            tax_ids = Tax.search(domain, order="type_tax_use, name")
        except Exception as e:
            return [TextContent(type="text", text=(
                "Error searching account.tax. The Accounting/Invoicing app may "
                f"not be installed on this Odoo instance. Details: {e}"
            ))]

        have_price_include = self._has_field("account.tax", "price_include")
        fields = ["id", "name", "amount", "amount_type", "type_tax_use", "active"]
        if have_price_include:
            fields.append("price_include")

        rows = []
        if tax_ids:
            for rec in Tax.read(tax_ids, fields):
                rows.append({
                    "id": rec["id"],
                    "name": rec.get("name"),
                    "amount": rec.get("amount"),
                    "amount_type": rec.get("amount_type"),
                    "type_tax_use": rec.get("type_tax_use"),
                    "price_include": (
                        rec.get("price_include") if have_price_include else None
                    ),
                    "active": rec.get("active", True),
                })

        header = f"# Taxes ({len(rows)})\n\n"
        return [TextContent(type="text", text=header + _json_block(rows))]
