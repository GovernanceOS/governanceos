"""Rule packs: one YAML file per instrument, generated from GovernanceOS's register coverage research
by tools/gen_packs.py. Each field carries its basis in the instrument's own wording and a citation."""
import os
import re

PACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")
SCHEMA = "goslint-pack/1"
BASES = ("required", "expected", "recommended")
SEVERITY = {"required": "error", "expected": "warning", "recommended": "note"}
VERB = {"required": "Required by", "expected": "Expected by", "recommended": "Recommended by"}
EXTRA = 'the lint extra is not installed. Install it with: pip install "governanceos[lint]"'


class SetupError(Exception):
    """A usage or setup problem. goslint reports it and exits 2."""


def normalize(text):
    """Header text as goslint compares it: lower case, "(s)" folded, punctuation and spacing collapsed."""
    s = str(text).lower().replace("&", " and ").replace("(s)", "s")
    return " ".join(re.sub(r"[\W_]+", " ", s).split())


class Field(object):
    def __init__(self, d, number):
        self.id = d["id"]
        self.label = d["label"]
        self.basis = d["basis"]
        self.citation = d["citation"]
        self.synonyms = list(d["synonyms"])
        self.number = number
        keys = [normalize(s) for s in self.synonyms] + [normalize(self.label), normalize(self.id)]
        self.keys = [k for k in dict.fromkeys(keys) if k]  # synonyms first, in their listed order

    @property
    def severity(self):
        return SEVERITY[self.basis]


class Pack(object):
    def __init__(self, d):
        self.id = d["pack"]
        self.title = d["title"]
        self.region = d["region"]
        self.instrument_version = d["instrument_version"]
        self.read = d["read"]
        self.source = d["source"]
        self.row = d["row"]
        self.note = d["note"]
        self.next_review_field = d.get("next_review_field")
        self.fields = [Field(f, n) for n, f in enumerate(d["fields"], 1)]

    def field(self, fid):
        for f in self.fields:
            if f.id == fid:
                return f
        raise KeyError(fid)

    def counts(self):
        return [(b, sum(1 for f in self.fields if f.basis == b)) for b in BASES]


def available():
    return sorted(n[:-5] for n in os.listdir(PACK_DIR) if n.endswith(".yaml"))


def _yaml():
    try:
        import yaml
    except ImportError:
        raise SetupError(EXTRA)
    return yaml


def _check(pid, d):
    def bad(why):
        return SetupError("pack %s is malformed: %s" % (pid, why))

    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise bad("schema is not %s" % SCHEMA)
    if d.get("pack") != pid:
        raise bad("its id does not match its file name")
    for key in ("title", "region", "instrument_version", "read", "source", "row", "note"):
        if not isinstance(d.get(key), str) or not d[key].strip():
            raise bad("%s is missing" % key)
    fields = d.get("fields")
    if not isinstance(fields, list) or not fields:
        raise bad("it has no fields")
    seen = set()
    for f in fields:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or f["id"] in seen:
            raise bad("a field id is missing or repeated")
        seen.add(f["id"])
        if f.get("basis") not in BASES:
            raise bad("field %s has no basis (required, expected or recommended)" % f["id"])
        for key in ("label", "citation"):
            if not isinstance(f.get(key), str) or not f[key].strip():
                raise bad("field %s has no %s" % (f["id"], key))
        syn = f.get("synonyms")
        if not isinstance(syn, list) or not all(isinstance(s, str) for s in syn):
            raise bad("field %s has no synonym list" % f["id"])
    nrf = d.get("next_review_field")
    if nrf is not None and nrf not in seen:
        raise bad("next_review_field names no field")


def load(pid):
    if pid not in available():
        raise SetupError("unknown pack %r. Installed: %s" % (pid, ", ".join(available())))
    with open(os.path.join(PACK_DIR, pid + ".yaml"), encoding="utf-8") as f:
        d = _yaml().safe_load(f)
    _check(pid, d)
    return Pack(d)


def load_many(ids=None):
    """The named packs in the order given, or every installed pack."""
    ids = list(dict.fromkeys(ids)) if ids else available()
    return [load(pid) for pid in ids]
