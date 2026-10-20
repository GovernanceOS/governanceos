"""goslint against the Nebula Mutual sample register (a fictional institution constructed for illustration;
any resemblance to a real organization is unintended). Needs the lint extra: pip install ".[lint]".
The register is built by tests/data/make_sample_register.py."""
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from governanceos.goslint import packs as P
from governanceos.goslint.checks import CLOSING, LINK, to_date
from governanceos.goslint.cli import main

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(HERE, "data", "nebula-mutual-register.xlsx")
CSV = os.path.join(HERE, "data", "nebula-mutual-register.csv")
GOSLINT = os.path.dirname(os.path.abspath(P.__file__))
AS_OF = "2026-10-19"


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


def lint_json(*args):
    code, out, err = run("lint", *(list(args) + ["--json", "-"]))
    return code, json.loads(out) if out else None


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def by_cell(doc):
    return dict((f["cell"], f) for f in doc["findings"] if f["cell"])


class Packs(unittest.TestCase):
    def test_the_shipped_packs(self):
        self.assertEqual(P.available(), ["eu-aia-annex8-a", "eu-aia-annex8-b", "eu-aia-annex8-c", "osfi-e23"])

    def test_osfi_e23_is_appendix_1_six_required_eleven_expected(self):
        p = P.load("osfi-e23")
        self.assertIn("Appendix 1", p.title)
        self.assertEqual(dict(p.counts()), {"required": 6, "expected": 11, "recommended": 0})
        self.assertEqual([f.basis for f in p.fields[:6]], ["required"] * 6)
        self.assertTrue(all(f.citation.startswith("E-23 Appendix 1") for f in p.fields))
        self.assertEqual(p.next_review_field, "next_review_date")
        self.assertEqual(p.field("next_review_date").basis, "expected")

    def test_annex_viii_sections_a_b_c(self):
        a, b, c = (P.load("eu-aia-annex8-" + s) for s in "abc")
        self.assertEqual(dict(a.counts()), {"required": 12, "expected": 0, "recommended": 1})
        self.assertIn("item 13 (optional)", a.fields[-1].citation)
        self.assertEqual(len(b.fields), 7)
        items = [int(re.search(r"item (\d+)", f.citation).group(1)) for f in b.fields]
        self.assertEqual(items, [1, 2, 3, 4, 5, 6, 8])  # points 7 and 9 deleted by Regulation (EU) 2026/1744
        self.assertEqual(len(c.fields), 5)
        for p in (a, b, c):
            self.assertIsNone(p.next_review_field)

    def test_every_field_carries_basis_and_citation(self):
        for p in P.load_many():
            self.assertTrue(p.source.startswith("http"), p.id)
            self.assertEqual(p.read, "2026-10-19")
            for f in p.fields:
                self.assertIn(f.basis, P.BASES)
                self.assertTrue(f.citation.strip())
                self.assertTrue(f.keys)

    def test_a_malformed_pack_is_refused(self):
        with open(os.path.join(GOSLINT, "packs", "osfi-e23.yaml"), encoding="utf-8") as f:
            d = P._yaml().safe_load(f)
        del d["fields"][0]["basis"]
        with self.assertRaises(P.SetupError):
            P._check("osfi-e23", d)


class SampleRegister(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.doc = lint_json(XLSX, "--pack", "osfi-e23", "--as-of", AS_OF)
        cls.cells = by_cell(cls.doc)

    def test_exit_code_and_summary(self):
        self.assertEqual(self.code, 1)
        self.assertEqual(self.doc["schema"], "goslint-findings/1")
        self.assertEqual(self.doc["summary"], {"errors": 3, "warnings": 14, "notes": 0})

    def test_sheet_header_and_hash(self):
        w = self.doc["workbook"]
        self.assertEqual((w["sheet"], w["header_row"], w["entries"]), ("Model inventory", 3, 7))
        self.assertEqual(w["file"], "nebula-mutual-register.xlsx")  # the name only, never the path
        self.assertEqual(w["sha256"], sha(XLSX))

    def test_check_1_missing_columns(self):
        cols = [f for f in self.doc["findings"] if f["kind"] == "column"]
        self.assertEqual(sorted(f["field"] for f in cols), ["model_dependencies", "model_limitations"])
        self.assertTrue(all(f["severity"] == "warning" and f["basis"] == "expected" for f in cols))

    def test_check_1_empty_cells_and_placeholders(self):
        rating, developer = self.cells["D9"], self.cells["F9"]
        self.assertEqual((rating["severity"], rating["field"], rating["entry"]),
                         ("error", "model_risk_rating", "Policy lapse prediction"))
        self.assertIn("is empty", rating["message"])
        self.assertEqual(rating["citation"], "E-23 Appendix 1, minimum")
        self.assertIn('placeholder ("TBD")', developer["message"])
        self.assertEqual(self.cells["K6"]["severity"], "warning")  # expected field, model not yet approved

    def test_check_2_overdue_and_unreadable(self):
        overdue = [f for f in self.doc["findings"] if f["kind"] == "overdue"]
        self.assertEqual([f["cell"] for f in overdue], ["P7"])
        self.assertIn("34 days past", overdue[0]["message"])
        self.assertEqual(overdue[0]["severity"], "error")
        self.assertIn("ambiguous (2027-04-03 or 2027-03-04)", self.cells["P8"]["message"])
        self.assertIn("not a date", self.cells["P10"]["message"])
        self.assertEqual(self.cells["P10"]["severity"], "warning")

    def test_an_empty_review_date_is_reported_once(self):
        p9 = [f for f in self.doc["findings"] if f["cell"] == "P9"]
        self.assertEqual([f["check"] for f in p9], ["missing_field"])

    def test_check_3_typed_and_derived(self):
        prov = self.doc["provenance"]
        self.assertTrue(prov["available"])
        p = [c for c in prov["columns"] if c["column"] == "P"][0]
        self.assertEqual((p["typed"], p["derived"], p["blank"], p["derived_cells"]), (4, 2, 1, ["P5", "P6"]))
        self.assertEqual(prov["derived"], 2)
        self.assertNotIn("P5", self.cells)  # derived dates in the future are not findings
        self.assertNotIn("P6", self.cells)

    def test_check_4_provability(self):
        pv = self.doc["provability"]
        self.assertEqual((pv["history"], pv["signers"], pv["hashes"]), (False, False, False))
        self.assertEqual(pv["entries_affected"], 7)
        self.assertEqual((pv["statement"], pv["link"]), (CLOSING, LINK))

    def test_grace_days_and_as_of(self):
        def overdue(*extra):
            _, doc = lint_json(XLSX, "--pack", "osfi-e23", *extra)
            return [f["cell"] for f in doc["findings"] if f["kind"] == "overdue"]

        self.assertEqual(overdue("--as-of", AS_OF, "--grace-days", "33"), ["P7"])
        self.assertEqual(overdue("--as-of", AS_OF, "--grace-days", "34"), [])
        self.assertEqual(overdue("--as-of", "2026-09-15"), [])
        self.assertEqual(overdue("--as-of", "2027-08-22"), ["P4", "P5", "P6", "P7"])


class Terminal(unittest.TestCase):
    def test_report_closes_with_check_4_and_the_link(self):
        code, out, _ = run("lint", XLSX, "--pack", "osfi-e23", "--as-of", AS_OF)
        self.assertEqual(code, 1)
        for text in ("Check 1  Missing fields", "Check 2  Next review date", "Check 3  Typed or derived",
                     "Check 4  What this spreadsheet cannot prove", CLOSING, LINK):
            self.assertIn(text, out)
        self.assertLess(out.index(CLOSING), out.index(LINK))
        self.assertTrue(out.rstrip().endswith("Result    3 errors, 14 warnings, 0 notes (exit 1)"))

    def test_quiet_and_verbose(self):
        _, out, _ = run("lint", XLSX, "--pack", "osfi-e23", "--as-of", AS_OF, "--quiet")
        self.assertEqual(out.strip().splitlines(), ["Result    3 errors, 14 warnings, 0 notes (exit 1)"])
        _, out, _ = run("lint", XLSX, "--pack", "osfi-e23", "--as-of", AS_OF, "--verbose")
        self.assertIn('next_review_date           column P "Next review date"', out)

    def test_default_runs_every_pack_and_says_so(self):
        code, out, _ = run("lint", XLSX, "--as-of", AS_OF)
        self.assertEqual(code, 1)
        self.assertIn("Every installed pack ran", out)
        _, doc = lint_json(XLSX, "--as-of", AS_OF)
        self.assertEqual([p["id"] for p in doc["packs"]], P.available())

    def test_packs_command(self):
        code, out, _ = run("packs")
        self.assertEqual(code, 0)
        self.assertIn("osfi-e23  OSFI Guideline E-23 (2027), Appendix 1", out)
        self.assertIn("17 fields (6 required, 11 expected)", out)


class CsvRegister(unittest.TestCase):
    def test_csv_gives_the_same_check_1_and_2_findings(self):
        _, x = lint_json(XLSX, "--pack", "osfi-e23", "--as-of", AS_OF)
        code, c = lint_json(CSV, "--pack", "osfi-e23", "--as-of", AS_OF)
        self.assertEqual(code, 1)

        def key(doc):
            return [(f["check"], f["kind"], f["field"], f["row"], f["severity"]) for f in doc["findings"]]

        self.assertEqual(key(c), key(x))
        self.assertEqual(c["workbook"]["format"], "csv")

    def test_csv_has_no_check_3(self):
        _, c = lint_json(CSV, "--pack", "osfi-e23", "--as-of", AS_OF)
        self.assertFalse(c["provenance"]["available"])
        self.assertIn("keeps no formulas", c["provenance"]["reason"])


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmp):
            os.chmod(os.path.join(self.tmp, name), stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(self.tmp)

    def test_never_writes_to_the_register(self):
        reg = os.path.join(self.tmp, "register.xlsx")
        shutil.copyfile(XLSX, reg)
        os.chmod(reg, stat.S_IREAD)
        before = (sha(reg), os.stat(reg).st_mtime_ns)
        code, _, _ = run("lint", reg, "--as-of", AS_OF, "--json", os.path.join(self.tmp, "findings.json"))
        self.assertEqual(code, 1)
        self.assertEqual((sha(reg), os.stat(reg).st_mtime_ns), before)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["findings.json", "register.xlsx"])

    def test_json_cannot_name_the_register(self):
        reg = os.path.join(self.tmp, "register.xlsx")
        shutil.copyfile(XLSX, reg)
        before = sha(reg)
        code, _, err = run("lint", reg, "--json", reg)
        self.assertEqual(code, 2)
        self.assertIn("never writes to the register", err)
        self.assertEqual(sha(reg), before)

    def test_runs_with_the_network_cut(self):
        def refuse(*a, **k):
            raise AssertionError("goslint tried to use the network")

        with mock.patch("socket.socket", side_effect=refuse), mock.patch("socket.create_connection", refuse), \
                mock.patch("socket.getaddrinfo", refuse):
            code, out, _ = run("lint", XLSX, "--as-of", AS_OF)
        self.assertEqual(code, 1)
        self.assertIn(CLOSING, out)

    def test_holds_no_network_code(self):
        net = re.compile(r"^\s*(import|from)\s+(socket|ssl|urllib|http|requests|httpx|ftplib|smtplib)\b", re.M)
        for name in os.listdir(GOSLINT):
            if name.endswith(".py"):
                with open(os.path.join(GOSLINT, name), encoding="utf-8") as f:
                    self.assertIsNone(net.search(f.read()), name)

    def test_usage_errors_exit_2(self):
        old = os.path.join(self.tmp, "old.xls")
        open(old, "wb").close()
        cases = [
            (["lint", os.path.join(self.tmp, "absent.xlsx")], "cannot read"),
            (["lint", old], "Excel 97-2003"),
            (["lint", XLSX, "--as-of", "19/10/2026"], "YYYY-MM-DD"),
            (["lint", XLSX, "--sheet", "Nowhere"], "no sheet named"),
            (["lint", XLSX, "--pack", "naic-ai-bulletin"], "unknown pack"),
            (["lint", XLSX, "--grace-days", "-1"], "cannot be negative"),
        ]
        for args, said in cases:
            code, _, err = run(*args)
            self.assertEqual(code, 2, args)
            self.assertIn(said, err, args)
        self.assertEqual(run()[0], 2)

    def test_a_complete_register_exits_0(self):
        p = P.load("osfi-e23")
        reg = os.path.join(self.tmp, "complete.csv")
        with open(reg, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([fl.label for fl in p.fields])
            w.writerow(["2027-01-31" if fl.id.endswith("date") else "x" for fl in p.fields])
        code, doc = lint_json(reg, "--pack", "osfi-e23", "--as-of", AS_OF)
        self.assertEqual(code, 0)
        self.assertEqual(doc["summary"], {"errors": 0, "warnings": 0, "notes": 0})
        self.assertEqual(doc["packs"][0]["fields_with_column"], 17)


class Dependencies(unittest.TestCase):
    def py(self, code):
        return subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_gos_verify_loads_no_lint_dependency(self):
        r = self.py("import sys, governanceos, governanceos.cli, governanceos.verify\n"
                    "bad = [m for m in ('openpyxl', 'yaml') if m in sys.modules]\n"
                    "sys.exit(len(bad))")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_the_extra_goslint_says_how_to_install_it(self):
        r = self.py("import sys\nsys.modules['yaml'] = None\nsys.modules['openpyxl'] = None\n"
                    "from governanceos.goslint.cli import main\n"
                    "sys.exit(main(['lint', %r, '--pack', 'osfi-e23']))" % XLSX)
        self.assertEqual(r.returncode, 2)
        self.assertIn('pip install "governanceos[lint]"', r.stderr)


class Dates(unittest.TestCase):
    def test_reads_dates_without_guessing(self):
        import datetime

        d = datetime.date
        self.assertEqual(to_date(datetime.datetime(2026, 9, 15, 0, 0))[0], d(2026, 9, 15))
        for text in ("2026-09-15", "2026/09/15", "15 September 2026", "15 Sep 2026", "September 15, 2026",
                     "Sept 15 2026", "15/09/2026", "09/15/2026", "2026-09-15 00:00:00"):
            self.assertEqual(to_date(text), (d(2026, 9, 15), None), text)
        self.assertEqual(to_date("05/05/2027"), (d(2027, 5, 5), None))
        self.assertEqual(to_date("03/04/2027"), (None, "ambiguous (2027-04-03 or 2027-03-04)"))
        self.assertEqual(to_date("2026-02-30"), (None, "not a valid date"))
        self.assertEqual(to_date(46280), (None, "a number, not a date"))
        self.assertEqual(to_date("Q1 2027"), (None, "not a date"))


class Guards(unittest.TestCase):
    """Words that never ship in this repository (built from pieces so this file passes its own scan)."""

    BANNED = [
        ("configuration " + "fingerprint", re.I), ("execution " + "state", re.I), ("four" + "-input", re.I),
        ("seven " + "states", re.I), ("Hand" + "book", re.I), ("Enterprise " + "Playbook", re.I),
        ("Na" + "beel", 0), ("i" + "Systematic", re.I), ("\\$\\s?\\d", 0), (chr(0x2014), 0),
    ]

    def test_no_banned_words(self):
        roots = [os.path.join(ROOT, d) for d in ("src", "tests", "tools", ".github")]
        files = [os.path.join(ROOT, n) for n in ("README.md", "NOTICE", "pyproject.toml")]
        for r in roots:
            for dirpath, _, names in os.walk(r):
                files += [os.path.join(dirpath, n) for n in names
                          if os.path.splitext(n)[1] in (".py", ".yaml", ".yml", ".json", ".csv", ".md", ".toml")]
        self.assertTrue(any(f.endswith("osfi-e23.yaml") for f in files))
        for path in files:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for pattern, flags in self.BANNED:
                self.assertIsNone(re.search(pattern, text, flags), "%s in %s" % (pattern, path))


if __name__ == "__main__":
    unittest.main()
