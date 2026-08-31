# AI-RAN ↔ Neocloud Resiliency: the last mile, priced in nines

**When an operator hosts tenant AI at a radio site and calls it carrier-grade, what does the last mile actually deliver — and which investment buys the next nine?** This repository answers with a Monte Carlo fault-injection model of the converged AI-RAN/edge-neocloud site: calibrated fiber cuts, microwave rain fades, LEO flaps calibrated against Starlink's measured 15-second reconfiguration cadence, grid outages, storms that correlate all of them, and GNSS jamming against holdover clocks — run against a five-rung resilience policy ladder, P0 (single fiber) to P4 (multi-transport bonding + generator + rubidium + local autonomy).

**TL;DR:** run `airan-resiliency ladder` and the ordering the industry's pitch implies comes out backwards. **(1) A single-fiber edge site is a ~2.7-nines site** (~17 h/yr of tenant downtime; ~19 h/yr for the radio class) — "carrier-grade edge AI" on that footing is marketing. **(2) Multi-transport bonding is the cheapest rung ($400/mo) and it works — but only for tenant traffic**: the fronthaul/timing class R0 cannot ride 5G or LEO, so the class that justifies the site gains nothing. **(3) You cannot bond your way out of a power outage**: every transport rung — second fiber, E-band, bonded 5G+LEO — converges on the same ~3.0-nines wall (the site's own power chain), worth ~0.3 nines over P0; the generator rung buys ~1.2 more — buy the generator (and the $60/mo rubidium clock) before the third link. **(4) E-band microwave matches a second fiber** — within simulation noise on availability — at $700/mo less: the shared-duct SRLG tax eats part of what "diverse" fiber should buy, and rain mostly degrades a properly engineered E-band link rather than dropping it. **(5) Availability nines are cheaper than capacity nines**: no transport rung moves R2 *usable-capacity retention* off ~99.8% — rain fades and lost bond links are charged by capacity share — and even P4 only reaches ~99.88%.

*Part of the DIMAGGI series on turning GPU capital into usable compute — the recovery factor of `usable = nominal × network × scheduling × recovery × placement`, taken to the network edge. Full analysis in [docs/study.md](docs/study.md) (including the Deliverable-1 convergence blueprint: split planes, R0/R1/R2 classes, DPU-enforced zero trust, and what control-plane machinery is actually mature); all calibrations trace to [REFERENCES.md](REFERENCES.md). Companion repo: [edge-continuum-placement](https://github.com/dimaggi-ai/edge-continuum-placement) — where workloads belong on the continuum this repo keeps alive.*

---

## What each rung buys

![Availability ladder](figures/availability_ladder.png)

Transport rungs (P1–P3) move R1/R2 from 2.7 to ~3.0 nines and stall — the $400 bonding rung, the $800 E-band rung, and the $1,500 second fiber all land within noise of each other, because what remains is the site's own power chain. And P3's R0 equals P0's: the ladder holds everything else fixed (same 4 h battery, same clock), and bonded 5G/LEO paths cannot carry a ~100 µs fronthaul budget. The jump to ~4.2 nines across every class is the generator rung.

## Where the hours live

![Downtime split](figures/downtime_split.png)

Decomposed by cause: bonding (P3) eliminates the connectivity share of tenant downtime almost entirely — what remains is *pure power*, plus the GNSS tail for R0 that only a better holdover clock (rubidium: 36 h inside ±1.5 µs, vs ~6 h for OCXO) removes. That is consistent with the FCC's disaster record — more than half of cell-site outages in major events are power failures — which the storm process was calibrated to reflect. What survives at P4 is the shape carrier engineers will recognize: roughly one ~21-hour event every ~40 years, the generator that didn't start in the storm that outlasted everything else.

## The price of a nine

![Cost per nine](figures/cost_per_nine.png)

P0→P4 is ~1.5 additional nines of tenant availability for $2,120/month. The best-value transport rung is the cheapest one (bonding, $400); the decisive rung is the generator; the worst $/nine on the board is the second fiber — $1,500 for what E-band delivers at $800 and bonding approximates at $400.

## Quickstart

```
pip install airan-neocloud-resiliency        # or: pip install -e .
airan-resiliency ladder                       # P0->P4, availability + cost
airan-resiliency policy -p P3                 # one policy: ETTR, retention
airan-resiliency transports                   # the calibrated failure catalog
```

Every rate, repair time, battery-hour, and dollar is a dataclass field — recalibrate to your region and rerun:

```python
from resiliency.policies import P2
from resiliency.sim import StormConfig, simulate

hurricane_coast = StormConfig(rate_per_year=2.5, mean_duration_h=36.0)
simulate(P2, years=2000, storm=hurricane_coast).classes["R2"].nines
```

## The validation project

Every headline above is a Monte Carlo result, and a Monte Carlo result
that only holds at one seed is a coincidence with a README. The
[validation registry](validation.py) re-runs each finding across **eight
independent seeds** (none of them the repo's default) at the 2,000-year
horizon the study's own seed-spread table uses, and requires it to hold
in *all* of them.

**Calibrated** — the three numbers a published source can settle. With
the storm process switched off, the grid inputs yield **1.95 interruption
hours** per customer-year against EIA's ~2 h routine component for 2024
[12]; the rubidium/OCXO holdover constants are the vendor's recommended
budget rows, used verbatim [13]; the single-fiber site lands at **2.70
nines** (2.68–2.72 across seeds), pinned to ±0.01 — about two standard
errors, fixed in advance rather than widened until the run fit inside it
[1, 2].

**Emergent** — findings the model was not tuned to produce, none of them
resting on a threshold. The three transport rungs differ from one another
by **0.044 nines** on average, *less* than the **0.067** a single rung
varies against its own reseeding — which is how "within simulation noise"
gets stated without a hand-picked number. Every transport rung beats the
best single-fiber run. The generator rung buys **more than the best
transport rung bought over a single fiber, in every seed** — an ordering,
not a margin (an earlier version asserted "≥1.0 nines", a number picked
after seeing 1.15; it failed on reseeding, and this is the replacement).
Bonding moves R0 by 0.014 nines against a single fiber, inside the 0.040
that P0's own R0 moves across seeds: the class that justifies the radio
site gains nothing measurable from the cheapest rung. R2 capacity
retention never clears 99.9% at any transport rung.

**Sanity** — the model's own inputs and statistics, claiming no evidence.
The 11.9 h of grid interruption the storms add is pinned as what it is: a
property of `StormConfig`, not a calibration, and every power finding
rests on it. P4's availability is the *least* seed-stable number on the
board (sd 0.088 nines, against a worst case of 0.033 among all four rungs
below it) — quote it as a band, never as a point estimate.

What the registry does **not** check is printed every run: the storm
magnitude, the 6% generator start-failure rate, the 15% SRLG fraction,
P4's absolute availability, and the 60% autonomy retention figure are all
uncalibrated inputs, named so they cannot pass for results.

Six tests in [`tests/test_validation.py`](tests/test_validation.py) break
the simulator on purpose — delete the power chain, delete transport
redundancy, let a satellite carry fronthaul, switch off the storms, move
the grid inputs, double the fiber failure rates — and require the
registry to go **red** on the point that claims to be about that
mechanism. A registry that cannot fail is not evidence.

```
make validation   # 8 seeds x 2,000 simulated years, ~8 s
```

## Reproduce

```
make test        # the registry, then 41 tests: eligibility, monotonicity,
                 # findings, and the negative controls above
make figures     # regenerates figures/ (needs matplotlib)
```

Python 3.10+, stdlib only; `matplotlib` only for figures. The findings the study reports are asserted as test invariants — they must *fall out* of the simulation, not be asserted by it.

## Series — turning GPU capital into usable compute

- **GPU Cluster Networking** ([network-vs-more-gpus](https://github.com/dimaggi-ai/network-vs-more-gpus)) · **GPU Cluster Scheduling** ([scheduler-vs-more-gpus](https://github.com/dimaggi-ai/scheduler-vs-more-gpus))
- **Compute↔Power Placement** ([compute-power-placement](https://github.com/dimaggi-ai/compute-power-placement)) · **Edge↔Neocloud Placement** ([edge-continuum-placement](https://github.com/dimaggi-ai/edge-continuum-placement)) — the companion: where workloads belong
- **Chaos Fidelity Standard** ([ai-cluster-chaos-fidelity](https://github.com/dimaggi-ai/ai-cluster-chaos-fidelity)) · **Reliability Economics** ([reliability-economics](https://github.com/dimaggi-ai/reliability-economics)) · **Governed Autonomy** ([governed-autonomy](https://github.com/dimaggi-ai/governed-autonomy))
- **AI-RAN ↔ Neocloud Resiliency** (this work) — the last mile, priced in nines

---

*Margaret (Maggie) Nanyonga — Founder & Principal Architect, [DIMAGGI AI](https://dimaggi.ai). Governed AI infrastructure: the control, reliability, and audit layer for autonomous systems operating production networks and compute.*
