"""
Unit tests for Completeness Analyser (W3)
------------------------------------------
Tests are grouped into 6 suites:

  Suite 1 — CompletenessReport dataclass helpers
  Suite 2 — Raw score (Formula 1: covered / 24)
  Suite 3 — Weighted score (Formula 2: weighted_covered / 58)
  Suite 4 — Gap detection (critical_gaps, gap_details)
  Suite 5 — Per-group coverage breakdown
  Suite 6 — Combined-text re-analysis (LLM-extracted content adds coverage)

Run:
    python metagpt/elicitation/analyser/test_completeness_analyser.py
    python -m pytest metagpt/elicitation/analyser/test_completeness_analyser.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import importlib.util
import sys
import unittest
from pathlib import Path


# ------------------------------------------------------------------ #
#  Load modules directly (bypass metagpt.__init__ import chain)       #
# ------------------------------------------------------------------ #

def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_BASE         = Path(__file__).parent
_ELICITATION  = _BASE.parent

schema_mod    = _load(str(_ELICITATION / "schema"  / "ecommerce_schema.py"), "ecommerce_schema")
parser_mod    = _load(str(_ELICITATION / "parser"  / "srs_parser.py"),       "srs_parser")
analyser_mod  = _load(str(_BASE        / "completeness_analyser.py"),         "completeness_analyser")

ECOMMERCE_SCHEMA     = schema_mod.ECOMMERCE_SCHEMA
ParsedSRS            = parser_mod.ParsedSRS
CompletenessReport   = analyser_mod.CompletenessReport
CompletenessAnalyser = analyser_mod.CompletenessAnalyser

_TOTAL_CATS   = schema_mod.total_categories()   # 24
_TOTAL_WEIGHT = schema_mod.total_weight()        # 58
_ALL_CATS     = list(ECOMMERCE_SCHEMA.keys())

# Weight-3 category names
_CRITICAL_CATS = [k for k, v in ECOMMERCE_SCHEMA.items() if v.weight == 3]


# ------------------------------------------------------------------ #
#  SRS fixtures                                                        #
# ------------------------------------------------------------------ #

SRS_RICH = (
    "Build a B2C e-commerce platform where customers can register, "
    "login, browse a product catalog with search and filter, add items "
    "to their cart, and checkout using Stripe or PayPal. "
    "Admins can manage products, view orders, and issue refunds. "
    "The system should handle 5000 concurrent users with <2s response time. "
    "GDPR and PCI-DSS compliance are required. "
    "Inventory must be tracked in real-time across two warehouses."
)

SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."


# ------------------------------------------------------------------ #
#  ParsedSRS fixture builders                                          #
# ------------------------------------------------------------------ #

def _make_empty_parsed() -> ParsedSRS:
    """ParsedSRS with no coverage signals."""
    return ParsedSRS(
        raw_text="",
        schema_hints={k: False for k in _ALL_CATS},
    )


def _make_full_parsed() -> ParsedSRS:
    """ParsedSRS with all 24 categories covered."""
    return ParsedSRS(
        raw_text="",
        schema_hints={k: True for k in _ALL_CATS},
    )


def _make_half_parsed() -> ParsedSRS:
    """ParsedSRS with exactly 12 categories covered (first 12 alphabetically)."""
    half = sorted(_ALL_CATS)[:12]
    return ParsedSRS(
        raw_text="",
        schema_hints={k: (k in half) for k in _ALL_CATS},
    )


def _make_critical_only_parsed() -> ParsedSRS:
    """ParsedSRS where ONLY weight-3 categories are covered."""
    return ParsedSRS(
        raw_text="",
        schema_hints={k: (ECOMMERCE_SCHEMA[k].weight == 3) for k in _ALL_CATS},
    )


def _make_noncritical_only_parsed() -> ParsedSRS:
    """ParsedSRS where ONLY weight-1/2 categories are covered (no critical)."""
    return ParsedSRS(
        raw_text="",
        schema_hints={k: (ECOMMERCE_SCHEMA[k].weight < 3) for k in _ALL_CATS},
    )


# ================================================================== #
#  Suite 1 — CompletenessReport helpers                               #
# ================================================================== #

class TestCompletenessReport(unittest.TestCase):

    def _report(self, covered_count: int, include_critical: bool = True) -> CompletenessReport:
        """Build a minimal report for helper testing."""
        cats = sorted(_ALL_CATS)
        covered = cats[:covered_count]
        missing = cats[covered_count:]
        critical = [k for k in missing if ECOMMERCE_SCHEMA[k].weight == 3]
        weighted = sum(ECOMMERCE_SCHEMA[k].weight for k in covered)
        per_group = {g: 0.0 for g in ("FUNCTIONAL", "NON_FUNCTIONAL", "DOMAIN")}
        return CompletenessReport(
            raw_score=covered_count / _TOTAL_CATS,
            weighted_score=weighted / _TOTAL_WEIGHT,
            covered_categories=covered,
            missing_categories=missing,
            critical_gaps=critical,
            gap_details={k: ECOMMERCE_SCHEMA[k] for k in missing},
            per_group_coverage=per_group,
            coverage_map={k: (k in covered) for k in _ALL_CATS},
        )

    def test_raw_score_is_float(self):
        r = self._report(12)
        self.assertIsInstance(r.raw_score, float)

    def test_weighted_score_is_float(self):
        r = self._report(12)
        self.assertIsInstance(r.weighted_score, float)

    def test_has_critical_gaps_true_when_weight3_missing(self):
        # If any critical cat is in missing, has_critical_gaps must be True
        r = self._report(1)   # only 1 covered → many missing including critical
        if r.critical_gaps:
            self.assertTrue(r.has_critical_gaps())

    def test_has_critical_gaps_false_when_all_critical_covered(self):
        analyser = CompletenessAnalyser()
        r = analyser.analyse(_make_critical_only_parsed())
        self.assertFalse(r.has_critical_gaps())

    def test_coverage_level_bands(self):
        analyser = CompletenessAnalyser()
        self.assertEqual(analyser.analyse(_make_empty_parsed()).coverage_level(), "POOR")
        # Create a 50%-covered report manually
        mid = ParsedSRS(raw_text="", schema_hints={k: (i < 12) for i, k in enumerate(_ALL_CATS)})
        mid_report = analyser.analyse(mid)
        self.assertIn(mid_report.coverage_level(), ("POOR", "PARTIAL", "GOOD"))
        self.assertEqual(analyser.analyse(_make_full_parsed()).coverage_level(), "COMPLETE")

    def test_summary_is_non_empty_string(self):
        r = self._report(10)
        s = r.summary()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 0)

    def test_summary_contains_score(self):
        analyser = CompletenessAnalyser()
        r = analyser.analyse(_make_full_parsed())
        self.assertIn("1.00", r.summary())


# ================================================================== #
#  Suite 2 — Raw Score (Formula 1)                                    #
# ================================================================== #

class TestRawScore(unittest.TestCase):

    def setUp(self):
        self.analyser = CompletenessAnalyser()

    def test_empty_parsed_gives_zero(self):
        r = self.analyser.analyse(_make_empty_parsed())
        self.assertEqual(r.raw_score, 0.0)

    def test_full_parsed_gives_one(self):
        r = self.analyser.analyse(_make_full_parsed())
        self.assertAlmostEqual(r.raw_score, 1.0)

    def test_half_coverage_raw_score(self):
        r = self.analyser.analyse(_make_half_parsed())
        # 12 / 24 = 0.5 (may vary slightly if combined_text picks up more)
        self.assertGreaterEqual(r.raw_score, 0.5)

    def test_raw_score_formula(self):
        # Verify: raw_score == len(covered_categories) / 24
        r = self.analyser.analyse(_make_half_parsed())
        expected = len(r.covered_categories) / _TOTAL_CATS
        self.assertAlmostEqual(r.raw_score, expected)

    def test_covered_length_matches_numerator(self):
        r = self.analyser.analyse(_make_full_parsed())
        self.assertEqual(len(r.covered_categories), _TOTAL_CATS)

    def test_covered_and_missing_partition_all_categories(self):
        r = self.analyser.analyse(_make_half_parsed())
        all_from_report = set(r.covered_categories) | set(r.missing_categories)
        self.assertEqual(all_from_report, set(_ALL_CATS))
        self.assertEqual(len(r.covered_categories) + len(r.missing_categories), _TOTAL_CATS)


# ================================================================== #
#  Suite 3 — Weighted Score (Formula 2)                               #
# ================================================================== #

class TestWeightedScore(unittest.TestCase):

    def setUp(self):
        self.analyser = CompletenessAnalyser()

    def test_empty_gives_zero(self):
        r = self.analyser.analyse(_make_empty_parsed())
        self.assertEqual(r.weighted_score, 0.0)

    def test_full_gives_one(self):
        r = self.analyser.analyse(_make_full_parsed())
        self.assertAlmostEqual(r.weighted_score, 1.0)

    def test_only_critical_weighted_greater_than_raw(self):
        r = self.analyser.analyse(_make_critical_only_parsed())
        # Covering only high-weight cats → weighted > raw
        self.assertGreater(r.weighted_score, r.raw_score)

    def test_only_noncritical_weighted_less_than_raw(self):
        r = self.analyser.analyse(_make_noncritical_only_parsed())
        # Covering only low-weight cats → weighted < raw
        self.assertLess(r.weighted_score, r.raw_score)

    def test_weighted_formula_verified(self):
        # Verify with a known subset: all critical cats covered only
        r = self.analyser.analyse(_make_critical_only_parsed())
        covered_weight = sum(
            ECOMMERCE_SCHEMA[k].weight for k in r.covered_categories
        )
        self.assertAlmostEqual(r.weighted_score, covered_weight / _TOTAL_WEIGHT)


# ================================================================== #
#  Suite 4 — Gap Detection                                            #
# ================================================================== #

class TestGapDetection(unittest.TestCase):

    def setUp(self):
        self.analyser = CompletenessAnalyser()

    def test_critical_gaps_only_weight3(self):
        r = self.analyser.analyse(_make_empty_parsed())
        for cat in r.critical_gaps:
            self.assertEqual(ECOMMERCE_SCHEMA[cat].weight, 3)

    def test_no_critical_gaps_when_all_critical_covered(self):
        r = self.analyser.analyse(_make_critical_only_parsed())
        self.assertEqual(r.critical_gaps, [])

    def test_gap_details_keys_match_missing(self):
        r = self.analyser.analyse(_make_half_parsed())
        self.assertEqual(set(r.gap_details.keys()), set(r.missing_categories))

    def test_gap_details_values_have_question(self):
        r = self.analyser.analyse(_make_empty_parsed())
        for cat_name, cat_obj in r.gap_details.items():
            self.assertTrue(hasattr(cat_obj, "question"))
            self.assertIsInstance(cat_obj.question, str)
            self.assertGreater(len(cat_obj.question), 0)

    def test_gap_details_values_have_suggestions(self):
        r = self.analyser.analyse(_make_empty_parsed())
        for cat_obj in r.gap_details.values():
            self.assertTrue(hasattr(cat_obj, "suggestions"))
            self.assertIsInstance(cat_obj.suggestions, list)

    def test_has_critical_gaps_false_when_list_empty(self):
        r = self.analyser.analyse(_make_critical_only_parsed())
        self.assertFalse(r.has_critical_gaps())

    def test_has_critical_gaps_true_when_list_nonempty(self):
        r = self.analyser.analyse(_make_empty_parsed())
        self.assertTrue(r.has_critical_gaps())

    def test_vague_srs_has_payment_in_critical_gaps(self):
        r = self.analyser.analyse_text(SRS_VAGUE)
        self.assertIn("payment", r.critical_gaps)

    def test_rich_srs_has_fewer_critical_gaps_than_vague(self):
        rich_r  = self.analyser.analyse_text(SRS_RICH)
        vague_r = self.analyser.analyse_text(SRS_VAGUE)
        self.assertLess(len(rich_r.critical_gaps), len(vague_r.critical_gaps))


# ================================================================== #
#  Suite 5 — Per-Group Coverage                                       #
# ================================================================== #

class TestPerGroupCoverage(unittest.TestCase):

    def setUp(self):
        self.analyser = CompletenessAnalyser()

    def test_three_groups_present(self):
        r = self.analyser.analyse(_make_empty_parsed())
        self.assertEqual(set(r.per_group_coverage.keys()),
                         {"FUNCTIONAL", "NON_FUNCTIONAL", "DOMAIN"})

    def test_all_values_between_0_and_1(self):
        r = self.analyser.analyse(_make_half_parsed())
        for v in r.per_group_coverage.values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_empty_all_groups_zero(self):
        r = self.analyser.analyse(_make_empty_parsed())
        for v in r.per_group_coverage.values():
            self.assertEqual(v, 0.0)

    def test_full_all_groups_one(self):
        r = self.analyser.analyse(_make_full_parsed())
        for v in r.per_group_coverage.values():
            self.assertAlmostEqual(v, 1.0)

    def test_functional_group_denominator(self):
        # FUNCTIONAL group has 12 categories
        functional_cats = [k for k, v in ECOMMERCE_SCHEMA.items() if v.group == "FUNCTIONAL"]
        self.assertEqual(len(functional_cats), 12)

    def test_nonfunctional_group_denominator(self):
        nf_cats = [k for k, v in ECOMMERCE_SCHEMA.items() if v.group == "NON_FUNCTIONAL"]
        self.assertEqual(len(nf_cats), 4)


# ================================================================== #
#  Suite 6 — Combined-Text Re-analysis                                #
# ================================================================== #

class TestCombinedTextAnalysis(unittest.TestCase):

    def setUp(self):
        self.analyser = CompletenessAnalyser()

    def test_llm_extracted_intent_adds_payment_coverage(self):
        # schema_hints has payment=False (raw_text has no payment keywords)
        # but functional_intents contains "user pays with stripe"
        # → combined_text() contains "stripe" → payment should be covered
        parsed = ParsedSRS(
            raw_text="Build an online store.",
            schema_hints={k: False for k in _ALL_CATS},
            functional_intents=["user pays with stripe"],
        )
        r = self.analyser.analyse(parsed)
        self.assertTrue(r.coverage_map.get("payment", False))

    def test_llm_extracted_actor_adds_auth_signal(self):
        # raw_text has no auth keywords, but actors contains "Customer"
        # combined_text will contain "customer" → may still not hit auth keywords
        # (auth keywords are: login, register, oauth, etc. — "customer" is not one)
        # So this test verifies that schema_hints signal alone works if hint=True
        parsed = ParsedSRS(
            raw_text="Build a store.",
            schema_hints={**{k: False for k in _ALL_CATS}, "authentication": True},
        )
        r = self.analyser.analyse(parsed)
        self.assertTrue(r.coverage_map.get("authentication", False))

    def test_coverage_map_has_24_keys(self):
        r = self.analyser.analyse(_make_empty_parsed())
        self.assertEqual(len(r.coverage_map), _TOTAL_CATS)
        self.assertEqual(set(r.coverage_map.keys()), set(_ALL_CATS))

    def test_analyse_text_returns_report(self):
        r = self.analyser.analyse_text(SRS_VAGUE)
        self.assertIsInstance(r, CompletenessReport)

    def test_vague_srs_is_poor_or_partial(self):
        r = self.analyser.analyse_text(SRS_VAGUE)
        self.assertIn(r.coverage_level(), ("POOR", "PARTIAL"))

    def test_rich_srs_scores_higher_than_vague(self):
        # Keyword-only (no LLM) typically hits PARTIAL on SRS_RICH (~10/24 cats).
        # We only assert it beats the vague SRS, not that it reaches GOOD.
        rich_r  = self.analyser.analyse_text(SRS_RICH)
        vague_r = self.analyser.analyse_text(SRS_VAGUE)
        self.assertGreater(rich_r.raw_score, vague_r.raw_score)


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCompletenessReport))
    suite.addTests(loader.loadTestsFromTestCase(TestRawScore))
    suite.addTests(loader.loadTestsFromTestCase(TestWeightedScore))
    suite.addTests(loader.loadTestsFromTestCase(TestGapDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestPerGroupCoverage))
    suite.addTests(loader.loadTestsFromTestCase(TestCombinedTextAnalysis))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
