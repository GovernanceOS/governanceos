"""The verifier against the sample pack and its tampered twin (both public at governanceos.si/verify)."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout

from governanceos.verify import key_hash, main

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
GOOD = os.path.join(D, "nebula-mutual-2026Q3.pack.json")
BAD = os.path.join(D, "nebula-mutual-2026Q3-tampered.pack.json")


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["gos-verify"] + list(args))
    return code, out.getvalue()


class Verify(unittest.TestCase):
    def setUp(self):
        with open(GOOD, encoding="utf-8") as f:
            self.kh = key_hash(json.load(f)["public_key"])

    def test_good_pack_verifies_with_the_pinned_key(self):
        code, out = run(GOOD, "--key", self.kh)
        self.assertEqual(code, 0)
        self.assertIn("VERIFIED", out)

    def test_without_a_pinned_key_it_is_not_verified(self):
        code, out = run(GOOD)
        self.assertEqual(code, 1)
        self.assertNotIn("Result: VERIFIED", out)

    def test_tampered_twin_breaks_the_chain(self):
        code, _ = run(BAD, "--key", self.kh)
        self.assertEqual(code, 2)

    def test_a_different_pinned_key_is_refused(self):
        code, _ = run(GOOD, "--key", "0" * 64)
        self.assertEqual(code, 6)


if __name__ == "__main__":
    unittest.main()
