"""
Unit tests for W7 — PURE Dataset Loader + Batch Runner
--------------------------------------------------------
Suites:
  Suite 1 — PURESample dataclass            (5 tests)
  Suite 2 — PUREDatasetLoader               (10 tests)
  Suite 3 — BatchResult dataclass           (8 tests)
  Suite 4 — BatchRunner in silent mode      (12 tests)

Total: 35 tests.  No live LLM calls required.

Run:
    python metagpt/elicitation/evaluation/test_w7.py
    python -m pytest metagpt/elicitation/evaluation/test_w7.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import importlib.util
import sys
import tempfile
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

schema_mod   = _load(str(_ELICITATION / "schema"      / "ecommerce_schema.py"),         "ecommerce_schema")
parser_mod   = _load(str(_ELICITATION / "parser"      / "srs_parser.py"),               "srs_parser")
analyser_mod = _load(str(_ELICITATION / "analyser"    / "completeness_analyser.py"),    "completeness_analyser")
prio_mod     = _load(str(_ELICITATION / "dialogue"    / "question_prioritiser.py"),     "question_prioritiser")
dialogue_mod = _load(str(_ELICITATION / "dialogue"    / "elicitation_dialogue.py"),     "elicitation_dialogue")
synth_mod    = _load(str(_ELICITATION / "synthesiser" / "srs_synthesiser.py"),          "srs_synthesiser")
logger_mod   = _load(str(_BASE        / "metrics_logger.py"),                           "metrics_logger")
runner_mod   = _load(str(_BASE        / "elicitation_runner.py"),                       "elicitation_runner")
dataset_mod  = _load(str(_BASE        / "pure_dataset.py"),                             "pure_dataset")
batch_mod    = _load(str(_BASE        / "batch_runner.py"),                             "batch_runner")

PURESample         = dataset_mod.PURESample
PUREDatasetLoader  = dataset_mod.PUREDatasetLoader
BatchResult        = batch_mod.BatchResult
BatchRunner        = batch_mod.BatchRunner

# Temp CSV for tests — avoids touching the real batch_results.csv
_TEST_CSV = _BASE / "_test_batch_results.csv"

SRS_VAGUE = "Build a fast, modern online shop for users to buy products."
SRS_RICH  = (
    "B2C e-commerce platform: customers register, login, browse products, "
    "add to cart, checkout with Stripe or PayPal. "
    "Admins manage products, inventory, and orders. "
    "Handles 10,000 concurrent users, GDPR compliant."
)


def _make_sample(doc_id="S01", text=SRS_VAGUE) -> PURESample:
    return PURESample(
        doc_id=doc_id,
        filename=f"{doc_id}.txt",
        raw_text=text,
        domain="ecommerce",
        word_count=len(text.split()),
        source="builtin",
    )


def _make_batch_result(**overrides) -> BatchResult:
    defaults = dict(
        batch_id="batch-1",
        doc_id="S01",
        domain="ecommerce",
        word_count=20,
        source="builtin",
        run_id="run-1",
        timestamp="2026-06-01T10:00:00",
        mode="silent",
        parse_method="fallback",
        synthesis_method="template",
        pre_score=0.10,
        pre_weighted_score=0.08,
        post_score=0.10,
        post_weighted_score=0.08,
        score_improvement=0.0,
        pre_coverage_level="POOR",
        post_coverage_level="POOR",
        critical_gaps_before=9,
        critical_gaps_after=9,
        questions_asked=0,
        answers_collected=0,
        duration_seconds=0.5,
        error="",
    )
    defaults.update(overrides)
    return BatchResult(**defaults)


# ================================================================== #
#  Suite 1 — PURESample dataclass                                     #
# ================================================================== #

class TestPURESample(unittest.TestCase):

    def test_fields_exist(self):
        s = _make_sample()
        self.assertEqual(s.doc_id, "S01")
        self.assertEqual(s.domain, "ecommerce")
        self.assertEqual(s.source, "builtin")

    def test_word_count_computed_from_text(self):
        text = "one two three four five"
        s = PURESample(
            doc_id="X", filename="x.txt",
            raw_text=text, domain="ecommerce",
            word_count=0, source="builtin",
        )
        self.assertEqual(s.word_count, 5)

    def test_word_count_explicit(self):
        s = _make_sample()
        self.assertEqual(s.word_count, len(SRS_VAGUE.split()))

    def test_raw_text_preserved(self):
        s = _make_sample(text=SRS_RICH)
        self.assertEqual(s.raw_text, SRS_RICH)

    def test_source_values(self):
        s1 = _make_sample()
        self.assertIn(s1.source, ("builtin", "file"))


# ================================================================== #
#  Suite 2 — PUREDatasetLoader                                        #
# ================================================================== #

class TestPUREDatasetLoader(unittest.TestCase):

    def test_load_builtin_returns_list(self):
        samples = PUREDatasetLoader.load_builtin()
        self.assertIsInstance(samples, list)

    def test_load_builtin_returns_10_samples(self):
        samples = PUREDatasetLoader.load_builtin()
        self.assertEqual(len(samples), 10)

    def test_all_builtin_have_doc_ids(self):
        for s in PUREDatasetLoader.load_builtin():
            self.assertGreater(len(s.doc_id), 0)

    def test_all_builtin_doc_ids_unique(self):
        ids = [s.doc_id for s in PUREDatasetLoader.load_builtin()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_builtin_have_raw_text(self):
        for s in PUREDatasetLoader.load_builtin():
            self.assertGreater(len(s.raw_text.strip()), 0)

    def test_all_builtin_word_counts_positive(self):
        for s in PUREDatasetLoader.load_builtin():
            self.assertGreater(s.word_count, 0)

    def test_builtin_source_is_builtin(self):
        for s in PUREDatasetLoader.load_builtin():
            self.assertEqual(s.source, "builtin")

    def test_load_from_dir_reads_txt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "doc1.txt").write_text("Sample requirements text.", encoding="utf-8")
            (tmp_path / "doc2.txt").write_text("Another SRS document here.", encoding="utf-8")
            samples = PUREDatasetLoader.load_from_dir(tmp_path)
            self.assertEqual(len(samples), 2)

    def test_load_from_dir_sets_source_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "doc1.txt").write_text("Requirements text.", encoding="utf-8")
            samples = PUREDatasetLoader.load_from_dir(tmp_path)
            self.assertEqual(samples[0].source, "file")

    def test_load_falls_back_to_builtin_when_no_dir(self):
        samples = PUREDatasetLoader.load(path=Path("/nonexistent/path"))
        self.assertGreater(len(samples), 0)
        for s in samples:
            self.assertEqual(s.source, "builtin")


# ================================================================== #
#  Suite 3 — BatchResult dataclass                                    #
# ================================================================== #

class TestBatchResult(unittest.TestCase):

    def test_fields_exist(self):
        br = _make_batch_result()
        self.assertEqual(br.batch_id, "batch-1")
        self.assertEqual(br.doc_id,   "S01")
        self.assertEqual(br.mode,     "silent")

    def test_to_row_is_dict(self):
        br = _make_batch_result()
        self.assertIsInstance(br.to_row(), dict)

    def test_to_row_has_all_csv_fields(self):
        from batch_runner import _BATCH_CSV_FIELDS
        row = _make_batch_result().to_row()
        for f in _BATCH_CSV_FIELDS:
            self.assertIn(f, row)

    def test_from_row_roundtrip(self):
        original = _make_batch_result(pre_score=0.25, post_score=0.60)
        row      = original.to_row()
        restored = BatchResult.from_row(row)
        self.assertEqual(restored.doc_id, original.doc_id)
        self.assertAlmostEqual(restored.pre_score,  0.25, places=4)
        self.assertAlmostEqual(restored.post_score, 0.60, places=4)

    def test_from_row_preserves_error_field(self):
        original = _make_batch_result(error="ValueError: test error")
        restored = BatchResult.from_row(original.to_row())
        self.assertEqual(restored.error, "ValueError: test error")

    def test_make_batch_id_is_uuid_string(self):
        bid = BatchResult.make_batch_id()
        self.assertIsInstance(bid, str)
        self.assertIn("-", bid)

    def test_make_batch_id_is_unique(self):
        self.assertNotEqual(
            BatchResult.make_batch_id(),
            BatchResult.make_batch_id(),
        )

    def test_error_default_is_empty_string(self):
        br = _make_batch_result()
        self.assertEqual(br.error, "")


# ================================================================== #
#  Suite 4 — BatchRunner in silent mode                               #
# ================================================================== #

class TestBatchRunnerSilent(unittest.TestCase):

    def setUp(self):
        self.runner = BatchRunner(mode="silent", verbose=False)
        BatchRunner.clear_results(_TEST_CSV)

    def tearDown(self):
        BatchRunner.clear_results(_TEST_CSV)
        BatchRunner.clear_results()  # also clear default

    def test_run_one_returns_batch_result(self):
        sample = _make_sample()
        result = self.runner.run_one(sample, batch_id="test-batch")
        self.assertIsInstance(result, BatchResult)

    def test_run_one_preserves_doc_id(self):
        sample = _make_sample(doc_id="PURE-S01")
        result = self.runner.run_one(sample, batch_id="b1")
        self.assertEqual(result.doc_id, "PURE-S01")

    def test_run_one_scores_are_between_0_and_1(self):
        sample = _make_sample()
        result = self.runner.run_one(sample, batch_id="b1")
        self.assertGreaterEqual(result.pre_score, 0.0)
        self.assertLessEqual(result.pre_score, 1.0)
        self.assertGreaterEqual(result.post_score, 0.0)
        self.assertLessEqual(result.post_score, 1.0)

    def test_run_one_no_error_on_valid_input(self):
        sample = _make_sample()
        result = self.runner.run_one(sample, batch_id="b1")
        self.assertEqual(result.error, "")

    def test_run_one_error_on_empty_text(self):
        # Empty text should be handled without crashing the runner
        sample = PURESample(
            doc_id="EMPTY", filename="empty.txt",
            raw_text="", domain="ecommerce",
            word_count=0, source="builtin",
        )
        result = self.runner.run_one(sample, batch_id="b1")
        self.assertIsInstance(result, BatchResult)

    def test_run_dataset_returns_list(self):
        samples = PUREDatasetLoader.load_builtin()[:3]
        results = self.runner.run_dataset(samples)
        self.assertIsInstance(results, list)

    def test_run_dataset_one_result_per_sample(self):
        samples = PUREDatasetLoader.load_builtin()[:3]
        results = self.runner.run_dataset(samples)
        self.assertEqual(len(results), 3)

    def test_run_dataset_results_have_same_batch_id(self):
        samples = PUREDatasetLoader.load_builtin()[:3]
        results = self.runner.run_dataset(samples)
        batch_ids = {r.batch_id for r in results}
        self.assertEqual(len(batch_ids), 1)

    def test_save_and_load_results_roundtrip(self):
        samples = PUREDatasetLoader.load_builtin()[:2]
        results = self.runner.run_dataset(samples)
        BatchRunner.save_results(results, _TEST_CSV)
        loaded  = BatchRunner.load_results(_TEST_CSV)
        self.assertEqual(len(loaded), 2)

    def test_loaded_doc_ids_match_original(self):
        samples = PUREDatasetLoader.load_builtin()[:2]
        results = self.runner.run_dataset(samples)
        BatchRunner.save_results(results, _TEST_CSV)
        loaded  = BatchRunner.load_results(_TEST_CSV)
        self.assertEqual(
            {r.doc_id for r in loaded},
            {r.doc_id for r in results},
        )

    def test_coverage_level_is_valid_string(self):
        sample = _make_sample(text=SRS_VAGUE)
        result = self.runner.run_one(sample, batch_id="b1")
        self.assertIn(result.pre_coverage_level,
                      ("POOR", "PARTIAL", "GOOD", "COMPLETE"))

    def test_rich_srs_scores_higher_than_vague(self):
        vague_result = self.runner.run_one(
            _make_sample(doc_id="V", text=SRS_VAGUE), batch_id="b1"
        )
        rich_result  = self.runner.run_one(
            _make_sample(doc_id="R", text=SRS_RICH),  batch_id="b1"
        )
        self.assertGreater(rich_result.pre_score, vague_result.pre_score)


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPURESample))
    suite.addTests(loader.loadTestsFromTestCase(TestPUREDatasetLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestBatchResult))
    suite.addTests(loader.loadTestsFromTestCase(TestBatchRunnerSilent))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
