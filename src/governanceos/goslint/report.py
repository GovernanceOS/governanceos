"""Output: the terminal report and the JSON findings export (schema goslint-findings/1)."""
import datetime

from . import VERSION
from .checks import letter
from .packs import BASES, VERB

SCHEMA = "goslint-findings/1"
LABEL = {"error": "ERROR", "warning": "WARNING", "note": "NOTE"}


def summary(findings):
    return {"errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            "notes": sum(1 for f in findings if f["severity"] == "note")}


def document(res):
    from .. import __version__

    lay, reg = res.layout, res.register
    workbook = {"file": reg.file, "format": reg.format, "sha256": reg.sha256, "sheet": lay.sheet.name,
                "header_row": lay.header_index + 1, "entries": len(lay.rows)}
    if reg.note:
        workbook["note"] = reg.note
    packs = []
    for p in res.packs:
        cols = res.columns[p.id]
        packs.append({"id": p.id, "title": p.title, "region": p.region, "instrument_version": p.instrument_version,
                      "read": p.read, "source": p.source, "fields": len(p.fields), "fields_with_column": len(cols),
                      "columns": dict((f.id, letter(cols[f.id]) if f.id in cols else None) for f in p.fields)})
    return {
        "schema": SCHEMA,
        "tool": "goslint %s" % VERSION,
        "package": "governanceos %s" % __version__,
        "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": res.as_of.isoformat(),
        "grace_days": res.grace_days,
        "workbook": workbook,
        "packs": packs,
        "summary": summary(res.findings),
        "findings": res.findings,
        "next_review_dates": res.review_info,
        "provenance": res.provenance,
        "provability": res.provability,
    }


def _line(f):
    where = "" if f["row"] is None else "Row %d, %s: " % (f["row"], f["entry"])
    cite = ""
    if f["citation"]:
        cite = " %s %s." % (VERB[f["basis"]], f["citation"])
    return "    %-8s %s%s%s" % (LABEL[f["severity"]], where, f["message"], cite)


def terminal(res, verbose=False):
    lay, reg = res.layout, res.register
    s = summary(res.findings)
    out = ["goslint %s, the GovernanceOS register linter" % VERSION, ""]
    out.append("Workbook  %s" % reg.file + (" (%s)" % reg.note if reg.note else ""))
    out.append("SHA-256   %s (the file as read now)" % reg.sha256)
    out.append("Sheet     %s, header row %d, %d entr%s (%s)" % (
        lay.sheet.name, lay.header_index + 1, len(lay.rows), "y" if len(lay.rows) == 1 else "ies", lay.chosen_by))
    out.append("As of     %s, grace %d day%s" % (res.as_of.isoformat(), res.grace_days, "" if res.grace_days == 1 else "s"))
    out.append("Packs     %s" % ", ".join("%s (instrument %s, read %s)" % (p.id, p.instrument_version, p.read)
                                         for p in res.packs))
    if res.all_packs and len(res.packs) > 1:
        out.append("          Every installed pack ran. Name the ones that apply to you with --pack.")

    out += ["", "Check 1  Missing fields"]
    for p in res.packs:
        cols = res.columns[p.id]
        counts = ", ".join("%d %s" % (n, b) for b, n in p.counts() if n)
        out.append("  %s: %s" % (p.id, p.title))
        out.append("    %d of %d fields have a column (%s)." % (len(cols), len(p.fields), counts))
        if verbose:
            for f in p.fields:
                c = cols.get(f.id)
                out.append("      %-26s %s" % (f.id, "column %s \"%s\"" % (letter(c), lay.headers[c]) if c is not None else "no column"))
        mine = [f for f in res.findings if f["check"] == "missing_field" and f["pack"] == p.id]
        out += [_line(f) for f in mine] or ["    No missing fields."]

    out += ["", "Check 2  Next review date"]
    if not res.review_info:
        out.append("  None of these packs names a next review date.")
    for i in res.review_info:
        if i["column"] is None:
            out.append("  %s: no column for \"%s\" (reported under check 1)." % (i["pack"], i["label"]))
            continue
        out.append("  %s: column %s \"%s\"" % (i["pack"], i["column"], i["header"]))
        mine = [f for f in res.findings if f["check"] == "review_date" and f["pack"] == i["pack"]]
        out += [_line(f) for f in mine] or ["    No next review date is past or unreadable."]

    out += ["", "Check 3  Typed or derived"]
    prov = res.provenance
    if not prov["available"]:
        out.append("  " + prov["reason"])
    else:
        out.append("  %d typed, %d derived by formula, %d blank, across %d entries." % (
            prov["typed"], prov["derived"], prov["blank"], len(lay.rows)))
        for col in prov["columns"]:
            if col["derived"] or verbose:
                line = "    Column %s \"%s\": %d typed, %d derived, %d blank" % (
                    col["column"], col["header"], col["typed"], col["derived"], col["blank"])
                if col["derived_cells"] and (verbose or len(col["derived_cells"]) <= 10):
                    line += " (derived: %s)" % ", ".join(col["derived_cells"])
                out.append(line)
        if not prov["derived"]:
            out.append("    No cell in the register is derived by a formula.")
        out.append("  " + prov["caveat"])

    pv = res.provability
    out += ["", "Check 4  What this spreadsheet cannot prove"]
    out += ["  " + line for line in pv["findings"]]
    n = pv["entries_affected"]
    out.append("  %s %d entr%s in this register %s affected. %s" % (
        "All" if n != 1 else "The", n, "y" if n == 1 else "ies", "is" if n == 1 else "are", pv["statement"]))
    out.append("  " + pv["link"])

    out += ["", result_line(s)]
    return "\n".join(out) + "\n"


def result_line(s):
    code = 1 if s["errors"] or s["warnings"] else 0
    return "Result    %d error%s, %d warning%s, %d note%s (exit %d)" % (
        s["errors"], "" if s["errors"] == 1 else "s", s["warnings"], "" if s["warnings"] == 1 else "s",
        s["notes"], "" if s["notes"] == 1 else "s", code)


REGIONS = ["Canada", "United States", "GCC, six states", "European Union", "United Kingdom", "Switzerland",
           "Asia-Pacific"]
# The regulators a person looks for in each region, for the interactive lists and goslint ui.
REGION_HINTS = {"Canada": "AMF, OSFI", "United States": "NIST, Colorado", "GCC, six states": "CBUAE, QCB",
                "European Union": "ECB, ESMA, EU AI Act", "United Kingdom": "PRA", "Switzerland": "FINMA",
                "Asia-Pacific": "Australia, China, MAS, RBI"}


def region_label(region):
    return "GCC" if region == "GCC, six states" else region


def _counts(pairs):
    return ", ".join("%d %s" % (n, b) for b, n in pairs if n)


def pack_list(packs):
    """The packs grouped by region, in the order of the GovernanceOS regulation rows, then a total line."""
    rank = dict((r, i) for i, r in enumerate(REGIONS))
    out, region, totals = [], None, dict((b, 0) for b in BASES)
    for p in sorted(packs, key=lambda p: (rank.get(p.region, len(REGIONS)), p.region, p.id)):
        if p.region != region:
            region = p.region
            out += [""] if out else []
            out.append(region)
        out.append("  %s  %s" % (p.id, p.title))
        out.append("      instrument %s; read %s; %d fields (%s)" % (p.instrument_version, p.read, len(p.fields),
                                                                   _counts(p.counts())))
        out.append("      %s" % p.source)
        for b, n in p.counts():
            totals[b] += n
    out += ["", "%d packs, %d fields (%s)" % (len(packs), sum(totals.values()), _counts((b, totals[b]) for b in BASES))]
    return "\n".join(out) + "\n"

