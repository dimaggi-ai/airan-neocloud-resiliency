"""Generate the study figures into figures/.

  availability_ladder.png   nines per class, P0 -> P4
  cost_per_nine.png         $/month vs R2 nines: the price curve
  downtime_split.png        where the remaining hours live (power vs
                            connectivity vs timing), P0/P3/P4

Run: python3 run.py
"""

from dataclasses import replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from resiliency.classes import CLASSES  # noqa: E402
from resiliency.policies import LADDER, Policy  # noqa: E402
from resiliency.sim import StormConfig, ladder, simulate  # noqa: E402
from resiliency.site import PowerConfig, TimingConfig  # noqa: E402
from resiliency.transports import CATALOG, custom  # noqa: E402

import pathlib  # noqa: E402

FIGDIR = pathlib.Path(__file__).parent / "figures"
FIGDIR.mkdir(exist_ok=True)

INK = "#1a1a2e"
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.edgecolor": INK, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
})

YEARS = 2000
SEED = 7
RESULTS = ladder(LADDER, years=YEARS, seed=SEED)

CLASS_COLOR = {"R0": "#c0392b", "R1": "#2980b9", "R2": "#27ae60"}


def availability_ladder():
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    width = 0.26
    xs = range(len(RESULTS))
    for k, c in enumerate(CLASSES):
        vals = [r.classes[c.name].nines for r in RESULTS]
        ax.bar([x + (k - 1) * width for x in xs], vals, width,
               color=CLASS_COLOR[c.name], label=c.name)
    short = {"P0": "single\nfiber", "P1": "dual diverse\nfiber",
             "P2": "fiber +\ne-band MW", "P3": "fiber + 5G\n+ LEO bonded",
             "P4": "multi-transport\n+ gen + autonomy"}
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{r.policy}\n{short[r.policy]}" for r in RESULTS],
                       fontsize=7.5)
    ax.set_ylabel("availability (nines)")
    ax.axhline(3.0, color="#7f8c8d", ls=":", lw=1)
    ax.text(-0.42, 3.03, "99.9%", fontsize=7, color="#7f8c8d")
    ax.axhline(4.0, color="#7f8c8d", ls=":", lw=1)
    ax.text(-0.42, 4.03, "99.99%", fontsize=7, color="#7f8c8d")
    ax.set_title("What each rung buys: transport diversity moves R1/R2; "
                 "only the generator rung moves everything", fontsize=10)
    ax.legend(frameon=False, loc="upper left")
    fig.text(0.99, 0.01, f"{YEARS} simulated years/policy, seed {SEED}",
             fontsize=7, color="#7f8c8d", ha="right")
    fig.tight_layout()
    fig.savefig(FIGDIR / "availability_ladder.png")
    plt.close(fig)


def cost_per_nine():
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    xs = [r.monthly_usd for r in RESULTS]
    ys = [r.classes["R2"].nines for r in RESULTS]
    ax.plot(xs, ys, color="#bdc3c7", lw=1, zorder=1)
    ax.scatter(xs, ys, s=60, color="#27ae60", zorder=2)
    for r, x, y in zip(RESULTS, xs, ys):
        ax.annotate(f"{r.policy}: {r.label}", (x, y),
                    textcoords="offset points", xytext=(8, -3), fontsize=8)
    ax.set_xlabel("policy cost ($/month)")
    ax.set_ylabel("R2 availability (nines)")
    ax.set_title("The price of a nine: dual fiber is the expensive rung, "
                 "the generator is the effective one", fontsize=10)
    ax.set_xlim(min(xs) - 200, max(xs) + 1400)
    fig.tight_layout()
    fig.savefig(FIGDIR / "cost_per_nine.png")
    plt.close(fig)


def downtime_split():
    """Decompose R0/R2 downtime into power / connectivity / timing by
    re-running each policy with the other fault sources disabled."""
    calm = StormConfig()
    rows = []
    CATALOG["perfect"] = custom("fiber", name="perfect", modes=())
    try:
        for p in (LADDER[0], LADDER[3], LADDER[4]):
            full = next(r for r in RESULTS if r.policy == p.name)
            power_only = simulate(
                Policy(name="pw", label="", transports=("perfect",),
                       power=p.power,
                       timing=TimingConfig(gnss_events_per_year=0.0),
                       local_autonomy=p.local_autonomy),
                years=YEARS, seed=SEED, storm=calm)
            timing_only = simulate(
                Policy(name="tm", label="", transports=("perfect",),
                       power=PowerConfig(routine_outages_per_year=0.0,
                                         battery_h=999.0),
                       timing=p.timing, local_autonomy=p.local_autonomy),
                years=YEARS, seed=SEED,
                storm=StormConfig(grid_outage_p=0.0))
            for cname in ("R0", "R2"):
                tot = full.classes[cname].downtime_h_yr
                pw = min(power_only.classes[cname].downtime_h_yr, tot)
                tm = min(timing_only.classes[cname].downtime_h_yr,
                         tot - pw)
                conn = max(tot - pw - tm, 0.0)
                rows.append((f"{p.name} {cname}", pw, conn, tm))
    finally:
        del CATALOG["perfect"]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels = [r[0] for r in rows]
    pws = [r[1] for r in rows]
    conns = [r[2] for r in rows]
    tms = [r[3] for r in rows]
    xs = range(len(rows))
    ax.bar(xs, pws, 0.6, color="#e67e22", label="site power")
    ax.bar(xs, conns, 0.6, bottom=pws, color="#2980b9",
           label="connectivity")
    ax.bar(xs, tms, 0.6, bottom=[a + b for a, b in zip(pws, conns)],
           color="#8e44ad", label="timing (GNSS)")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("downtime (hours/year)")
    ax.set_title("Where the hours live: bonding shrinks the blue; "
                 "only the generator shrinks the orange", fontsize=10)
    ax.legend(frameon=False)
    fig.text(0.99, 0.01,
             "components re-simulated with other fault sources disabled; "
             "overlap makes the split approximate",
             fontsize=7, color="#7f8c8d", ha="right")
    fig.tight_layout()
    fig.savefig(FIGDIR / "downtime_split.png")
    plt.close(fig)


if __name__ == "__main__":
    availability_ladder()
    cost_per_nine()
    downtime_split()
    print(f"figures written to {FIGDIR}/")
