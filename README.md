# dq-synth

Generate time-partitioned synthetic datasets seeded with **labeled** data-quality
defects, plus a ground-truth manifest describing exactly what was planted and where.



https://github.com/user-attachments/assets/3502a39c-cac8-4900-bd68-456a73e160ed



## Why this exists

A data-observability platform only delivers value once it's pointed at data and
catching real problems. But during onboarding, the slowest step is usually
getting access to the customer's actual data — it lives inside their VPC, it's
governed, it's PII-laden, and standing up a representative sample takes days of
back-and-forth before anyone sees the product catch anything.

`dq-synth` removes that wait. It generates realistic data that already
contains the failure modes an observability platform is built to detect, so you
can stand up a working demo or test environment in **minutes** — before real
data is connected — and show the platform catching planted issues on day one.

Because every defect is recorded in a ground-truth manifest, the output doubles
as an **evaluation harness**: after the platform scans the data, you can compare
what it flagged against what was actually injected.

## What it generates

A B2B SaaS invoices table, split into daily partitions (`dt=YYYY-MM-DD/`) in
Parquet — the Hive-partitioned layout lakehouse engines (Databricks, Snowflake
external tables, BigQuery) ingest directly. A small customer dimension is written
alongside so referential-integrity checks have something to resolve against.

Defects map one-to-one onto standard observability detection categories:

| Defect | What it plants | Expected detection |
|---|---|---|
| `schema_drift` | renames `amount` → `amount_usd` and changes its type in a later batch | schema change / missing column / type mismatch across loads |
| `null_spike` | pushes a column's null rate to ~40% in one batch | completeness / null-rate monitor breach |
| `volume_anomaly` | shrinks one partition to ~15% of normal (partial load) | row-count anomaly vs partition baseline |
| `invalid_values` | malformed emails, negative amounts, invalid currency codes, future dates | validity-rule breaches |
| `rule_violation` | orphaned foreign keys + duplicate primary keys | referential-integrity + uniqueness checks |

## Usage

```bash
pip install -r requirements.txt

# one-command walkthrough: generate, then independently verify (5/5)
./demo.sh

# generate everything (all defects, 7 daily partitions)
python -m dq_synth --rows 100000 --batches 7 --out ./out

# pick specific defects
python -m dq_synth --rows 50000 --defects schema_drift,null_spike --out ./out

# list available defects
python -m dq_synth --list-defects

# independently confirm the planted defects are detectable
python verify.py ./out
```

Sample run output:

```
Wrote 4391 rows to ./out/dt=*/ across 7 partition(s).
Ground truth: ./out/manifest.json

Manifest: 5 defect(s) planted across 7 batch(es), seed=42
  - [schema_drift] 2026-03-07 col=amount: Column 'amount' renamed to 'amount_usd' ...
  - [null_spike] 2026-03-04 col=customer_email rows~285: Null rate spiked to ~40% ...
  - [volume_anomaly] 2026-03-05 rows~607: Partition row count dropped ~85% ...
  ...
```

`verify.py` reads the manifest and confirms each defect round-trips:

```
  [PASS] schema_drift @ 2026-03-07: columns=[... amount_usd ...]
  [PASS] null_spike @ 2026-03-04: null_rate=40%
  [PASS] volume_anomaly @ 2026-03-05: rows=107 vs expected~714
  [PASS] invalid_values @ 2026-03-01: negative_amounts=35, invalid_currency=35
  [PASS] rule_violation @ 2026-03-07: orphan_fks=57, max_pk_dups=4

  5/5 planted defects independently confirmed.
```

Runs are deterministic for a given `--seed`, so a demo is repeatable.

## Design

```
dq_synth/
  generators.py   clean base data, split into daily batches
  defects.py      one injector per defect category, in a registry
  manifest.py     ground-truth records (what / where / expected signal)
  writer.py       Hive-partitioned Parquet + customer dimension
  cli.py          argparse entry point
verify.py         independent detectability check (eval-harness demo)
```

Defects live in a registry (`DEFECTS`), so adding a new category is one
decorated function — the CLI picks it up automatically.

## Deliberately out of scope

Kept intentionally tight so it stays a fixture, not a platform:

- **No live platform integration** — outputs files; point any tool at them.
- **No UI / no cloud deploy** — runs locally, writes to a directory.
- **Single table family** — invoices + customer dim; the pattern extends, but
  one realistic domain keeps the example readable.

Natural next steps would be config-driven schemas (YAML), more table families,
and a thin adapter that posts the manifest against a platform's findings API to
score detection automatically.
