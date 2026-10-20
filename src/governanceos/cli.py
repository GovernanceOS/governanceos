"""Console entry points. verify.py is byte-identical to the download at governanceos.si/verify."""
import sys

from .verify import main


def verify():
    """gos-verify PACK.json --key KEYHASH [--expect HEAD]"""
    raise SystemExit(main(sys.argv))
