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

    def test_merge_clips_before_filtering(self):
        # An event starting past year-end must vanish entirely -- not
        # survive as a zero-length interval at the year boundary.
        self.assertEqual(merge([(9000.0, 9010.0)]), [])
        self.assertEqual(merge([(-10.0, 9000.0)]), [(0.0, HOURS)])

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
    def test_direct_quote_shares_dual_fiber_refusal_with_simulation(self):
        from dataclasses import replace
        from unittest.mock import patch
        from resiliency.policies import P1
        from resiliency.sim import _policy_transports, ladder, simulate
        from resiliency.transports import CATALOG, custom
        with patch.dict(CATALOG, {'renamed-fiber': custom('fiber', name='renamed-fiber')}):
            for names in (('renamed-fiber',), ('microwave',), ()):
                p = replace(P1, transports=names)
                messages = []
                for entry in (p.monthly_usd, lambda: _policy_transports(p),
                              lambda: simulate(p, years=1, seed=7),
                              lambda: ladder([p], years=1, seed=7)):
                    with self.subTest(transports=names, entry=entry):
                        with self.assertRaisesRegex(ValueError, "dual_fiber=True requires.*'fiber'") as error:
                            entry()
                        messages.append(str(error.exception))
                self.assertEqual(len(set(messages)), 1)

    def test_quotes_preserve_valid_prices_and_recover_after_refusal(self):
        from dataclasses import replace
        from unittest.mock import patch
        from resiliency.policies import LADDER, P0, P1
        from resiliency.transports import CATALOG, custom
        self.assertEqual({p.name: p.monthly_usd() for p in LADDER},
                         {'P0': 1660., 'P1': 3160., 'P2': 2460.,
                          'P3': 2060., 'P4': 3780.})
        with patch.dict(CATALOG, {'renamed-fiber': custom('fiber', name='renamed-fiber')}):
            invalid = replace(P1, transports=('renamed-fiber',))
            with self.assertRaises(ValueError):
                invalid.monthly_usd()
            self.assertEqual(replace(invalid, dual_fiber=False).monthly_usd(), 1660.)
            self.assertEqual(replace(invalid, transports=('fiber',)).monthly_usd(), 3160.)
            self.assertEqual(replace(P0, transports=('renamed-fiber',)).monthly_usd(), 1660.)
        for names in (('fiber', 'microwave'), ('microwave', 'fiber')):
            self.assertEqual(replace(P1, transports=names).monthly_usd(), 3960.)

    def test_dual_fiber_accepts_canonical_fiber_in_either_transport_order(self):
        from dataclasses import replace
        from resiliency.policies import P1
        from resiliency.sim import ladder, simulate
        for names in (('fiber', 'microwave'), ('microwave', 'fiber')):
            with self.subTest(transports=names):
                policy = replace(P1, transports=names)
                result = simulate(policy, years=2, seed=7)
                self.assertEqual(set(result.classes), {'R0', 'R1', 'R2'})
                self.assertEqual(ladder([policy], years=2, seed=7), [result])

    def test_dual_fiber_requires_canonical_primary(self):
        from dataclasses import replace
        from unittest.mock import patch
        from resiliency.policies import P1
        from resiliency.sim import simulate
        from resiliency.transports import CATALOG, custom
        with patch.dict(CATALOG, {'renamed-fiber': custom('fiber', name='renamed-fiber')}):
            for names in (('renamed-fiber',), ('microwave',), ()):
                with self.subTest(transports=names):
                    with self.assertRaisesRegex(ValueError, "dual_fiber=True requires.*'fiber'"):
                        simulate(replace(P1, transports=names), years=1, seed=7)

    def test_custom_single_and_canonical_dual_recover_after_refusal(self):
        from dataclasses import replace
        from unittest.mock import patch
        from resiliency.policies import P0, P1
        from resiliency.sim import simulate
        from resiliency.transports import CATALOG, custom
        expected_single = simulate(P0, years=50, seed=7)
        expected_dual = simulate(P1, years=50, seed=7)
        with patch.dict(CATALOG, {'renamed-fiber': custom('fiber', name='renamed-fiber')}):
            unsupported = replace(P1, transports=('renamed-fiber',))
            with self.assertRaises(ValueError):
                simulate(unsupported, years=50, seed=7)
            single = replace(P0, transports=('renamed-fiber',))
            self.assertEqual(simulate(single, years=50, seed=7), expected_single)
            corrected = replace(unsupported, transports=('fiber',))
            self.assertEqual(simulate(corrected, years=50, seed=7), expected_dual)

    def test_dual_fiber_duplicate_instances_still_refuse(self):
        from dataclasses import replace
        from unittest.mock import patch
        from resiliency.policies import P1
        from resiliency.sim import simulate
        from resiliency.transports import CATALOG, custom
        with patch.dict(CATALOG, {'fiber-b': custom('fiber', name='fiber-b')}):
            for names in (('fiber', 'fiber'), ('fiber', 'fiber-b')):
                with self.subTest(transports=names):
                    with self.assertRaisesRegex(ValueError, 'duplicate transport instance'):
                        simulate(replace(P1, transports=names), years=1, seed=7)

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
