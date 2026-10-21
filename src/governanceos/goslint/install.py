"""Offer to install the lint extra when it is missing (goslint ui and the interactive command line).

It asks first and installs only on a yes. pip makes the download, into the Python that runs goslint; goslint itself
opens no connection. The two requirements are the ones the lint extra names in pyproject.toml.
"""
import importlib
import importlib.util
import subprocess
import sys

NEEDED = [("openpyxl", "openpyxl>=3.1"), ("yaml", "PyYAML>=6.0")]  # (module, requirement)
LATER = '%s -m pip install "governanceos[lint]"'


def missing():
    return [req for module, req in NEEDED if importlib.util.find_spec(module) is None]


def offer(ask=input, out=None, run=subprocess.call):
    """True when the libraries are there, already or after a yes and an install that worked."""
    out = out or sys.stdout
    need = missing()
    if not need:
        return True
    out.write("goslint needs two libraries to read spreadsheets: openpyxl and PyYAML.\n"
              "pip can install them from PyPI into this Python (%s).\n" % sys.executable)
    try:
        answer = ask("Install them now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer not in ("", "y", "yes"):
        out.write("Nothing installed. To install them later: %s\n" % (LATER % sys.executable))
        return False
    out.write("Installing %s with pip...\n" % ", ".join(need))
    code = run([sys.executable, "-m", "pip", "install"] + need)
    importlib.invalidate_caches()
    if code != 0 or missing():
        out.write("The install did not finish. Try it yourself: %s\n" % (LATER % sys.executable))
        return False
    out.write("Installed.\n\n")
    return True
