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
  R0 down  = site dark  OR timing lost  OR all fronthaul-grade links
             down -- where 'down' for R0 includes degraded links: a
             rain-faded E-band at 25% capacity cannot carry fronthaul.
  R1 down  = site dark  OR all R1-eligible links down (hard outages)
  R2 down  = site dark  OR (all R2-eligible links down, unless the policy
             provisions local autonomy -- then those hours run degraded
             at the class's retention factor instead of down)
  R2 retention additionally charges partial-capacity hours: losing one
  link of a bond, or a rain fade, costs capacity-share x lost-fraction
  even while the class stays 'available'.
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
    # Clip FIRST, then drop empties: an event starting past year-end
    # must vanish, not survive as a zero-length interval.
    clipped = [(max(0.0, a), min(HOURS, b)) for a, b in intervals]
    clipped = [(a, b) for a, b in clipped if b > a]
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
    # Usable-capacity fraction: charges full-down hours, degraded
    # local-autonomy hours (at 1 - degraded_retention), and -- for
    # capacity-weighted classes -- partial-capacity hours on the bond.
    retention: float


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


@dataclass
class TransportYear:
    """One transport-instance-year of failure intervals (all merged)."""
    hard: list                      # hard outages (capacity_factor == 0)
    soft: list                      # [(capacity_factor, intervals)] per
                                    # degraded mode
    cuts: list                      # physical-plant severances only --
                                    # the SRLG-shareable subset of hard


def _transport_year(rng, t: Transport, storms: list[Interval],
                    grid_down: list[Interval],
                    neighbor_battery_h: float) -> TransportYear:
    hard, soft, cuts = [], [], []
    storm_hours = total(storms)
    for m in t.modes:
        starts = _poisson_starts(rng, m.rate_per_year)
        # Extra storm-window arrivals for weather-boosted modes; pick
        # the storm weighted by its duration (a 40 h storm attracts
        # arrivals over 40 hours, not one share).
        if m.storm_rate_mult > 1.0 and storm_hours > 0:
            extra = m.rate_per_year * (m.storm_rate_mult - 1.0) \
                * storm_hours / HOURS
            durations = [b - a for a, b in storms]
            for _ in range(_poisson(rng, extra)):
                a, b = rng.choices(storms, weights=durations)[0]
                starts.append(rng.uniform(a, b))
        events = []
        for s in starts:
            mttr = m.mttr_h
            if m.storm_mttr_mult > 1.0 and _in_storm(s, storms):
                mttr *= m.storm_mttr_mult
            d = rng.expovariate(1.0 / mttr)
            events.append((s, s + d))
        if m.capacity_factor == 0.0:
            hard += events
            if m.physical_cut:
                cuts += events
        elif events:
            soft.append((m.capacity_factor, merge(events)))
    if t.grid_dependent:
        # The neighboring macro rides its own battery, then goes dark.
        for a, b in grid_down:
            if b - a > neighbor_battery_h:
                hard.append((a + neighbor_battery_h, b))
    return TransportYear(merge(hard), soft, merge(cuts))


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
    names = [n for n, _ in out]
    if len(names) != len(set(names)):
        raise ValueError(
            f"duplicate transport instance in {names!r}: for a second "
            "fiber use dual_fiber=True; otherwise register a renamed "
            "custom() transport in the CATALOG")
    return out


def _class_down(c: ResilienceClass, ty: TransportYear) -> list[Interval]:
    """Intervals during which this transport cannot carry class c."""
    if c.needs_full_capacity:
        return merge(ty.hard + [iv for _cf, ivs in ty.soft for iv in ivs])
    return ty.hard


def simulate(p: Policy, years: int = 2000, seed: int = 7,
             storm: StormConfig = StormConfig()) -> Result:
    rng = random.Random(seed)
    res = Result(p.name, p.label, years, round(p.monthly_usd(), 0))
    acc = {c.name: {"down": 0.0, "episodes": 0, "ep_h": 0.0, "deg": 0.0,
                    "caploss": 0.0}
           for c in CLASSES}
    pt = _policy_transports(p)

    for _ in range(years):
        storms = merge([(s, s + rng.expovariate(1.0 / storm.mean_duration_h))
                        for s in _poisson_starts(rng, storm.rate_per_year)])
        grid_down = _grid_year(rng, storms, storm,
                               p.power.routine_outages_per_year,
                               p.power.routine_outage_h)
        site_dark = _site_dark(rng, grid_down, p.power)
        timing_down = _timing_down(rng, p.timing)

        tyears: dict[str, TransportYear] = {}
        for iname, t in pt:
            tyears[iname] = _transport_year(rng, t, storms, grid_down,
                                            storm.neighbor_battery_h)
        # SRLG: a share of primary-fiber physical CUTS also severs the
        # 'diverse' path (shared duct/bridge/backhoe). Upstream and
        # equipment events are not shared -- the paths are diverse
        # everywhere except in the ground.
        if p.dual_fiber and tyears["fiber"].cuts:
            shared = [iv for iv in tyears["fiber"].cuts
                      if rng.random() < p.shared_cut_fraction]
            if shared:
                tb = tyears["fiber-b"]
                tb.hard = merge(tb.hard + shared)
                tb.cuts = merge(tb.cuts + shared)

        for c in CLASSES:
            eligible = [(iname, t) for iname, t in pt
                        if c.name in t.carries]
            if eligible:
                all_down = _class_down(c, tyears[eligible[0][0]])
                for iname, _t in eligible[1:]:
                    all_down = intersect(all_down,
                                         _class_down(c, tyears[iname]))
            else:
                all_down = [(0.0, HOURS)]   # no eligible link, ever
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
            # Partial-capacity hours: losing one link of the bond, or a
            # rain fade, charged by capacity share -- but never during
            # hours already charged as down or degraded-autonomy.
            if c.capacity_weighted and eligible:
                cap_total = sum(t.capacity_gbps for _i, t in eligible)
                exclude = merge(down + partition_degraded)
                for iname, t in eligible:
                    ty = tyears[iname]
                    share = t.capacity_gbps / cap_total
                    a["caploss"] += share * total(
                        subtract(ty.hard, exclude))
                    for cf, ivs in ty.soft:
                        live = subtract(subtract(ivs, ty.hard), exclude)
                        a["caploss"] += share * (1.0 - cf) * total(live)

    for c in CLASSES:
        a = acc[c.name]
        down_yr = a["down"] / years
        avail = 1.0 - down_yr / HOURS
        deg_yr = a["deg"] / years
        cap_yr = a["caploss"] / years
        retention = 1.0 - (down_yr
                           + (1.0 - c.degraded_retention) * deg_yr
                           + cap_yr) / HOURS
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


def ladder(policies, years: int = 2000, seed: int = 7,
           storm: StormConfig = StormConfig()) -> list[Result]:
    return [simulate(p, years, seed, storm) for p in policies]
