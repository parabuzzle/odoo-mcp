"""Helpers for building Odoo o-spreadsheet JSON payloads.

Odoo spreadsheets (Documents app) and spreadsheet dashboards (Dashboards app)
both store their content as an o-spreadsheet JSON document in a text field
(``spreadsheet_data``). This module builds a minimal, broadly-compatible
o-spreadsheet payload from a simple table of headers + rows, with an optional
chart figure.

The generated payload intentionally sticks to the long-stable core of the
o-spreadsheet data model (``sheets[].cells`` with ``content``/``style`` plus
top-level ``styles`` and ``figures``). This keeps snapshot dashboards working
across Odoo versions. For advanced content (e.g. live pivots), callers can
build/supply their own JSON and pass it through the ``data_json`` argument of
the create/update tools instead.
"""

import json

# Style indexes referenced by cells. Kept small and stable.
_STYLES = {
    "1": {"bold": True, "fontSize": 16},          # Title
    "2": {"bold": True, "fillColor": "#F2F2F2"},  # Header row
    "3": {"bold": True},                           # Totals row
}


def col_letter(index: int) -> str:
    """Convert a 0-based column index to a spreadsheet column letter (0 -> A)."""
    result = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _chart_figure(
    figure_id: str,
    sheet_name: str,
    chart_type: str,
    title: str,
    label_range: str,
    data_ranges: list[str],
    x: int = 40,
    y: int = 40,
    width: int = 600,
    height: int = 380,
) -> dict:
    """Build a single chart figure for an o-spreadsheet sheet."""
    return {
        "id": figure_id,
        "tag": "chart",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "data": {
            "type": chart_type,  # 'bar', 'line', 'pie'
            "title": {"text": title},
            "background": "#FFFFFF",
            "dataSets": [{"dataRange": r} for r in data_ranges],
            "labelRange": label_range,
            "dataSetsHaveTitle": True,
            "legendPosition": "top",
            "verticalAxisPosition": "left",
        },
    }


def build_table_spreadsheet(
    sheet_name: str,
    headers: list[str],
    rows: list[list],
    title: str | None = None,
    totals_row: list | None = None,
    chart_type: str | None = None,
    chart_title: str | None = None,
    chart_label_col: int = 0,
    chart_value_cols: list[int] | None = None,
) -> dict:
    """Build an o-spreadsheet data dict from a simple table.

    Args:
        sheet_name: Name shown on the sheet tab (kept free of spaces/special
            characters is safest since it is used in chart range references).
        headers: Column header labels.
        rows: List of rows, each a list of cell values (str/int/float/None).
        title: Optional big title placed in cell A1.
        totals_row: Optional bold summary row appended after the data.
        chart_type: One of 'bar', 'line', 'pie'. When set, a chart figure is
            added referencing the value column(s).
        chart_title: Title for the chart (defaults to the sheet title/name).
        chart_label_col: 0-based column index used for chart labels.
        chart_value_cols: 0-based column indexes to plot. Defaults to [1].

    Returns:
        A dict ready to be ``json.dumps``-ed into ``spreadsheet_data``.
    """
    cells: dict[str, dict] = {}
    row_cursor = 1  # 1-indexed spreadsheet row

    if title:
        cells[f"A{row_cursor}"] = {"content": str(title), "style": 1}
        row_cursor += 2  # leave a blank spacer row

    header_row = row_cursor
    for c, header in enumerate(headers):
        cells[f"{col_letter(c)}{header_row}"] = {"content": str(header), "style": 2}

    first_data_row = header_row + 1
    for i, row in enumerate(rows):
        rr = first_data_row + i
        for c, value in enumerate(row):
            content = "" if value is None else str(value)
            cells[f"{col_letter(c)}{rr}"] = {"content": content}

    last_data_row = first_data_row + len(rows) - 1 if rows else header_row

    if totals_row:
        tr = last_data_row + 1 if rows else header_row + 1
        for c, value in enumerate(totals_row):
            content = "" if value is None else str(value)
            cells[f"{col_letter(c)}{tr}"] = {"content": content, "style": 3}

    figures = []
    if chart_type and rows:
        value_cols = chart_value_cols or [1]
        label_col_letter = col_letter(chart_label_col)
        # Include the header cell in the ranges so series get their names.
        label_range = f"{sheet_name}!{label_col_letter}{header_row}:{label_col_letter}{last_data_row}"
        data_ranges = [
            f"{sheet_name}!{col_letter(vc)}{header_row}:{col_letter(vc)}{last_data_row}"
            for vc in value_cols
        ]
        chart_x = (len(headers) + 1) * 110
        figures.append(
            _chart_figure(
                figure_id="chart1",
                sheet_name=sheet_name,
                chart_type=chart_type,
                title=chart_title or title or sheet_name,
                label_range=label_range,
                data_ranges=data_ranges,
                x=chart_x,
                y=20,
            )
        )

    col_number = max(len(headers), 10)
    row_number = max(last_data_row + 5, 50)

    return {
        "version": 1,
        "sheets": [
            {
                "id": "sheet1",
                "name": sheet_name,
                "colNumber": col_number,
                "rowNumber": row_number,
                "cells": cells,
                "merges": [],
                "cols": {},
                "rows": {},
                "conditionalFormats": [],
                "figures": figures,
            }
        ],
        "styles": _STYLES,
        "formats": {},
        "borders": {},
        "revisionId": "START_REVISION",
    }


def empty_spreadsheet(sheet_name: str = "Sheet1") -> dict:
    """Return a minimal empty o-spreadsheet data dict."""
    return {
        "version": 1,
        "sheets": [
            {
                "id": "sheet1",
                "name": sheet_name,
                "colNumber": 26,
                "rowNumber": 100,
                "cells": {},
                "merges": [],
                "cols": {},
                "rows": {},
                "conditionalFormats": [],
                "figures": [],
            }
        ],
        "styles": {},
        "formats": {},
        "borders": {},
        "revisionId": "START_REVISION",
    }


def dumps(data: dict) -> str:
    """Serialize an o-spreadsheet data dict to the JSON string Odoo stores."""
    return json.dumps(data, separators=(",", ":"))
