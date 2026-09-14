"""
Unit tests for W8 — Results Analyser
--------------------------------------
Suites:
  Suite 1 — AggregateStats dataclass        (8 tests)
  Suite 2 — ResultsAnalyser.analyse()       (12 tests)
  Suite 3 — Formatting + Comparison         (10 tests)

Total: 30 tests.  No LLM calls; uses fixture BatchResult objects.

Run:
    python metagpt/elicitation/evaluation/test_w8.py
    python -m pytest metagpt/elicitation/evaluation/test_w8.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import importlib.util
import sys
import unittest
from pathlib import Path

# ------------------------------------------------------------------ #
#  Module loading                                                      #
# ------------------------------------------------------------------ #

def _load(path: str, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_BASE        = Path(__file__).parent
_ELICITATION = _BASE.parent

schema_mod    = _load(str(_ELICITATION / "schema"      / "ecommerce_schema.py"),         "ecommerce_schema")
parser_mod    = _load(str(_ELICITATION / "parser"      / "srs_parser.py"),               "srs_parser")
analyser_mod  = _load(str(_ELICITATION / "analyser"    / "completeness_analyser.py"),    "completeness_analyser")
prio_mod      = _load(str(_ELICITATION / "dialogue"    / "question_prioritiser.py"),     "question_prioritiser")
dialogue_mod  = _load(str(_ELICITATION / "dialogue"    / "elicitation_dialogue.py"),     "elicitation_dialogue")
synth_mod     = _load(str(_ELICITATION / "synthesiser" / "srs_synthesiser.py"),          "srs_synthesiser")
logger_mod    = _load(str(_BASE        / "metrics_logger.py"),                           "metrics_logger")
runner_mod    = _load(str(_BASE        / "elicitation_runner.py"),                       "elicitation_runner")
dataset_mod   = _load(str(_BASE        / "pure_dataset.py"),                             "pure_dataset")
batch_mod     = _load(str(_BASE        / "batch_runner.py"),                             "batch_runner")
analyser8_mod = _load(str(_BASE        / "results_analyser.py"),                        "results_analyser")

BatchResult     = batch_mod.BatchResult
ResultsAnalyser = analyser8_mod.ResultsAnalyser
AggregateStats  = analyser8_mod.AggregateStats


# ------------------------------------------------------------------ #
#  Fixtures                                                            #
# ------------------------------------------------------------------ #

def _br(doc_id="S01", pre=0.10, post=0.30, mode="silent",
        pre_lvl="POOR", post_lvl="PARTIAL",
        gap_pre=9, gap_after=5, error="") -> BatchResult:
    """Construct a minimal BatchResult for testing."""
    return BatchResult(
        batch_id="b1",
        doc_id=doc_id,
        domain="ecommerce",
        word_count=50,
        source="builtin",
        run_id=f"run-{doc_id}",
        timestamp="2026-06-01T10:00:00",
        mode=mode,
        parse_method="fallback",
        synthesis_method="template",
        pre_score=pre,
        pre_weighted_score=round(pre * 0.9, 4),
        post_score=post,
        post_weighted_score=round(post * 0.9, 4),
        score_improvement=round(post - pre, 4),
        pre_coverage_level=pre_lvl,
        post_coverage_level=post_lvl,
        critical_gaps_before=gap_pre,
        critical_gaps_after=gap_after,
        questions_asked=0,
        answers_collected=0,
        duration_seconds=1.0,
        error=error,
    )


# A set of 5 fixture results: 4 successful, 1 with error
RESULTS_MIX = [
    _br("S01", pre=0.08, post=0.08, pre_lvl="POOR",    post_lvl="POOR"),
    _br("S02", pre=0.25, post=0.33, pre_lvl="PARTIAL", post_lvl="PARTIAL"),
    _br("S03", pre=0.42, post=0.54, pre_lvl="PARTIAL", post_lvl="PARTIAL"),
    _br("S04", pre=0.67, post=0.75, pre_lvl="GOOD",    post_lvl="GOOD"),
    _br("S05", error="RuntimeError: test"),  # failed doc
]

# All-improved set (post > pre for every doc)
RESULTS_ALL_IMPROVED = [
    _br("A01", pre=0.10, post=0.40),
    _br("A02", pre=0.20, post=0.50),
    _br("A03", pre=0.30, post=0.60),
]

# Flat set (post == pre, silent mode baseline)
RESULTS_SILENT = [
    _br("B01", pre=0.10, post=0.10, mode="silent"),
    _br("B02", pre=0.25, post=0.25, mode="silent"),
    _br("B03", pre=0.50, post=0.50, mode="silent"),
]

# LLM mode (post > pre)
RESULTS_LLM = [
    _br("C01", pre=0.10, post=0.40, mode="llm"),
    _br("C02", pre=0.25, post=0.55, mode="llm"),
    _br("C03", pre=0.50, post=0.70, mode="llm"),
]


# ================================================================== #
#  Suite 1 — AggregateStats dataclass                                 #
# ================================================================== #

class TestAggregateStats(unittest.TestCase):

    def setUp(self):
        self.analyser = ResultsAnalyser()
        self.stats    = self.analyser.analyse(RESULTS_ALL_IMPROVED)

    def test_n_docs_is_total_count(self):
        self.assertEqual(self.stats.n_docs, 3)

    def test_n_errors_zero_when_no_errors(self):
        self.assertEqual(self.stats.n_errors, 0)

    def test_mean_pre_score_in_range(self):
        self.assertGreaterEqual(self.stats.mean_pre_score, 0.0)
        self.assertLessEqual(self.stats.mean_pre_score,    1.0)

    def test_mean_post_score_in_range(self):
        self.assertGreaterEqual(self.stats.mean_post_score, 0.0)
        self.assertLessEqual(self.stats.mean_post_score,    1.0)

    def test_std_improvement_non_negative(self):
        self.assertGreaterEqual(self.stats.std_improvement, 0.0)

    def test_pre_distribution_has_four_keys(self):
        self.assertEqual(
            set(self.stats.pre_distribution.keys()),
            {"POOR", "PARTIAL", "GOOD", "COMPLETE"},
        )

    def test_post_distribution_has_four_keys(self):
        self.assertEqual(
            set(self.stats.post_distribution.keys()),
            {"POOR", "PARTIAL", "GOOD", "COMPLETE"},
        )

    def test_improvement_pct_positive_when_improved(self):
        self.assertGreater(self.stats.improvement_pct(), 0.0)


# ================================================================== #
#  Suite 2 — ResultsAnalyser.analyse()                                #
# ================================================================== #

class TestResultsAnalyserAnalyse(unittest.TestCase):

    def setUp(self):
        self.analyser = ResultsAnalyser()

    def test_empty_list_returns_stats(self):
        stats = self.analyser.analyse([])
        self.assertIsInstance(stats, AggregateStats)
        self.assertEqual(stats.n_docs, 0)

    def test_n_errors_counted_correctly(self):
        stats = self.analyser.analyse(RESULTS_MIX)
        self.assertEqual(stats.n_errors, 1)

    def test_n_docs_includes_errors(self):
        stats = self.analyser.analyse(RESULTS_MIX)
        self.assertEqual(stats.n_docs, 5)

    def test_all_improved_docs_improved_equals_n(self):
        stats = self.analyser.analyse(RESULTS_ALL_IMPROVED)
        self.assertEqual(stats.docs_improved, 3)
        self.assertEqual(stats.docs_unchanged, 0)

    def test_silent_baseline_docs_unchanged(self):
        stats = self.analyser.analyse(RESULTS_SILENT)
        self.assertEqual(stats.docs_unchanged, 3)

    def test_mean_improvement_positive_when_post_gt_pre(self):
        stats = self.analyser.analyse(RESULTS_ALL_IMPROVED)
        self.assertGreater(stats.mean_improvement, 0.0)

    def test_mean_improvement_zero_for_silent_baseline(self):
        stats = self.analyser.analyse(RESULTS_SILENT)
        self.assertAlmostEqual(stats.mean_improvement, 0.0, places=4)

    def test_pct_improved_100_when_all_improved(self):
        stats = self.analyser.analyse(RESULTS_ALL_IMPROVED)
        self.assertAlmostEqual(stats.pct_improved, 100.0, places=1)

    def test_pct_improved_0_when_all_unchanged(self):
        stats = self.analyser.analyse(RESULTS_SILENT)
        self.assertAlmostEqual(stats.pct_improved, 0.0, places=1)

    def test_mean_pre_score_formula(self):
        pre_scores = [0.08, 0.25, 0.42, 0.67]   # S05 has error, excluded
        expected   = sum(pre_scores) / len(pre_scores)
        stats = self.analyser.analyse(RESULTS_MIX)
        self.assertAlmostEqual(stats.mean_pre_score, expected, places=3)

    def test_coverage_distribution_counts_correct(self):
        stats = self.analyser.analyse(RESULTS_MIX)
        # RESULTS_MIX has: POOR=1, PARTIAL=2, GOOD=1 (S05 excluded, error)
        self.assertEqual(stats.pre_distribution["POOR"],    1)
        self.assertEqual(stats.pre_distribution["PARTIAL"], 2)
        self.assertEqual(stats.pre_distribution["GOOD"],    1)

    def test_mean_gap_reduction_non_negative_when_improved(self):
        stats = self.analyser.analyse(RESULTS_ALL_IMPROVED)
        self.assertGreaterEqual(stats.mean_gap_reduction, 0.0)


# ================================================================== #
#  Suite 3 — Formatting + Comparison                                  #
# ================================================================== #

class TestFormattingAndComparison(unittest.TestCase):

    def setUp(self):
        self.analyser = ResultsAnalyser()
        self.stats    = self.analyser.analyse(RESULTS_ALL_IMPROVED)

    def test_format_summary_returns_string(self):
        s = self.analyser.format_summary(self.stats)
        self.assertIsInstance(s, str)

    def test_format_summary_non_empty(self):
        s = self.analyser.format_summary(self.stats)
        self.assertGreater(len(s), 0)

    def test_format_summary_contains_mean_pre(self):
        s = self.analyser.format_summary(self.stats)
        self.assertIn("pre-score", s)

    def test_format_summary_contains_coverage_levels(self):
        s = self.analyser.format_summary(self.stats)
        for level in ("POOR", "PARTIAL", "GOOD", "COMPLETE"):
            self.assertIn(level, s)

    def test_format_summary_custom_label(self):
        s = self.analyser.format_summary(self.stats, label="PURE Baseline")
        self.assertIn("PURE Baseline", s)

    def test_compare_returns_string(self):
        result = self.analyser.compare(RESULTS_SILENT, RESULTS_LLM, "Silent", "LLM")
        self.assertIsInstance(result, str)

    def test_compare_contains_both_labels(self):
        result = self.analyser.compare(RESULTS_SILENT, RESULTS_LLM, "Silent", "LLM")
        self.assertIn("Silent", result)
        self.assertIn("LLM", result)

    def test_compare_contains_improvement_row(self):
        result = self.analyser.compare(RESULTS_SILENT, RESULTS_LLM)
        self.assertIn("improvement", result.lower())

    def test_filter_by_mode_returns_correct_subset(self):
        all_results = RESULTS_SILENT + RESULTS_LLM
        silent = ResultsAnalyser.filter_by_mode(all_results, "silent")
        llm    = ResultsAnalyser.filter_by_mode(all_results, "llm")
        self.assertEqual(len(silent), 3)
        self.assertEqual(len(llm),    3)

    def test_filter_successful_excludes_errors(self):
        ok = ResultsAnalyser.filter_successful(RESULTS_MIX)
        self.assertEqual(len(ok), 4)
        for r in ok:
            self.assertEqual(r.error, "")


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAggregateStats))
    suite.addTests(loader.loadTestsFromTestCase(TestResultsAnalyserAnalyse))
    suite.addTests(loader.loadTestsFromTestCase(TestFormattingAndComparison))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
