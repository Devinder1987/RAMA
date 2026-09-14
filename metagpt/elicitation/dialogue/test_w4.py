"""
Unit tests for W4 — Question Prioritiser + Elicitation Dialogue
-----------------------------------------------------------------
Suites:

  Suite 1 — ElicitationQuestion dataclass
  Suite 2 — QuestionPrioritiser ordering + filtering
  Suite 3 — Input parsing (numbers / free text / edge cases)
  Suite 4 — ElicitationSession accessors + context dict
  Suite 5 — ElicitationDialogue silent + LLM mode (skipped if no key)

Run:
    python metagpt/elicitation/dialogue/test_w4.py
    python -m pytest metagpt/elicitation/dialogue/test_w4.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

# ------------------------------------------------------------------ #
#  Load all modules directly (bypass metagpt.__init__)                #
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

schema_mod    = _load(str(_ELICITATION / "schema"   / "ecommerce_schema.py"),          "ecommerce_schema")
parser_mod    = _load(str(_ELICITATION / "parser"   / "srs_parser.py"),                "srs_parser")
analyser_mod  = _load(str(_ELICITATION / "analyser" / "completeness_analyser.py"),     "completeness_analyser")
prio_mod      = _load(str(_BASE        / "question_prioritiser.py"),                   "question_prioritiser")
dialogue_mod  = _load(str(_BASE        / "elicitation_dialogue.py"),                   "elicitation_dialogue")

ECOMMERCE_SCHEMA     = schema_mod.ECOMMERCE_SCHEMA
ParsedSRS            = parser_mod.ParsedSRS
CompletenessAnalyser = analyser_mod.CompletenessAnalyser
CompletenessReport   = analyser_mod.CompletenessReport
ElicitationQuestion  = prio_mod.ElicitationQuestion
QuestionPrioritiser  = prio_mod.QuestionPrioritiser
DialogueAnswer       = dialogue_mod.DialogueAnswer
ElicitationSession   = dialogue_mod.ElicitationSession
ElicitationDialogue  = dialogue_mod.ElicitationDialogue

_ALL_CATS     = list(ECOMMERCE_SCHEMA.keys())
_TOTAL_CATS   = schema_mod.total_categories()   # 24
_TOTAL_WEIGHT = schema_mod.total_weight()        # 58

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
#  Report fixtures                                                     #
# ------------------------------------------------------------------ #

def _make_empty_report() -> CompletenessReport:
    analyser = CompletenessAnalyser()
    parsed   = ParsedSRS(raw_text="", schema_hints={k: False for k in _ALL_CATS})
    return analyser.analyse(parsed)


def _make_full_report() -> CompletenessReport:
    analyser = CompletenessAnalyser()
    parsed   = ParsedSRS(raw_text="", schema_hints={k: True for k in _ALL_CATS})
    return analyser.analyse(parsed)


def _make_rich_report() -> CompletenessReport:
    return CompletenessAnalyser().analyse_text(SRS_RICH)


def _make_vague_report() -> CompletenessReport:
    return CompletenessAnalyser().analyse_text(SRS_VAGUE)


# ================================================================== #
#  Suite 1 — ElicitationQuestion dataclass                            #
# ================================================================== #

class TestElicitationQuestion(unittest.TestCase):

    def _make_q(self, weight=3, group="FUNCTIONAL", priority=1) -> ElicitationQuestion:
        return ElicitationQuestion(
            category_name="payment",
            question="Which payment methods are required?",
            suggestions=["Stripe", "PayPal", "Razorpay"],
            weight=weight,
            group=group,
            priority=priority,
        )

    def test_fields_exist(self):
        q = self._make_q()
        self.assertEqual(q.category_name, "payment")
        self.assertEqual(q.question, "Which payment methods are required?")
        self.assertIsInstance(q.suggestions, list)
        self.assertEqual(q.weight, 3)
        self.assertEqual(q.group, "FUNCTIONAL")
        self.assertEqual(q.priority, 1)

    def test_is_critical_true_for_weight3(self):
        self.assertTrue(self._make_q(weight=3).is_critical())

    def test_is_critical_false_for_weight2(self):
        self.assertFalse(self._make_q(weight=2).is_critical())

    def test_display_contains_question_text(self):
        q = self._make_q()
        d = q.display()
        self.assertIn("Which payment methods are required?", d)

    def test_display_contains_all_suggestions(self):
        q = self._make_q()
        d = q.display()
        for s in q.suggestions:
            self.assertIn(s, d)

    def test_display_contains_priority_number(self):
        q = self._make_q(priority=3)
        self.assertIn("[Q3]", q.display())


# ================================================================== #
#  Suite 2 — QuestionPrioritiser                                      #
# ================================================================== #

class TestQuestionPrioritiser(unittest.TestCase):

    def setUp(self):
        self.p = QuestionPrioritiser()

    def test_empty_report_returns_empty_list(self):
        qs = self.p.prioritise(_make_full_report())
        self.assertEqual(qs, [])

    def test_full_missing_returns_all_categories(self):
        qs = self.p.prioritise(_make_empty_report())
        self.assertEqual(len(qs), _TOTAL_CATS)

    def test_all_returned_questions_are_elicitation_question(self):
        for q in self.p.prioritise(_make_empty_report()):
            self.assertIsInstance(q, ElicitationQuestion)

    def test_weight3_questions_come_before_weight2(self):
        qs = self.p.prioritise(_make_empty_report())
        weights = [q.weight for q in qs]
        # All 3s must appear before any 2
        saw_two = False
        for w in weights:
            if w == 2:
                saw_two = True
            if saw_two:
                self.assertNotEqual(w, 3, "Weight-3 question appeared after weight-2")

    def test_within_same_weight_functional_before_nonfunctional(self):
        qs    = self.p.prioritise(_make_empty_report())
        # Filter weight-3 questions only
        w3    = [q for q in qs if q.weight == 3]
        groups = [q.group for q in w3]
        saw_nf = False
        for g in groups:
            if g == "NON_FUNCTIONAL":
                saw_nf = True
            if saw_nf:
                self.assertNotEqual(g, "FUNCTIONAL",
                    "FUNCTIONAL weight-3 appeared after NON_FUNCTIONAL weight-3")

    def test_within_same_weight_nonfunctional_before_domain(self):
        qs     = self.p.prioritise(_make_empty_report())
        w3     = [q for q in qs if q.weight == 3]
        groups = [q.group for q in w3]
        saw_d  = False
        for g in groups:
            if g == "DOMAIN":
                saw_d = True
            if saw_d:
                self.assertNotEqual(g, "NON_FUNCTIONAL",
                    "NON_FUNCTIONAL weight-3 appeared after DOMAIN weight-3")

    def test_priorities_are_sequential_from_1(self):
        qs = self.p.prioritise(_make_empty_report())
        for i, q in enumerate(qs):
            self.assertEqual(q.priority, i + 1)

    def test_category_names_match_schema_keys(self):
        qs = self.p.prioritise(_make_empty_report())
        schema_keys = set(ECOMMERCE_SCHEMA.keys())
        for q in qs:
            self.assertIn(q.category_name, schema_keys)

    def test_questions_have_non_empty_question_text(self):
        for q in self.p.prioritise(_make_empty_report()):
            self.assertGreater(len(q.question), 0)

    def test_questions_have_non_empty_suggestions(self):
        for q in self.p.prioritise(_make_empty_report()):
            self.assertGreater(len(q.suggestions), 0)

    def test_critical_questions_all_weight3(self):
        cqs = self.p.critical_questions(_make_empty_report())
        for q in cqs:
            self.assertEqual(q.weight, 3)

    def test_critical_questions_count(self):
        cqs = self.p.critical_questions(_make_empty_report())
        w3_cats = [k for k, v in ECOMMERCE_SCHEMA.items() if v.weight == 3]
        self.assertEqual(len(cqs), len(w3_cats))

    def test_top_n_returns_n_items(self):
        qs = self.p.top_n(_make_empty_report(), 5)
        self.assertEqual(len(qs), 5)

    def test_top_n_greater_than_total_returns_all(self):
        qs = self.p.top_n(_make_empty_report(), 999)
        self.assertEqual(len(qs), _TOTAL_CATS)

    def test_top_n_zero_returns_empty(self):
        qs = self.p.top_n(_make_empty_report(), 0)
        self.assertEqual(qs, [])

    def test_questions_by_group_has_three_keys(self):
        grouped = self.p.questions_by_group(_make_empty_report())
        self.assertIn("FUNCTIONAL", grouped)
        self.assertIn("NON_FUNCTIONAL", grouped)
        self.assertIn("DOMAIN", grouped)

    def test_vague_srs_has_payment_as_early_question(self):
        report = _make_vague_report()
        qs     = self.p.prioritise(report)
        cats   = [q.category_name for q in qs[:10]]
        self.assertIn("payment", cats)

    def test_rich_srs_has_fewer_questions_than_vague(self):
        rich_qs  = self.p.prioritise(_make_rich_report())
        vague_qs = self.p.prioritise(_make_vague_report())
        self.assertLess(len(rich_qs), len(vague_qs))


# ================================================================== #
#  Suite 3 — Input Parsing                                            #
# ================================================================== #

class TestInputParsing(unittest.TestCase):

    def setUp(self):
        self.dialogue    = ElicitationDialogue()
        self.suggestions = ["Stripe", "PayPal", "Razorpay", "COD"]

    def _parse(self, raw: str):
        return self.dialogue._parse_input(raw, self.suggestions)

    def test_single_number_selects_suggestion(self):
        answer, selected = self._parse("1")
        self.assertEqual(selected, ["Stripe"])
        self.assertEqual(answer, "Stripe")

    def test_multiple_numbers_select_multiple_suggestions(self):
        answer, selected = self._parse("1, 3")
        self.assertIn("Stripe", selected)
        self.assertIn("Razorpay", selected)
        self.assertEqual(len(selected), 2)

    def test_numbers_with_no_space_separator(self):
        answer, selected = self._parse("2,4")
        self.assertIn("PayPal", selected)
        self.assertIn("COD", selected)

    def test_free_text_returns_no_selections(self):
        answer, selected = self._parse("We need cash on delivery only")
        self.assertEqual(selected, [])
        self.assertEqual(answer, "We need cash on delivery only")

    def test_out_of_range_number_is_free_text(self):
        answer, selected = self._parse("99")
        self.assertEqual(selected, [])
        self.assertEqual(answer, "99")

    def test_empty_string_returns_empty(self):
        answer, selected = self._parse("")
        self.assertEqual(answer, "")
        self.assertEqual(selected, [])

    def test_mixed_number_and_text_is_free_text(self):
        answer, selected = self._parse("1 and also custom text")
        self.assertEqual(selected, [])

    def test_whitespace_only_returns_empty(self):
        answer, selected = self._parse("   ")
        self.assertEqual(answer, "")
        self.assertEqual(selected, [])

    def test_answer_text_joins_selected_suggestions(self):
        answer, selected = self._parse("1, 2")
        self.assertIn("Stripe", answer)
        self.assertIn("PayPal", answer)

    def test_zero_is_treated_as_free_text(self):
        answer, selected = self._parse("0")
        self.assertEqual(selected, [])


# ================================================================== #
#  Suite 4 — ElicitationSession                                       #
# ================================================================== #

class TestElicitationSession(unittest.TestCase):

    def _make_session(self) -> ElicitationSession:
        questions = [
            ElicitationQuestion("payment",         "Payment method?",   ["Stripe", "PayPal"], 3, "FUNCTIONAL", 1),
            ElicitationQuestion("authentication",  "Auth method?",      ["Email", "OAuth"],   3, "FUNCTIONAL", 2),
            ElicitationQuestion("seo",             "SEO required?",     ["Yes", "No"],        2, "DOMAIN",     3),
        ]
        answers = [
            DialogueAnswer("payment",        "Payment method?",  "Stripe",       ["Stripe"]),
            DialogueAnswer("authentication", "Auth method?",     "Email, OAuth", ["Email", "OAuth"]),
        ]
        return ElicitationSession(
            original_requirement="Build a shop",
            questions_asked=questions,
            answers=answers,
            started_at="2026-06-14T10:00:00",
            completed_at="2026-06-14T10:05:00",
            mode="interactive",
        )

    def test_get_answer_returns_correct_answer(self):
        s = self._make_session()
        a = s.get_answer("payment")
        self.assertIsNotNone(a)
        self.assertEqual(a.answer, "Stripe")

    def test_get_answer_returns_none_for_missing(self):
        s = self._make_session()
        self.assertIsNone(s.get_answer("seo"))

    def test_answered_categories_lists_answered(self):
        s = self._make_session()
        cats = s.answered_categories()
        self.assertIn("payment", cats)
        self.assertIn("authentication", cats)
        self.assertNotIn("seo", cats)

    def test_unanswered_questions_excludes_answered(self):
        s = self._make_session()
        unanswered = s.unanswered_questions()
        cats = [q.category_name for q in unanswered]
        self.assertIn("seo", cats)
        self.assertNotIn("payment", cats)

    def test_to_context_dict_has_required_keys(self):
        ctx = self._make_session().to_context_dict()
        self.assertIn("original_requirement", ctx)
        self.assertIn("clarifications", ctx)
        self.assertIn("answered_categories", ctx)
        self.assertIn("session_mode", ctx)

    def test_to_context_dict_clarifications_maps_categories(self):
        ctx = self._make_session().to_context_dict()
        clars = ctx["clarifications"]
        self.assertIn("payment", clars)
        self.assertIn("authentication", clars)
        self.assertEqual(clars["payment"], "Stripe")

    def test_to_context_dict_original_requirement_preserved(self):
        ctx = self._make_session().to_context_dict()
        self.assertEqual(ctx["original_requirement"], "Build a shop")

    def test_summary_is_non_empty_string(self):
        s = self._make_session().summary()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 0)

    def test_summary_contains_mode(self):
        self.assertIn("interactive", self._make_session().summary())

    def test_summary_contains_answer_count(self):
        s = self._make_session()
        summary = s.summary()
        self.assertIn("2", summary)


# ================================================================== #
#  Suite 5 — ElicitationDialogue (silent + LLM)                      #
# ================================================================== #

class TestElicitationDialogue(unittest.TestCase):

    def setUp(self):
        self.dialogue = ElicitationDialogue(max_questions=5)
        self.report   = _make_vague_report()

    def _run(self, mode: str) -> ElicitationSession:
        return asyncio.run(self.dialogue.run(SRS_VAGUE, self.report, mode=mode))

    def test_silent_mode_returns_session(self):
        s = self._run("silent")
        self.assertIsInstance(s, ElicitationSession)

    def test_silent_mode_has_no_answers(self):
        s = self._run("silent")
        self.assertEqual(s.answers, [])

    def test_silent_mode_questions_asked_is_populated(self):
        s = self._run("silent")
        self.assertGreater(len(s.questions_asked), 0)

    def test_silent_mode_questions_limited_to_max(self):
        s = self._run("silent")
        self.assertLessEqual(len(s.questions_asked), 5)

    def test_session_has_started_at(self):
        s = self._run("silent")
        self.assertIsNotNone(s.started_at)
        self.assertGreater(len(s.started_at), 0)

    def test_session_has_completed_at_after_run(self):
        s = self._run("silent")
        self.assertIsNotNone(s.completed_at)

    def test_original_requirement_preserved(self):
        s = self._run("silent")
        self.assertEqual(s.original_requirement, SRS_VAGUE)

    def test_mode_recorded_in_session(self):
        s = self._run("silent")
        self.assertEqual(s.mode, "silent")

    def test_questions_are_elicitation_question_instances(self):
        s = self._run("silent")
        for q in s.questions_asked:
            self.assertIsInstance(q, ElicitationQuestion)

    def test_first_question_is_highest_weight(self):
        s = self._run("silent")
        if len(s.questions_asked) >= 2:
            self.assertGreaterEqual(
                s.questions_asked[0].weight,
                s.questions_asked[1].weight,
            )

    def test_llm_mode_skipped_without_api_key(self):
        if not self.dialogue._api_key:
            self.skipTest("No API key — skipping LLM mode test")
        s = self._run("llm")
        self.assertGreater(len(s.answers), 0)

    def test_llm_mode_answers_have_text(self):
        if not self.dialogue._api_key:
            self.skipTest("No API key — skipping LLM mode test")
        s = self._run("llm")
        for a in s.answers:
            self.assertIsInstance(a.answer, str)

    def test_context_dict_from_silent_session(self):
        s   = self._run("silent")
        ctx = s.to_context_dict()
        self.assertIn("original_requirement", ctx)
        self.assertEqual(ctx["clarifications"], {})   # no answers in silent


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestElicitationQuestion))
    suite.addTests(loader.loadTestsFromTestCase(TestQuestionPrioritiser))
    suite.addTests(loader.loadTestsFromTestCase(TestInputParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestElicitationSession))
    suite.addTests(loader.loadTestsFromTestCase(TestElicitationDialogue))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
