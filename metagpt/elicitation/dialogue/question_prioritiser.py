"""
Question Prioritiser (W4a)
---------------------------
Converts a CompletenessReport (W3 output) into a ranked list of
ElicitationQuestion objects ready for the dialogue loop.

Priority ordering:
  1. Weight-3 (critical) categories → asked first
  2. Weight-2 (important) categories → asked second
  3. Within the same weight: FUNCTIONAL > NON_FUNCTIONAL > DOMAIN
  4. Within the same weight + group: schema insertion order preserved

Output feeds ElicitationDialogue (W4b), which presents questions to
the user / LLM and collects answers that W5 uses to synthesise the
enriched SRS.

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ------------------------------------------------------------------ #
#  Schema import — bypass metagpt.__init__ via importlib.util         #
# ------------------------------------------------------------------ #
import importlib.util as _ilu

_SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "ecommerce_schema.py"


def _load(path: Path, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_schema_mod      = _load(_SCHEMA_PATH, "ecommerce_schema")
ECOMMERCE_SCHEMA = _schema_mod.ECOMMERCE_SCHEMA

# Group sort order: FUNCTIONAL is most user-visible, so ask those first
_GROUP_ORDER = {"FUNCTIONAL": 0, "NON_FUNCTIONAL": 1, "DOMAIN": 2}


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class ElicitationQuestion:
    """
    A single clarifying question derived from a missing schema category.

    Fields produced by QuestionPrioritiser and consumed by
    ElicitationDialogue to drive the Q&A session.
    """
    category_name: str          # matches ECOMMERCE_SCHEMA key
    question: str               # SchemaCategory.question text
    suggestions: List[str]      # SchemaCategory.suggestions (selectable options)
    weight: int                 # 3=critical, 2=important, 1=optional
    group: str                  # FUNCTIONAL | NON_FUNCTIONAL | DOMAIN
    priority: int = 0           # 1 = ask first; set by prioritise()
    rag_hints: List[str] = field(default_factory=list)
    # ↑ W1 knowledge-base excerpts added by ElicitationDialogue when RAG
    #   enrichment is enabled; shown as domain context, not selectable options

    def is_critical(self) -> bool:
        return self.weight == 3

    def display(self) -> str:
        """Formatted question block for terminal output."""
        lines = [f"[Q{self.priority}] {self.question}"]
        for i, s in enumerate(self.suggestions, 1):
            lines.append(f"  {i}. {s}")
        for h in self.rag_hints:
            lines.append(f"  (domain hint) {h}")
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Prioritiser                                                         #
# ------------------------------------------------------------------ #

class QuestionPrioritiser:
    """
    Converts a CompletenessReport into a sorted list of
    ElicitationQuestion objects.

    Usage:
        prioritiser = QuestionPrioritiser()
        questions   = prioritiser.prioritise(report)
        critical    = prioritiser.critical_questions(report)
        top5        = prioritiser.top_n(report, 5)
    """

    def prioritise(self, report) -> List[ElicitationQuestion]:
        """
        Return all missing categories as ElicitationQuestion objects,
        sorted by (weight DESC, group order ASC).
        """
        questions: List[ElicitationQuestion] = []

        for cat_name in report.missing_categories:
            cat_obj = report.gap_details.get(cat_name)
            if cat_obj is None:
                continue
            questions.append(ElicitationQuestion(
                category_name=cat_name,
                question=cat_obj.question,
                suggestions=list(cat_obj.suggestions),
                weight=cat_obj.weight,
                group=cat_obj.group,
                priority=0,
            ))

        # Primary sort: weight descending (3 → 2 → 1)
        # Secondary sort: group order (FUNCTIONAL → NON_FUNCTIONAL → DOMAIN)
        questions.sort(key=lambda q: (-q.weight, _GROUP_ORDER.get(q.group, 99)))

        # Assign 1-based sequential priority
        for i, q in enumerate(questions):
            q.priority = i + 1

        return questions

    def critical_questions(self, report) -> List[ElicitationQuestion]:
        """Only weight-3 questions, in priority order."""
        return [q for q in self.prioritise(report) if q.weight == 3]

    def top_n(self, report, n: int) -> List[ElicitationQuestion]:
        """Top N questions by priority (respects the weight/group sort)."""
        return self.prioritise(report)[:n]

    def questions_by_group(self, report) -> dict:
        """
        Return questions grouped by schema group.
        Useful for structured reporting.
        """
        result = {"FUNCTIONAL": [], "NON_FUNCTIONAL": [], "DOMAIN": []}
        for q in self.prioritise(report):
            result.setdefault(q.group, []).append(q)
        return result
