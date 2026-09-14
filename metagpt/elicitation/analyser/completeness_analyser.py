"""
Completeness Analyser (W3)
---------------------------
Consumes a ParsedSRS (W2 output) and scores it against the
24-category ECOMMERCE_SCHEMA, producing a CompletenessReport.

Scoring uses two signals:
  Signal 1 — parsed.schema_hints   : keyword hits on raw_text (W2 Pass 1)
  Signal 2 — parsed.combined_text(): keyword scan on richer text that
              includes LLM-extracted actors/entities/intents (W2 Pass 2)

Formulas:
  raw_score      = covered_count / 24              (Formula 1, thesis §3.2)
  weighted_score = sum(covered weights) / 58       (Formula 2, thesis §3.2)

Output CompletenessReport feeds W4 (QuestionPrioritiser):
  critical_gaps + gap_details → prioritised question list.

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# ------------------------------------------------------------------ #
#  Module imports — bypass metagpt.__init__ via importlib.util        #
# ------------------------------------------------------------------ #
import importlib.util as _ilu

_SCHEMA_PATH  = Path(__file__).parent.parent / "schema"  / "ecommerce_schema.py"
_PARSER_PATH  = Path(__file__).parent.parent / "parser"  / "srs_parser.py"

def _load(path: Path, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_schema_mod = _load(_SCHEMA_PATH, "ecommerce_schema")
ECOMMERCE_SCHEMA    = _schema_mod.ECOMMERCE_SCHEMA
_total_categories   = _schema_mod.total_categories      # → 24
_total_weight       = _schema_mod.total_weight          # → 58
_get_by_group       = _schema_mod.get_by_group


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

_LEVEL_THRESHOLDS = [
    (0.9, "COMPLETE"),
    (0.6, "GOOD"),
    (0.3, "PARTIAL"),
    (0.0, "POOR"),
]


@dataclass
class CompletenessReport:
    """
    Full coverage report for one SRS document.
    Produced by CompletenessAnalyser and consumed by W4 QuestionPrioritiser.
    """
    raw_score: float                        # covered_count / 24  (Formula 1)
    weighted_score: float                   # sum(covered weights) / 58
    covered_categories: List[str]           # category names with coverage = True
    missing_categories: List[str]           # category names with coverage = False
    critical_gaps: List[str]                # missing categories with weight == 3
    gap_details: Dict[str, Any]             # {missing_cat_name: SchemaCategory}
    per_group_coverage: Dict[str, float]    # {"FUNCTIONAL": 0.58, ...}
    coverage_map: Dict[str, bool]           # {category_name: covered}

    def has_critical_gaps(self) -> bool:
        """True when at least one weight-3 category is not covered."""
        return len(self.critical_gaps) > 0

    def coverage_level(self) -> str:
        """Qualitative label for the raw score."""
        for threshold, label in _LEVEL_THRESHOLDS:
            if self.raw_score >= threshold:
                return label
        return "POOR"

    def summary(self) -> str:
        lines = [
            f"Raw score        : {self.raw_score:.2f}  ({len(self.covered_categories)}/{_total_categories()} categories)",
            f"Weighted score   : {self.weighted_score:.2f}",
            f"Coverage level   : {self.coverage_level()}",
            f"Critical gaps    : {self.critical_gaps or 'none'}",
            f"Missing          : {self.missing_categories}",
            "Per-group        :",
        ]
        for group, score in self.per_group_coverage.items():
            lines.append(f"  {group:<20}: {score:.2f}")
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Analyser                                                            #
# ------------------------------------------------------------------ #

class CompletenessAnalyser:
    """
    Scores a ParsedSRS against the ECOMMERCE_SCHEMA.

    Usage:
        analyser = CompletenessAnalyser()
        report   = analyser.analyse(parsed_srs)      # ParsedSRS → CompletenessReport
        report   = analyser.analyse_text("Build...")  # raw text → CompletenessReport
    """

    def analyse(self, parsed) -> CompletenessReport:
        """
        Score a ParsedSRS and return a CompletenessReport.

        Coverage for a category is True when:
          - parsed.schema_hints[cat] is True  (W2 Pass 1 keyword hit on raw_text)
          OR
          - any schema keyword appears in parsed.combined_text()
            (catches LLM-extracted content that adds new coverage)
        """
        combined = parsed.combined_text()
        hints    = parsed.schema_hints or {}

        # Build coverage_map using union of both signals
        coverage_map: Dict[str, bool] = {}
        for cat_name, cat in ECOMMERCE_SCHEMA.items():
            hint_signal     = hints.get(cat_name, False)
            combined_signal = any(kw.lower() in combined for kw in cat.keywords)
            coverage_map[cat_name] = hint_signal or combined_signal

        covered  = [k for k, v in coverage_map.items() if v]
        missing  = [k for k, v in coverage_map.items() if not v]

        # Formula 1: raw score
        total_cats = _total_categories()
        raw_score  = len(covered) / total_cats if total_cats > 0 else 0.0

        # Formula 2: weighted score
        total_wt         = _total_weight()
        weighted_covered = sum(ECOMMERCE_SCHEMA[k].weight for k in covered)
        weighted_score   = weighted_covered / total_wt if total_wt > 0 else 0.0

        # Gap analysis
        critical_gaps = [k for k in missing if ECOMMERCE_SCHEMA[k].weight == 3]
        gap_details   = {k: ECOMMERCE_SCHEMA[k] for k in missing}

        # Per-group breakdown
        per_group: Dict[str, float] = {}
        for group in ("FUNCTIONAL", "NON_FUNCTIONAL", "DOMAIN"):
            group_cats    = list(_get_by_group(group).keys())
            group_covered = sum(1 for k in group_cats if coverage_map.get(k, False))
            per_group[group] = group_covered / len(group_cats) if group_cats else 0.0

        return CompletenessReport(
            raw_score=raw_score,
            weighted_score=weighted_score,
            covered_categories=covered,
            missing_categories=missing,
            critical_gaps=critical_gaps,
            gap_details=gap_details,
            per_group_coverage=per_group,
            coverage_map=coverage_map,
        )

    def analyse_text(self, text: str) -> CompletenessReport:
        """
        Convenience method: parse raw text with the fallback parser then analyse.
        No LLM required — suitable for batch evaluation and tests.
        """
        _parser_mod = _load(_PARSER_PATH, "srs_parser")
        parser      = _parser_mod.SRSParser()
        parsed      = parser.parse_fallback(text)
        return self.analyse(parsed)


# ------------------------------------------------------------------ #
#  CLI entry point — quick sanity check                                #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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

    analyser = CompletenessAnalyser()

    for label, srs in [("SRS_RICH", SRS_RICH), ("SRS_VAGUE", SRS_VAGUE)]:
        print(f"\n{'='*55}")
        print(f" {label}")
        print(f"{'='*55}")
        report = analyser.analyse_text(srs)
        print(report.summary())
