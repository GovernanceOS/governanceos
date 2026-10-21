"""goslint lint REGISTER --pack IDS [--sheet NAME] [--as-of YYYY-MM-DD] [--grace-days N] [--json PATH|-]
goslint packs
goslint ui          the goslint page in your browser, served on this computer only (127.0.0.1)
goslint             at a terminal, a question at a time (so is `goslint lint REGISTER` without --pack)

Exit 0: no errors or warnings. 1: errors or warnings reported. 2: usage or setup error.
Notes and check 4 inform; they do not change the exit code. goslint lint makes no network calls; goslint ui
talks only to your browser on this computer. The one download is the lint extra, offered and installed only on a yes.
"""
import argparse
import datetime
import json
import os
import sys

from . import VERSION, checks, packs, report, workbook
from .packs import SetupError

DESCRIPTION = ("Check an AI or model register spreadsheet against regulator rule packs, on your own machine. "
               "The workbook is read, never written.")


class Result(object):
    pass


def lint(path, pack_ids=None, sheet=None, as_of=None, grace_days=0, data=None):
    """Run the four checks. Raises SetupError for anything that is the caller's to fix. With data, the register's
    bytes are already in memory (goslint ui) and path only names the file."""
    res = Result()
    res.packs = packs.load_many(pack_ids)
    res.all_packs = not pack_ids
    res.register = workbook.read(path) if data is None else workbook.from_bytes(path, data)
    res.layout = checks.locate(res.register, res.packs, sheet)
    res.as_of = as_of or datetime.date.today()
    res.grace_days = grace_days
    res.columns = dict((p.id, checks.map_columns(res.layout, p)) for p in res.packs)
    res.findings = []
    for p in res.packs:
        res.findings += checks.check_fields(res.layout, p, res.columns[p.id])
    review, res.review_info = checks.check_review_dates(res.layout, res.packs, res.columns, res.as_of, grace_days)
    res.findings += review
    res.provenance = checks.check_provenance(res.layout)
    res.provability = checks.check_provability(res.layout)
    return res


def _parser():
    from .. import __version__

    ap = argparse.ArgumentParser(prog="goslint", description=DESCRIPTION)
    ap.add_argument("--version", action="version", version="goslint %s (governanceos %s)" % (VERSION, __version__))
    sub = ap.add_subparsers(dest="command", metavar="{lint,packs,ui}")
    lp = sub.add_parser("lint", help="lint a register (.xlsx, .xlsm or .csv)", description=DESCRIPTION)
    lp.add_argument("register", help="the register file")
    lp.add_argument("--pack", help="comma-separated pack ids, required; 'goslint packs' lists them")
    lp.add_argument("--sheet", help="the sheet that holds the register (default: the most matching headers)")
    lp.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD", help="the date check 2 runs against (default: today)")
    lp.add_argument("--grace-days", dest="grace_days", metavar="N", type=int, default=0,
                    help="days past the next review date before it is reported (default: 0)")
    lp.add_argument("--json", metavar="PATH", help="also write the findings export to PATH; '-' prints only the JSON")
    talk = lp.add_mutually_exclusive_group()
    talk.add_argument("--quiet", action="store_true", help="print the result line only")
    talk.add_argument("--verbose", action="store_true", help="add the column map and every derived cell")
    sub.add_parser("packs", help="list the installed rule packs")
    up = sub.add_parser("ui", help="open the goslint page in your browser, served on this computer only")
    up.add_argument("--no-browser", dest="no_browser", action="store_true", help="print the address; open no browser")
    up.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)  # tests and previews only; 0 = the system picks
    return ap


def _tty():
    """A person at a terminal: both ends are a terminal, so questions can be asked and read."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask_mode(register=None):
    from . import install, interactive

    if not install.offer():
        return 2
    return interactive.run(register)


def _ui(args):
    from . import install, ui

    if _tty():
        if not install.offer():
            return 2
    elif install.missing():
        raise SetupError(packs.EXTRA)
    return ui.serve(open_browser=not args.no_browser, app=ui.App(port=args.port))


def _date(text):
    try:
        if len(text) != 10:
            raise ValueError
        return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:]))
    except ValueError:
        raise SetupError("--as-of must be a date written YYYY-MM-DD, not %r." % text)


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _run(args, out):
    if args.command == "packs":
        out.write(report.pack_list(packs.load_many()))
        return 0
    if args.command == "ui":
        return _ui(args)
    if args.grace_days < 0:
        raise SetupError("--grace-days cannot be negative.")
    as_of = _date(args.as_of) if args.as_of else None
    if args.json and args.json != "-" and _same_file(args.json, args.register):
        raise SetupError("--json names the register itself; goslint never writes to the register.")
    if not args.pack and _tty():
        return _ask_mode(args.register)  # a person at a terminal chooses the packs from lists
    if not args.pack:
        # Packs are chosen, never assumed (D153.4): every pack on a single-jurisdiction register is noise.
        raise SetupError("Choose the rule packs for this register's jurisdictions with --pack, "
                         "for example --pack osfi-e23. Installed packs:\n" + report.pack_list(packs.load_many()).rstrip())
    ids = [i.strip() for i in args.pack.split(",") if i.strip()]
    res = lint(args.register, ids, args.sheet, as_of, args.grace_days)
    s = report.summary(res.findings)
    if args.json:
        text = json.dumps(report.document(res), indent=2, ensure_ascii=False) + "\n"
        if args.json == "-":
            out.write(text)
        else:
            try:
                with open(args.json, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            except OSError as e:
                raise SetupError("cannot write %s: %s" % (args.json, e.strerror or e))
    if args.json != "-":
        out.write(report.result_line(s) + "\n" if args.quiet else report.terminal(res, args.verbose))
        if args.json:
            out.write("Findings  written to %s\n" % args.json)
    return 1 if s["errors"] or s["warnings"] else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    ap = _parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:  # argparse: 2 for a usage error, 0 after --help or --version
        return e.code if isinstance(e.code, int) else 2
    if args.command is None:
        if _tty():
            try:
                return _ask_mode()
            except SetupError as e:
                sys.stderr.write("goslint: %s\n" % e)
                return 2
        ap.print_usage(sys.stderr)
        return 2
    try:
        return _run(args, sys.stdout)
    except SetupError as e:
        sys.stderr.write("goslint: %s\n" % e)
        return 2
