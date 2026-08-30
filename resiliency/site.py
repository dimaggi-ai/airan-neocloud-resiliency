"""Site survivability envelope: power chain and timing chain.

Power: grid -> battery bridge -> (optional) generator. The FCC's disaster
data is unambiguous: more than half of cell-site outages in major events
are power failures, not transport failures -- so the power chain is
modeled with the same care as the links (see REFERENCES.md).

Timing: R0 needs GNSS-disciplined phase within +/-1.5 us. When GNSS is
jammed, spoofed, or fails, a holdover oscillator carries the site: an
OCXO holds the budget for hours, a rubidium clock for more than a day.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PowerConfig:
    battery_h: float = 4.0          # bridge before the site goes dark
    has_generator: bool = False
    generator_fuel_h: float = 96.0  # runtime per fuel tank
    # Planning assumption: standby gensets fail to start a few percent
    # of the time (industry rule of thumb, no single public per-event
    # stat for telecom sites).
    generator_start_fail_p: float = 0.06
    # Grid inputs (EIA SAIDI split): routine interruptions plus
    # major-event tails that arrive with storms.
    routine_outages_per_year: float = 1.5
    routine_outage_h: float = 1.3


@dataclass(frozen=True)
class TimingConfig:
    holdover: str = "ocxo"          # 'ocxo' | 'rubidium'
    # Planning assumption: rare long GNSS denial events (jamming,
    # spoofing, receiver faults). Sourced facts are the +/-1.5 us phase
    # budget and the holdover classes below; the event rate is not.
    gnss_events_per_year: float = 0.5
    gnss_event_h: float = 8.0

    @property
    def holdover_h(self) -> float:
        """Hours the clock holds the +/-1.5 us phase budget without GNSS."""
        return {"ocxo": 6.0, "rubidium": 36.0}[self.holdover]


GENERATOR_MONTHLY_USD = 400.0       # amortized genset + fuel service
RUBIDIUM_MONTHLY_USD = 60.0         # amortized module premium
BATTERY_MONTHLY_USD_PER_H = 40.0    # amortized plant per bridge-hour


def power_monthly_usd(p: PowerConfig) -> float:
    cost = p.battery_h * BATTERY_MONTHLY_USD_PER_H
    if p.has_generator:
        cost += GENERATOR_MONTHLY_USD
    return cost


def timing_monthly_usd(t: TimingConfig) -> float:
    return RUBIDIUM_MONTHLY_USD if t.holdover == "rubidium" else 0.0


def custom_power(base: PowerConfig = PowerConfig(), **kw) -> PowerConfig:
    return replace(base, **kw)
