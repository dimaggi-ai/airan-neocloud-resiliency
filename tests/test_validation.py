"""The validation registry: every point reproduces, the kinds stay honest,
and — the part that matters — a deliberately BROKEN model is rejected.

A registry test suite that only asserts the registry passes is a tautology
detector with the detector switched off. Six of the tests below break one
mechanism in the simulator (delete the power chain, delete transport
redundancy, let a satellite carry fronthaul, switch off the storms, move
the grid inputs, hide the references) and require the registry to go RED
on the specific point that claims to be about that mechanism.

The mutations run at a reduced horizon so the suite stays quick, and
`test_the_reduced_horizon_is_green_unmutated` is the control for the
control: it proves a mutation's failure is the mutation, not the shorter
run.
"""

import dataclasses
import sys
import unittest
from pathlib import Path
from unittest import mock

# Importable whether unittest is run from the repo root or from tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validation                                             # noqa: E402
from resiliency import sim, transports                        # noqa: E402

_POINTS = validation.points()

# Mutation configuration: green unmutated (see the control test), and fast
# enough that six mutations cost a few seconds rather than a minute.
FAST = {"years": 600, "grid_years": 1000}


def _failing(**kw) -> set[str]:
    pts, _ok = validation.validate(**FAST, **kw)
    return {p.name for p in pts if not p.ok}


class TestValidationRegistry(unittest.TestCase):

    def test_every_point_reproduces(self):
        for p in _POINTS:
            with self.subTest(point=p.name):
                self.assertTrue(
                    p.ok,
                    f"{p.name}: expected {p.expected} +/- {p.tolerance} "
                    f"{p.ref}, model gives {p.actual}")

    def test_all_three_kinds_present(self):
        self.assertEqual({p.kind for p in _POINTS},
                         {"calibrated", "emergent", "sanity"})

    def test_only_calibrated_points_cite_sources(self):
        """An emergent point is a simulation output; a reference beside one
        would dress a model result as a sourced result. The sources behind
        its inputs belong in the note, where they cannot be mistaken for
        evidence of the finding itself."""
        for p in _POINTS:
            with self.subTest(point=p.name):
                if p.kind == "calibrated":
                    self.assertTrue(p.ref.startswith("["), p.name)
                else:
                    self.assertEqual(p.ref, "-", p.name)

    def test_no_tolerance_is_wide_enough_to_be_meaningless(self):
        """A band wider than 20% of the value it brackets is a range, not
        a pin, and would pass whatever the model did."""
        for p in _POINTS:
            if p.expected:
                rel = p.tolerance / abs(p.expected)
                with self.subTest(point=p.name):
                    self.assertLessEqual(
                        rel, 0.20,
                        f"{p.name}: +/-{p.tolerance} on {p.expected} is "
                        f"{rel:.0%} — too wide to fail")

    def test_findings_are_checked_on_more_than_one_seed(self):
        # The whole point of this registry: a Monte Carlo finding that
        # holds at one seed is not a finding.
        self.assertGreaterEqual(len(validation.SEEDS), 8)
        self.assertEqual(len(set(validation.SEEDS)), len(validation.SEEDS))
        self.assertNotIn(7, validation.SEEDS,
                         "seeds must be independent of the repo default")

    def test_horizon_matches_the_studys_own_reseeding_standard(self):
        # docs/study.md reports its seed spread at 2,000 years. Validating
        # at a shorter horizon would let noise decide the findings.
        self.assertGreaterEqual(validation.YEARS, 2000)

    def test_registry_has_not_silently_shrunk(self):
        self.assertEqual(len(_POINTS), 13)
        self.assertEqual(len({p.name for p in _POINTS}), len(_POINTS))

    def test_declined_anchors_are_disclosed(self):
        self.assertGreaterEqual(len(validation.DECLINED), 5)
        for what, why in validation.DECLINED:
            self.assertTrue(what and why)

    def test_validate_reports_all_ok(self):
        pts, ok = validation.validate()
        self.assertTrue(ok)
        self.assertEqual(len(pts), len(_POINTS))


class TestBrokenModelFailsTheRegistry(unittest.TestCase):
    """Each test deletes one mechanism and names the point that must notice."""

    def test_the_reduced_horizon_is_green_unmutated(self):
        self.assertEqual(_failing(), set(),
                         "the mutation configuration must pass on an "
                         "unmutated model, or a red point below proves "
                         "nothing about the mutation")

    def test_a_site_that_never_goes_dark_hides_the_generators_value(self):
        with mock.patch.object(sim, "_site_dark", lambda rng, grid, p: []):
            self.assertIn("generator-outranks-every-transport-rung",
                          _failing())

    def test_deleting_transport_redundancy_is_noticed(self):
        """Strip every transport rung back to the single fiber it was meant
        to improve on. P1-P3 then ARE P0, and the point that says each one
        beats P0 must stop holding."""
        stripped = tuple(
            dataclasses.replace(p, transports=("fiber",), dual_fiber=False)
            if p.name in validation.TRANSPORT_RUNGS else p
            for p in validation.LADDER)
        with mock.patch.object(validation, "LADDER", stripped):
            self.assertIn("every-transport-rung-beats-single-fiber",
                          _failing())

    def test_letting_leo_and_5g_carry_fronthaul_breaks_the_r0_finding(self):
        """The R0 finding is a consequence of the eligibility rules. If a
        satellite were allowed to carry fronthaul, bonding WOULD move R0 —
        and the point must say so instead of holding regardless."""
        eligible_everywhere = {
            n: dataclasses.replace(transports.CATALOG[n],
                                   carries=("R0", "R1", "R2"))
            for n in ("leo", "5g-fwa")
        }
        with mock.patch.dict(transports.CATALOG, eligible_everywhere):
            self.assertIn("bonding-leaves-r0-inside-its-own-noise",
                          _failing())

    def test_switching_off_the_storms_is_noticed(self):
        """With no storms the grid's full run IS its routine run, so the
        excess is zero — and a point that pins the storm component as a
        model input has to notice the input going away."""
        calm = dataclasses.replace(validation.STORM, rate_per_year=0.0)
        with mock.patch.object(validation, "STORM", calm):
            self.assertIn("storm-excess-is-a-model-input", _failing())

    def test_moving_the_grid_inputs_breaks_the_calibrated_grid_point(self):
        """The EIA point is the one grid number a public source settles.
        Halve the routine outage duration and it must go red — otherwise
        the calibration is decorative."""
        halved = dataclasses.replace(
            validation.GRID_POWER,
            routine_outage_h=validation.GRID_POWER.routine_outage_h / 2)
        with mock.patch.object(validation, "GRID_POWER", halved):
            self.assertIn("routine-grid-hours-match-eia-routine", _failing())

    def test_doubling_the_fiber_failure_rates_breaks_the_2_7_nines_point(self):
        """The +/-0.01 band on P0 is ~2 standard errors: tight enough to
        notice a model that fails twice as often."""
        fiber = transports.CATALOG["fiber"]
        worse = dataclasses.replace(fiber, modes=tuple(
            dataclasses.replace(m, rate_per_year=m.rate_per_year * 2)
            for m in fiber.modes))
        with mock.patch.dict(transports.CATALOG, {"fiber": worse}):
            self.assertIn("single-fiber-site-is-2.7-nines", _failing())

    def test_hiding_the_references_breaks_the_ref_point(self):
        with mock.patch.object(validation, "REFERENCES",
                               Path("/nonexistent/REFERENCES.md")):
            self.assertIn("every-ref-resolves", _failing())


if __name__ == "__main__":
    unittest.main()
