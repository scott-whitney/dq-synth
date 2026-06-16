"""Defect injectors.

Each injector takes the list of clean batches + the manifest, mutates the data
in place to introduce one class of data-quality problem, and records exactly
what it did in the manifest. Categories map one-to-one onto the failure modes a
data-quality / observability platform is expected to detect:

    schema_drift    - column renamed / retyped / dropped across later batches
    null_spike      - null rate jumps sharply in one column for one batch
    volume_anomaly  - a partition with an abnormal row count
    invalid_values  - out-of-domain values (bad emails, negatives, bad enums)
    rule_violation  - referential / uniqueness breaks (orphan FKs, dup PKs)

Injectors are registered in DEFECTS so the CLI can offer them by name and new
ones can be added without touching the CLI.
"""

from __future__ import annotations

import random
from typing import Callable

import numpy as np
import pandas as pd

from .manifest import DefectRecord, Manifest

Batch = tuple[str, pd.DataFrame]
Injector = Callable[[list[Batch], pd.DataFrame, Manifest, random.Random], None]

DEFECTS: dict[str, Injector] = {}


def _register(name: str) -> Callable[[Injector], Injector]:
    def deco(fn: Injector) -> Injector:
        DEFECTS[name] = fn
        return fn

    return deco


def _last_batch_index(batches: list[Batch]) -> int:
    return len(batches) - 1


@_register("schema_drift")
def inject_schema_drift(
    batches: list[Batch], customers: pd.DataFrame, manifest: Manifest, rng: random.Random
) -> None:
    """Rename `amount` -> `amount_usd` and coerce it to string in the final batch.

    Simulates an upstream producer changing a field name and type mid-stream,
    the classic break that silently corrupts a downstream pipeline.
    """
    idx = _last_batch_index(batches)
    part, df = batches[idx]
    df = df.rename(columns={"amount": "amount_usd"})
    df["amount_usd"] = df["amount_usd"].astype(str)  # type drift float -> string
    batches[idx] = (part, df)
    manifest.add(
        DefectRecord(
            defect_type="schema_drift",
            batch=part,
            column="amount",
            description="Column 'amount' renamed to 'amount_usd' and retyped float64->string in final batch.",
            expected_signal="Schema change detection: missing expected column 'amount', new column 'amount_usd', type mismatch vs prior batches.",
            detail={"renamed_to": "amount_usd", "old_type": "float64", "new_type": "string"},
        )
    )


@_register("null_spike")
def inject_null_spike(
    batches: list[Batch], customers: pd.DataFrame, manifest: Manifest, rng: random.Random
) -> None:
    """Null out ~40% of customer_email in one interior batch."""
    if len(batches) < 2:
        target = 0
    else:
        target = len(batches) // 2
    part, df = batches[target]
    n = len(df)
    k = int(n * 0.40)
    null_idx = rng.sample(range(n), k) if k <= n else list(range(n))
    df.loc[df.index[null_idx], "customer_email"] = None
    batches[target] = (part, df)
    manifest.add(
        DefectRecord(
            defect_type="null_spike",
            batch=part,
            column="customer_email",
            description=f"Null rate for 'customer_email' spiked to ~40% in this batch (baseline ~0%).",
            expected_signal="Completeness/null-rate monitor breach on 'customer_email' for this partition.",
            affected_rows=k,
            detail={"approx_null_rate": 0.40, "baseline_null_rate": 0.0},
        )
    )


@_register("volume_anomaly")
def inject_volume_anomaly(
    batches: list[Batch], customers: pd.DataFrame, manifest: Manifest, rng: random.Random
) -> None:
    """Drop one interior batch to ~15% of its size (a partial/failed load)."""
    if len(batches) < 3:
        target = len(batches) - 1
    else:
        target = len(batches) // 2 + 1 if len(batches) // 2 + 1 < len(batches) else 1
    part, df = batches[target]
    original = len(df)
    keep = max(1, int(original * 0.15))
    df = df.iloc[:keep].copy()
    batches[target] = (part, df)
    manifest.add(
        DefectRecord(
            defect_type="volume_anomaly",
            batch=part,
            column=None,
            description=f"Partition row count dropped from ~{original} to {keep} (~15%), simulating a partial/failed load.",
            expected_signal="Volume/row-count anomaly vs historical partition baseline.",
            affected_rows=original - keep,
            detail={"expected_rows": original, "actual_rows": keep},
        )
    )


@_register("invalid_values")
def inject_invalid_values(
    batches: list[Batch], customers: pd.DataFrame, manifest: Manifest, rng: random.Random
) -> None:
    """Introduce out-of-domain values: malformed emails, negative amounts,
    invalid currency codes, and future-dated timestamps in the first batch."""
    part, df = batches[0]
    n = len(df)
    touched = 0

    # malformed emails
    k_email = max(1, int(n * 0.10))
    for i in rng.sample(range(n), min(k_email, n)):
        df.iat[i, df.columns.get_loc("customer_email")] = "not-an-email##"
        touched += 1

    # negative amounts (only if column present / numeric)
    if "amount" in df.columns:
        k_amt = max(1, int(n * 0.05))
        for i in rng.sample(range(n), min(k_amt, n)):
            df.iat[i, df.columns.get_loc("amount")] = -abs(
                float(df.iat[i, df.columns.get_loc("amount")])
            )
            touched += 1

    # invalid currency codes
    k_cur = max(1, int(n * 0.05))
    for i in rng.sample(range(n), min(k_cur, n)):
        df.iat[i, df.columns.get_loc("currency")] = "XXX"
        touched += 1

    # future-dated created_at
    k_dt = max(1, int(n * 0.03))
    for i in rng.sample(range(n), min(k_dt, n)):
        df.iat[i, df.columns.get_loc("created_at")] = pd.Timestamp("2099-01-01")
        touched += 1

    batches[0] = (part, df)
    manifest.add(
        DefectRecord(
            defect_type="invalid_values",
            batch=part,
            column="customer_email,amount,currency,created_at",
            description="Out-of-domain values planted: malformed emails (~10%), negative amounts (~5%), invalid currency 'XXX' (~5%), future-dated created_at (~3%).",
            expected_signal="Validity rule breaches: email format, amount>=0, currency in allowed set, created_at not in future.",
            affected_rows=touched,
            detail={
                "rules": [
                    "email_format",
                    "amount_non_negative",
                    "currency_in_set",
                    "timestamp_not_future",
                ]
            },
        )
    )


@_register("rule_violation")
def inject_rule_violation(
    batches: list[Batch], customers: pd.DataFrame, manifest: Manifest, rng: random.Random
) -> None:
    """Break referential integrity (orphan customer_id) and uniqueness (dup PK)."""
    idx = _last_batch_index(batches)
    part, df = batches[idx]
    n = len(df)

    # orphaned foreign keys: customer_id not present in the customer dimension
    k_orphan = max(1, int(n * 0.08))
    for i in rng.sample(range(n), min(k_orphan, n)):
        df.iat[i, df.columns.get_loc("customer_id")] = "CUST-99999999"

    # duplicate primary keys: clone one invoice_id onto several rows
    if n >= 4:
        dup_value = df.iat[0, df.columns.get_loc("invoice_id")]
        for i in range(1, 4):
            df.iat[i, df.columns.get_loc("invoice_id")] = dup_value

    batches[idx] = (part, df)
    manifest.add(
        DefectRecord(
            defect_type="rule_violation",
            batch=part,
            column="customer_id,invoice_id",
            description="Referential break: ~8% orphaned customer_id ('CUST-99999999' not in customer dim). Uniqueness break: invoice_id duplicated across 4 rows.",
            expected_signal="Referential-integrity check on customer_id; primary-key uniqueness check on invoice_id.",
            affected_rows=k_orphan + 3,
            detail={"orphan_customer_id": "CUST-99999999", "duplicated_pk_rows": 4},
        )
    )


def apply_defects(
    batches: list[Batch],
    customers: pd.DataFrame,
    manifest: Manifest,
    defect_names: list[str],
    seed: int = 42,
) -> None:
    """Apply the named defects in order, recording each in the manifest."""
    rng = random.Random(seed)
    unknown = [d for d in defect_names if d not in DEFECTS]
    if unknown:
        raise ValueError(
            f"Unknown defect(s): {unknown}. Available: {sorted(DEFECTS)}"
        )
    for name in defect_names:
        DEFECTS[name](batches, customers, manifest, rng)
