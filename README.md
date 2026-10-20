# GovernanceOS

Open-source tools from [GovernanceOS](https://governanceos.si), under the Apache License 2.0. They run on your own machine with Python 3 and nothing else installed, and they make no network calls.

```
pip install governanceos
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

## Try it

`tests/data` holds a sample pack from a fictional institution and a tampered copy of it:

```
python -m unittest discover -s tests -v
```

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The license grants no rights to the GovernanceOS name or marks (section 6).
