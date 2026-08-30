"""Resilience-ladder invariants: the findings the study reports must fall
out of the simulation, not be asserted by it."""

import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from resiliency.classes import R0  # noqa: E402
from resiliency.policies import LADDER, P0, P3, P4  # noqa: E402
from resiliency.sim import ladder, simulate  # noqa: E402
from resiliency.transports import CATALOG  # noqa: E402

YEARS = 400
RESULTS = ladder(LADDER, years=YEARS, seed=11)
BY_NAME = {r.policy: r for r in RESULTS}


class TestEligibility(unittest.TestCase):
    def test_r0_never_rides_satellite_or_cellular(self):
        for t in CATALOG.values():
            if t.kind in ("leo", "cellular"):
                self.assertNotIn("R0", t.carries, t.name)

    def test_fronthaul_grade_transports_exist(self):
        grades = [t for t in CATALOG.values() if "R0" in t.carries]
        self.assertEqual(sorted(t.kind for t in grades),
                         ["fiber", "microwave"])


class TestLadderMonotonicity(unittest.TestCase):
    def test_r2_availability_never_degrades_up_the_ladder_ends(self):
        # The ladder's endpoints must order strictly; middle rungs trade
        # differently per class but P4 dominates P0 everywhere.
        for c in ("R0", "R1", "R2"):
            self.assertGreater(BY_NAME["P4"].classes[c].availability,
                               BY_NAME["P0"].classes[c].availability, c)

    def test_cost_increases_with_the_ladder_ends(self):
        self.assertGreater(BY_NAME["P4"].monthly_usd,
                           BY_NAME["P0"].monthly_usd)


class TestFindings(unittest.TestCase):
    def test_bonding_buys_r0_nothing(self):
        # P3 adds 5G + LEO: R0 cannot ride either, so R0 availability
        # stays within noise of P0's.
        d = abs(BY_NAME["P3"].classes["R0"].downtime_h_yr
                - BY_NAME["P0"].classes["R0"].downtime_h_yr)
        self.assertLess(d, 3.0)

    def test_bonding_does_buy_r1_r2(self):
        self.assertGreater(BY_NAME["P3"].classes["R2"].availability,
                           BY_NAME["P0"].classes["R2"].availability)

    def test_generator_is_the_binding_investment(self):
        # The generator rung (P4) buys more R2 nines than all transport
        # diversity combined (P0->P3).
        transport_gain = (BY_NAME["P3"].classes["R2"].nines
                          - BY_NAME["P0"].classes["R2"].nines)
        power_gain = (BY_NAME["P4"].classes["R2"].nines
                      - BY_NAME["P3"].classes["R2"].nines)
        self.assertGreater(power_gain, transport_gain)

    def test_power_dominates_p3_downtime(self):
        # With three bonded transports but only 4 h of battery, most
        # remaining R2 downtime is the site going dark, not a partition:
        # a pure-power policy variant with perfect transports shows it.
        from resiliency.policies import Policy
        from resiliency.site import PowerConfig, TimingConfig
        from resiliency.transports import custom
        CATALOG["perfect"] = custom("fiber", name="perfect", modes=())
        try:
            power_only = Policy(
                name="PP", label="perfect transports, P3 power",
                transports=("perfect",), power=PowerConfig(battery_h=4.0),
                timing=TimingConfig())
            r = simulate(power_only, years=YEARS, seed=11)
            p3 = BY_NAME["P3"].classes["R2"].downtime_h_yr
            self.assertGreater(r.classes["R2"].downtime_h_yr, 0.5 * p3)
        finally:
            del CATALOG["perfect"]

    def test_rubidium_removes_timing_downtime(self):
        # P4 carries rubidium (36 h holdover) against 8 h mean GNSS
        # events: R0 timing downtime should be near zero; with OCXO the
        # same site shows measurable timing loss.
        from dataclasses import replace
        p4_ocxo = replace(P4, timing=replace(P4.timing, holdover="ocxo"))
        with_ocxo = simulate(p4_ocxo, years=YEARS, seed=11)
        with_rb = BY_NAME["P4"]
        self.assertGreater(with_ocxo.classes["R0"].downtime_h_yr,
                           with_rb.classes["R0"].downtime_h_yr)

    def test_autonomy_keeps_r2_retention_above_availability_floor(self):
        # Wherever partitions do occur under P4, retention >= availability
        # (degraded serving counts partially).
        r2 = BY_NAME["P4"].classes["R2"]
        self.assertGreaterEqual(r2.retention, r2.availability - 1e-9)


class TestCli(unittest.TestCase):
    def _run(self, *argv):
        import contextlib
        import io
        from resiliency.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_ladder_runs(self):
        code, out = self._run("ladder", "--years", "20")
        self.assertEqual(code, 0)
        self.assertIn("P4", out)

    def test_policy_runs(self):
        code, out = self._run("policy", "-p", "P2", "--years", "20")
        self.assertEqual(code, 0)
        self.assertIn("R0", out)

    def test_transports_runs(self):
        code, out = self._run("transports")
        self.assertEqual(code, 0)
        self.assertIn("leo", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
