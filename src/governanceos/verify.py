#!/usr/bin/env python3
# GovernanceOS pack verifier 1.2.1
# Copyright 2026 GovernanceOS. Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License. You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the License is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# What it does, offline, with Python 3 and nothing else installed:
#   1. recomputes the SHA-256 hash of every record, checks each one links to the record before it, and checks the
#      positions run without a gap;
#   2. checks the Ed25519 signature (RFC 8032, pure Python below) over the whole pack: the header, every record and
#      the summaries. Only the anchors are outside it, because they are added later and checked online;
#   3. prints the signing key's hash (SHA-256 of the public key) and compares it with the one the institution sent
#      you separately (--key), and compares the head with a head it sent you (--expect);
#   4. says plainly that the public anchor was not checked, because it needs a network.
# The key inside a pack proves nothing on its own: anyone can change or shorten a pack, rebuild the chain and sign it
# with a key of their own. Only the pack key hash, received by another route, ties the pack to the institution, so
# the result is VERIFIED only when --key matches. A head alone shows the records end there, not that nothing earlier
# was left out.
# What it proves: the pack was not changed after the key you pinned signed it.
# What it does not prove: that the records were true when they were written.
#
# Usage:  python gos-verify.py PACK.json --key KEYHASH [--expect HEAD]
# Exit:   0 verified (intact, signed by the pinned key) · 1 intact but the signer is not pinned · 2 chain broken
#         3 signature invalid · 4 head differs from --expect · 5 cannot be read · 6 key differs from --key
import hashlib, json, sys, unicodedata

VERSION = "1.2.1"
MAX_BYTES = 200 * 1024 * 1024  # a pack larger than this is refused, unread

# ---- Ed25519 verification, after the reference code in RFC 8032, section 6 ----
_p = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _inv(x):
    return pow(x, _p - 2, _p)


def _recover_x(y, sign):
    if y >= _p:
        return None
    x2 = (y * y - 1) * _inv(_d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _I % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


_gy = 4 * _inv(5) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _decompress(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def ed25519_verify(public, message, signature):
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    R = _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))


# ---- the pack ----
UNSIGNED = ("signature", "anchors", "anchors_note", "verifier")  # anchors: added later, checked online; verifier: checked by its own SHA-256
HEX = set("0123456789abcdef")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(prev_hash, record):
    return hashlib.sha256(bytes.fromhex(prev_hash) + canonical(record)).hexdigest()


def signed_message(pack):
    """Everything the institution signs: the whole pack except the signature and the anchors."""
    return canonical({k: v for k, v in pack.items() if k not in UNSIGNED})


def key_hash(public_hex):
    """SHA-256 of the raw 32-byte public key, as 64 lowercase hex characters."""
    return hashlib.sha256(bytes.fromhex(public_hex)).hexdigest()


def _grouped(h):
    return " ".join(h[i:i + 8] for i in range(0, len(h), 8))


def clean(v, limit=400):
    """Pack text as it may be printed: no control or direction characters, so a pack cannot write its own result lines."""
    t = "".join("?" if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in str(v))
    return t if len(t) <= limit else t[:limit] + "…"


USAGE = "Usage: python gos-verify.py PACK.json --key KEYHASH [--expect HEAD]"
HELP = USAGE + """
  --key KEYHASH   the pack key hash the institution sent you by another route (64 hex characters, or at least 32)
  --expect HEAD   a chain head the institution sent you (64 hex characters); optional
Exit: 0 verified · 1 signer not pinned · 2 chain broken · 3 signature invalid · 4 head differs · 5 cannot be read · 6 key differs"""


def _option(args, name):
    """The value after name. A value pasted in groups of eight (as the pages show it) is read whole."""
    if name not in args:
        return None, True
    i = args.index(name)
    if i + 1 >= len(args):
        return None, False
    v = args[i + 1].strip().lower().replace(" ", "").replace("sha256:", "")
    j = i + 2
    while len(v) < 64 and j < len(args) and len(args[j]) == 8 and all(c in HEX for c in args[j].lower()):
        v += args[j].lower(); j += 1
    del args[i:j]
    return v, True


def _strict_object(pairs):
    """A JSON object with a repeated key is refused: two readers could see two different packs."""
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key appears twice")
    return dict(pairs)


def _no_constant(name):
    raise ValueError("NaN or Infinity is not a number in a pack")


def main(argv):
    try:  # a non-ASCII issuer line must never turn a good pack into an unreadable one on a redirected console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = [a for a in argv[1:]]
    if any(a in ("-h", "--help") for a in args):
        print(HELP); return 0
    expect, ok1 = _option(args, "--expect")
    pin, ok2 = _option(args, "--key")
    if not (ok1 and ok2) or len(args) != 1:
        print(USAGE); return 5
    if pin is not None and (len(pin) < 32 or len(pin) > 64 or any(c not in HEX for c in pin)):
        print("Key: give the pack key hash you were sent, 64 hexadecimal characters (at least 32)."); print(USAGE); return 5
    if expect is not None and (len(expect) != 64 or any(c not in HEX for c in expect)):
        print("Head: give the chain head you were sent, 64 hexadecimal characters."); print(USAGE); return 5
    print(f"GovernanceOS pack verifier {VERSION} (Apache-2.0)")
    try:
        return _verify(args[0], pin, expect)
    except Exception as e:  # anything the checks did not expect means the file is not a pack this verifier reads
        print(f"Format: NOT READABLE ({e.__class__.__name__}). The file is not a pack this verifier reads, or it is cut short.")
        print("What to do: download it again, check its SHA-256, and ask the institution if it persists.")
        return 5


def _verify(path, pin, expect):
    try:
        import os
        if os.path.getsize(path) > MAX_BYTES:
            raise ValueError("larger than the verifier reads")
        with open(path, encoding="utf-8") as f:
            pack = json.load(f, object_pairs_hook=_strict_object, parse_constant=_no_constant)
        recs = pack["records"]
        assert isinstance(pack, dict) and pack["format"] == "governanceos-pack/1" and isinstance(recs, list) and recs
        assert all(isinstance(r, dict) and isinstance(r["position"], int) for r in recs)
    except Exception as e:
        print(f"Format: NOT READABLE ({e.__class__.__name__}). The file is not a pack this verifier reads, or it is cut short.")
        print("What to do: download it again, check its SHA-256, and ask the institution if it persists.")
        return 5
    print(f"Pack: {clean(pack['pack_id'], 120)} · {len(recs)} records, chain positions {recs[0]['position']} to {recs[-1]['position']}")
    print(f"Created: {clean(pack.get('created', 'not stated'), 40)} · Period: {clean(pack.get('period', 'not stated'), 60)}")
    print(f"Issued by: {clean(pack['issued_by'], 200)}")
    if pack.get("notice"):
        print(f"Notice: {clean(pack['notice'])}")
    prev = pack["segment_start_prev_hash"]
    for i, r in enumerate(recs):
        if i and r["position"] != recs[i - 1]["position"] + 1:
            print(f"Chain: BROKEN at position {r['position']}: the positions do not run on from {recs[i - 1]['position']}.")
            print("What to do: keep this output as evidence and ask the institution (the issuer above) to explain the gap."); return 2
        if r["prev_hash"] != prev:
            print(f"Chain: BROKEN at position {r['position']}: it does not link to the record before it.")
            print("What to do: keep this output as evidence and ask the institution (the issuer above) to explain the break."); return 2
        h = record_hash(prev, r["record"])
        if h != r["hash"]:
            print(f"Chain: BROKEN at position {r['position']}: the stored hash differs from the hash recomputed from the record.")
            print("What to do: keep this output as evidence and ask the institution (the issuer above) to explain the change."); return 2
        prev = h
    if prev != pack["head"]:
        print("Chain: BROKEN: the last record's hash is not the head the pack declares."); return 2
    print(f"Chain: OK ({len(recs)} of {len(recs)} records recomputed and linked)")
    try:
        ok = ed25519_verify(bytes.fromhex(pack["public_key"]), signed_message(pack), bytes.fromhex(pack["signature"]))
    except Exception:
        ok = False
    if not ok:
        print(f"Signature: INVALID (key {clean(pack.get('key_id'), 80)}). The pack changed after it was signed, or another key signed it.")
        print("What to do: keep this output and ask the institution which key signed the pack."); return 3
    print(f"Signature: OK (Ed25519, key {clean(pack['key_id'], 80)}; it covers the header, every record and the summaries)")
    fp = key_hash(pack["public_key"])
    if pin is None:
        print(f"Key: SHA256 {_grouped(fp)}")
        print("     Not compared. The key inside a pack is the pack's own claim.")
    elif fp.startswith(pin):
        print(f"Key: SHA256 {_grouped(fp)}  MATCH with the pack key hash you were sent")
    else:
        print(f"Key: SHA256 {_grouped(fp)}  MISMATCH: the pack was signed by a key other than the one you were sent.")
        print("What to do: do not rely on this pack; ask the institution, by a route you trust, which key signs its packs."); return 6
    head = pack["head"]
    grouped = _grouped(head)
    if expect is None:
        print(f"Head: {grouped}")
        print("      Not compared. Add --expect with a head the institution sent you to compare it too.")
    elif expect == head:
        print(f"Head: {grouped}  MATCH with the value you were sent")
    else:
        print(f"Head: {grouped}  MISMATCH: you were sent a different head.")
        print("What to do: do not rely on this pack; ask the institution which head is correct."); return 4
    print("Anchor: not checked (offline). No anchor operator is named yet; once one is, compare the head with its published anchor.")
    if pin is None:
        if expect is None:
            print("Result: INTACT, NOT PINNED. The pack matches its own chain and its own key, but nothing ties that key to the")
        else:
            print("Result: INTACT, SIGNER NOT PINNED. The records end at the head you were sent, but a shortened or changed pack")
            print("        can be re-signed with another key. Nothing ties this pack's key to the")
        print("        institution. Run again with --key and the pack key hash the institution sent you by another route.")
        return 1
    print("Result: VERIFIED. The pack was not changed after the pack key you were sent signed it: the header, every record")
    print("        and the summaries. The same key signs every pack, so check the pack name and positions above are the ones")
    print("        you expect. It does not prove the records were true when written; that is for the examination.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
