"""
Results Analyser (W8)
----------------------
Computes aggregate statistics over BatchResult lists and produces
formatted tables for the thesis evaluation chapter.

Key outputs:
  AggregateStats  — mean/std/median scores, coverage distribution,
                    gap reduction, improvement rate
  compare()       — side-by-side ablation table (e.g. silent vs. llm)
  format_summary()— ASCII table for thesis chapter copy-paste

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ------------------------------------------------------------------ #
#  Module loading                                                      #
# ------------------------------------------------------------------ #
import importlib.util as _ilu

_BASE = Path(__file__).parent


def _load(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_batch_mod   = _load(_BASE / "batch_runner.py",  "batch_runner")
BatchResult  = _batch_mod.BatchResult

_COVERAGE_LEVELS = ["POOR", "PARTIAL", "GOOD", "COMPLETE"]


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return round(variance ** 0.5, 4)


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    if n % 2 == 0:
        return round((sorted_v[mid - 1] + sorted_v[mid]) / 2, 4)
    return round(sorted_v[mid], 4)


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class AggregateStats:
    """
    Summary statistics for a set of BatchResult records.
    All float fields are rounded to 4 decimal places.
    """
    n_docs:  int
    n_errors: int

    mean_pre_score:   float
    mean_post_score:  float
    mean_improvement: float
    std_improvement:  float
    median_improvement: float

    min_pre_score: float
    max_pre_score: float
    min_post_score: float
    max_post_score: float

    docs_improved:   int    # score_improvement > 0
    docs_unchanged:  int    # score_improvement == 0
    docs_regressed:  int    # score_improvement < 0
    pct_improved:    float  # docs_improved / n_docs * 100

    mean_critical_gaps_before: float
    mean_critical_gaps_after:  float
    mean_gap_reduction:        float  # before - after

    mean_weighted_pre:  float
    mean_weighted_post: float

    pre_distribution:  Dict[str, int]   # {POOR: n, PARTIAL: n, ...}
    post_distribution: Dict[str, int]

    mean_duration_seconds: float

    def improvement_pct(self) -> float:
        """Relative score improvement as a percentage."""
        if self.mean_pre_score == 0:
            return 0.0
        return round((self.mean_improvement / self.mean_pre_score) * 100, 1)


# ------------------------------------------------------------------ #
#  Analyser                                                            #
# ------------------------------------------------------------------ #

class ResultsAnalyser:
    """
    Analyses BatchResult lists and produces thesis evaluation artefacts.

    Usage:
        analyser = ResultsAnalyser()
        stats    = analyser.analyse(results)
        print(analyser.format_summary(stats))
        print(analyser.compare(silent_results, llm_results))
    """

    # ---------------------------------------------------------------- #
    #  Core analysis                                                    #
    # ---------------------------------------------------------------- #

    def analyse(self, results: List[BatchResult]) -> AggregateStats:
        """Compute AggregateStats from a list of BatchResult objects."""
        if not results:
            return self._empty_stats()

        ok = [r for r in results if not r.error]
        n_errors = len(results) - len(ok)

        if not ok:
            return self._empty_stats(n_docs=len(results), n_errors=n_errors)

        pre_scores   = [r.pre_score   for r in ok]
        post_scores  = [r.post_score  for r in ok]
        improvements = [r.score_improvement for r in ok]

        docs_improved  = sum(1 for i in improvements if i > 0)
        docs_unchanged = sum(1 for i in improvements if i == 0)
        docs_regressed = sum(1 for i in improvements if i < 0)
        n = len(ok)

        gap_before = [r.critical_gaps_before for r in ok]
        gap_after  = [r.critical_gaps_after  for r in ok]

        pre_dist  = self._distribution([r.pre_coverage_level  for r in ok])
        post_dist = self._distribution([r.post_coverage_level for r in ok])

        return AggregateStats(
            n_docs=len(results),
            n_errors=n_errors,
            mean_pre_score=_mean(pre_scores),
            mean_post_score=_mean(post_scores),
            mean_improvement=_mean(improvements),
            std_improvement=_std(improvements),
            median_improvement=_median(improvements),
            min_pre_score=round(min(pre_scores), 4),
            max_pre_score=round(max(pre_scores), 4),
            min_post_score=round(min(post_scores), 4),
            max_post_score=round(max(post_scores), 4),
            docs_improved=docs_improved,
            docs_unchanged=docs_unchanged,
            docs_regressed=docs_regressed,
            pct_improved=round(docs_improved / n * 100, 1),
            mean_critical_gaps_before=_mean([float(g) for g in gap_before]),
            mean_critical_gaps_after=_mean([float(g) for g in gap_after]),
            mean_gap_reduction=round(
                _mean([float(g) for g in gap_before]) -
                _mean([float(g) for g in gap_after]), 4
            ),
            mean_weighted_pre=_mean([r.pre_weighted_score  for r in ok]),
            mean_weighted_post=_mean([r.post_weighted_score for r in ok]),
            pre_distribution=pre_dist,
            post_distribution=post_dist,
            mean_duration_seconds=_mean([r.duration_seconds for r in ok]),
        )

    # ---------------------------------------------------------------- #
    #  Formatting                                                       #
    # ---------------------------------------------------------------- #

    def format_summary(self, stats: AggregateStats, label: str = "Run") -> str:
        """
        Render AggregateStats as a formatted ASCII table.
        Suitable for copy-paste into thesis chapters or terminal output.
        """
        sep = "=" * 62
        lines = [
            sep,
            f" RAMA Evaluation Summary — {label}",
            sep,
            f"  Documents          : {stats.n_docs}  "
            f"(errors: {stats.n_errors})",
            "",
            "  Completeness Scores (Formula 1, scale 0–1):",
            f"    Mean pre-score   : {stats.mean_pre_score:.4f}",
            f"    Mean post-score  : {stats.mean_post_score:.4f}",
            f"    Mean improvement : {stats.mean_improvement:+.4f}  "
            f"({stats.improvement_pct():+.1f}% relative)",
            f"    Std  improvement : {stats.std_improvement:.4f}",
            f"    Median improvement: {stats.median_improvement:+.4f}",
            f"    Range (pre)      : [{stats.min_pre_score:.4f}, "
            f"{stats.max_pre_score:.4f}]",
            "",
            "  Weighted Scores (Formula 2, scale 0–1):",
            f"    Mean weighted pre : {stats.mean_weighted_pre:.4f}",
            f"    Mean weighted post: {stats.mean_weighted_post:.4f}",
            "",
            "  Gap Reduction:",
            f"    Mean critical gaps (pre)  : {stats.mean_critical_gaps_before:.2f}",
            f"    Mean critical gaps (post) : {stats.mean_critical_gaps_after:.2f}",
            f"    Mean gap reduction        : {stats.mean_gap_reduction:.2f}",
            "",
            "  Improvement Rate:",
            f"    Docs improved   : {stats.docs_improved}  "
            f"({stats.pct_improved:.1f}%)",
            f"    Docs unchanged  : {stats.docs_unchanged}",
            f"    Docs regressed  : {stats.docs_regressed}",
            "",
            "  Coverage Distribution (pre → post):",
        ]

        for level in _COVERAGE_LEVELS:
            pre_n  = stats.pre_distribution.get(level, 0)
            post_n = stats.post_distribution.get(level, 0)
            n_ok   = stats.n_docs - stats.n_errors
            pre_pct  = f"{pre_n  / max(n_ok, 1) * 100:.0f}%"
            post_pct = f"{post_n / max(n_ok, 1) * 100:.0f}%"
            lines.append(
                f"    {level:<10} : {pre_n:>3} ({pre_pct:>4}) → "
                f"{post_n:>3} ({post_pct:>4})"
            )

        lines += [
            "",
            f"  Mean run duration  : {stats.mean_duration_seconds:.1f}s",
            sep,
        ]
        return "\n".join(lines)

    def compare(
        self,
        results_a: List[BatchResult],
        results_b: List[BatchResult],
        label_a: str = "Condition A",
        label_b: str = "Condition B",
    ) -> str:
        """
        Side-by-side ablation comparison table.
        Typical use: compare(silent_results, llm_results, "Silent", "LLM").
        """
        stats_a = self.analyse(results_a)
        stats_b = self.analyse(results_b)

        col = 22
        sep = "=" * (col * 3 + 4)
        hdr = f"{'Metric':<{col}}  {label_a:<{col}}  {label_b:<{col}}"

        def row(label: str, val_a, val_b, fmt=".4f") -> str:
            fa = format(val_a, fmt) if isinstance(val_a, float) else str(val_a)
            fb = format(val_b, fmt) if isinstance(val_b, float) else str(val_b)
            return f"  {label:<{col-2}}  {fa:<{col}}  {fb:<{col}}"

        lines = [
            sep,
            f" RAMA Ablation Comparison: {label_a} vs {label_b}",
            sep,
            hdr,
            "-" * (col * 3 + 4),
            row("N docs",           stats_a.n_docs,              stats_b.n_docs,              "d"),
            row("Mean pre-score",   stats_a.mean_pre_score,      stats_b.mean_pre_score),
            row("Mean post-score",  stats_a.mean_post_score,     stats_b.mean_post_score),
            row("Mean improvement", stats_a.mean_improvement,    stats_b.mean_improvement),
            row("Std improvement",  stats_a.std_improvement,     stats_b.std_improvement),
            row("Median improv.",   stats_a.median_improvement,  stats_b.median_improvement),
            row("% improved",       stats_a.pct_improved,        stats_b.pct_improved,        ".1f"),
            row("Mean gaps before", stats_a.mean_critical_gaps_before, stats_b.mean_critical_gaps_before, ".2f"),
            row("Mean gaps after",  stats_a.mean_critical_gaps_after,  stats_b.mean_critical_gaps_after,  ".2f"),
            row("Mean gap reduc.",  stats_a.mean_gap_reduction,  stats_b.mean_gap_reduction,  ".2f"),
            row("Mean wtd pre",     stats_a.mean_weighted_pre,   stats_b.mean_weighted_pre),
            row("Mean wtd post",    stats_a.mean_weighted_post,  stats_b.mean_weighted_post),
            row("Mean duration(s)", stats_a.mean_duration_seconds, stats_b.mean_duration_seconds, ".1f"),
            sep,
        ]
        return "\n".join(lines)

    # ---------------------------------------------------------------- #
    #  Utility                                                          #
    # ---------------------------------------------------------------- #

    def coverage_distribution(
        self,
        results: List[BatchResult],
        use_pre: bool = True,
    ) -> Dict[str, int]:
        """Return {POOR: n, PARTIAL: n, GOOD: n, COMPLETE: n}."""
        levels = [
            r.pre_coverage_level if use_pre else r.post_coverage_level
            for r in results if not r.error
        ]
        return self._distribution(levels)

    @staticmethod
    def filter_by_mode(
        results: List[BatchResult],
        mode: str,
    ) -> List[BatchResult]:
        return [r for r in results if r.mode == mode]

    @staticmethod
    def filter_successful(results: List[BatchResult]) -> List[BatchResult]:
        return [r for r in results if not r.error]

    @staticmethod
    def filter_by_domain(
        results: List[BatchResult],
        domain: str,
    ) -> List[BatchResult]:
        return [r for r in results if r.domain == domain]

    # ---------------------------------------------------------------- #
    #  Internals                                                        #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _distribution(levels: List[str]) -> Dict[str, int]:
        dist = {lvl: 0 for lvl in _COVERAGE_LEVELS}
        for lvl in levels:
            if lvl in dist:
                dist[lvl] += 1
        return dist

    @staticmethod
    def _empty_stats(n_docs: int = 0, n_errors: int = 0) -> AggregateStats:
        return AggregateStats(
            n_docs=n_docs, n_errors=n_errors,
            mean_pre_score=0.0, mean_post_score=0.0,
            mean_improvement=0.0, std_improvement=0.0,
            median_improvement=0.0,
            min_pre_score=0.0, max_pre_score=0.0,
            min_post_score=0.0, max_post_score=0.0,
            docs_improved=0, docs_unchanged=0, docs_regressed=0,
            pct_improved=0.0,
            mean_critical_gaps_before=0.0,
            mean_critical_gaps_after=0.0,
            mean_gap_reduction=0.0,
            mean_weighted_pre=0.0, mean_weighted_post=0.0,
            pre_distribution={lvl: 0 for lvl in _COVERAGE_LEVELS},
            post_distribution={lvl: 0 for lvl in _COVERAGE_LEVELS},
            mean_duration_seconds=0.0,
        )


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = _batch_mod.BatchRunner.load_results()
    if not results:
        print("No batch results found. Run run_pure_baseline.py first.")
        sys.exit(1)

    analyser = ResultsAnalyser()
    stats    = analyser.analyse(results)
    print(analyser.format_summary(stats, label="PURE Baseline"))

    silent_r = ResultsAnalyser.filter_by_mode(results, "silent")
    llm_r    = ResultsAnalyser.filter_by_mode(results, "llm")
    if silent_r and llm_r:
        print()
        print(analyser.compare(silent_r, llm_r, "Silent (Baseline)", "LLM (RAMA)"))
