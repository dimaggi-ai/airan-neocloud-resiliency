"""Monte Carlo fault injection for the last-mile complex.

Simulates years of correlated failures -- fiber cuts, microwave rain
fades, LEO flaps, cellular outages, grid failures, storms, GNSS loss --
against a resilience policy, and reports per-class availability, restore
times, usable-capacity retention, and cost.

The correlation structure is the point. Independent-failure math makes
any two transports look like five nines; the storm process (grid down +
crews saturated + rain fades tripled + neighbor macros dark) is what
actually bounds the last mile, exactly as the FCC's disaster reports
describe (REFERENCES.md).

Semantics per resilience class (see classes.py):
  R0 down  = site dark  OR timing lost  OR all fronthaul-grade links down
  R1 down  = site dark  OR all R1-eligible links down
  R2 down  = site dark  OR (all R2-eligible links down, unless the policy
             provisions local autonomy -- then those hours run degraded
             at the class's retention factor instead of down)
"""

import random
from dataclasses import dataclass, field

from .classes import CLASSES, ResilienceClass
from .policies import Policy
from .transports import Transport, transport

HOURS = 8760.0

Interval = tuple[float, float]


# --- interval algebra -------------------------------------------------------

def merge(intervals: list[Interval]) -> list[Interval]:
    """Sorted union of intervals, clipped to the year."""
    clipped = [(max(0.0, a), min(HOURS, b)) for a, b in intervals if b > a]
    if not clipped:
        return []
    clipped.sort()
    out = [clipped[0]]
    for a, b in clipped[1:]:
        if a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if lo < hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """a minus b (both merged)."""
    out = []
    for lo, hi in a:
        cur = lo
        for blo, bhi in b:
            if bhi <= cur or blo >= hi:
                continue
            if blo > cur:
                out.append((cur, blo))
            cur = max(cur, bhi)
            if cur >= hi:
                break
        if cur < hi:
            out.append((cur, hi))
    return out


def total(intervals: list[Interval]) -> float:
    return sum(b - a for a, b in intervals)


# --- scenario configuration -------------------------------------------------

@dataclass(frozen=True)
class StormConfig:
    rate_per_year: float = 0.8      # regional severe-weather events
    mean_duration_h: float = 24.0
    grid_outage_p: float = 0.7      # storm takes the local grid with it
    neighbor_battery_h: float = 4.0  # battery at the macro carrying 5G FWA


@dataclass
class ClassResult:
    name: str
    downtime_h_yr: float
    availability: float
    nines: float
    ettr_h: float                   # mean restore time per down episode
    episodes_per_year: float
    retention: float                # usable-capacity fraction (R2 autonomy)


@dataclass
class Result:
    policy: str
    label: str
    years: int
    monthly_usd: float
    classes: dict[str, ClassResult] = field(default_factory=dict)


# --- event generation -------------------------------------------------------

def _poisson_starts(rng, rate: float) -> list[float]:
    n = _poisson(rng, rate)
    return [rng.uniform(0.0, HOURS) for _ in range(n)]


def _poisson(rng, lam: float) -> int:
    # Knuth; lam is small (<300) everywhere in this model.
    if lam <= 0:
        return 0
    l, k, p = pow(2.718281828459045, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _in_storm(t: float, storms: list[Interval]) -> bool:
    return any(a <= t < b for a, b in storms)


def _transport_year(rng, t: Transport, storms: list[Interval],
                    grid_down: list[Interval],
                    neighbor_battery_h: float) -> tuple[list, list]:
    """(hard-down intervals, degraded intervals) for one transport-year."""
    hard, soft = [], []
    storm_hours = total(storms)
    for m in t.modes:
        starts = _poisson_starts(rng, m.rate_per_year)
        # Extra storm-window arrivals for weather-boosted modes.
        if m.storm_rate_mult > 1.0 and storm_hours > 0:
            extra = m.rate_per_year * (m.storm_rate_mult - 1.0) \
                * storm_hours / HOURS
            for _ in range(_poisson(rng, extra)):
                a, b = storms[rng.randrange(len(storms))]
                starts.append(rng.uniform(a, min(b, HOURS)))
        for s in starts:
            mttr = m.mttr_h
            if m.storm_mttr_mult > 1.0 and _in_storm(s, storms):
                mttr *= m.storm_mttr_mult
            d = rng.expovariate(1.0 / mttr)
            (hard if m.capacity_factor == 0.0 else soft).append((s, s + d))
    if t.grid_dependent:
        # The neighboring macro rides its own battery, then goes dark.
        for a, b in grid_down:
            if b - a > neighbor_battery_h:
                hard.append((a + neighbor_battery_h, b))
    return merge(hard), merge(soft)


def _grid_year(rng, storms: list[Interval], storm: StormConfig,
               routine_rate: float, routine_h: float) -> list[Interval]:
    down = [(s, s + rng.expovariate(1.0 / routine_h))
            for s in _poisson_starts(rng, routine_rate)]
    for a, b in storms:
        if rng.random() < storm.grid_outage_p:
            down.append((a, a + (b - a) * rng.uniform(0.5, 1.2)))
    return merge(down)


def _site_dark(rng, grid_down: list[Interval], p) -> list[Interval]:
    """Grid outages that outlast battery (+ generator, if it starts)."""
    dark = []
    for a, b in grid_down:
        covered = p.battery_h
        if p.has_generator and rng.random() >= p.generator_start_fail_p:
            covered += p.generator_fuel_h
        if b - a > covered:
            dark.append((a + covered, b))
    return merge(dark)


def _timing_down(rng, cfg) -> list[Interval]:
    down = []
    for s in _poisson_starts(rng, cfg.gnss_events_per_year):
        d = rng.expovariate(1.0 / cfg.gnss_event_h)
        if d > cfg.holdover_h:
            down.append((s + cfg.holdover_h, s + d))
    return merge(down)


# --- the simulation ---------------------------------------------------------

def _policy_transports(p: Policy) -> list[tuple[str, Transport]]:
    """(instance-name, transport) pairs; dual fiber = two instances."""
    out = [(n, transport(n)) for n in p.transports]
    if p.dual_fiber:
        out.append(("fiber-b", transport("fiber")))
    return out


def simulate(p: Policy, years: int = 1000, seed: int = 7,
             storm: StormConfig = StormConfig()) -> Result:
    rng = random.Random(seed)
    res = Result(p.name, p.label, years, round(p.monthly_usd(), 0))
    acc = {c.name: {"down": 0.0, "episodes": 0, "ep_h": 0.0, "deg": 0.0}
           for c in CLASSES}

    for _ in range(years):
        storms = merge([(s, s + rng.expovariate(1.0 / storm.mean_duration_h))
                        for s in _poisson_starts(rng, storm.rate_per_year)])
        grid_down = _grid_year(rng, storms, storm,
                               p.power.routine_outages_per_year,
                               p.power.routine_outage_h)
        site_dark = _site_dark(rng, grid_down, p.power)
        timing_down = _timing_down(rng, p.timing)

        downs: dict[str, list[Interval]] = {}
        for iname, t in _policy_transports(p):
            hard, _soft = _transport_year(rng, t, storms, grid_down,
                                          storm.neighbor_battery_h)
            downs[iname] = hard
        # SRLG: a share of primary-fiber cuts also severs the diverse path.
        if p.dual_fiber and downs.get("fiber"):
            shared = [iv for iv in downs["fiber"]
                      if rng.random() < p.shared_cut_fraction]
            downs["fiber-b"] = merge(downs["fiber-b"] + shared)

        for c in CLASSES:
            eligible = [iname for iname, t in _policy_transports(p)
                        if c.name in t.carries]
            all_down = downs[eligible[0]]
            for iname in eligible[1:]:
                all_down = intersect(all_down, downs[iname])
            down = list(site_dark)
            if c.needs_timing:
                down += timing_down
            partition_degraded: list[Interval] = []
            if c.partition_survivable and p.local_autonomy:
                partition_degraded = subtract(merge(all_down),
                                              merge(down))
            else:
                down += all_down
            down = merge(down)
            a = acc[c.name]
            a["down"] += total(down)
            a["episodes"] += len(down)
            a["ep_h"] += total(down)
            a["deg"] += total(partition_degraded)

    for c in CLASSES:
        a = acc[c.name]
        down_yr = a["down"] / years
        avail = 1.0 - down_yr / HOURS
        deg_yr = a["deg"] / years
        retention = 1.0 - (down_yr
                           + (1.0 - c.degraded_retention) * deg_yr) / HOURS
        res.classes[c.name] = ClassResult(
            name=c.name,
            downtime_h_yr=round(down_yr, 2),
            availability=avail,
            nines=round(_nines(avail), 2),
            ettr_h=round(a["ep_h"] / a["episodes"], 2) if a["episodes"]
            else 0.0,
            episodes_per_year=round(a["episodes"] / years, 2),
            retention=round(retention, 5),
        )
    return res


def _nines(avail: float) -> float:
    import math
    if avail >= 1.0:
        return 9.0
    return -math.log10(1.0 - avail)


def ladder(policies, years: int = 1000, seed: int = 7,
           storm: StormConfig = StormConfig()) -> list[Result]:
    return [simulate(p, years, seed, storm) for p in policies]
