"""The four checks.

1. Missing fields: a pack field with no column, or a row whose cell is empty or a placeholder.
2. Next review date: only the field a pack names as the regulator's next review date, read as it stands.
3. Typed or derived: each data cell is typed by a person, derived by a formula, or blank.
4. What a spreadsheet cannot prove: no history, no signers, no hashes. Stated once per run.
"""
import datetime
import re

from .packs import SetupError, normalize

SCAN_ROWS = 20  # the header row is looked for in the first rows of each sheet
PLACEHOLDERS = {"tbd", "tba", "tbc", "todo", "to do", "xxx", "placeholder"}

CAVEAT = ("Cached formula values may be stale if the workbook was not recalculated before it was saved. "
          "Whether a cell is typed or derived is read from the file itself and is unaffected.")
CSV_NOTE = "A CSV file keeps no formulas, so typed and derived cells cannot be told apart. Lint the .xlsx for check 3."
HISTORY = ("No history: a spreadsheet keeps no append-only record of its changes, so the state of an entry "
           "on any past date cannot be reconstructed from it.")
SIGNERS = "No signers: nothing binds an entry to an accountable person. A name in a cell is a claim, not a signature."
HASHES = "No integrity: no entry carries a hash, so any value may have been overwritten without a trace."
CLOSING = "These cannot be fixed in a spreadsheet. That is what GovernanceOS is for."
LINK = "https://governanceos.si"


def letter(c):
    """Zero-based column index to its spreadsheet letters (0 -> A, 26 -> AA)."""
    s = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def ref(r, c):
    return "%s%d" % (letter(c), r + 1)


def cell(row, c):
    return row[c] if c < len(row) else None


def blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


class Layout(object):
    """Where the register sits: its sheet, header row and data rows."""

    def __init__(self, sheet, header_index, chosen_by):
        self.sheet = sheet
        self.header_index = header_index
        self.chosen_by = chosen_by
        header = sheet.values[header_index]
        self.headers = ["" if blank(v) else " ".join(str(v).split()) for v in header]
        self.norms = [normalize(h) for h in self.headers]
        self.rows = [(r, row) for r, row in enumerate(sheet.values)
                     if r > header_index and any(not blank(v) for v in row)]
        self.width = max([len(self.headers)] + [len(row) for _, row in self.rows])
        names = [c for c, n in enumerate(self.norms) if "name" in n.split()]
        self.name_column = names[0] if names else 0

    def is_formula(self, r, c):
        return self.sheet.formulas is not None and (r, c) in self.sheet.formulas

    def entry(self, r, row):
        v = cell(row, self.name_column)
        return " ".join(str(v).split())[:60] if not blank(v) else "row %d" % (r + 1)


def locate(register, packs, sheet_name=None):
    """The sheet and header row with the most cells matching a pack field (ties go to the earlier one)."""
    keys = set(k for p in packs for f in p.fields for k in f.keys)
    if sheet_name is not None:
        sheets = [s for s in register.sheets if s.name == sheet_name]
        if not sheets:
            raise SetupError("no sheet named %r. Sheets: %s" % (sheet_name, ", ".join(s.name for s in register.sheets)))
    else:
        sheets = [s for s in register.sheets if any(not blank(v) for row in s.values for v in row)]
        if not sheets:
            raise SetupError("%s holds no data." % register.file)
    best = None
    for s in sheets:
        for r, row in enumerate(s.values[:SCAN_ROWS]):
            score = len(set(c for c, v in enumerate(row) if not blank(v) and normalize(v) in keys))
            if best is None or score > best[0]:
                best = (score, s, r)
    if best is None or best[0] == 0:  # nothing matched: the first row with content is the header
        s = sheets[0]
        filled = [r for r, row in enumerate(s.values) if any(not blank(v) for v in row)]
        if not filled:
            raise SetupError("sheet %r is empty." % s.name)
        best = (0, s, filled[0])
    chosen_by = "named with --sheet" if sheet_name is not None else (
        "the only sheet with data" if len(sheets) == 1 else "chosen for the most matching headers; name another with --sheet")
    return Layout(best[1], best[2], chosen_by)


def map_columns(layout, pack):
    """Field id -> column index. Within a pack a column serves one field; synonyms are tried in order."""
    used, columns = set(), {}
    for f in pack.fields:
        for key in f.keys:
            hit = [c for c, n in enumerate(layout.norms) if n == key and c not in used]
            if hit:
                columns[f.id] = hit[0]
                used.add(hit[0])
                break
    return columns


def _finding(check, kind, severity, pack, field, message, layout=None, r=None, row=None, c=None):
    return {
        "check": check, "kind": kind, "severity": severity, "pack": pack.id,
        "field": field.id if field else None, "basis": field.basis if field else None,
        "row": None if r is None else r + 1,
        "entry": layout.entry(r, row) if r is not None else None,
        "cell": ref(r, c) if r is not None else None,
        "message": message, "citation": field.citation if field else None,
    }


def emptiness(layout, r, row, c):
    """Why a cell counts as empty, or None when it holds a value."""
    v = cell(row, c)
    if blank(v):
        return "is empty (a formula with no value)" if layout.is_formula(r, c) else "is empty"
    if isinstance(v, str) and (normalize(v) in PLACEHOLDERS or not normalize(v)):
        return 'holds a placeholder ("%s")' % v.strip()
    return None


def check_fields(layout, pack, columns):
    """Check 1. Severity follows the field's basis: required, expected, recommended."""
    out = []
    for f in pack.fields:
        c = columns.get(f.id)
        if c is None:
            out.append(_finding("missing_field", "column", f.severity, pack, f, 'No column for "%s".' % f.label))
            continue
        for r, row in layout.rows:
            why = emptiness(layout, r, row, c)
            if why:
                out.append(_finding("missing_field", "cell", f.severity, pack, f,
                                    '"%s" %s.' % (f.label, why), layout, r, row, c))
    rank = dict((f.id, f.number) for f in pack.fields)
    out.sort(key=lambda x: (x["kind"] != "column", x["row"] or 0, rank[x["field"]]))
    return out


MONTHS = dict((m, i) for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1))
MONTHS.update(dict((m[:3], i) for m, i in list(MONTHS.items())))
MONTHS["sept"] = 9
ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
DAY_MONTH = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?[ -]([a-z]+)\.?,?[ -](\d{4})$")
MONTH_DAY = re.compile(r"^([a-z]+)\.?[ -](\d{1,2})(?:st|nd|rd|th)?,?[ -](\d{4})$")


def _valid(y, m, d):
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def to_date(v):
    """(date, None) or (None, why it is not a date). Standard library only; never guesses a day-month order."""
    if isinstance(v, datetime.datetime):
        return v.date(), None
    if isinstance(v, datetime.date):
        return v, None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return None, "a number, not a date"
    if not isinstance(v, str):
        return None, "not a date"
    s = " ".join(v.split()).lower()
    m = ISO.match(s)
    if m:
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (d, None) if d else (None, "not a valid date")
    m = NUMERIC.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        day_first, month_first = _valid(y, b, a), _valid(y, a, b)
        if day_first and month_first and day_first != month_first:
            return None, "ambiguous (%s or %s)" % (day_first.isoformat(), month_first.isoformat())
        d = day_first or month_first
        return (d, None) if d else (None, "not a valid date")
    for pattern, day, month in ((DAY_MONTH, 1, 2), (MONTH_DAY, 2, 1)):
        m = pattern.match(s)
        if m and m.group(month) in MONTHS:
            d = _valid(int(m.group(3)), MONTHS[m.group(month)], int(m.group(day)))
            return (d, None) if d else (None, "not a valid date")
    return None, "not a date"


def check_review_dates(layout, packs, columns, as_of, grace_days):
    """Check 2. Reads only each pack's next_review_field, once per column. An empty cell is check 1's."""
    targets, info = {}, []
    for p in packs:
        if not p.next_review_field:
            continue
        f = p.field(p.next_review_field)
        c = columns[p.id].get(f.id)
        info.append({"pack": p.id, "field": f.id, "label": f.label,
                     "column": None if c is None else letter(c),
                     "header": None if c is None else layout.headers[c]})
        if c is not None:
            targets.setdefault(c, (p, f))
    out = []
    for c in sorted(targets):
        p, f = targets[c]
        for r, row in layout.rows:
            if emptiness(layout, r, row, c):
                continue
            v = cell(row, c)
            d, why = to_date(v)
            if d is None:
                shown = '"%s"' % " ".join(v.split()) if isinstance(v, str) else str(v)
                hint = "Format the cell as a date." if why.startswith("a number") else "Write it as YYYY-MM-DD."
                out.append(_finding("review_date", "unreadable", "warning", p, f,
                                    '"%s" holds %s: %s. %s' % (f.label, shown, why, hint), layout, r, row, c))
                continue
            days = (as_of - d).days
            if days > grace_days:
                grace = ", grace %d days" % grace_days if grace_days else ""
                out.append(_finding("review_date", "overdue", "error", p, f,
                                    "Next review date %s is %d day%s past (as of %s%s)."
                                    % (d.isoformat(), days, "" if days == 1 else "s", as_of.isoformat(), grace),
                                    layout, r, row, c))
    return out, info


def check_provenance(layout):
    """Check 3. Counts per column; the derived cells are listed by reference."""
    if layout.sheet.formulas is None:
        return {"available": False, "reason": CSV_NOTE, "columns": []}
    columns, totals = [], {"typed": 0, "derived": 0, "blank": 0}
    for c in range(layout.width):
        n = {"typed": 0, "derived": 0, "blank": 0}
        derived = []
        for r, row in layout.rows:
            if layout.is_formula(r, c):
                n["derived"] += 1
                derived.append(ref(r, c))
            elif blank(cell(row, c)):
                n["blank"] += 1
            else:
                n["typed"] += 1
        header = layout.headers[c] if c < len(layout.headers) else ""
        if header or n["typed"] or n["derived"]:
            columns.append({"column": letter(c), "header": header, "typed": n["typed"], "derived": n["derived"],
                            "blank": n["blank"], "derived_cells": derived})
            for k in totals:
                totals[k] += n[k]
    out = {"available": True, "caveat": CAVEAT}
    out.update(totals)
    out["columns"] = columns
    return out


def check_provability(layout):
    """Check 4. Structural: true of every spreadsheet, so stated once and never counted as a finding."""
    return {"history": False, "signers": False, "hashes": False, "entries_affected": len(layout.rows),
            "findings": [HISTORY, SIGNERS, HASHES], "statement": CLOSING, "link": LINK}
