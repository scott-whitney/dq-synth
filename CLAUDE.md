# CLAUDE.md

Project context for Claude Code. Read this first.

## What this is

`dq-synth` generates time-partitioned synthetic datasets seeded with
**labeled** data-quality defects, plus a ground-truth manifest describing
exactly what was planted and where.

The point: a data-observability / data-quality platform only shows value once
it's pointed at data and catching real problems, but during onboarding the
slowest step is getting access to a customer's real data (VPC-bound, governed,
PII-laden). This tool removes that wait — it produces realistic data that
already contains the failure modes such a platform detects, so a working demo or
test environment can be stood up in minutes. Because every defect is recorded in
the manifest, the output also works as an **evaluation harness**: compare what a
platform flags against what was actually injected.

## Architecture

Data flows in one direction:

```
generators.py   -> clean base data (B2B invoices), split into daily batches
defects.py      -> registry of injectors; each mutates batches + logs to manifest
manifest.py     -> ground-truth DefectRecord list (what / where / expected signal)
writer.py       -> Hive-partitioned Parquet (dt=YYYY-MM-DD/) + customer dimension
cli.py          -> argparse entry point (python -m dq_synth ...)
verify.py       -> reads manifest, independently confirms each defect round-trips
```

Defect categories map one-to-one onto standard observability detections:
`schema_drift`, `null_spike`, `volume_anomaly`, `invalid_values`,
`rule_violation`.

## Design rules — keep these invariants

- **Defects live in the `DEFECTS` registry** (`defects.py`). Add a new defect as
  a `@_register("name")`-decorated function with the
  `(batches, customers, manifest, rng)` signature. Do NOT special-case defects
  in the CLI — the CLI discovers them from the registry.
- **Every injected defect must record a `DefectRecord`** in the manifest. The
  manifest is the contract that makes the output an eval harness; an unlabeled
  mutation is a bug.
- **Runs stay deterministic for a given `--seed`.** Anything random must draw
  from the seeded `rng` / seeded numpy/Faker. Don't introduce unseeded
  randomness.
- **Output stays generic.** No company name in the code or README. (Any
  company-specific framing belongs in an application/cover note, not the repo —
  the repo is reusable across data-quality / observability roles.)
- **Partition layout is Hive-style** (`dt=YYYY-MM-DD/part-*.parquet`) so it
  ingests directly into lakehouse engines (Databricks, Snowflake external
  tables, BigQuery). Don't change this without reason.

## Out of scope (do not build unless asked)

- No live platform API integration (outputs files; any tool gets pointed at them).
- No UI, no cloud deployment — runs locally, writes to a directory.
- Single table family (invoices + customer dimension) on purpose, for
  readability.

## How to test

A full run should report 5/5 defects confirmed:

```bash
pip install -r requirements.txt
python -m dq_synth --rows 100000 --batches 7 --out ./out
python verify.py ./out          # expect: 5/5 planted defects independently confirmed.
python -m dq_synth --list-defects
```

`verify.py` returns non-zero if any planted defect can't be confirmed, so it
doubles as a smoke test after changes.

## Working agreement

- The tool is already built and tested. Don't refactor working code unprompted —
  read this file and the README first, then do the requested task.
- After any change to generation or defect logic, re-run the test block above
  and confirm 5/5 before considering the change done.
- Sensible next steps (only if asked): config-driven schemas via YAML; more
  table families; a thin adapter that scores a platform's findings against the
  manifest automatically.
