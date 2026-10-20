# GovernanceOS

Open-source tools from [GovernanceOS](https://governanceos.si), under the Apache License 2.0. They run on your own machine and make no network calls. `gos-verify` needs Python 3 and nothing else; `goslint` adds two libraries, openpyxl and PyYAML.

```
pip install governanceos              # gos-verify
pip install "governanceos[lint]"      # gos-verify and goslint
```

## gos-verify: verify an evidence pack offline

An institution that keeps its AI governance records in GovernanceOS can share an evidence pack with an examiner. `gos-verify` checks that pack on the examiner's own machine:

1. It recomputes the SHA-256 hash of every record, checks that each links to the one before it, and checks that the positions run without a gap.
2. It checks the Ed25519 signature over the whole pack: the header, every record and the summaries.
3. It prints the signing key's hash and compares it with the one the institution sent you by another route (`--key`), and compares the head with a head it sent you (`--expect`).
4. It says plainly that the public anchor was not checked, because that needs a network.

```
gos-verify PACK.json --key KEYHASH [--expect HEAD]
```

| Exit | Meaning |
|---|---|
| 0 | Verified: intact, and signed by the key you pinned |
| 1 | Intact, but the signer is not pinned |
| 2 | Chain broken |
| 3 | Signature invalid |
| 4 | Head differs from `--expect` |
| 5 | The pack cannot be read |
| 6 | The key differs from `--key` |

**What it proves:** the pack was not changed after the key you pinned signed it.
**What it does not prove:** that the records were true when they were written. That is for the examination.

The same verifier is the single-file download at [governanceos.si/verify](https://governanceos.si/verify). The two are byte-identical.

## goslint: lint a model register offline

Many practitioners keep their AI and model inventory in a spreadsheet. `goslint` checks that spreadsheet (`.xlsx`, `.xlsm` or `.csv`) against regulator rule packs on your own machine and reports four things:

1. **Missing fields.** Each pack lists the fields an instrument names for an inventory, each with its basis in the instrument's own words (required, expected or recommended) and a citation. A missing column is reported once; an empty cell, or a placeholder such as "TBD", once per row.
2. **Next review date.** Where the instrument's field list names a next review date (OSFI E-23 Appendix 1 does), dates that have passed, and dates that cannot be read, such as 03/04/2027.
3. **Typed or derived.** Whether each cell was typed by a person or derived by a formula, read from the workbook itself.
4. **What a spreadsheet cannot prove.** No history, no signers, no hashes. True of every spreadsheet, so it is stated once.

```
goslint lint REGISTER.xlsx [--pack osfi-e23] [--sheet NAME] [--as-of YYYY-MM-DD] [--grace-days N]
                           [--json findings.json] [--quiet | --verbose]
goslint packs
```

| Pack | Instrument | Fields |
|---|---|---|
| `osfi-e23` | OSFI Guideline E-23 (2027), Appendix 1, information tracking for models | 17: 6 required, 11 expected |
| `eu-aia-annex8-a` | EU AI Act, Annex VIII Section A: provider registration, Art. 49(1) | 13: 12 required, 1 recommended |
| `eu-aia-annex8-b` | Annex VIII Section B as amended by Regulation (EU) 2026/1744: Art. 6(3) systems, Art. 49(2) | 7 required |
| `eu-aia-annex8-c` | Annex VIII Section C: deployers that are public authorities or EU bodies, Art. 49(3) | 5 required |

Without `--pack`, every installed pack runs. Severity follows the basis: required is an error, expected a warning, recommended a note.

| Exit | Meaning |
|---|---|
| 0 | No errors or warnings |
| 1 | Errors or warnings reported |
| 2 | A usage or setup problem: the file, a pack, the sheet, a date, or the lint extra |

Notes and check 4 do not change the exit code.

**The workbook is read, never written.** goslint reads the file once, prints the SHA-256 of what it read, and parses that copy in memory. `--json` writes the findings (schema `goslint-findings/1`) to a file you name; the export names the workbook by file name, never by path.

**What it checks:** that fields are present, that next review dates have not passed, and where values come from.
**What it does not check:** whether the values are true.

Each pack is generated from GovernanceOS's register coverage research, which read every source at its official URL on 2026-10-19 (`tools/gen_packs.py`). Header synonyms are working guesses for matching column names, not source text.

## Try it

`tests/data` holds a sample pack from a fictional institution and a tampered copy of it, and the same institution's model register, kept by hand with the gaps such registers have. Nebula Mutual is a fictional institution constructed for illustration; any resemblance to a real organization is unintended.

```
goslint lint tests/data/nebula-mutual-register.xlsx --pack osfi-e23 --as-of 2026-10-19
```

The tests need the lint extra:

```
pip install ".[lint]"
python -m unittest discover -s tests -v
```

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The license grants no rights to the GovernanceOS name or marks (section 6).
