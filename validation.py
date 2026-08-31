#!/usr/bin/env python3
"""The validation project: public outage statistics, and every finding re-run
across independent seeds.

The invariant suite (tests/) checks the model's behaviors at ONE seed.
That is the right place to catch a broken mechanism and the wrong place
to establish that a *finding* is real: a Monte Carlo result that only
holds at seed 7 is a coincidence with a README. This registry does two
things the suite cannot:

  1. **Public outage statistics.** The grid process's ROUTINE component
     is checked against EIA's published routine interruption hours, and
     the holdover constants against their vendor source.
  2. **Multi-seed Monte Carlo.** Every headline claim in the README is
     re-run across eight independent seeds at the horizon the study's
     own tables use, and required to hold in ALL of them — including the
     uncomfortable one: the P4 rung's own availability figure is the
     least seed-stable number on the board, and this registry says so
     rather than quoting the prettiest run.

Three kinds of points, honestly separated:

  calibrated  the model pinned to a published figure. Passing proves it
              has not drifted from its citation, not that it predicts.
              Only these carry a reference — a citation beside a
              simulation output would dress a model result as a sourced
              one. The sources BEHIND an emergent finding's inputs are
              named in its note instead.
  emergent    findings the model was not tuned to produce, required to
              hold across all seeds. These can fail; that is the point.
  sanity      properties of the model's own statistics and structure
              (seed spread, determinism, its own inputs). Cites no
              external evidence and claims none.

Two rules this registry follows, learned from the ones that came before:

  * **No threshold chosen after seeing the number.** Where a claim is
    "within noise", the comparison is against the model's OWN reseeding
    spread, so there is nothing to tune. Where a tolerance is fixed, it
    is a constant set once — never recomputed from the run it judges,
    which is how a check ends up unable to fail.
  * **What is NOT checked is named.** See DECLINED. A registry that
    lists only the anchors it passes is a highlight reel.

Run: python3 validation.py   (exit 1 if any point fails; ~8 s)
"""

from __future__ import annotations

import dataclasses
import pathlib
import random
import re
import statistics
import sys

from resiliency.policies import LADDER, P0, P4
from resiliency.sim import (
    StormConfig,
    _grid_year,
    _poisson_starts,
    merge,
    simulate,
    total,
)

# Independent of the repo's default seed (7) on purpose.
SEEDS = (11, 23, 37, 51, 67, 83, 97, 113)
# The horizon the study's own seed-spread table uses (docs/study.md,
# "Monte Carlo precision"). At 400 years the rung-to-rung differences are
# the same size as the reseeding noise, which is a fact about the sample
# size rather than about the ladder.
YEARS = 2000
GRID_YEARS = 4000

# The two model inputs the grid points are about, hoisted to module level
# so a test can swap one out and watch the registry go red.
GRID_POWER = P0.power
STORM = StormConfig()

TRANSPORT_RUNGS = ("P1", "P2", "P3")

# Fixed constants, set once from the shipped configuration and never
# recomputed from the run they judge — a tolerance computed alongside the
# value it brackets cannot fail. P0_NINES_TOL is ~2 standard errors on
# eight seeds x 2,000 years (measured sd ~0.013 nines, SE ~0.005).
P0_NINES = 2.70
P0_NINES_TOL = 0.01
EIA_ROUTINE_H = 2.0        # [12] ~2 h routine, of ~11 h total for 2024
EIA_ROUTINE_TOL = 0.2
STORM_EXCESS_H = 11.9      # this model's storm component; NOT calibrated
STORM_EXCESS_TOL = 1.5

REFERENCES = pathlib.Path(__file__).with_name("REFERENCES.md")

# Anchors a skeptic would want and this registry does NOT provide.
DECLINED: tuple[tuple[str, str], ...] = (
    ("The storm process's magnitude",
     "rate 0.8/yr, mean 24 h, grid_outage_p 0.7 are planning assumptions. "
     "The FCC record [10] supports the DIRECTION (power dominates in major "
     "events), not these numbers. Every emergent point inherits them."),
    ("The 6% generator start-failure probability",
     "an industry rule of thumb with no public per-event telecom statistic. "
     "It sets how much of P4's remaining downtime exists at all."),
    ("The 15% SRLG shared-cut fraction",
     "a planning assumption, and the single input that decides how much a "
     "second fiber is worth. Audit your own duct maps before quoting P1."),
    ("P4's absolute availability",
     "no public per-site measurement exists to check ~4 nines against, which "
     "is why P4 is reported as a band and its sd is pinned as a point."),
    ("The 60% degraded-retention figure for local autonomy",
     "a design target for cached models and a local index, not a "
     "measurement. Nothing here validates it."),
)


@dataclasses.dataclass(frozen=True)
class Point:
    name: str
    kind: str        # 'calibrated' | 'emergent' | 'sanity'
    ref: str         # '[n]' for calibrated points; '-' for the rest
    expected: float
    tolerance: float
    actual: float
    note: str

    @property
    def ok(self) -> bool:
        return abs(self.actual - self.expected) <= self.tolerance


def _sweep(years: int, seeds: tuple[int, ...]) -> dict[str, dict[str, list[float]]]:
    """Every ladder policy, every seed. The registry's raw material."""
    out: dict[str, dict[str, list[float]]] = {}
    for p in LADDER:
        runs = [simulate(p, years=years, seed=s) for s in seeds]
        out[p.name] = {
            "r2_nines": [r.classes["R2"].nines for r in runs],
            "r0_nines": [r.classes["R0"].nines for r in runs],
            "r2_down_h": [r.classes["R2"].downtime_h_yr for r in runs],
            "r2_retention": [r.classes["R2"].retention for r in runs],
        }
    return out


def _grid_hours_per_year(years: int, storm: StormConfig, seed: int) -> float:
    """Simulated grid interruption hours per year under one storm process."""
    rng = random.Random(seed)
    acc = 0.0
    for _ in range(years):
        storms = merge([
            (s, s + rng.expovariate(1.0 / storm.mean_duration_h))
            for s in _poisson_starts(rng, storm.rate_per_year)
        ])
        acc += total(_grid_year(rng, storms, storm,
                                GRID_POWER.routine_outages_per_year,
                                GRID_POWER.routine_outage_h))
    return acc / years


def _spread(xs: list[float]) -> float:
    """How far one quantity moves when nothing changes but the seed."""
    return max(xs) - min(xs)


def _declared_refs() -> set[str]:
    """Reference numbers REFERENCES.md actually defines."""
    if not REFERENCES.exists():
        return set()
    return set(re.findall(r"^\*\*\[(\d+)\]", REFERENCES.read_text(), re.M))


def points(years: int = YEARS, seeds: tuple[int, ...] = SEEDS,
           grid_years: int = GRID_YEARS) -> tuple[Point, ...]:
    pts: list[Point] = []
    sw = _sweep(years, seeds)
    n = len(seeds)

    # ---------------------------------------------------------- calibrated
    # EIA splits its interruption hours into routine and major-event, and
    # only the routine half is a number this model can honestly be pinned
    # to: the storm component is a planning assumption about a
    # storm-exposed edge site, not a national average. So the calibrated
    # point checks the routine process ALONE (storms switched off), and the
    # storm component is pinned separately as what it is — a model input.
    routine_h = _grid_hours_per_year(
        grid_years, dataclasses.replace(STORM, rate_per_year=0.0), 101)
    pts.append(Point(
        "routine-grid-hours-match-eia-routine", "calibrated", "[12]",
        expected=EIA_ROUTINE_H, tolerance=EIA_ROUTINE_TOL, actual=routine_h,
        note=f"With the storm process off, the site's grid inputs "
             f"({GRID_POWER.routine_outages_per_year}/yr x "
             f"{GRID_POWER.routine_outage_h} h) yield {routine_h:.2f} "
             f"interruption hours per customer-year against EIA's ~2 h "
             f"routine component for 2024 (of ~11 h total, ~9 h of it from "
             f"major events). This is the ONLY grid number in the model "
             f"that a published figure can settle; halve either input and "
             f"this point goes red.",
    ))
    pts.append(Point(
        "holdover-constants", "calibrated", "[13]",
        expected=36.0, tolerance=0.0, actual=float(P4.timing.holdover_h),
        note="Rubidium holdover 36 h against 6 h for the OCXO class, used "
             "verbatim as TimingConfig.holdover_h. The vendor's MEASURED "
             "figure is 400 ns over 24 h; 36 h is the row of its "
             "recommended budget table (750 ns at 36 h) that still sits "
             "inside the 3GPP +/-1.5 us cell budget — a recommendation "
             "adopted as an input, not a measurement reproduced. This "
             "point can only fail if site.py drifts from its citation; it "
             "is a drift detector and claims nothing more.",
    ))
    p0_nines = statistics.mean(sw["P0"]["r2_nines"])
    p0_se = statistics.stdev(sw["P0"]["r2_nines"]) / (n ** 0.5)
    pts.append(Point(
        "single-fiber-site-is-2.7-nines", "calibrated", "[1][2]",
        expected=P0_NINES, tolerance=P0_NINES_TOL, actual=p0_nines,
        note=f"The README's headline: a single-fiber edge site is a "
             f"~2.7-nines site. Across {n} seeds it lands "
             f"{min(sw['P0']['r2_nines']):.2f}-"
             f"{max(sw['P0']['r2_nines']):.2f} "
             f"({statistics.mean(sw['P0']['r2_down_h']):.1f} h/yr of "
             f"tenant downtime), mean {p0_nines:.4f} with a standard error "
             f"of {p0_se:.4f}. The +/-{P0_NINES_TOL} band is a fixed "
             f"constant of about two standard errors — not a band widened "
             f"until the run fit inside it. Calibrated because the fiber "
             f"cut rate and repair time that produce it are the published "
             f"planning numbers.",
    ))

    # ------------------------------------------------------------ emergent
    # "Within simulation noise" stated without a hand-picked threshold:
    # compare the spread BETWEEN the three rungs against the spread each
    # single rung shows against ITSELF across seeds. If three different
    # investments differ by less than one investment differs from its own
    # reseeding, they are indistinguishable at this sample size. Both sides
    # are means over their sample, so neither is a single lucky extreme.
    between = statistics.mean(
        max(sw[x]["r2_nines"][i] for x in TRANSPORT_RUNGS)
        - min(sw[x]["r2_nines"][i] for x in TRANSPORT_RUNGS)
        for i in range(n)
    )
    within = statistics.mean(_spread(sw[x]["r2_nines"]) for x in TRANSPORT_RUNGS)
    pts.append(Point(
        "transport-rungs-tie-within-monte-carlo-noise", "emergent", "-",
        expected=1.0, tolerance=0.0, actual=float(between <= within),
        note=f"The three transport rungs — second fiber ($1,500/mo), "
             f"E-band ($800), bonded 5G+LEO ($400) — differ from each "
             f"other by {between:.3f} nines on average, LESS than the "
             f"{within:.3f} nines a single rung varies against its own "
             f"reseeding. Stated this way the claim needs no chosen "
             f"threshold. Nothing equalizes them in the model — different "
             f"transports, failure modes and costs; they converge because "
             f"what remains after the first redundant path is the site's "
             f"own power chain. Driven by the cut rates of [1] and the "
             f"bonding mechanism of [8]; the tie is a model output, which "
             f"is why no reference sits beside it.",
    ))
    beat_p0 = sum(
        1 for i in range(n)
        if min(sw[x]["r2_nines"][i] for x in TRANSPORT_RUNGS)
        > max(sw["P0"]["r2_nines"])
    )
    pts.append(Point(
        "every-transport-rung-beats-single-fiber", "emergent", "-",
        expected=float(n), tolerance=0.0, actual=float(beat_p0),
        note="In every seed the worst transport rung still beats the "
             "BEST single-fiber run across all seeds — the P0-to-"
             "redundancy step is real and separable from noise, even "
             "though the choice among the three rungs is not.",
    ))
    # The generator's value stated as an ORDERING rather than a margin: in
    # every seed the step from the best transport rung to the generator
    # rung is larger than the step from no redundancy to ANY transport
    # rung. An earlier version asserted ">= 1.0 nines", a number chosen
    # after seeing 1.15 — it failed on reseeding at shorter horizons. This
    # form has nothing to tune and held in every seed set tried.
    gen_outranks = sum(
        1 for i in range(n)
        if sw["P4"]["r2_nines"][i] - sw["P3"]["r2_nines"][i]
        > max(sw[x]["r2_nines"][i] - sw["P0"]["r2_nines"][i]
              for x in TRANSPORT_RUNGS)
    )
    gen_gain = [sw["P4"]["r2_nines"][i]
                - max(sw[x]["r2_nines"][i] for x in TRANSPORT_RUNGS)
                for i in range(n)]
    pts.append(Point(
        "generator-outranks-every-transport-rung", "emergent", "-",
        expected=float(n), tolerance=0.0, actual=float(gen_outranks),
        note=f"In every seed the generator rung buys MORE than the best "
             f"transport rung bought over a single fiber — measured "
             f"{min(gen_gain):.2f}-{max(gen_gain):.2f} nines over the best "
             f"transport rung, mean {statistics.mean(gen_gain):.2f} — for "
             f"less than the second fiber. An ordering, not a margin: "
             f"there is no threshold here to fit. Consistent with the "
             f"FCC's disaster record [10] that more than half of cell-site "
             f"outages in major events are power failures, though it is "
             f"the storm process that produces it (see DECLINED).",
    ))
    r0_gap = statistics.mean(
        abs(sw["P3"]["r0_nines"][i] - sw["P0"]["r0_nines"][i])
        for i in range(n)
    )
    r0_noise = _spread(sw["P0"]["r0_nines"])
    pts.append(Point(
        "bonding-leaves-r0-inside-its-own-noise", "emergent", "-",
        expected=1.0, tolerance=0.0, actual=float(r0_gap <= r0_noise),
        note=f"The bonded 5G+LEO rung moves the R0 (fronthaul/timing) "
             f"class by {r0_gap:.3f} nines on average against a single "
             f"fiber — less than the {r0_noise:.3f} nines P0's own R0 "
             f"moves across seeds. The class that justifies the radio site "
             f"gains nothing measurable from the cheapest availability "
             f"rung, because a ~100 us fronthaul budget cannot ride a "
             f"25-60 ms satellite or a jittery cellular path [15]. The "
             f"repo's least comfortable finding, and stated against the "
             f"model's own noise rather than a chosen tolerance.",
    ))
    ret_wall = sum(
        1 for x in TRANSPORT_RUNGS
        for r in sw[x]["r2_retention"] if r <= 0.999
    )
    pts.append(Point(
        "capacity-retention-wall", "emergent", "-",
        expected=float(len(TRANSPORT_RUNGS) * n), tolerance=0.0,
        actual=float(ret_wall),
        note=f"Across the three transport rungs and all {n} seeds, R2 "
             f"usable-capacity retention never clears 99.9% "
             f"(~{statistics.mean(sw['P3']['r2_retention']):.4f}), and "
             f"even P4 reaches only "
             f"~{statistics.mean(sw['P4']['r2_retention']):.4f}. P0 is "
             f"excluded on purpose: a site with no redundancy fails this "
             f"bar trivially, and counting it would pad the result with "
             f"the one rung nobody claims otherwise about. Availability "
             f"nines are cheaper than capacity nines: rain fades and lost "
             f"bond links are charged by capacity share, which no amount "
             f"of transport redundancy refunds.",
    ))

    # -------------------------------------------------------------- sanity
    full_h = _grid_hours_per_year(grid_years, STORM, 101)
    pts.append(Point(
        "storm-excess-is-a-model-input", "sanity", "-",
        expected=STORM_EXCESS_H, tolerance=STORM_EXCESS_TOL,
        actual=full_h - routine_h,
        note=f"Switching the storm process on takes the grid from "
             f"{routine_h:.2f} to {full_h:.2f} interruption hours per "
             f"customer-year — an excess of {full_h - routine_h:.2f} h "
             f"that is a PROPERTY OF StormConfig, not a calibration. It "
             f"sits above EIA's ~9 h major-event component for 2024 "
             f"deliberately (a storm-exposed edge site is not the average "
             f"customer), but no published figure settles the number, so "
             f"it is pinned here as an input rather than presented as "
             f"evidence. Every power finding in the study rests on it.",
    ))
    sd = {x: statistics.stdev(sw[x]["r2_nines"]) for x in sw}
    pts.append(Point(
        "top-rung-is-the-least-seed-stable", "sanity", "-",
        expected=1.0, tolerance=0.0,
        actual=float(sd["P4"] > max(sd[x] for x in ("P0", "P1", "P2", "P3"))),
        note=f"The honest caveat, pinned as a check: P4's availability is "
             f"the LEAST reproducible number on the ladder (sd "
             f"{sd['P4']:.3f} nines across seeds, against a worst-case "
             f"{max(sd[x] for x in ('P0', 'P1', 'P2', 'P3')):.3f} among "
             f"ALL four rungs below it, not just P0), because once the "
             f"generator removes the common failures the remainder is a "
             f"handful of rare long events. Quote P4 as a band, never as a "
             f"point estimate.",
    ))
    a = simulate(LADDER[2], years=50, seed=5)
    b = simulate(LADDER[2], years=50, seed=5)
    pts.append(Point(
        "simulation-is-deterministic-per-seed", "sanity", "-",
        expected=1.0, tolerance=0.0,
        actual=float(a.classes["R2"].downtime_h_yr
                     == b.classes["R2"].downtime_h_yr),
        note="Same seed, same result — every number in this registry is "
             "reproducible by rerunning it.",
    ))
    inversions = sum(
        1 for i in range(len(LADDER) - 1)
        if LADDER[i + 1].monthly_usd() < LADDER[i].monthly_usd()
    )
    pts.append(Point(
        "ladder-has-two-price-inversions", "sanity", "-",
        expected=2.0, tolerance=0.0, actual=float(inversions),
        note="The ladder rungs are NOT priced in ascending order: two of "
             "them (E-band $2,460/mo after the second fiber's $3,160; "
             "bonding $2,060 after that) cost less than the rung before. "
             "The name says what is counted — a price ordering — because "
             "the earlier name claimed the ladder was ordered by "
             "resilience, which is a different statement and one this "
             "count does not check.",
    ))
    declared = _declared_refs()
    used = {r for p in pts for r in re.findall(r"\d+", p.ref)}
    pts.append(Point(
        "every-ref-resolves", "sanity", "-",
        expected=0.0, tolerance=0.0, actual=float(len(used - declared)),
        note=f"Every reference cited by a point above resolves to an entry "
             f"in REFERENCES.md ({len(used)} cited, {len(declared)} "
             f"declared). Catches a citation that was renumbered or "
             f"deleted out from under a claim.",
    ))

    return tuple(pts)


def validate(**kw) -> tuple[tuple[Point, ...], bool]:
    pts = points(**kw)
    return pts, all(p.ok for p in pts)


def main() -> int:
    pts, ok = validate()
    w = max(len(p.name) for p in pts)
    print(f"{'point':<{w}}  {'kind':<10}  {'ref':<8}  {'expected':>8}  "
          f"{'actual':>8}  verdict")
    for p in pts:
        print(f"{p.name:<{w}}  {p.kind:<10}  {p.ref:<8}  {p.expected:>8.3f}  "
              f"{p.actual:>8.3f}  {'PASS' if p.ok else 'FAIL'}")
    print()
    print("not checked here:")
    for what, why in DECLINED:
        print(f"  - {what}: {why}")
    print()
    if ok:
        print(f"all points reproduced over {len(SEEDS)} independent seeds "
              f"x {YEARS} simulated years — the calibrated points hold the "
              f"model to the one grid figure a public source can settle "
              f"and to its vendor constants, the emergent points show "
              f"every headline finding survives reseeding without a "
              f"fitted threshold, and the sanity points pin the model's "
              f"own inputs and statistics (including where it is least "
              f"stable)")
    else:
        print("VALIDATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
