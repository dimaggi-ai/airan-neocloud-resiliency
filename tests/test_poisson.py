"""Poisson distribution, stream compatibility and bounded refusal regressions."""
import math
import random
import statistics
import unittest
from unittest.mock import patch
from resiliency import sim


def old_knuth(rng, rate):
    if rate <= 0:
        return 0
    threshold, k, product = pow(2.718281828459045, -rate), 0, 1.
    while True:
        product *= rng.random()
        if product <= threshold:
            return k
        k += 1


class CountingRng:
    def __init__(self, value):
        self.value, self.calls = value, 0
    def random(self):
        self.calls += 1
        return self.value


class PoissonTests(unittest.TestCase):
    def test_small_rate_draw_and_next_state_parity(self):
        for rate in (0, .001, .08, .8, 1, 40, 200, 299.9, 300):
            for seed in range(20):
                a, b = random.Random(seed), random.Random(seed)
                self.assertEqual(sim._poisson(a, rate), old_knuth(b, rate))
                self.assertEqual(a.getstate(), b.getstate())
        rng = CountingRng(1.)
        self.assertEqual(sim._poisson(rng, 0), 0)
        self.assertEqual(rng.calls, 0)

    def test_independent_additivity_oracle(self):
        # Construct the independent chunk sum outside the implementation; the
        # leftover is a separate Poisson variate, not a scaled count.
        for rate in (300.25, 600, 750, 15000, 100000):
            for seed in range(4):
                a, b = random.Random(seed), random.Random(seed)
                whole, remainder = divmod(rate, 300)
                expected = sum(old_knuth(b, 300) for _ in range(int(whole)))
                if remainder:
                    expected += old_knuth(b, remainder)
                self.assertEqual(sim._poisson(a, rate), expected)
                self.assertEqual(a.getstate(), b.getstate())

    def test_large_rate_mean_and_variance(self):
        n = 400
        for rate in (301, 750, 15000):
            rng = random.Random(215)
            samples = [sim._poisson(rng, rate) for _ in range(n)]
            # Poisson mean variance=lambda/n. Sample variance asymptotic
            # variance=lambda/n + 2*lambda**2/(n-1). Wide 8-sigma bands are
            # regression diagnostics, not proof of a distribution or qualification.
            self.assertLess(abs(statistics.mean(samples)-rate), 8*math.sqrt(rate/n))
            self.assertLess(abs(statistics.variance(samples)-rate), 8*math.sqrt(rate/n+2*rate**2/(n-1)))
            self.assertTrue(all(type(x) is int and x >= 0 for x in samples))

    def test_invalid_rate_refusal_without_rng_use_and_recovery(self):
        for value in (math.nan, math.inf, -math.inf, -1, True, False, '1', None, 1j, 10**400, 100001):
            rng = CountingRng(0.)
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, 'lam'):
                    sim._poisson(rng, value)
                self.assertEqual(rng.calls, 0)
        self.assertEqual(sim._poisson(random.Random(4), 200), old_knuth(random.Random(4), 200))

    def test_draw_budget_exhaustion_and_exact_boundary(self):
        with patch.object(sim, '_MAX_POISSON_DRAWS', 3):
            rng = CountingRng(1.)
            with self.assertRaisesRegex(ValueError,'draw budget'): sim._poisson(rng, 1)
            self.assertEqual(rng.calls, 3)
            rng = CountingRng(0.)
            self.assertEqual(sim._poisson(rng, 900), 0)
            self.assertEqual(rng.calls, 3)
            with self.assertRaisesRegex(ValueError,'draw budget'): sim._poisson(CountingRng(0.), 901)

    def test_event_budget_no_partial_sample_or_arrivals(self):
        with patch.object(sim, '_MAX_POISSON_EVENTS', 2):
            rng = CountingRng(.9)
            with self.assertRaisesRegex(ValueError,'event budget'): sim._poisson_starts(rng, 300)
            self.assertEqual(rng.calls, 3)
        with patch.object(sim, '_MAX_POISSON_EVENTS', 0):
            self.assertEqual(sim._poisson(CountingRng(0.), 300), 0)

if __name__ == '__main__': unittest.main()
