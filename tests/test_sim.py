"""Interval algebra + simulator mechanics."""

import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from resiliency.sim import (HOURS, intersect, merge, subtract,  # noqa: E402
                            total)


class TestIntervals(unittest.TestCase):
    def test_merge_overlaps_and_clips(self):
        self.assertEqual(merge([(5, 10), (8, 12), (20, 25)]),
                         [(5, 12), (20, 25)])
        self.assertEqual(merge([(-5, 3), (8755, 9000)]),
                         [(0, 3), (8755, HOURS)])
        self.assertEqual(merge([(4, 4), (7, 6)]), [])

    def test_intersect(self):
        a = [(0, 10), (20, 30)]
        b = [(5, 25)]
        self.assertEqual(intersect(a, b), [(5, 10), (20, 25)])
        self.assertEqual(intersect(a, []), [])

    def test_subtract(self):
        a = [(0, 10)]
        b = [(2, 4), (6, 8)]
        self.assertEqual(subtract(a, b), [(0, 2), (4, 6), (8, 10)])
        self.assertEqual(subtract(a, [(0, 10)]), [])

    def test_total(self):
        self.assertAlmostEqual(total([(0, 1.5), (10, 12)]), 3.5)


class TestMechanics(unittest.TestCase):
    def test_deterministic_for_seed(self):
        from resiliency.policies import P0
        from resiliency.sim import simulate
        a = simulate(P0, years=50, seed=3)
        b = simulate(P0, years=50, seed=3)
        self.assertEqual(a.classes["R2"].downtime_h_yr,
                         b.classes["R2"].downtime_h_yr)

    def test_no_failures_means_no_downtime(self):
        from resiliency.policies import Policy
        from resiliency.site import PowerConfig, TimingConfig
        from resiliency.sim import StormConfig, simulate
        from resiliency.transports import CATALOG, custom
        # A transport with zero failure rates, perfect grid, no storms.
        CATALOG["perfect"] = custom("fiber", name="perfect", modes=())
        try:
            p = Policy(
                name="PX", label="perfect world",
                transports=("perfect",),
                power=PowerConfig(routine_outages_per_year=0.0),
                timing=TimingConfig(gnss_events_per_year=0.0),
            )
            r = simulate(p, years=20, seed=1,
                         storm=StormConfig(rate_per_year=0.0))
            for c in ("R0", "R1", "R2"):
                self.assertEqual(r.classes[c].downtime_h_yr, 0.0)
                self.assertEqual(r.classes[c].retention, 1.0)
        finally:
            del CATALOG["perfect"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
