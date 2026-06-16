"""verify.py — independent check that planted defects are detectable.

This is the "eval harness" half of the tool. It reads the ground-truth manifest
and, for each planted defect, runs a simple independent check against the
generated Parquet to confirm the defect is actually present and detectable.

In a real onboarding demo you would instead point the data-quality platform at
the same output and compare *its* findings against this manifest — this script
shows the principle without needing platform access.

Usage:
    python verify.py ./out
"""

from __future__ import annotations

import glob
import json
import os
import sys

import pandas as pd

VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}


def _read_batch(out_dir: str, batch: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(out_dir, f"dt={batch}", "*.parquet"))
    return pd.read_parquet(files[0]) if files else pd.DataFrame()


def verify(out_dir: str) -> int:
    with open(os.path.join(out_dir, "manifest.json")) as f:
        manifest = json.load(f)

    customers = pd.read_parquet(os.path.join(out_dir, "_dimensions", "customers.parquet"))
    valid_customer_ids = set(customers["customer_id"])

    passed = 0
    failed = 0
    for d in manifest["defects"]:
        dt = d["defect_type"]
        batch = d["batch"]
        df = _read_batch(out_dir, batch)
        ok = False
        evidence = ""

        if dt == "schema_drift":
            ok = "amount_usd" in df.columns and "amount" not in df.columns
            evidence = f"columns={list(df.columns)}"
        elif dt == "null_spike":
            rate = df["customer_email"].isna().mean()
            ok = rate > 0.2
            evidence = f"null_rate={rate:.0%}"
        elif dt == "volume_anomaly":
            expected = d["detail"]["expected_rows"]
            ok = len(df) < expected * 0.5
            evidence = f"rows={len(df)} vs expected~{expected}"
        elif dt == "invalid_values":
            neg = int((df["amount"] < 0).sum()) if "amount" in df.columns else 0
            badcur = int((~df["currency"].isin(VALID_CURRENCIES)).sum())
            ok = neg > 0 and badcur > 0
            evidence = f"negative_amounts={neg}, invalid_currency={badcur}"
        elif dt == "rule_violation":
            orphans = int((~df["customer_id"].isin(valid_customer_ids)).sum())
            dup = int(df["invoice_id"].value_counts().max()) if len(df) else 0
            ok = orphans > 0 and dup > 1
            evidence = f"orphan_fks={orphans}, max_pk_dups={dup}"

        status = "PASS" if ok else "FAIL"
        passed += ok
        failed += not ok
        print(f"  [{status}] {dt} @ {batch}: {evidence}")

    print(f"\n{passed}/{passed + failed} planted defects independently confirmed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "./out"
    raise SystemExit(verify(out))
