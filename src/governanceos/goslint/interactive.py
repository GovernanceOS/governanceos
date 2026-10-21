"""goslint a question at a time, for a person at a terminal: `goslint` on its own, or `goslint lint FILE` without
--pack. Packs are still chosen, never assumed: the person picks them from numbered lists. At the end it prints the
one-line command that runs the same check, so the next run can be scripted. Scripts and pipes never reach this module;
they keep the plain behavior (no --pack lists the packs and exits 2).
"""
import datetime
import json
import os
import shlex

from . import VERSION, report
from .packs import SetupError

STOP = "Stopped. Nothing was changed."


class Quit(Exception):
    pass


def clean_path(text):
    """A path typed, pasted or dragged into a terminal: quotes removed, macOS's escaped spaces restored."""
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    if os.name != "nt":
        s = s.replace("\\ ", " ")
    return os.path.expanduser(s)


def numbers(text, count):
    """Choices like "2", "1,4", "1 4" or "1-3" as zero-based indexes; None when any is not on the list."""
    out = []
    for part in text.replace(",", " ").split():
        if "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            span = range(int(a), int(b) + 1)
        elif part.isdigit():
            span = [int(part)]
        else:
            return None
        for n in span:
            if not 1 <= n <= count:
                return None
            if n - 1 not in out:
                out.append(n - 1)
    return out or None


def quoted(path):
    if os.name == "nt":
        return '"%s"' % path if " " in path else path
    return shlex.quote(path)


class Session(object):
    def __init__(self, ask, out):
        self.ask, self.out = ask, out

    def say(self, text=""):
        self.out.write(text + "\n")

    def question(self, prompt):
        try:
            return self.ask(prompt)
        except (EOFError, KeyboardInterrupt):
            raise Quit()

    def until(self, prompt, accept):
        """Ask until accept(answer) returns (value, None); otherwise say why and ask again."""
        while True:
            answer = self.question(prompt)
            value, why = accept(answer)
            if why is None:
                return value
            self.say("  " + why)


def run(register=None, ask=input, out=None, today=None):
    """Returns goslint's exit code: 0 no errors or warnings, 1 errors or warnings, 2 stopped or a setup problem."""
    import sys

    from . import cli
    from . import packs as P

    s = Session(ask, out or sys.stdout)
    today = today or datetime.date.today()
    try:
        s.say("goslint %s, the GovernanceOS register linter. A few questions, then your report." % VERSION)
        s.say("Press Enter to take the answer in [brackets]. Ctrl+C stops at any time.")
        s.say()

        def file_ok(answer):
            path = clean_path(answer)
            if not path:
                return None, "Type the path of the register, or drag the file into this window."
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".xlsx", ".xlsm", ".csv"):
                return None, "goslint reads .xlsx, .xlsm and .csv files. Save the register as one of these."
            if not os.path.isfile(path):
                return None, "No file at %s. Check the path and try again." % path
            return path, None

        if register:
            path, why = file_ok(register)
            if why:
                s.say("  " + why)
                register = None
        if not register:
            path = s.until("Which register? Type or drag the file here: ", file_ok)

        packs = P.load_many()
        regions = [r for r in report.REGIONS if any(p.region == r for p in packs)]
        s.say()
        s.say("Who supervises this register?")
        for i, r in enumerate(regions, 1):
            n = sum(1 for p in packs if p.region == r)
            s.say("  %d  %-15s %-27s %d pack%s" % (i, report.region_label(r), report.REGION_HINTS.get(r, ""), n,
                                                 "" if n == 1 else "s"))
        def regions_ok(answer):
            chosen = numbers(answer, len(regions))
            return (chosen, None) if chosen else (None, "Type one or more numbers from the list, for example 1 or 1,4.")

        picked = s.until("Choose regions by number, for example 1 or 1,4: ", regions_ok)
        offered = [p for r in [regions[i] for i in picked] for p in packs if p.region == r]
        s.say()
        s.say("Which rule packs?")
        for i, p in enumerate(offered, 1):
            s.say("  %d  %-27s %s (%d fields)" % (i, p.id, p.title.split(": ")[0], len(p.fields)))

        def packs_ok(answer):
            if answer.strip().lower() in ("a", "all"):
                return list(range(len(offered))), None
            chosen = numbers(answer, len(offered))
            return (chosen, None) if chosen else (None, 'Type numbers from the list, or "all" for every pack shown.')

        ids = [offered[i].id for i in s.until('Choose packs by number, or "all" for every pack shown: ', packs_ok)]

        def date_ok(answer):
            text = answer.strip() or today.isoformat()
            try:
                return cli._date(text), None
            except SetupError:
                return None, "Write the date as YYYY-MM-DD, for example %s." % today.isoformat()

        s.say()
        as_of = s.until("Check next review dates as of [%s]: " % today.isoformat(), date_ok)
        s.say()
        res = cli.lint(path, ids, None, as_of, 0)
        s.out.write(report.terminal(res))
        summary = report.summary(res.findings)

        s.say()
        save = s.question("Save the findings as JSON? [y/N] ").strip().lower()
        if save in ("y", "yes"):
            stem = os.path.splitext(os.path.basename(path))[0]
            default = "goslint-findings-%s.json" % stem

            def target_ok(answer):
                target = clean_path(answer) or default
                if cli._same_file(target, path):
                    return None, "That is the register itself; goslint never writes to the register."
                return target, None

            target = s.until("Save as [%s]: " % default, target_ok)
            try:
                with open(target, "w", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(report.document(res), indent=2, ensure_ascii=False) + "\n")
                s.say("Findings written to %s" % target)
            except OSError as e:
                s.say("Could not write %s: %s" % (target, e.strerror or e))

        s.say()
        s.say("The same check in one line, for next time:")
        s.say("  goslint lint %s --pack %s --as-of %s" % (quoted(path), ",".join(ids), as_of.isoformat()))
        return 1 if summary["errors"] or summary["warnings"] else 0
    except Quit:
        s.say()
        s.say(STOP)
        return 2
