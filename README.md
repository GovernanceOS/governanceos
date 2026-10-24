# GovernanceOS

[![PyPI](https://img.shields.io/pypi/v/governanceos)](https://pypi.org/project/governanceos/) [![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) [![Tests](https://github.com/GovernanceOS/governanceos/actions/workflows/test.yml/badge.svg)](https://github.com/GovernanceOS/governanceos/actions/workflows/test.yml)

<img src="https://raw.githubusercontent.com/GovernanceOS/governanceos/main/assets/goslint-icon-tile-192.png" alt="goslint" width="72" height="72">

**New in 0.4.0: goslint ui.** Run `goslint ui` and the goslint page opens in your browser, served from your own computer: choose your register, tick the regulators that supervise it, and read what to fix. Or run `goslint` and answer a few questions in the terminal. goslint checks the AI and model register you keep in a spreadsheet against 23 regulator rule packs and 246 fields, for Canada, the United States, the GCC, the European Union, the United Kingdom, Switzerland and Asia-Pacific. It is free, under Apache 2.0, and it also runs in your browser at [governanceos.si/lint](https://governanceos.si/lint).

```
pip install governanceos
goslint ui
```

Open-source tools from [GovernanceOS™](https://governanceos.si), under the Apache License 2.0. They run on your own machine. `gos-verify` and `goslint lint` make no network calls; `goslint ui` serves its page only to your own browser, at 127.0.0.1. `gos-verify` needs Python 3 and nothing else; `goslint` adds two libraries, openpyxl and PyYAML, and `goslint ui` or `goslint` at a terminal offers to install them for you.

```
pip install governanceos              # gos-verify
pip install "governanceos[lint]"      # gos-verify and goslint
```

Follow GovernanceOS on [YouTube](https://www.youtube.com/@GovernanceOS) and [X](https://x.com/GovernanceOSx). Both tools are described at [governanceos.si/open-source](https://governanceos.si/open-source).

## Install on a computer with no internet

Both tools run without a network, so they can go on a workstation that has none. Download the files on a connected computer, carry the folder across by your organization's own transfer process, and install from the folder. On macOS and Linux, write `python3` for `python`.

On the connected computer, with the same operating system and Python version as the workstation:

```
python -m pip download -d governanceos-files "governanceos[lint]"
```

On the workstation:

```
python -m pip install --no-index --find-links governanceos-files "governanceos[lint]"
```

`--no-index` keeps pip away from every package index: it installs only what is in the folder, and stops with an error if anything is missing. The folder holds four files: governanceos, openpyxl, et_xmlfile and PyYAML. The PyYAML file is built for one Python version and one operating system, so a folder made for one workstation may not install on another.

If the connected computer differs from the workstation, name the workstation's Python version and platform when you download. For Python 3.10 on 64-bit Windows:

```
python -m pip download -d governanceos-files --only-binary=:all: --python-version 3.10 --platform win_amd64 "governanceos[lint]"
```

For 64-bit Linux, the platform is `manylinux2014_x86_64`. PyPI shows the SHA-256 checksum of every file on each project's page, under Release files, then Details, so your security team can check the folder before it crosses.

## goslint: lint a model register offline

Many practitioners keep their AI and model inventory in a spreadsheet. `goslint` checks that spreadsheet (`.xlsx`, `.xlsm` or `.csv`) against regulator rule packs on your own machine and reports four things:

1. **Missing fields.** Each pack lists the fields an instrument names for an inventory, each with its basis in the instrument's own words (required, expected or recommended) and a citation. A missing column is reported once; an empty cell, or a placeholder such as "TBD", once per row.
2. **Next review date.** Where the instrument's field list names a next review date (OSFI E-23 Appendix 1 field 17, and the QCB AI Guideline's next planned risk assessment or audit, Article 10.9), dates that have passed, and dates that cannot be read, such as 03/04/2027. goslint reads the date the register holds and computes none of its own.
3. **Typed or derived.** Whether each cell was typed by a person or derived by a formula, read from the workbook itself.
4. **What a spreadsheet cannot prove.** No history, no signers, no hashes. True of every spreadsheet, so it is stated once.

```
goslint lint REGISTER.xlsx --pack osfi-e23 [--sheet NAME] [--as-of YYYY-MM-DD] [--grace-days N]
                           [--json findings.json] [--quiet | --verbose]
goslint packs
```

| Region | Pack | Instrument | Fields | Required | Expected | Recommended |
|---|---|---|---|---|---|---|
| Canada | `amf-ai` | AMF Guideline for the Use of Artificial Intelligence (March 2026), s. 6, 6.1, 6.2 and Annex 2 | 13 | 0 | 5 | 8 |
|  | `osfi-e23` | OSFI Guideline E-23 (2027), Appendix 1: information tracking for models | 17 | 6 | 11 | 0 |
| United States | `nist-ai-600-1` | NIST AI 600-1, Generative AI Profile, GV-1.6-003 | 7 | 0 | 0 | 7 |
|  | `nist-ai-rmf-playbook-gv16` | NIST AI RMF Playbook, GOVERN 1.6 (companion to NIST AI 100-1) | 7 | 0 | 0 | 7 |
|  | `us-co-3ccr702-10` | Colorado 3 CCR 702-10 (Regulation 10-1-1), s. 5.A.9 and 5.A.10: inventory of ECDIS, algorithms and predictive models | 6 | 6 | 0 | 0 |
| GCC | `cbuae-ai-gn` | CBUAE Guidance Note on the responsible adoption and use of AI and ML by licensed financial institutions (2026), para 2(f) | 4 | 3 | 1 | 0 |
|  | `cbuae-mms` | CBUAE Model Management Standards, Part II, 4.4 and 10.5.2 | 12 | 12 | 0 | 0 |
|  | `qcb-ai` | QCB Artificial Intelligence Guideline (2024), Article 10 Register | 20 | 17 | 3 | 0 |
| European Union | `ecb-egim-model-register` | ECB Guide to internal models (version 4.1, June 2026), paras 6 and 13 | 10 | 8 | 1 | 1 |
|  | `esma-ai-investment-records` | ESMA Public Statement on AI in retail investment services (2024), paras 23 and 24 | 6 | 0 | 6 | 0 |
|  | `eu-aia-annex8-a` | EU AI Act, Annex VIII Section A: provider registration, Art. 49(1) | 13 | 12 | 0 | 1 |
|  | `eu-aia-annex8-b` | EU AI Act, Annex VIII Section B as amended by Regulation (EU) 2026/1744: Art. 6(3) systems, Art. 49(2) | 7 | 7 | 0 | 0 |
|  | `eu-aia-annex8-c` | EU AI Act, Annex VIII Section C: deployers that are public authorities or EU bodies, Art. 49(3) | 5 | 5 | 0 | 0 |
| United Kingdom | `pra-ss1-23` | PRA SS1/23 Model risk management principles for banks, Principle 1.2 and related clauses | 21 | 0 | 11 | 10 |
| Switzerland | `finma-08-2024` | FINMA Guidance 08/2024, Governance and risk management when using AI, 2.1 and 2.2 | 4 | 0 | 3 | 1 |
| Asia-Pacific | `au-ai-register-template` | Australia National AI Centre AI register template | 12 | 0 | 0 | 12 |
|  | `au-gaia-register` | Australia Guidance for AI Adoption, Implementation guidance 4.1.1 | 11 | 0 | 0 | 11 |
|  | `au-vaiss-guardrail9` | Australia Voluntary AI Safety Standard (2024), Guardrail 9, 9.1.1 | 11 | 0 | 0 | 11 |
|  | `cn-algorithm-filing` | China algorithm filing: Algorithm Recommendation Provisions Art. 24, with Labeling Measures Art. 12 | 7 | 7 | 0 | 0 |
|  | `mas-ai-mrm-ip-2024` | MAS Information Paper, AI Model Risk Management (December 2024), 5.2 | 17 | 0 | 0 | 17 |
|  | `mas-airm-gl-2026` | MAS Guidelines on AI Risk Management for Financial Institutions (October 2026), 4.5 to 4.9 | 15 | 0 | 0 | 15 |
|  | `rbi-free-ai-inventory` | RBI FREE-AI Committee Report (2025), 4.4.48, 4.4.67 to 4.4.69 and Recommendation 23 | 11 | 0 | 0 | 11 |
|  | `rbi-mrm-draft-2026` | RBI draft Guidance on Model Risk Management (2026), paras 21 to 23 (draft, not in force) | 10 | 8 | 1 | 1 |
| **All** | **23 packs** | | **246** | **91** | **42** | **113** |

Packs are chosen, never assumed: without `--pack`, goslint lists the installed packs by region and stops, so a register is checked only against the jurisdictions it answers to. Name several with commas: `--pack osfi-e23,amf-ai`. Severity follows the basis: required is an error, expected a warning, recommended a note.

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

## goslint ui: the page on your own computer

```
goslint ui
```

goslint opens its page in your browser, served from this computer: drop or choose a register (or try the fictional Nebula Mutual sample), tick the regulators that supervise it, then copy or save the report and findings. If openpyxl and PyYAML are missing, it asks first and installs them with pip only on a yes. It runs the same code as `goslint lint`, so both give the same findings.

Four safeguards keep the page to you:

1. It listens only on 127.0.0.1, on a port the system picks, and opens no outbound connection.
2. A one-time secret token is part of every address; a request without it is answered "not found".
3. A request for any host other than 127.0.0.1 or localhost on that port is refused, and so is a POST from another site.
4. It stops a few seconds after you close the page, or when you press Ctrl+C.

Your register goes from your browser to goslint on this computer in memory; nothing is written to disk, and no request is logged.

## goslint, a question at a time

At a terminal, `goslint` on its own (or `goslint lint register.xlsx` without `--pack`) asks which register, which regions and which rule packs (from numbered lists), and the review date (Enter means today). It prints the report, offers to save the findings, and ends with the one-line command that runs the same check, for next time. In scripts and pipes nothing is asked: without `--pack`, goslint lists the packs and stops, so packs are always chosen, never assumed.

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

## Try it

`tests/data` holds a sample pack from a fictional institution and a tampered copy of it, the same institution's model register, kept by hand with the gaps such registers have, and the registers of two more fictional institutions. Nebula Mutual, Nebula Gulf Bank and Nebula Regional Health are fictional institutions constructed for illustration; any resemblance to a real organization is unintended.

```
goslint lint tests/data/nebula-mutual-register.xlsx --pack osfi-e23,amf-ai --as-of 2026-10-19
goslint lint tests/data/nebula-gulf-bank-register.csv --pack cbuae-ai-gn,cbuae-mms
goslint lint tests/data/nebula-regional-health-register.csv --pack nist-ai-600-1,nist-ai-rmf-playbook-gv16
```

The tests need the lint extra:

```
pip install ".[lint]"
python -m unittest discover -s tests -v
```

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).

The tools are open source so that practitioners can use them in banks and on other client work without license concerns. Commercial use, changes and redistribution are all allowed. Keep the copyright notice, the license and the NOTICE file with any copy, and mark the files you change. The license grants no rights to the GovernanceOS name or marks (section 6).

In return, a word about GovernanceOS is appreciated: a post or a tweet that links to [governanceos.si](https://governanceos.si). It is a request, not a condition of the license.
