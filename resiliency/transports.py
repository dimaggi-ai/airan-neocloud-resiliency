"""Last-mile transport catalog with calibrated failure modes.

Each transport is defined by capacity, latency, cost, which resilience
classes it may carry, and a set of failure modes (rate + mean restore
time). Every number traces to REFERENCES.md; every number is overridable.

Eligibility encodes hard physics, not preference:
  R0 (hard-real-time radio / fronthaul + PTP timing) rides only fiber or
     engineered E-band microwave -- never a bonded 5G/LEO path: the ~100 us
     one-way fronthaul budget and +/-1.5 us phase budget cannot survive
     25-60 ms satellite latency or cellular jitter.
  R1 (control loops, near-RT RIC, orchestration) tolerates tens of ms.
  R2 (tenant AI traffic) is elastic in latency, hungry in bandwidth.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FailureMode:
    name: str
    rate_per_year: float        # Poisson arrival rate
    mttr_h: float               # mean restore time (exponential)
    capacity_factor: float = 0.0  # capacity retained during the event
                                  # (0.0 = hard outage; 0.25 = rain fade)
    storm_rate_mult: float = 1.0  # arrival-rate multiplier inside a storm
    storm_mttr_mult: float = 1.0  # restore-time multiplier inside a storm


@dataclass(frozen=True)
class Transport:
    name: str
    kind: str                   # 'fiber' | 'microwave' | 'cellular' | 'leo'
    capacity_gbps: float
    rtt_ms: float
    carries: tuple[str, ...]    # subset of ('R0', 'R1', 'R2')
    modes: tuple[FailureMode, ...]
    monthly_usd: float
    grid_dependent: bool = False  # dies with the local grid (no own backup)

    def hard_downtime_h(self) -> float:
        """Expected standalone hard-outage hours/year (no storms)."""
        return sum(m.rate_per_year * m.mttr_h for m in self.modes
                   if m.capacity_factor == 0.0)


# --- catalog (defaults; see REFERENCES.md for each calibration) -------------

FIBER_ACCESS = Transport(
    name="fiber",
    kind="fiber",
    capacity_gbps=10.0,
    rtt_ms=0.5,
    carries=("R0", "R1", "R2"),
    modes=(
        # ~13 cuts/yr per 1,000 route-miles metro; ~10 km access route.
        # Buried-fiber repair is a civil-works truck roll; crews saturate
        # in storms.
        FailureMode("cut", rate_per_year=0.08, mttr_h=8.0,
                    storm_mttr_mult=3.0),
        # Everything else on a single-homed circuit: upstream equipment,
        # power at the serving CO, maintenance. Calibrated so a single
        # unprotected access lands at/below its 99.9% SLA floor.
        FailureMode("upstream", rate_per_year=6.0, mttr_h=1.2),
    ),
    monthly_usd=1_500.0,
)

MICROWAVE_EBAND = Transport(
    name="microwave",
    kind="microwave",
    capacity_gbps=10.0,
    rtt_ms=0.3,
    carries=("R0", "R1", "R2"),
    modes=(
        FailureMode("hardware", rate_per_year=0.5, mttr_h=4.0),
        # Rain on an E-band link mostly degrades (adaptive modulation),
        # rather than drops; storms multiply the fade rate.
        FailureMode("rain-fade", rate_per_year=40.0, mttr_h=0.3,
                    capacity_factor=0.25, storm_rate_mult=3.0),
    ),
    monthly_usd=800.0,
)

FWA_5G = Transport(
    name="5g-fwa",
    kind="cellular",
    capacity_gbps=0.3,
    rtt_ms=25.0,
    carries=("R1", "R2"),
    modes=(
        FailureMode("outage", rate_per_year=12.0, mttr_h=1.0),
    ),
    monthly_usd=150.0,
    # Rides a neighboring macro site: in a regional power event it goes
    # down with the same grid (>50% of disaster cell outages are power).
    grid_dependent=True,
)

LEO_SAT = Transport(
    name="leo",
    kind="leo",
    capacity_gbps=0.15,
    rtt_ms=50.0,
    carries=("R1", "R2"),
    modes=(
        # Short interruptions aligned to the constellation's 15-s
        # reconfiguration cadence; heavy-tailed durations. Modeled as
        # frequent ~1-minute flaps.
        FailureMode("flap", rate_per_year=200.0, mttr_h=0.02),
        FailureMode("outage", rate_per_year=3.0, mttr_h=1.5),
    ),
    monthly_usd=250.0,
)

CATALOG = {t.name: t for t in
           (FIBER_ACCESS, MICROWAVE_EBAND, FWA_5G, LEO_SAT)}


def transport(name: str) -> Transport:
    if name not in CATALOG:
        raise KeyError(f"unknown transport {name!r}; know {list(CATALOG)}")
    return CATALOG[name]


def custom(base: str, **overrides) -> Transport:
    return replace(transport(base), **overrides)
