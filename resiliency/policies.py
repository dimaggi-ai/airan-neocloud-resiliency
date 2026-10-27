"""The resilience policy ladder P0 -> P4.

Each rung adds one investment. The simulator prices what each rung
actually buys, per resilience class -- availability, restore time,
usable-capacity retention, and dollars.
"""

from dataclasses import dataclass, field

from .site import (PowerConfig, TimingConfig, power_monthly_usd,
                   timing_monthly_usd)
from .transports import CATALOG, transport


@dataclass(frozen=True)
class Policy:
    name: str
    label: str
    transports: tuple[str, ...]       # names into transports.CATALOG
    power: PowerConfig
    timing: TimingConfig
    dual_fiber: bool = False
    # Fraction of physical fiber CUTS (not upstream/equipment events)
    # that hit both 'diverse' paths anyway (shared duct, same bridge
    # crossing, same backhoe): the SRLG tax. Planning assumption --
    # audit your own duct maps.
    shared_cut_fraction: float = 0.15
    # Degraded local serving during WAN partition (cached models, local
    # RAG index, store-and-forward telemetry).
    local_autonomy: bool = False

    def monthly_usd(self) -> float:
        cost = sum(transport(n).monthly_usd for n in self.transports)
        if self.dual_fiber:
            cost += transport("fiber").monthly_usd
        cost += power_monthly_usd(self.power)
        cost += timing_monthly_usd(self.timing)
        if self.local_autonomy:
            cost += 300.0   # local model/index storage + failover control
        return cost


P0 = Policy(
    name="P0", label="single fiber",
    transports=("fiber",),
    # Battery is held at 4 h across P0-P3 so each rung isolates ONE
    # investment; only P4 changes the power chain.
    power=PowerConfig(battery_h=4.0),
    timing=TimingConfig(holdover="ocxo"),
)

P1 = Policy(
    name="P1", label="dual diverse fiber",
    transports=("fiber",),
    dual_fiber=True,
    power=PowerConfig(battery_h=4.0),
    timing=TimingConfig(holdover="ocxo"),
)

P2 = Policy(
    name="P2", label="fiber + e-band microwave",
    transports=("fiber", "microwave"),
    power=PowerConfig(battery_h=4.0),
    timing=TimingConfig(holdover="ocxo"),
)

P3 = Policy(
    name="P3", label="fiber + 5G + LEO bonded",
    transports=("fiber", "5g-fwa", "leo"),
    power=PowerConfig(battery_h=4.0),
    timing=TimingConfig(holdover="ocxo"),
)

P4 = Policy(
    name="P4", label="multi-transport + generator + autonomy",
    transports=("fiber", "microwave", "5g-fwa", "leo"),
    power=PowerConfig(battery_h=8.0, has_generator=True),
    timing=TimingConfig(holdover="rubidium"),
    local_autonomy=True,
)

LADDER = (P0, P1, P2, P3, P4)


def policy(name: str) -> Policy:
    for p in LADDER:
        if p.name == name:
            return p
    raise KeyError(f"unknown policy {name!r}; know {[p.name for p in LADDER]}")
