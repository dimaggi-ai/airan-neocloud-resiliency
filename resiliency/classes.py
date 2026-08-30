"""The three resilience classes of an AI-RAN aggregation site.

The split-plane blueprint (docs/study.md) assigns every flow at the
edge<->neocloud demark to exactly one class, and the class -- not the
application -- decides which transports may carry it, what happens
during a WAN partition, and what 'down' means.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResilienceClass:
    name: str
    needs_timing: bool        # PTP phase inside +/-1.5 us (GNSS/holdover)
    # Can the site keep delivering this class locally during a WAN
    # partition, if the policy provisions local autonomy?
    partition_survivable: bool
    # Usable-capacity retention while operating in degraded local mode.
    degraded_retention: float
    note: str


R0 = ResilienceClass(
    "R0", needs_timing=True, partition_survivable=False,
    degraded_retention=0.0,
    note="hard-real-time radio: fronthaul, DU/CU processing, PTP. "
         "Rides fiber/E-band only -- the ~100 us fronthaul and +/-1.5 us "
         "phase budgets cannot survive satellite or cellular paths -- and "
         "dies with site power, timing, or its last fronthaul-grade link.")

R1 = ResilienceClass(
    "R1", needs_timing=False, partition_survivable=False,
    degraded_retention=0.0,
    note="control plane: near-RT RIC, orchestration, telemetry export. "
         "Any transport; a partition severs it -- the site falls back to "
         "last-known-good policy.")

R2 = ResilienceClass(
    "R2", needs_timing=False, partition_survivable=True,
    degraded_retention=0.6,
    note="tenant AI: inference serving, RAG, video analytics. Any "
         "transport; with local autonomy the site keeps serving cached "
         "models/indices at ~60% usable capacity during a partition.")

CLASSES = (R0, R1, R2)
