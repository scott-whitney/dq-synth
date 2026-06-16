"""Output writer.

Writes each batch as a Hive-style date partition:

    <out>/dt=YYYY-MM-DD/part-0000.parquet

This layout is what lakehouse ingestion (Databricks, Snowflake external tables,
BigQuery external/Hive partitioning) expects, so the fixture can be pointed at a
real platform with no reshaping. The customer dimension and the ground-truth
manifest are written alongside.
"""

from __future__ import annotations

import os

import pandas as pd


def write_partitioned(
    batches: list[tuple[str, pd.DataFrame]],
    customers: pd.DataFrame,
    out_dir: str,
) -> dict[str, int]:
    """Write batches to partitioned parquet. Returns {partition: row_count}."""
    os.makedirs(out_dir, exist_ok=True)
    counts: dict[str, int] = {}
    for part_date, df in batches:
        part_dir = os.path.join(out_dir, f"dt={part_date}")
        os.makedirs(part_dir, exist_ok=True)
        df.to_parquet(
            os.path.join(part_dir, "part-0000.parquet"), index=False
        )
        counts[part_date] = len(df)

    # customer dimension (for referential-integrity checks downstream)
    dim_dir = os.path.join(out_dir, "_dimensions")
    os.makedirs(dim_dir, exist_ok=True)
    customers.to_parquet(os.path.join(dim_dir, "customers.parquet"), index=False)
    return counts
