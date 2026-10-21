"""goslint ui (the page served to your own browser), the interactive command line and the install offer.
The Nebula Mutual sample is a fictional institution constructed for illustration; any resemblance to a real
organization is unintended. Needs the lint extra: pip install ".[lint]"."""
import contextlib
import http.client
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from governanceos.goslint import cli, install, interactive, report, ui

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(HERE, "data", "nebula-mutual-register.xlsx")
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(ui.__file__)), "ui")


class Server(unittest.TestCase):
    """The four safeguards, against a real server on 127.0.0.1."""

    @classmethod
    def setUpClass(cls):
        cls.app = ui.App()
        cls.thread = threading.Thread(target=cls.app.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        cls.thread.start()
        cls.own = "http://127.0.0.1:%d" % cls.app.port
        cls.base = "/%s/" % cls.app.token

    @classmethod
    def tearDownClass(cls):
        cls.app.server.shutdown()
        cls.app.server.server_close()

    def call(self, method, path, host=None, origin=None, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.app.port, timeout=20)
        h = {"Host": host or "127.0.0.1:%d" % self.app.port}
        if origin:
            h["Origin"] = origin
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data, dict((k.lower(), v) for k, v in r.getheaders())

    def test_1_listens_on_this_computer_only(self):
        self.assertEqual(self.app.server.server_address[0], "127.0.0.1")
        with open(ui.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("0.0.0.0", src)

    def test_2_the_token_is_in_every_address(self):
        self.assertEqual(self.call("GET", self.base)[0], 200)
        self.assertEqual(self.call("GET", "/")[0], 404)
        self.assertEqual(self.call("GET", "/not-the-token/")[0], 404)
        self.assertEqual(self.call("GET", "/not-the-token/catalog")[0], 404)
        self.assertGreaterEqual(len(self.app.token), 32)
        other = ui.App()
        self.assertNotEqual(self.app.token, other.token)  # one-time: a new token each run
        other.server.server_close()

    def test_3_other_hosts_and_origins_are_refused(self):
        self.assertEqual(self.call("GET", self.base, host="evil.example:%d" % self.app.port)[0], 403)
        self.assertEqual(self.call("GET", self.base, host="localhost:%d" % self.app.port)[0], 200)
        self.assertEqual(self.call("POST", self.base + "beat", origin="https://evil.example")[0], 403)
        self.assertEqual(self.call("POST", self.base + "beat")[0], 403)  # a POST must say where it comes from
        self.assertEqual(self.call("POST", self.base + "beat", origin=self.own)[0], 204)

    def test_every_answer_carries_the_policy(self):
        status, body, h = self.call("GET", self.base)
        self.assertIn("connect-src 'self'", h["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", h["content-security-policy"])
        self.assertEqual(h["cache-control"], "no-store")
        self.assertEqual(h["referrer-policy"], "same-origin")
        self.assertIn(b"Check your model register", body)

    def test_the_catalog_and_a_lint_match_the_command_line(self):
        cat = json.loads(self.call("GET", self.base + "catalog")[1])
        self.assertEqual(len(cat["packs"]), 23)
        with open(XLSX, "rb") as f:
            data = f.read()
        status, body, _ = self.call("POST", self.base + "lint?name=nebula-mutual-register.xlsx&packs=osfi-e23&as_of=2026-10-19",
                                    origin=self.own, body=data)
        out = json.loads(body)
        self.assertEqual(out["doc"]["summary"], {"errors": 3, "warnings": 14, "notes": 0})
        self.assertEqual(out["doc"]["workbook"]["file"], "nebula-mutual-register.xlsx")
        res = cli.lint(XLSX, ["osfi-e23"], None, cli._date("2026-10-19"))
        self.assertEqual(out["text"], report.terminal(res))  # the same report as `goslint lint`

    def test_lint_answers_setup_problems_in_words(self):
        status, body, _ = self.call("POST", self.base + "lint?name=old.xls&packs=osfi-e23", origin=self.own, body=b"x")
        self.assertIn("Excel 97-2003", json.loads(body)["error"])
        status, body, _ = self.call("POST", self.base + "lint?name=a.xlsx", origin=self.own, body=b"x")
        self.assertIn("Choose at least one regulator", json.loads(body)["error"])

    def test_a_file_too_large_to_be_a_register_is_refused(self):
        status, _, _ = self.call("POST", self.base + "lint?name=a.xlsx&packs=osfi-e23", origin=self.own, body=b"x",
                                 headers={"Content-Length": str(ui.MAX_BYTES + 1)})
        self.assertEqual(status, 413)


class Stopping(unittest.TestCase):
    def test_when_it_stops(self):
        app = ui.App(heartbeat=10, first_visit=5, goodbye=2)
        t0 = app.started
        self.assertIsNone(app.should_stop(t0 + 1))
        self.assertEqual(app.should_stop(t0 + 6), "the page was never opened")
        app.beat()
        b = app.last_beat
        self.assertIsNone(app.should_stop(b + 9))
        self.assertEqual(app.should_stop(b + 11), "the page stopped answering")
        app.bye()
        self.assertEqual(app.should_stop(app.bye_at + 3), "the page was closed")
        app.bye()
        app.beat()  # a reload says hello again inside the goodbye window
        self.assertIsNone(app.should_stop(app.last_beat + 3))
        app.server.server_close()

    def test_4_closing_the_page_stops_it(self):
        app = ui.App(goodbye=0.2)
        out = io.StringIO()
        t = threading.Thread(target=ui.serve, kwargs={"open_browser": False, "out": out, "app": app}, daemon=True)
        t.start()
        own = "http://127.0.0.1:%d" % app.port
        for path in ("beat", "bye"):
            c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
            c.request("POST", "/%s/%s" % (app.token, path), headers={"Host": "127.0.0.1:%d" % app.port, "Origin": own})
            c.getresponse().read()
            c.close()
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertIn("stopped: the page was closed", out.getvalue())
        self.assertIn(app.url, out.getvalue())


class PageFiles(unittest.TestCase):
    def test_the_page_runs_under_its_policy(self):
        self.assertEqual(sorted(os.listdir(UI_DIR)), ["app.css", "app.js", "index.html", "sample.xlsx"])
        with open(os.path.join(UI_DIR, "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page))  # no inline script
        self.assertIsNone(re.search(r"\sstyle=", page))  # no inline style
        self.assertIn("a fictional institution constructed for illustration", page)
        with open(os.path.join(UI_DIR, "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIsNone(re.search(r"fetch\(\s*['\"]https?:", js))  # it talks only to its own address
        with open(os.path.join(UI_DIR, "sample.xlsx"), "rb") as a, open(XLSX, "rb") as b:
            self.assertEqual(a.read(), b.read())


def answers(*replies):
    it = iter(replies)

    def ask(prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError()
    return ask


class Interactive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.reg = os.path.join(self.tmp, "my register.xlsx")
        shutil.copyfile(XLSX, self.reg)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_a_question_at_a_time(self):
        out = io.StringIO()
        target = os.path.join(self.tmp, "findings.json")
        code = interactive.run(ask=answers(os.path.join(self.tmp, "absent.xlsx"), '"%s"' % self.reg, "9", "1", "2",
                                           "19/10/2026", "2026-10-19", "y", target),
                               out=out, today=cli._date("2026-10-20"))
        text = out.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("No file at", text)  # a wrong path is asked again
        self.assertIn("Type one or more numbers", text)  # so is a region not on the list
        self.assertIn("Write the date as YYYY-MM-DD", text)
        self.assertIn("Check 4  What this spreadsheet cannot prove", text)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["summary"], {"errors": 3, "warnings": 14, "notes": 0})
        self.assertIn("--pack osfi-e23 --as-of 2026-10-19", text)

    def test_enter_takes_today_and_all_takes_every_pack_shown(self):
        out = io.StringIO()
        code = interactive.run(register=self.reg, ask=answers("1", "all", "", "n"), out=out, today=cli._date("2026-10-19"))
        self.assertEqual(code, 1)
        self.assertIn("--pack amf-ai,osfi-e23 --as-of 2026-10-19", out.getvalue())

    def test_ctrl_d_stops_and_changes_nothing(self):
        out = io.StringIO()
        self.assertEqual(interactive.run(ask=answers(), out=out), 2)
        self.assertIn(interactive.STOP, out.getvalue())

    def test_paths_typed_pasted_or_dragged(self):
        self.assertEqual(interactive.clean_path('  "C:/a b/r.xlsx" '), "C:/a b/r.xlsx")
        self.assertEqual(interactive.clean_path("'/tmp/r.xlsx'"), "/tmp/r.xlsx")
        if os.name != "nt":
            self.assertEqual(interactive.clean_path("/tmp/my\\ register.xlsx"), "/tmp/my register.xlsx")
        self.assertEqual(interactive.numbers("1,3", 4), [0, 2])
        self.assertEqual(interactive.numbers("2-4", 4), [1, 2, 3])
        self.assertIsNone(interactive.numbers("5", 4))
        self.assertIsNone(interactive.numbers("x", 4))


class Routing(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_scripts_keep_the_plain_behavior(self):
        code, _, err = self.run_cli("lint", XLSX)  # no terminal here: packs are listed and goslint stops
        self.assertEqual(code, 2)
        self.assertIn("--pack", err)

    def test_a_person_at_a_terminal_is_asked(self):
        with mock.patch.object(cli, "_tty", return_value=True), \
                mock.patch.object(install, "offer", return_value=True), \
                mock.patch.object(interactive, "run", return_value=7) as run:
            self.assertEqual(self.run_cli("lint", XLSX)[0], 7)
            run.assert_called_with(XLSX)
            self.assertEqual(self.run_cli()[0], 7)

    def test_ui_without_the_extra_and_no_terminal_says_how(self):
        with mock.patch.object(install, "missing", return_value=["openpyxl>=3.1"]):
            code, _, err = self.run_cli("ui", "--no-browser")
        self.assertEqual(code, 2)
        self.assertIn('pip install "governanceos[lint]"', err)


class InstallOffer(unittest.TestCase):
    def test_it_asks_before_installing(self):
        out = io.StringIO()
        with mock.patch.object(install, "missing", return_value=["openpyxl>=3.1", "PyYAML>=6.0"]):
            run = mock.Mock(return_value=0)
            self.assertFalse(install.offer(ask=answers("n"), out=out, run=run))
            run.assert_not_called()
            self.assertIn("Nothing installed", out.getvalue())

    def test_a_yes_installs_the_lint_extra_requirements(self):
        out = io.StringIO()
        state = {"missing": ["openpyxl>=3.1", "PyYAML>=6.0"]}
        run = mock.Mock(side_effect=lambda cmd: state.update(missing=[]) or 0)
        with mock.patch.object(install, "missing", side_effect=lambda: state["missing"]):
            self.assertTrue(install.offer(ask=answers(""), out=out, run=run))  # Enter means yes
        run.assert_called_once_with([sys.executable, "-m", "pip", "install", "openpyxl>=3.1", "PyYAML>=6.0"])

    def test_the_requirements_match_the_lint_extra(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            extra = re.search(r'^lint = \[(.*)\]$', f.read(), re.M).group(1)
        self.assertEqual(re.findall(r'"([^"]+)"', extra), [req for _, req in install.NEEDED])

    def test_nothing_to_offer_when_installed(self):
        run = mock.Mock()
        self.assertTrue(install.offer(ask=answers(), out=io.StringIO(), run=run))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
