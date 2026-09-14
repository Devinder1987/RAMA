"""
Unit tests for W6 — Metrics Logger + Elicitation Runner
---------------------------------------------------------
Suites:

  Suite 1 — RunMetrics dataclass
  Suite 2 — MetricsLogger (write / read / stats)
  Suite 3 — RunResult dataclass
  Suite 4 — ElicitationRunner (silent mode, no LLM needed)
  Suite 5 — Full pipeline end-to-end (LLM mode, skipped if no key)

Run:
    python metagpt/elicitation/evaluation/test_w6.py
    python -m pytest metagpt/elicitation/evaluation/test_w6.py -v

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

RunMetrics           = logger_mod.RunMetrics
MetricsLogger        = logger_mod.MetricsLogger
RunResult            = runner_mod.RunResult
ElicitationRunner    = runner_mod.ElicitationRunner

# ------------------------------------------------------------------ #
#  SRS fixtures                                                        #
# ------------------------------------------------------------------ #

SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."
SRS_RICH  = (
    "Build a B2C e-commerce platform where customers can register, "
    "login, browse a product catalog with search and filter, add items "
    "to their cart, and checkout using Stripe or PayPal. "
    "Admins can manage products, view orders, and issue refunds."
)

# Temporary log file for tests (avoids polluting the real runs.csv)
_TEST_LOG = Path(__file__).parent / "_test_runs.csv"


def _make_metrics(**overrides) -> RunMetrics:
    defaults = dict(
        run_id="test-run-1",
        timestamp="2026-06-19T10:00:00",
        mode="silent",
        parse_method="fallback",
        synthesis_method="template",
        pre_score=0.10,
        pre_weighted_score=0.08,
        post_score=0.42,
        post_weighted_score=0.45,
        questions_asked=10,
        answers_collected=8,
        critical_gaps_before=9,
        critical_gaps_after=3,
        duration_seconds=5.2,
        original_srs_excerpt=SRS_VAGUE[:120],
    )
    defaults.update(overrides)
    return RunMetrics(**defaults)


# ================================================================== #
#  Suite 1 — RunMetrics                                               #
# ================================================================== #

class TestRunMetrics(unittest.TestCase):

    def setUp(self):
        self.m = _make_metrics()

    def test_fields_exist(self):
        self.assertEqual(self.m.run_id, "test-run-1")
        self.assertEqual(self.m.mode, "silent")
        self.assertEqual(self.m.pre_score, 0.10)
        self.assertEqual(self.m.post_score, 0.42)

    def test_score_improvement_property(self):
        self.assertAlmostEqual(self.m.score_improvement, 0.32, places=4)

    def test_score_improvement_zero_when_no_change(self):
        m = _make_metrics(pre_score=0.5, post_score=0.5)
        self.assertEqual(m.score_improvement, 0.0)

    def test_to_row_is_dict(self):
        row = self.m.to_row()
        self.assertIsInstance(row, dict)

    def test_to_row_has_all_csv_fields(self):
        from metrics_logger import _CSV_FIELDS
        row = self.m.to_row()
        for f in _CSV_FIELDS:
            self.assertIn(f, row)

    def test_to_row_includes_score_improvement(self):
        row = self.m.to_row()
        self.assertIn("score_improvement", row)
        self.assertAlmostEqual(float(row["score_improvement"]), 0.32, places=4)

    def test_from_row_roundtrip(self):
        row = self.m.to_row()
        restored = RunMetrics.from_row(row)
        self.assertEqual(restored.run_id,    self.m.run_id)
        self.assertAlmostEqual(restored.pre_score,  self.m.pre_score)
        self.assertAlmostEqual(restored.post_score, self.m.post_score)

    def test_make_run_id_is_string(self):
        rid = RunMetrics.make_run_id()
        self.assertIsInstance(rid, str)
        self.assertGreater(len(rid), 0)

    def test_make_run_id_is_unique(self):
        self.assertNotEqual(RunMetrics.make_run_id(), RunMetrics.make_run_id())

    def test_now_iso_is_string(self):
        ts = RunMetrics.now_iso()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)   # ISO-8601 contains T between date and time


# ================================================================== #
#  Suite 2 — MetricsLogger                                            #
# ================================================================== #

class TestMetricsLogger(unittest.TestCase):

    def setUp(self):
        self.logger = MetricsLogger(log_file=_TEST_LOG)
        self.logger.clear()   # start fresh for each test

    def tearDown(self):
        self.logger.clear()

    def test_log_creates_file(self):
        self.logger.log(_make_metrics())
        self.assertTrue(_TEST_LOG.exists())

    def test_log_and_load_one_row(self):
        self.logger.log(_make_metrics(run_id="r1"))
        rows = self.logger.load_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].run_id, "r1")

    def test_log_multiple_rows(self):
        for i in range(3):
            self.logger.log(_make_metrics(run_id=f"r{i}"))
        rows = self.logger.load_all()
        self.assertEqual(len(rows), 3)

    def test_load_all_empty_when_no_file(self):
        rows = self.logger.load_all()
        self.assertEqual(rows, [])

    def test_load_last_returns_n_rows(self):
        for i in range(5):
            self.logger.log(_make_metrics(run_id=f"r{i}"))
        last3 = self.logger.load_last(3)
        self.assertEqual(len(last3), 3)

    def test_scores_preserved_after_roundtrip(self):
        m = _make_metrics(pre_score=0.25, post_score=0.67)
        self.logger.log(m)
        restored = self.logger.load_all()[0]
        self.assertAlmostEqual(restored.pre_score,  0.25, places=4)
        self.assertAlmostEqual(restored.post_score, 0.67, places=4)

    def test_summary_stats_returns_dict(self):
        for i in range(3):
            self.logger.log(_make_metrics(
                run_id=f"r{i}",
                pre_score=0.1 * (i + 1),
                post_score=0.1 * (i + 1) + 0.2,
            ))
        stats = self.logger.summary_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("run_count", stats)
        self.assertIn("mean_improvement", stats)

    def test_summary_stats_run_count(self):
        for i in range(4):
            self.logger.log(_make_metrics(run_id=f"r{i}"))
        self.assertEqual(self.logger.summary_stats()["run_count"], 4)

    def test_summary_stats_empty_when_no_runs(self):
        self.assertEqual(self.logger.summary_stats(), {})

    def test_pct_improved_all_positive(self):
        for i in range(5):
            self.logger.log(_make_metrics(
                run_id=f"r{i}", pre_score=0.1, post_score=0.5
            ))
        stats = self.logger.summary_stats()
        self.assertEqual(stats["pct_improved"], 100.0)

    def test_clear_removes_file(self):
        self.logger.log(_make_metrics())
        self.logger.clear()
        self.assertFalse(_TEST_LOG.exists())

    def test_append_does_not_duplicate_header(self):
        self.logger.log(_make_metrics(run_id="a"))
        self.logger.log(_make_metrics(run_id="b"))
        rows = self.logger.load_all()
        self.assertEqual(len(rows), 2)


# ================================================================== #
#  Suite 3 — RunResult                                                #
# ================================================================== #

class TestRunResult(unittest.TestCase):

    def setUp(self):
        # Build a minimal RunResult manually (no pipeline execution)
        analyser = analyser_mod.CompletenessAnalyser()
        parser   = parser_mod.SRSParser()

        pre_parsed  = parser.parse_fallback(SRS_VAGUE)
        post_parsed = parser.parse_fallback(SRS_RICH)

        self.pre_report  = analyser.analyse(pre_parsed)
        self.post_report = analyser.analyse(post_parsed)
        self.metrics     = _make_metrics(
            pre_score=self.pre_report.raw_score,
            post_score=self.post_report.raw_score,
        )

        self.result = RunResult(
            original_srs=SRS_VAGUE,
            enriched_srs=SRS_RICH,
            pre_report=self.pre_report,
            post_report=self.post_report,
            session=None,
            synthesis=None,
            metrics=self.metrics,
        )

    def test_score_improvement_positive(self):
        # Rich SRS scores higher than vague SRS
        self.assertGreater(self.result.score_improvement, 0)

    def test_score_improvement_formula(self):
        expected = round(
            self.post_report.raw_score - self.pre_report.raw_score, 4
        )
        self.assertAlmostEqual(self.result.score_improvement, expected)

    def test_summary_is_non_empty_string(self):
        s = self.result.summary()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 0)

    def test_summary_contains_scores(self):
        s = self.result.summary()
        self.assertIn("Before", s)
        self.assertIn("After", s)

    def test_summary_contains_run_id(self):
        self.assertIn("test-run-1", self.result.summary())


# ================================================================== #
#  Suite 4 — ElicitationRunner (silent mode)                          #
# ================================================================== #

class TestElicitationRunnerSilent(unittest.TestCase):

    def setUp(self):
        self.runner = ElicitationRunner(
            mode="silent",
            max_questions=5,
            log_file=_TEST_LOG,
        )
        self.runner.logger.clear()

    def tearDown(self):
        self.runner.logger.clear()

    def test_run_returns_run_result(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertIsInstance(r, RunResult)

    def test_original_srs_preserved(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertEqual(r.original_srs, SRS_VAGUE)

    def test_pre_report_is_not_none(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertIsNotNone(r.pre_report)

    def test_post_report_is_not_none(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertIsNotNone(r.post_report)

    def test_metrics_logged_to_csv(self):
        self.runner.run_sync(SRS_VAGUE)
        rows = self.runner.logger.load_all()
        self.assertEqual(len(rows), 1)

    def test_metrics_run_id_is_uuid(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreater(len(r.metrics.run_id), 0)
        self.assertIn("-", r.metrics.run_id)   # UUID contains hyphens

    def test_metrics_mode_is_silent(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertEqual(r.metrics.mode, "silent")

    def test_silent_mode_answers_collected_is_zero(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertEqual(r.metrics.answers_collected, 0)

    def test_questions_asked_limited_by_max(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertLessEqual(r.metrics.questions_asked, 5)

    def test_duration_seconds_positive(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreater(r.metrics.duration_seconds, 0)

    def test_pre_score_between_0_and_1(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreaterEqual(r.metrics.pre_score, 0.0)
        self.assertLessEqual(r.metrics.pre_score, 1.0)

    def test_two_runs_produce_two_csv_rows(self):
        self.runner.run_sync(SRS_VAGUE)
        self.runner.run_sync(SRS_RICH)
        rows = self.runner.logger.load_all()
        self.assertEqual(len(rows), 2)

    def test_enriched_srs_non_empty(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreater(len(r.enriched_srs.strip()), 0)

    def test_summary_is_string(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertIsInstance(r.summary(), str)


# ================================================================== #
#  Suite 5 — Full pipeline LLM mode (skipped if no API key)           #
# ================================================================== #

class TestElicitationRunnerLLM(unittest.TestCase):

    def setUp(self):
        self.runner = ElicitationRunner(
            mode="llm",
            max_questions=3,
            log_file=_TEST_LOG,
        )
        self.runner.logger.clear()
        if not self.runner.synthesiser._api_key:
            self.skipTest("No API key — skipping LLM pipeline tests")

    def tearDown(self):
        self.runner.logger.clear()

    def test_llm_run_returns_result(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertIsInstance(r, RunResult)

    def test_llm_answers_collected_positive(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreater(r.metrics.answers_collected, 0)

    def test_llm_post_score_gte_pre_score(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreaterEqual(r.metrics.post_score, r.metrics.pre_score)

    def test_llm_enriched_srs_longer_than_original(self):
        r = self.runner.run_sync(SRS_VAGUE)
        self.assertGreater(len(r.enriched_srs), len(SRS_VAGUE))

    def test_llm_metrics_in_csv(self):
        self.runner.run_sync(SRS_VAGUE)
        rows = self.runner.logger.load_all()
        self.assertGreater(len(rows), 0)
        self.assertIn(rows[0].mode, ("llm",))


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestRunMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestMetricsLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestRunResult))
    suite.addTests(loader.loadTestsFromTestCase(TestElicitationRunnerSilent))
    suite.addTests(loader.loadTestsFromTestCase(TestElicitationRunnerLLM))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
