"""
Metrics Logger (W6a)
---------------------
Records one row per RAMA evaluation run to a CSV file.

Each row captures:
  - Completeness score BEFORE elicitation  (pre_score,  Formula 1)
  - Completeness score AFTER  elicitation  (post_score, Formula 1)
  - Weighted scores (pre/post)
  - Questions asked / answers collected
  - Synthesis method used (llm | template)
  - Parse method (llm | fallback)
  - Wall-clock duration in seconds

The CSV at evaluation_logs/runs.csv is the primary data source for
thesis evaluation (W7-W8 ablation and baseline comparisons).

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Default log location (relative to project root)
DEFAULT_LOG_FILE = Path(__file__).parent.parent.parent.parent / "evaluation_logs" / "runs.csv"

# CSV column order
_CSV_FIELDS = [
    "run_id",
    "timestamp",
    "mode",
    "parse_method",
    "synthesis_method",
    "pre_score",
    "pre_weighted_score",
    "post_score",
    "post_weighted_score",
    "score_improvement",
    "questions_asked",
    "answers_collected",
    "critical_gaps_before",
    "critical_gaps_after",
    "duration_seconds",
    "original_srs_excerpt",
]


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class RunMetrics:
    """
    All measurable outputs of one end-to-end RAMA elicitation run.
    Written to CSV by MetricsLogger and read back for analysis.
    """
    run_id: str                     # UUID4 string
    timestamp: str                  # ISO-8601

    mode: str                       # "interactive" | "llm" | "silent"
    parse_method: str               # "llm" | "fallback"  (from SRSParser)
    synthesis_method: str           # "llm" | "template"  (from SRSSynthesiser)

    pre_score: float                # Formula 1 before elicitation
    pre_weighted_score: float       # Formula 2 before elicitation
    post_score: float               # Formula 1 after elicitation
    post_weighted_score: float      # Formula 2 after elicitation

    questions_asked: int
    answers_collected: int

    critical_gaps_before: int       # len(report.critical_gaps) pre-elicitation
    critical_gaps_after: int        # len(report.critical_gaps) post-elicitation

    duration_seconds: float         # wall-clock time for the full run

    original_srs_excerpt: str       # first 120 chars of original SRS

    @property
    def score_improvement(self) -> float:
        return round(self.post_score - self.pre_score, 4)

    def to_row(self) -> dict:
        """Flat dict with all CSV fields (including derived score_improvement)."""
        d = asdict(self)
        d["score_improvement"] = self.score_improvement
        return {k: d.get(k, "") for k in _CSV_FIELDS}

    @classmethod
    def from_row(cls, row: dict) -> "RunMetrics":
        """Reconstruct from a CSV row dict."""
        return cls(
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            mode=row["mode"],
            parse_method=row["parse_method"],
            synthesis_method=row["synthesis_method"],
            pre_score=float(row["pre_score"]),
            pre_weighted_score=float(row["pre_weighted_score"]),
            post_score=float(row["post_score"]),
            post_weighted_score=float(row["post_weighted_score"]),
            questions_asked=int(row["questions_asked"]),
            answers_collected=int(row["answers_collected"]),
            critical_gaps_before=int(row["critical_gaps_before"]),
            critical_gaps_after=int(row["critical_gaps_after"]),
            duration_seconds=float(row["duration_seconds"]),
            original_srs_excerpt=row["original_srs_excerpt"],
        )

    @staticmethod
    def make_run_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat()


# ------------------------------------------------------------------ #
#  Logger                                                              #
# ------------------------------------------------------------------ #

class MetricsLogger:
    """
    Append-only CSV logger for RAMA evaluation runs.

    Usage:
        logger  = MetricsLogger()
        logger.log(metrics)           # appends one row
        all_runs = logger.load_all()  # reads back all rows
        stats    = logger.summary_stats()
    """

    def __init__(self, log_file: Path = DEFAULT_LOG_FILE):
        self.log_file = Path(log_file)
        self._ensure_directory()

    # ---------------------------------------------------------------- #
    #  Write                                                             #
    # ---------------------------------------------------------------- #

    def log(self, metrics: RunMetrics) -> None:
        """Append one RunMetrics row to the CSV file."""
        write_header = not self.log_file.exists()
        with open(self.log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(metrics.to_row())

    # ---------------------------------------------------------------- #
    #  Read                                                              #
    # ---------------------------------------------------------------- #

    def load_all(self) -> List[RunMetrics]:
        """Load every row from the CSV file."""
        if not self.log_file.exists():
            return []
        with open(self.log_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [RunMetrics.from_row(row) for row in reader]

    def load_last(self, n: int = 10) -> List[RunMetrics]:
        """Return the N most recent runs."""
        return self.load_all()[-n:]

    # ---------------------------------------------------------------- #
    #  Statistics                                                        #
    # ---------------------------------------------------------------- #

    def summary_stats(self) -> dict:
        """
        Compute summary statistics across all logged runs.
        Returns empty dict if no runs have been logged yet.
        """
        runs = self.load_all()
        if not runs:
            return {}

        n = len(runs)

        def _mean(values):
            return round(sum(values) / len(values), 4)

        def _std(values):
            m = _mean(values)
            variance = sum((v - m) ** 2 for v in values) / len(values)
            return round(variance ** 0.5, 4)

        pre_scores  = [r.pre_score for r in runs]
        post_scores = [r.post_score for r in runs]
        improvements = [r.score_improvement for r in runs]
        q_asked     = [r.questions_asked for r in runs]

        return {
            "run_count":              n,
            "mean_pre_score":         _mean(pre_scores),
            "mean_post_score":        _mean(post_scores),
            "mean_improvement":       _mean(improvements),
            "std_improvement":        _std(improvements),
            "mean_questions_asked":   _mean(q_asked),
            "max_improvement":        round(max(improvements), 4),
            "min_improvement":        round(min(improvements), 4),
            "pct_improved":           round(
                sum(1 for i in improvements if i > 0) / n * 100, 1
            ),
        }

    def clear(self) -> None:
        """Delete the CSV file (used in tests)."""
        if self.log_file.exists():
            self.log_file.unlink()

    # ---------------------------------------------------------------- #
    #  Internals                                                         #
    # ---------------------------------------------------------------- #

    def _ensure_directory(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
