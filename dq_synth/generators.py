"""Clean base data generation.

Generates a realistic B2B SaaS transactions table, split into daily batches so
that defects can be introduced *across loads* (the way schema drift and volume
anomalies actually show up in a landing zone), not just statically.

The "clean" data here is the control: defects are layered on top by defects.py,
and only the layered changes are recorded in the manifest.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# Canonical schema for the base (clean) table. Defect injectors may diverge
# from this per-batch to simulate drift; the manifest records any divergence.
BASE_SCHEMA: dict[str, str] = {
    "invoice_id": "string",
    "customer_id": "string",
    "customer_email": "string",
    "country": "string",
    "currency": "string",
    "amount": "float64",
    "status": "string",
    "created_at": "timestamp",
}

VALID_CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD"]
VALID_STATUSES = ["paid", "pending", "refunded", "failed"]
VALID_COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "NL"]


def _make_customers(fake: Faker, n_customers: int) -> pd.DataFrame:
    """A small customer dimension so we can create valid (and later orphaned) FKs."""
    rows = []
    for i in range(n_customers):
        cid = f"CUST-{i:05d}"
        rows.append(
            {
                "customer_id": cid,
                "customer_email": fake.company_email(),
                "country": random.choice(VALID_COUNTRIES),
            }
        )
    return pd.DataFrame(rows)


def generate_clean_batches(
    rows: int,
    batches: int,
    seed: int = 42,
    start_date: date | None = None,
) -> tuple[list[tuple[str, pd.DataFrame]], pd.DataFrame]:
    """Return (list of (partition_date_str, dataframe), customer_dimension).

    Rows are spread roughly evenly across `batches` daily partitions.
    """
    random.seed(seed)
    np.random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    if start_date is None:
        start_date = date(2026, 3, 1)

    n_customers = max(50, rows // 20)
    customers = _make_customers(fake, n_customers)

    per_batch = max(1, rows // batches)
    out: list[tuple[str, pd.DataFrame]] = []

    invoice_counter = 0
    for b in range(batches):
        part_date = start_date + timedelta(days=b)
        recs = []
        for _ in range(per_batch):
            cust = customers.iloc[random.randint(0, n_customers - 1)]
            ts = pd.Timestamp(part_date) + pd.Timedelta(
                seconds=random.randint(0, 86399)
            )
            recs.append(
                {
                    "invoice_id": f"INV-{invoice_counter:08d}",
                    "customer_id": cust["customer_id"],
                    "customer_email": cust["customer_email"],
                    "country": cust["country"],
                    "currency": random.choice(VALID_CURRENCIES),
                    "amount": round(random.uniform(10.0, 9999.0), 2),
                    "status": random.choice(VALID_STATUSES),
                    "created_at": ts,
                }
            )
            invoice_counter += 1
        df = pd.DataFrame(recs, columns=list(BASE_SCHEMA.keys()))
        out.append((part_date.isoformat(), df))

    return out, customers
