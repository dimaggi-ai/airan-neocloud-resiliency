"""airan-resiliency: what does each rung of the resilience ladder buy?

Subcommands:
  ladder [--years N] [--seed S]     P0->P4, per-class availability + cost
  policy -p P [--years N]           one policy in detail
  transports                        the calibrated failure catalog
"""

import argparse
import sys

from .classes import CLASSES
from .policies import LADDER, policy
from .sim import StormConfig, ladder, simulate
from .transports import CATALOG


def _fmt_avail(cr) -> str:
    pct = cr.availability * 100
    return f"{pct:.4f}% ({cr.nines:.1f} nines)"


def _cmd_ladder(args) -> int:
    results = ladder(LADDER, years=args.years, seed=args.seed)
    base = results[0]
    print(f"{args.years} simulated years/policy, seed {args.seed}\n")
    hdr = (f"{'policy':<8}{'$/mo':>7}   "
           + "".join(f"{c.name+' avail':<22}" for c in CLASSES)
           + "R2 retention")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        row = f"{r.policy:<8}{r.monthly_usd:>7,.0f}   "
        for c in CLASSES:
            row += f"{_fmt_avail(r.classes[c.name]):<22}"
        row += f"{r.classes['R2'].retention * 100:.3f}%"
        print(row)
        print(f"         ({r.label})")
    r2_gain = (results[-1].classes["R2"].nines
               - base.classes["R2"].nines)
    dollars = results[-1].monthly_usd - base.monthly_usd
    print(f"\nP0 -> P4 buys {r2_gain:.1f} extra nines of R2 for "
          f"${dollars:,.0f}/month more")
    return 0


def _cmd_policy(args) -> int:
    p = policy(args.policy)
    r = simulate(p, years=args.years, seed=args.seed)
    print(f"{p.name}: {p.label}  (${r.monthly_usd:,.0f}/month)\n")
    for c in CLASSES:
        cr = r.classes[c.name]
        print(f"  {c.name}: {_fmt_avail(cr)}")
        print(f"      downtime {cr.downtime_h_yr:.1f} h/yr over "
              f"{cr.episodes_per_year:.1f} episodes; mean restore "
              f"{cr.ettr_h:.1f} h; usable capacity "
              f"{cr.retention * 100:.2f}%")
    return 0


def _cmd_transports(_args) -> int:
    for t in CATALOG.values():
        print(f"{t.name} ({t.kind}): {t.capacity_gbps:g} Gbps, "
              f"{t.rtt_ms:g} ms RTT, carries {'/'.join(t.carries)}, "
              f"${t.monthly_usd:,.0f}/mo"
              + (", grid-dependent" if t.grid_dependent else ""))
        for m in t.modes:
            kind = ("hard outage" if m.capacity_factor == 0.0
                    else f"degrades to {m.capacity_factor:.0%}")
            print(f"    {m.name}: {m.rate_per_year:g}/yr x "
                  f"{m.mttr_h:g} h ({kind})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="airan-resiliency",
        description="Monte Carlo resilience of the AI-RAN last mile.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lad = sub.add_parser("ladder", help="P0->P4 comparison")
    pol = sub.add_parser("policy", help="one policy in detail")
    pol.add_argument("-p", "--policy", required=True,
                     choices=[p.name for p in LADDER])
    sub.add_parser("transports", help="failure catalog")

    for s in (lad, pol):
        s.add_argument("--years", type=int, default=1000)
        s.add_argument("--seed", type=int, default=7)

    args = ap.parse_args(argv)
    return {"ladder": _cmd_ladder, "policy": _cmd_policy,
            "transports": _cmd_transports}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
