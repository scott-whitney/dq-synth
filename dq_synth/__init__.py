"""dq-synth: generate synthetic data-quality fixtures for onboarding/demo.

Produces time-partitioned datasets seeded with *labeled* data-quality defects
(schema drift, null spikes, volume anomalies, invalid values, rule violations)
plus a ground-truth manifest describing exactly what was planted and where.

The manifest turns the synthetic data into an evaluation harness: after a
data-quality / observability platform scans the output, you can check what it
flagged against what was actually injected.
"""

__version__ = "0.1.0"

from .generators import generate_clean_batches
from .defects import DEFECTS, apply_defects
from .manifest import Manifest

__all__ = ["generate_clean_batches", "DEFECTS", "apply_defects", "Manifest", "__version__"]
