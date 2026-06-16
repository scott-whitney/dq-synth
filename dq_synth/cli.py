"""Command-line interface for dq-synth.

Examples
--------
    python -m dq_synth --rows 100000 --batches 7 \
        --defects schema_drift,null_spike,volume_anomaly,invalid_values,rule_violation \
        --out ./out

    python -m dq_synth --list-defects
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .defects import DEFECTS, apply_defects
from .generators import BASE_SCHEMA, generate_clean_batches
from .manifest import Manifest
from .writer import write_partitioned


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dq-synth",
        description="Generate time-partitioned synthetic data seeded with labeled data-quality defects.",
    )
    p.add_argument("--rows", type=int, default=10000, help="Approx total rows across all batches (default 10000).")
    p.add_argument("--batches", type=int, default=7, help="Number of daily partitions (default 7).")
    p.add_argument(
        "--defects",
        type=str,
        default=",".join(DEFECTS.keys()),
        help="Comma-separated defect names to inject (default: all). Use --list-defects to see options.",
    )
    p.add_argument("--out", type=str, default="./out", help="Output directory (default ./out).")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default 42).")
    p.add_argument("--list-defects", action="store_true", help="List available defect types and exit.")
    p.add_argument("--version", action="version", version=f"dq-synth {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_defects:
        print("Available defects:")
        for name, fn in DEFECTS.items():
            doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
            print(f"  {name:16s} {doc}")
        return 0

    defect_names = [d.strip() for d in args.defects.split(",") if d.strip()]

    print(f"Generating ~{args.rows} rows across {args.batches} batch(es) (seed={args.seed})...")
    batches, customers = generate_clean_batches(
        rows=args.rows, batches=args.batches, seed=args.seed
    )

    manifest = Manifest(
        seed=args.seed,
        rows_requested=args.rows,
        batches=[p for p, _ in batches],
        base_schema=BASE_SCHEMA,
    )

    try:
        apply_defects(batches, customers, manifest, defect_names, seed=args.seed)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    counts = write_partitioned(batches, customers, args.out)
    import os

    manifest.write(os.path.join(args.out, "manifest.json"))

    total = sum(counts.values())
    print(f"Wrote {total} rows to {args.out}/dt=*/ across {len(counts)} partition(s).")
    print(f"Ground truth: {args.out}/manifest.json")
    print()
    print(manifest.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
