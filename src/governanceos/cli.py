"""Console entry points. verify.py is byte-identical to the download at governanceos.si/verify."""
import sys

from .verify import main


def verify():
    """gos-verify PACK.json --key KEYHASH [--expect HEAD]"""
    raise SystemExit(main(sys.argv))


def lint():
    """goslint lint REGISTER [options]; needs the lint extra: pip install "governanceos[lint]"."""
    from .goslint.cli import main as lint_main

    raise SystemExit(lint_main(sys.argv[1:]))
