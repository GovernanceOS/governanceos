"""goslint ui: the goslint page, served to your own browser on this computer.

His ruling (21 Oct 2026), after the research and the persona walkthrough: the page served on the user's own computer,
with four safeguards.
  1. It listens only on 127.0.0.1, on a port the system picks, and opens no outbound connection.
  2. A one-time secret token is part of every address. A request without it is answered 404.
  3. A request whose Host is not 127.0.0.1 or localhost on this port is refused, and so is a POST from another
     origin or with no origin (defenses against DNS rebinding and cross-site requests).
  4. It stops when the page is closed: the page says goodbye, and a heartbeat covers a crash. Ctrl+C stops it too.
The register travels from your browser to this process in memory and is read by the same code as `goslint lint`.
Nothing is written to disk, and no request is logged.
"""
import datetime
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION, report
from .packs import SetupError

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
FILES = {"": "index.html", "index.html": "index.html", "app.js": "app.js", "app.css": "app.css",
         "sample.xlsx": "sample.xlsx"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "form-action 'none'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
MAX_BYTES = 50 * 1024 * 1024  # a register larger than this is not a register
HEARTBEAT = 20  # seconds without a beat before the server stops; the page beats every 5
FIRST_VISIT = 600  # seconds to wait for the browser to open the page at all
GOODBYE = 4  # seconds after the page says goodbye, so a reload can say hello again


class App(object):
    def __init__(self, port=0, heartbeat=HEARTBEAT, first_visit=FIRST_VISIT, goodbye=GOODBYE):
        self.token = secrets.token_urlsafe(24)
        self.heartbeat, self.first_visit, self.goodbye = heartbeat, first_visit, goodbye
        self.started = time.time()
        self.last_beat = None
        self.bye_at = None
        self.server = ThreadingHTTPServer(("127.0.0.1", port), _handler(self))
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.hosts = {"127.0.0.1:%d" % self.port, "localhost:%d" % self.port}
        self.origins = {"http://" + h for h in self.hosts}
        self.stopped = threading.Event()
        self.reason = "Ctrl+C"

    @property
    def url(self):
        return "http://127.0.0.1:%d/%s/" % (self.port, self.token)

    def beat(self):
        self.last_beat = time.time()
        self.bye_at = None

    def bye(self):
        self.bye_at = time.time()

    def should_stop(self, now=None):
        now = now or time.time()
        if self.bye_at is not None and now - self.bye_at > self.goodbye:
            return "the page was closed"
        if self.last_beat is None:
            return "the page was never opened" if now - self.started > self.first_visit else None
        if now - self.last_beat > self.heartbeat:
            return "the page stopped answering"
        return None

    def watch(self):
        while not self.stopped.wait(0.5):
            why = self.should_stop()
            if why:
                self.reason = why
                self.server.shutdown()
                return

    def stop(self):
        self.stopped.set()
        self.server.shutdown()


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "goslint"
        sys_version = ""

        def log_message(self, *args):  # addresses carry the token, and file names are the register's
            pass

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")  # the token never leaves in a referrer; beacons keep their origin
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _route(self):
            """The path after the token, or None after a refusal has been sent."""
            if self.headers.get("Host", "") not in app.hosts:
                self._send(403, b"Refused: goslint ui answers only on this computer.")
                return None
            origin = self.headers.get("Origin")
            if self.command == "POST" and origin not in app.origins:
                self._send(403, b"Refused: another site cannot talk to goslint ui.")
                return None
            parts = urllib.parse.urlsplit(self.path).path.split("/")
            if len(parts) < 3 or not secrets.compare_digest(parts[1], app.token):
                self._send(404, b"Not found.")
                return None
            return "/".join(parts[2:])

        def do_GET(self):
            rest = self._route()
            if rest is None:
                return
            if rest == "catalog":
                return self._send(200, json.dumps(catalog()).encode("utf-8"), "application/json")
            name = FILES.get(rest)
            if name is None:
                return self._send(404, b"Not found.")
            with open(os.path.join(HERE, name), "rb") as f:
                self._send(200, f.read(), TYPES[os.path.splitext(name)[1]])

        def do_POST(self):
            rest = self._route()
            if rest is None:
                return
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_BYTES:
                return self._send(413, b"That file is too large to be a register.")
            body = self.rfile.read(size) if size else b""
            if rest == "beat":
                app.beat()
                return self._send(204)
            if rest == "bye":
                app.bye()
                return self._send(204)
            if rest == "lint":
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self._send(200, json.dumps(run(body, query)).encode("utf-8"), "application/json")
            return self._send(404, b"Not found.")

    return Handler


def catalog():
    from . import packs as P
    from .. import __version__

    return {"goslint": VERSION, "package": __version__, "regions": report.REGIONS, "hints": report.REGION_HINTS,
            "packs": [{"id": p.id, "title": p.title, "region": p.region, "fields": len(p.fields),
                       "counts": dict(p.counts())} for p in P.load_many()]}


def run(data, query):
    """Lint the bytes the page sent; the name only says which format they are in."""
    from . import cli

    name = os.path.basename((query.get("name") or ["register.xlsx"])[0]) or "register.xlsx"
    ids = [i for i in (query.get("packs") or [""])[0].split(",") if i]
    if not ids:
        return {"error": "Choose at least one regulator first."}
    try:
        as_of = cli._date((query.get("as_of") or [datetime.date.today().isoformat()])[0])
        res = cli.lint(name, ids, None, as_of, 0, data=data)
    except SetupError as e:
        return {"error": str(e)}
    return {"doc": report.document(res), "text": report.terminal(res)}


def serve(open_browser=True, out=None, app=None):
    out = out or sys.stdout
    app = app or App()
    out.write("goslint %s is open in your browser at\n  %s\n" % (VERSION, app.url))
    out.write("It runs on this computer only. Close the page to stop, or press Ctrl+C here.\n")
    out.flush()
    threading.Thread(target=app.watch, daemon=True).start()
    if open_browser:
        try:
            webbrowser.open(app.url)
        except Exception:
            out.write("Open the address above in your browser.\n")
    try:
        app.server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.stopped.set()
        app.server.server_close()
    out.write("goslint ui stopped: %s.\n" % app.reason)
    return 0
