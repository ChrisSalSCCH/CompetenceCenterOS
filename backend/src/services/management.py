"""Pure rules for management reporting: forecast buckets, capacity, duplicates and exports (no database)."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from services.commercial import effective_probability, money

FORECAST_CATEGORIES = ("secured", "weighted", "planned", "hypothetical")
UNDATED = "undated"


# ---------------------------------------------------------------- calendar


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def months_ahead(start: date, count: int) -> list[str]:
    out = []
    year, month = start.year, start.month
    for _ in range(count):
        out.append(f"{year}-{month:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return out


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weeks_ahead(start: date, count: int) -> list[date]:
    first = week_start(start)
    return [first + timedelta(weeks=i) for i in range(count)]


# ---------------------------------------------------------------- forecast


def _bucket(d: date | None, months: list[str], today: date) -> str:
    if d is None:
        return UNDATED
    key = month_key(max(d, today))  # overdue items are due now, not in the past
    return key if key in months else (UNDATED if key > months[-1] else months[0])


def build_forecast(
    milestones: list[dict[str, Any]], opportunities: list[dict[str, Any]], months: list[str], stage_config: dict[str, int] | None = None, today: date | None = None
) -> dict[str, dict[str, dict[str, Decimal]]]:
    """Revenue per currency, category and month. Currencies are never mixed.

    secured      payment milestones of signed contracts that are not paid yet
    weighted     open opportunities: value x probability, by expected decision month
    planned      won opportunities that have no signed contract yet, at full value
    hypothetical open opportunities: the part not covered by `weighted` (value x (1 - probability))

    The four categories use different records, so nothing is counted twice.
    """
    today = today or date.today()
    keys = [*months, UNDATED]
    out: dict[str, dict[str, dict[str, Decimal]]] = {}

    def add(currency: str, category: str, bucket: str, amount: Decimal) -> None:
        cur = out.setdefault(currency, {c: dict.fromkeys(keys, Decimal(0)) for c in FORECAST_CATEGORIES})
        cur[category][bucket] += amount

    for m in milestones:
        if m.get("amount") is None or m.get("status") == "paid":
            continue
        add(m["currency"], "secured", _bucket(m.get("due_date"), months, today), Decimal(str(m["amount"])))
    for o in opportunities:
        if o.get("value_amount") is None:
            continue
        value = Decimal(str(o["value_amount"]))
        stage = o["stage"]
        if stage == "lost":
            continue
        if stage == "won":
            if not o.get("has_signed_contract"):
                add(o["currency"], "planned", _bucket(o.get("expected_start") or o.get("expected_close"), months, today), value)
            continue
        prob = effective_probability(stage, o.get("probability"), bool(o.get("probability_manual")), stage_config)
        weighted = money(value * Decimal(prob) / 100)
        bucket = _bucket(o.get("expected_close"), months, today)
        add(o["currency"], "weighted", bucket, weighted)
        add(o["currency"], "hypothetical", bucket, money(value - weighted))
    return out


def forecast_totals(forecast: dict[str, dict[str, dict[str, Decimal]]]) -> dict[str, dict[str, Decimal]]:
    return {cur: {cat: sum(buckets.values(), Decimal(0)) for cat, buckets in cats.items()} for cur, cats in forecast.items()}


# ---------------------------------------------------------------- capacity


def weekdays_in_week(start: date, end: date, week: date) -> int:
    """Monday-Friday days of the week starting on `week` that lie inside [start, end]."""
    return sum(1 for i in range(5) if start <= week + timedelta(days=i) <= end)


def weekly_load(allocations: list[dict[str, Any]], week: date) -> Decimal:
    """Planned hours in a week; a part-week counts pro rata by working days."""
    total = Decimal(0)
    for a in allocations:
        days = weekdays_in_week(a["start_date"], a["end_date"], week)
        if days:
            total += Decimal(str(a["hours_per_week"])) * Decimal(days) / Decimal(5)
    return total.quantize(Decimal("0.1"))


def capacity_for(entries: list[dict[str, Any]], week: date) -> Decimal | None:
    """Explicit capacity valid in a week, or None. A missing entry is never replaced by an assumed 40 hours."""
    valid = [e for e in entries if e["valid_from"] <= week and (e.get("valid_to") is None or e["valid_to"] >= week)]
    if not valid:
        return None
    return Decimal(str(max(valid, key=lambda e: e["valid_from"])["weekly_hours"]))


def utilization(load: Decimal, capacity: Decimal | None) -> float | None:
    if capacity is None or capacity == 0:
        return None
    return round(float(load / capacity) * 100, 1)


# -------------------------------------------------------------- duplicates


def contact_key(first: str, last: str) -> str:
    return re.sub(r"[^a-z0-9]", "", f"{first}{last}".lower())


def find_duplicate_contacts(contacts: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Groups of contacts with the same normalized name. The caller decides which to merge."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in contacts:
        key = contact_key(c["first_name"], c["last_name"])
        if key:
            groups.setdefault(key, []).append(c)
    return [g for g in groups.values() if len(g) > 1]


# ------------------------------------------------------------------ export

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def csv_cell(value: Any) -> Any:
    """Neutralize spreadsheet formulas: a text starting with = + - @ would be executed by Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    if value is None:
        return ""
    return value


def make_csv(headers: list[str], rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([csv_cell(h) for h in headers])
    for row in rows:
        writer.writerow([csv_cell(v) for v in row])
    return buf.getvalue()


def _col(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _xlsx_cell(ref: str, value: Any) -> str:
    value = csv_cell(value)
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float, Decimal)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(_CONTROL.sub("", str(value)))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def make_xlsx(headers: list[str], rows: list[list[Any]], sheet: str = "Export") -> bytes:
    """A minimal, dependency-free .xlsx workbook with one sheet."""
    lines = []
    for r, row in enumerate([headers, *rows], start=1):
        cells = "".join(_xlsx_cell(f"{_col(c)}{r}", v) for c, v in enumerate(row))
        lines.append(f'<row r="{r}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(lines) + "</sheetData></worksheet>"
    )
    name = escape(re.sub(r"[\[\]:*?/\\]", "", sheet)[:31] or "Export")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in parts.items():
            zf.writestr(path, content)
    return buf.getvalue()
