"""
Unit tests for SRS Synthesiser (W5)
-------------------------------------
Suites:

  Suite 1 — SynthesisResult dataclass
  Suite 2 — Template synthesis (no LLM)
  Suite 3 — LLM synthesis (skipped if no API key)

Run:
    python metagpt/elicitation/synthesiser/test_srs_synthesiser.py
    python -m pytest metagpt/elicitation/synthesiser/test_srs_synthesiser.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import asyncio
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

schema_mod    = _load(str(_ELICITATION / "schema"   / "ecommerce_schema.py"),         "ecommerce_schema")
parser_mod    = _load(str(_ELICITATION / "parser"   / "srs_parser.py"),               "srs_parser")
analyser_mod  = _load(str(_ELICITATION / "analyser" / "completeness_analyser.py"),    "completeness_analyser")
prio_mod      = _load(str(_ELICITATION / "dialogue" / "question_prioritiser.py"),     "question_prioritiser")
dialogue_mod  = _load(str(_ELICITATION / "dialogue" / "elicitation_dialogue.py"),     "elicitation_dialogue")
synth_mod     = _load(str(_BASE        / "srs_synthesiser.py"),                       "srs_synthesiser")

SRSParser            = parser_mod.SRSParser
ParsedSRS            = parser_mod.ParsedSRS
CompletenessAnalyser = analyser_mod.CompletenessAnalyser
ElicitationDialogue  = dialogue_mod.ElicitationDialogue
DialogueAnswer       = dialogue_mod.DialogueAnswer
ElicitationSession   = dialogue_mod.ElicitationSession
ElicitationQuestion  = prio_mod.ElicitationQuestion
SRSSynthesiser       = synth_mod.SRSSynthesiser
SynthesisResult      = synth_mod.SynthesisResult


# ------------------------------------------------------------------ #
#  Fixtures                                                            #
# ------------------------------------------------------------------ #

SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."
SRS_RICH  = (
    "Build a B2C e-commerce platform where customers can register, "
    "login, browse a product catalog with search and filter, add items "
    "to their cart, and checkout using Stripe or PayPal."
)

SAMPLE_CLARS = {
    "payment":        "Stripe, PayPal",
    "authentication": "Email / password, Google OAuth",
    "business_model": "B2C",
}


def _make_session_with_answers(
    requirement: str,
    clars: dict,
) -> ElicitationSession:
    """Build a minimal ElicitationSession with pre-set answers (no LLM)."""
    questions = [
        ElicitationQuestion(cat, f"Q for {cat}", ["A", "B"], 3, "FUNCTIONAL", i + 1)
        for i, cat in enumerate(clars)
    ]
    answers = [
        DialogueAnswer(cat, f"Q for {cat}", ans, [ans])
        for cat, ans in clars.items()
    ]
    return ElicitationSession(
        original_requirement=requirement,
        questions_asked=questions,
        answers=answers,
        started_at="2026-06-19T10:00:00",
        completed_at="2026-06-19T10:01:00",
        mode="interactive",
    )


def _make_empty_session(requirement: str) -> ElicitationSession:
    return ElicitationSession(
        original_requirement=requirement,
        questions_asked=[],
        answers=[],
        started_at="2026-06-19T10:00:00",
        mode="silent",
    )


# ================================================================== #
#  Suite 1 — SynthesisResult dataclass                                #
# ================================================================== #

class TestSynthesisResult(unittest.TestCase):

    def _make_result(self, method="template", n_clars=3) -> SynthesisResult:
        return SynthesisResult(
            enriched_srs="Enriched text here.",
            original_srs=SRS_VAGUE,
            clarifications_applied=n_clars,
            synthesis_method=method,
        )

    def test_fields_exist(self):
        r = self._make_result()
        self.assertIsInstance(r.enriched_srs, str)
        self.assertIsInstance(r.original_srs, str)
        self.assertIsInstance(r.clarifications_applied, int)
        self.assertIsInstance(r.synthesis_method, str)

    def test_synthesis_method_values(self):
        self.assertEqual(self._make_result("llm").synthesis_method, "llm")
        self.assertEqual(self._make_result("template").synthesis_method, "template")

    def test_improvement_summary_is_string(self):
        r = self._make_result()
        s = r.improvement_summary()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 0)

    def test_improvement_summary_contains_method(self):
        r = self._make_result("template")
        self.assertIn("template", r.improvement_summary())

    def test_improvement_summary_contains_clarification_count(self):
        r = self._make_result(n_clars=5)
        self.assertIn("5", r.improvement_summary())


# ================================================================== #
#  Suite 2 — Template Synthesis (no LLM)                             #
# ================================================================== #

class TestTemplateSynthesis(unittest.TestCase):

    def setUp(self):
        self.synth = SRSSynthesiser()

    def test_template_includes_original(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        self.assertIn(SRS_VAGUE.rstrip("."), r.enriched_srs)

    def test_template_includes_all_clarification_values(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        for answer in SAMPLE_CLARS.values():
            self.assertIn(answer, r.enriched_srs)

    def test_template_method_is_template(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        self.assertEqual(r.synthesis_method, "template")

    def test_template_clarifications_applied_count(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        self.assertEqual(r.clarifications_applied, len(SAMPLE_CLARS))

    def test_template_no_clarifications_returns_original(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, {})
        self.assertEqual(r.enriched_srs, SRS_VAGUE)
        self.assertEqual(r.clarifications_applied, 0)

    def test_enriched_is_longer_than_original(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        self.assertGreater(len(r.enriched_srs), len(SRS_VAGUE))

    def test_original_srs_preserved_in_result(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, SAMPLE_CLARS)
        self.assertEqual(r.original_srs, SRS_VAGUE)

    def test_session_with_answers_synthesised_via_async(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        # Force template mode by temporarily removing API key
        synth         = SRSSynthesiser()
        synth._api_key = None
        result = asyncio.run(synth.synthesise(session))
        self.assertEqual(result.synthesis_method, "template")
        self.assertIn("Stripe, PayPal", result.enriched_srs)

    def test_empty_session_enriched_equals_original(self):
        session = _make_empty_session(SRS_VAGUE)
        synth         = SRSSynthesiser()
        synth._api_key = None
        result = asyncio.run(synth.synthesise(session))
        self.assertEqual(result.enriched_srs, SRS_VAGUE)

    def test_category_labels_human_readable_in_template(self):
        r = self.synth.synthesise_from_dict(SRS_VAGUE, {"business_model": "B2C"})
        # "business_model" should appear as "Business Model" in the output
        self.assertIn("Business Model", r.enriched_srs)


# ================================================================== #
#  Suite 3 — LLM Synthesis (skipped if no API key)                   #
# ================================================================== #

class TestLLMSynthesis(unittest.TestCase):

    def setUp(self):
        self.synth = SRSSynthesiser()
        if not self.synth._api_key:
            self.skipTest("No API key — skipping LLM synthesis tests")

    def test_llm_synthesise_returns_result(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        result  = self.synth.synthesise_sync(session)
        self.assertIsInstance(result, SynthesisResult)

    def test_llm_method_is_llm(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        result  = self.synth.synthesise_sync(session)
        self.assertEqual(result.synthesis_method, "llm")

    def test_llm_enriched_is_non_empty(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        result  = self.synth.synthesise_sync(session)
        self.assertGreater(len(result.enriched_srs.strip()), 0)

    def test_llm_enriched_longer_than_original(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        result  = self.synth.synthesise_sync(session)
        self.assertGreater(len(result.enriched_srs), len(SRS_VAGUE))

    def test_llm_clarifications_applied_count(self):
        session = _make_session_with_answers(SRS_VAGUE, SAMPLE_CLARS)
        result  = self.synth.synthesise_sync(session)
        self.assertEqual(result.clarifications_applied, len(SAMPLE_CLARS))


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSynthesisResult))
    suite.addTests(loader.loadTestsFromTestCase(TestTemplateSynthesis))
    suite.addTests(loader.loadTestsFromTestCase(TestLLMSynthesis))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
