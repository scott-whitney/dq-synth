"""Ground-truth manifest.

Every injected defect records what it is, where it lives (batch / column /
affected rows), and what a data-quality platform is expected to detect. This
is the part that makes the fixture useful as an eval harness rather than just
random dirty data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DefectRecord:
    defect_type: str  # one of DEFECTS keys, e.g. "null_spike"
    batch: str  # partition the defect lives in, e.g. "2026-03-04" (or "ALL")
    column: str | None  # affected column, if applicable
    description: str  # human-readable summary of what was planted
    expected_signal: str  # what a DQ platform should surface
    affected_rows: int | None = None  # count of rows touched, if known
    detail: dict[str, Any] = field(default_factory=dict)  # extra structured info


@dataclass
class Manifest:
    seed: int
    rows_requested: int
    batches: list[str]
    base_schema: dict[str, str]
    defects: list[DefectRecord] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add(self, record: DefectRecord) -> None:
        self.defects.append(record)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def write(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def summary(self) -> str:
        lines = [
            f"Manifest: {len(self.defects)} defect(s) planted across "
            f"{len(self.batches)} batch(es), seed={self.seed}",
        ]
        for d in self.defects:
            loc = d.batch if d.batch != "ALL" else "all batches"
            col = f" col={d.column}" if d.column else ""
            rows = f" rows~{d.affected_rows}" if d.affected_rows is not None else ""
            lines.append(f"  - [{d.defect_type}] {loc}{col}{rows}: {d.description}")
        return "\n".join(lines)
