"""
Elicitation Dialogue (W4b)
---------------------------
Drives the Q&A session between the system and the user (or LLM).

Two modes:
  interactive — prints questions to terminal, reads user input
  llm         — Gemini 2.5 Flash simulates a product-owner answering
                 each question based on the original SRS context.
                 Used during automated PURE-dataset evaluation runs.

Session object (ElicitationSession) is the output consumed by W5
(SRS Synthesiser) to build the enriched requirement string.

Flow:
    CompletenessReport  (W3)
          │
          ▼
    QuestionPrioritiser → List[ElicitationQuestion]
          │
          ▼
    ElicitationDialogue.run()
          │  interactive: print + input()
          │  llm:         Gemini answers from SRS context
          ▼
    ElicitationSession
          │
          ▼
    W5: SRSSynthesiser

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import asyncio
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ------------------------------------------------------------------ #
#  Local imports via importlib.util                                    #
# ------------------------------------------------------------------ #
import importlib.util as _ilu

_BASE        = Path(__file__).parent
_ELICITATION = _BASE.parent

def _load(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_prio_mod           = _load(_BASE / "question_prioritiser.py", "question_prioritiser")
QuestionPrioritiser = _prio_mod.QuestionPrioritiser
ElicitationQuestion = _prio_mod.ElicitationQuestion


# ------------------------------------------------------------------ #
#  Config loader (shared with SRSParser)                               #
# ------------------------------------------------------------------ #

def _load_api_key() -> Optional[str]:
    candidates = [
        Path(__file__).parent.parent.parent.parent / "config" / "config2.yaml",
        Path.home() / ".metagpt" / "config2.yaml",
    ]
    for p in candidates:
        if p.exists():
            cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
            return cfg.get("llm", {}).get("api_key")
    return None


# ------------------------------------------------------------------ #
#  LLM prompt                                                          #
# ------------------------------------------------------------------ #

_LLM_ANSWER_PROMPT = """\
You are acting as the product owner of a software project.

Below is a software requirements document (SRS) you have written:
---
{requirement}
---

A requirements engineer is asking you the following clarifying question:
Question: {question}

Available options:
{options}
{hints}

Instructions:
- Pick one or more option numbers that best match the intent of your SRS,
  OR write a short free-text answer (under 20 words) if none of the options fit.
- If options fit, reply with just the numbers separated by commas (e.g. "1, 3").
- If free text is better, reply with a single sentence only.
- Do NOT explain or add context.
"""


# ------------------------------------------------------------------ #
#  Data models                                                         #
# ------------------------------------------------------------------ #

@dataclass
class DialogueAnswer:
    """
    One answered question from the elicitation session.
    """
    category_name: str          # schema category key
    question: str               # question text shown to user
    answer: str                 # full answer text (canonical form)
    selected_suggestions: List[str] = field(default_factory=list)
    # ↑ empty when the answer was free-form text


@dataclass
class ElicitationSession:
    """
    Complete record of one elicitation run.
    Produced by ElicitationDialogue and consumed by W5 SRSSynthesiser.
    """
    original_requirement: str
    questions_asked: List[ElicitationQuestion]
    answers: List[DialogueAnswer]
    started_at: str
    completed_at: Optional[str] = None
    mode: str = "interactive"   # "interactive" | "llm" | "silent"

    # ---------------------------------------------------------------- #
    #  Accessors                                                         #
    # ---------------------------------------------------------------- #

    def get_answer(self, category_name: str) -> Optional[DialogueAnswer]:
        """Return the answer for a specific category, or None."""
        for a in self.answers:
            if a.category_name == category_name:
                return a
        return None

    def answered_categories(self) -> List[str]:
        return [a.category_name for a in self.answers]

    def unanswered_questions(self) -> List[ElicitationQuestion]:
        answered = set(self.answered_categories())
        return [q for q in self.questions_asked if q.category_name not in answered]

    # ---------------------------------------------------------------- #
    #  W5 interface                                                      #
    # ---------------------------------------------------------------- #

    def to_context_dict(self) -> Dict:
        """
        Structured dict consumed by W5 (SRS Synthesiser).
        Maps each answered category to its answer text.
        """
        return {
            "original_requirement": self.original_requirement,
            "clarifications": {
                a.category_name: a.answer for a in self.answers
            },
            "answered_categories": self.answered_categories(),
            "session_mode": self.mode,
        }

    # ---------------------------------------------------------------- #
    #  Display                                                           #
    # ---------------------------------------------------------------- #

    def summary(self) -> str:
        lines = [
            f"Mode             : {self.mode}",
            f"Questions asked  : {len(self.questions_asked)}",
            f"Answers collected: {len(self.answers)}",
            f"Started          : {self.started_at}",
            f"Completed        : {self.completed_at or 'in progress'}",
            "",
            "Answers:",
        ]
        for a in self.answers:
            lines.append(f"  [{a.category_name}] {a.answer}")
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Dialogue                                                            #
# ------------------------------------------------------------------ #

class ElicitationDialogue:
    """
    Runs the Q&A elicitation loop.

    Usage (interactive):
        dialogue = ElicitationDialogue(max_questions=8)
        session  = await dialogue.run(requirement, report, mode="interactive")

    Usage (LLM — automated evaluation):
        session = await dialogue.run(requirement, report, mode="llm")

    Usage (silent — testing):
        session = await dialogue.run(requirement, report, mode="silent")
    """

    def __init__(self, max_questions: int = 10, use_rag: bool = True,
                 random_questions: bool = False):
        self.max_questions    = max_questions
        self.use_rag          = use_rag    # enrich questions with W1 knowledge base
        self.random_questions = random_questions  # C1 control: pick gaps at random,
        #                                            not by weight priority (tests RQ1)
        self._api_key      = _load_api_key()
        self._client       = None   # lazy Gemini client
        self._kb           = None   # lazy EcommerceKnowledgeBase (W1)
        # Token accounting (Gemini usage_metadata), read by ElicitationRunner
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_calls = 0

    def _record_usage(self, response) -> None:
        """Accumulate Gemini token usage from a response (best-effort)."""
        um = getattr(response, "usage_metadata", None)
        if um is None:
            return
        self.prompt_tokens     += getattr(um, "prompt_token_count", 0) or 0
        self.completion_tokens += getattr(um, "candidates_token_count", 0) or 0
        self.llm_calls         += 1

    # ---------------------------------------------------------------- #
    #  Public API                                                        #
    # ---------------------------------------------------------------- #

    async def run(
        self,
        requirement: str,
        report,
        mode: str = "interactive",
    ) -> ElicitationSession:
        """
        Run the elicitation dialogue and return a completed session.

        Args:
            requirement : original raw SRS text
            report      : CompletenessReport from W3
            mode        : "interactive" | "llm" | "silent"
        """
        prioritiser = QuestionPrioritiser()
        if self.random_questions:
            # C1 control condition: select max_questions gaps uniformly at random
            # instead of by weight priority — isolates the value of prioritisation.
            all_q     = prioritiser.prioritise(report)
            questions = random.sample(all_q, min(self.max_questions, len(all_q)))
        else:
            questions = prioritiser.top_n(report, self.max_questions)

        # W1 RAG enrichment: attach domain-knowledge hints to each question.
        # Skipped in silent mode (no questions are presented) and when the
        # --no-rag ablation is active.
        if self.use_rag and questions and mode != "silent":
            self._enrich_with_rag(questions)

        session = ElicitationSession(
            original_requirement=requirement,
            questions_asked=questions,
            answers=[],
            started_at=datetime.now().isoformat(),
            mode=mode,
        )

        if mode == "interactive":
            session.answers = self._run_interactive(questions)
        elif mode == "llm":
            session.answers = await self._run_llm(requirement, questions)
        elif mode == "silent":
            pass  # no answers collected; used in tests and dry-runs

        session.completed_at = datetime.now().isoformat()
        return session

    def run_sync(self, requirement: str, report, mode: str = "interactive") -> ElicitationSession:
        """Synchronous wrapper around run()."""
        return asyncio.run(self.run(requirement, report, mode=mode))

    # ---------------------------------------------------------------- #
    #  W1 RAG enrichment                                                 #
    # ---------------------------------------------------------------- #

    def _enrich_with_rag(self, questions: List[ElicitationQuestion]) -> None:
        """
        Query the W1 e-commerce knowledge base for each question and attach
        up to 2 domain-knowledge excerpts as rag_hints.  Any failure
        (chromadb missing, empty store, model download issues) degrades
        silently — the dialogue works without hints.
        """
        try:
            if self._kb is None:
                _kb_mod = _load(
                    _ELICITATION / "rag" / "knowledge_base.py", "knowledge_base"
                )
                self._kb = _kb_mod.EcommerceKnowledgeBase()
            for q in questions:
                docs = self._kb.query(
                    q.question, n_results=2, category_filter=q.category_name
                )
                q.rag_hints = [
                    d[:120] + ("…" if len(d) > 120 else "") for d in docs
                ]
        except Exception as exc:
            print(f"  [ElicitationDialogue] RAG enrichment unavailable ({exc})")

    # ---------------------------------------------------------------- #
    #  Interactive mode                                                  #
    # ---------------------------------------------------------------- #

    def _run_interactive(self, questions: List[ElicitationQuestion]) -> List[DialogueAnswer]:
        answers = []
        print(f"\n{'─'*55}")
        print(f" Elicitation: {len(questions)} question(s) to answer")
        print(f"{'─'*55}")

        for q in questions:
            print(f"\n{q.display()}")
            print(f"\n  Enter number(s) (e.g. '1' or '1,3') or free text:")
            raw = input("  > ").strip()
            answer_text, selected = self._parse_input(raw, q.suggestions)
            answers.append(DialogueAnswer(
                category_name=q.category_name,
                question=q.question,
                answer=answer_text,
                selected_suggestions=selected,
            ))
            print(f"  ✓ Recorded: {answer_text}")

        print(f"\n{'─'*55}")
        print(f" Elicitation complete — {len(answers)} answer(s) collected")
        print(f"{'─'*55}\n")
        return answers

    # ---------------------------------------------------------------- #
    #  LLM mode (automated evaluation)                                   #
    # ---------------------------------------------------------------- #

    async def _run_llm(
        self,
        requirement: str,
        questions: List[ElicitationQuestion],
    ) -> List[DialogueAnswer]:
        """
        Gemini 2.5 Flash acts as the product owner and answers each
        clarifying question based on the SRS context.
        Used for automated PURE-dataset evaluation runs (W7).
        """
        if not self._api_key:
            print("  [ElicitationDialogue] No API key — LLM mode unavailable.")
            return []

        answers = []
        for q in questions:
            raw = await self._call_gemini(requirement, q)
            answer_text, selected = self._parse_input(raw or "", q.suggestions)
            answers.append(DialogueAnswer(
                category_name=q.category_name,
                question=q.question,
                answer=answer_text,
                selected_suggestions=selected,
            ))
        return answers

    async def _call_gemini(self, requirement: str, q: ElicitationQuestion) -> Optional[str]:
        try:
            from google import genai
            from google.genai import types

            if self._client is None:
                self._client = genai.Client(api_key=self._api_key)

            options_text = "\n".join(
                f"  {i}. {s}" for i, s in enumerate(q.suggestions, 1)
            )
            hints_text = ""
            if q.rag_hints:
                hints_text = "\nDomain knowledge (for context only):\n" + "\n".join(
                    f"  - {h}" for h in q.rag_hints
                )
            prompt = _LLM_ANSWER_PROMPT.format(
                requirement=requirement,
                question=q.question,
                options=options_text,
                hints=hints_text,
            )

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                ),
            )
            self._record_usage(response)
            return response.text.strip()

        except Exception as exc:
            print(f"  [ElicitationDialogue] LLM call failed ({exc})")
            return None

    # ---------------------------------------------------------------- #
    #  Input parsing                                                     #
    # ---------------------------------------------------------------- #

    def _parse_input(
        self,
        raw: str,
        suggestions: List[str],
    ) -> tuple[str, List[str]]:
        """
        Parse user / LLM input into (answer_text, selected_suggestions).

        "1"      → first suggestion selected
        "1, 3"   → first and third suggestions selected
        "Custom" → free-text answer, no suggestion selected

        Rules:
        - Numbers are 1-based and must be within range.
        - If any token is out-of-range or non-numeric, treat whole input
          as free text.
        - Empty input → answer is empty string, no selections.
        """
        raw = raw.strip()
        if not raw:
            return ("", [])

        # Try to parse as one or more comma/space-separated numbers
        tokens = re.split(r"[,\s]+", raw)
        indices = []
        for t in tokens:
            t = t.strip()
            if not t:
                continue
            if not t.isdigit():
                # Contains non-numeric token → free text
                return (raw, [])
            idx = int(t)
            if idx < 1 or idx > len(suggestions):
                # Out of range → free text
                return (raw, [])
            indices.append(idx - 1)   # convert to 0-based

        if not indices:
            return (raw, [])

        selected = [suggestions[i] for i in indices]
        answer   = ", ".join(selected)
        return (answer, selected)


# ------------------------------------------------------------------ #
#  CLI entry point — interactive demo                                  #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Quick demo: run elicitation in silent mode on SRS_VAGUE
    _analyser_path = Path(__file__).parent.parent / "analyser" / "completeness_analyser.py"
    _parser_path   = Path(__file__).parent.parent / "parser"   / "srs_parser.py"

    analyser_mod   = _load(_analyser_path, "completeness_analyser")
    CompletenessAnalyser = analyser_mod.CompletenessAnalyser

    SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."
    SRS_RICH  = (
        "Build a B2C e-commerce platform where customers can register, "
        "login, browse a product catalog with search and filter, add items "
        "to their cart, and checkout using Stripe or PayPal. "
        "Admins can manage products, view orders, and issue refunds. "
        "The system should handle 5000 concurrent users with <2s response time. "
        "GDPR and PCI-DSS compliance are required."
    )

    analyser = CompletenessAnalyser()
    report   = analyser.analyse_text(SRS_VAGUE)

    prioritiser = QuestionPrioritiser()
    questions   = prioritiser.prioritise(report)

    print(f"\nSRS_VAGUE → {len(questions)} questions to ask")
    print(f"Critical:  {[q.category_name for q in questions if q.is_critical()]}")
    print(f"\nTop 5 questions:")
    for q in questions[:5]:
        print(f"\n  {q.display()}")

    print("\n" + "="*55)
    print("Running LLM mode on SRS_VAGUE ...")
    dialogue = ElicitationDialogue(max_questions=3)
    session  = dialogue.run_sync(SRS_VAGUE, report, mode="llm")
    print(session.summary())
    print("\nContext dict for W5:")
    ctx = session.to_context_dict()
    for cat, ans in ctx["clarifications"].items():
        print(f"  [{cat}] {ans}")
