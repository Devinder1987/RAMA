"""
Batch Runner (W7b)
-------------------
Runs the RAMA ElicitationRunner over a list of PURESample documents
and aggregates the results into a CSV file for thesis evaluation.

Typical usage:
  from metagpt.elicitation.evaluation.pure_dataset import PUREDatasetLoader
  from metagpt.elicitation.evaluation.batch_runner  import BatchRunner

  samples = PUREDatasetLoader.load_builtin()
  runner  = BatchRunner(mode="silent")          # baseline (no dialogue)
  results = runner.run_dataset(samples)
  runner.save_results(results)

  runner2 = BatchRunner(mode="llm")             # full RAMA elicitation
  results2 = runner2.run_dataset(samples)
  runner2.save_results(results2, suffix="_llm")

Output:
  evaluation_logs/batch_results.csv             (silent baseline)
  evaluation_logs/batch_results_llm.csv         (LLM elicitation)

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import csv
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ------------------------------------------------------------------ #
#  Module loading                                                      #
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


_runner_mod   = _load(_BASE / "elicitation_runner.py", "elicitation_runner")
_dataset_mod  = _load(_BASE / "pure_dataset.py",       "pure_dataset")

ElicitationRunner = _runner_mod.ElicitationRunner
PURESample        = _dataset_mod.PURESample

# Dedicated metrics log for batch runs (separate from individual runs.csv)
_BATCH_LOG     = _BASE.parent.parent.parent / "evaluation_logs" / "batch_runs.csv"
_RESULTS_DIR   = _BASE.parent.parent.parent / "evaluation_logs"


# ------------------------------------------------------------------ #
#  CSV schema                                                          #
# ------------------------------------------------------------------ #

_BATCH_CSV_FIELDS = [
    "batch_id",
    "doc_id", "domain", "word_count", "source",
    "run_id", "timestamp", "mode",
    "parse_method", "synthesis_method",
    "pre_score", "pre_weighted_score",
    "post_score", "post_weighted_score",
    "score_improvement",
    "pre_coverage_level", "post_coverage_level",
    "critical_gaps_before", "critical_gaps_after",
    "questions_asked", "answers_collected",
    "duration_seconds", "error",
]


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class BatchResult:
    """
    Evaluation outcome for one PURESample through the RAMA pipeline.
    Extends RunMetrics with per-document fields (doc_id, domain, etc.)
    for thesis analysis.
    """
    batch_id:   str    # shared UUID for all results in one batch run
    doc_id:     str
    domain:     str
    word_count: int
    source:     str

    # from RunMetrics
    run_id:           str
    timestamp:        str
    mode:             str
    parse_method:     str
    synthesis_method: str

    pre_score:          float
    pre_weighted_score: float
    post_score:         float
    post_weighted_score: float
    score_improvement:  float   # post_score - pre_score

    pre_coverage_level:  str   # POOR / PARTIAL / GOOD / COMPLETE
    post_coverage_level: str

    critical_gaps_before: int
    critical_gaps_after:  int
    questions_asked:      int
    answers_collected:    int
    duration_seconds:     float

    error: str = ""    # non-empty if the pipeline raised an exception

    # ---------------------------------------------------------------- #

    def to_row(self) -> dict:
        return {
            "batch_id":            self.batch_id,
            "doc_id":              self.doc_id,
            "domain":              self.domain,
            "word_count":          self.word_count,
            "source":              self.source,
            "run_id":              self.run_id,
            "timestamp":           self.timestamp,
            "mode":                self.mode,
            "parse_method":        self.parse_method,
            "synthesis_method":    self.synthesis_method,
            "pre_score":           self.pre_score,
            "pre_weighted_score":  self.pre_weighted_score,
            "post_score":          self.post_score,
            "post_weighted_score": self.post_weighted_score,
            "score_improvement":   self.score_improvement,
            "pre_coverage_level":  self.pre_coverage_level,
            "post_coverage_level": self.post_coverage_level,
            "critical_gaps_before": self.critical_gaps_before,
            "critical_gaps_after":  self.critical_gaps_after,
            "questions_asked":     self.questions_asked,
            "answers_collected":   self.answers_collected,
            "duration_seconds":    self.duration_seconds,
            "error":               self.error,
        }

    @classmethod
    def from_row(cls, row: dict) -> "BatchResult":
        return cls(
            batch_id=row["batch_id"],
            doc_id=row["doc_id"],
            domain=row["domain"],
            word_count=int(row["word_count"]),
            source=row["source"],
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            mode=row["mode"],
            parse_method=row["parse_method"],
            synthesis_method=row["synthesis_method"],
            pre_score=float(row["pre_score"]),
            pre_weighted_score=float(row["pre_weighted_score"]),
            post_score=float(row["post_score"]),
            post_weighted_score=float(row["post_weighted_score"]),
            score_improvement=float(row["score_improvement"]),
            pre_coverage_level=row["pre_coverage_level"],
            post_coverage_level=row["post_coverage_level"],
            critical_gaps_before=int(row["critical_gaps_before"]),
            critical_gaps_after=int(row["critical_gaps_after"]),
            questions_asked=int(row["questions_asked"]),
            answers_collected=int(row["answers_collected"]),
            duration_seconds=float(row["duration_seconds"]),
            error=row.get("error", ""),
        )

    @staticmethod
    def make_batch_id() -> str:
        return str(uuid.uuid4())


# ------------------------------------------------------------------ #
#  Batch Runner                                                        #
# ------------------------------------------------------------------ #

class BatchRunner:
    """
    Runs ElicitationRunner over a list of PURESample documents.

    Args:
        mode          : "silent" | "llm" | "interactive"
        max_questions : cap on W4 questions per document
        verbose       : print progress to stdout

    One ElicitationRunner instance is reused across all documents
    (avoids re-initialising models for every sample).
    """

    def __init__(
        self,
        mode: str = "silent",
        max_questions: int = 10,
        verbose: bool = True,
        use_llm_parse: bool = True,
        use_rag: bool = True,
        use_llm_synthesis: bool = True,
        random_questions: bool = False,
    ):
        self.mode          = mode
        self.max_questions = max_questions
        self.verbose       = verbose
        # Use a dedicated log file so batch runs don't pollute runs.csv
        self._runner = ElicitationRunner(
            mode=mode,
            max_questions=max_questions,
            log_file=_BATCH_LOG,
            use_llm_parse=use_llm_parse,
            use_rag=use_rag,
            use_llm_synthesis=use_llm_synthesis,
            random_questions=random_questions,
        )

    # ---------------------------------------------------------------- #
    #  Core                                                             #
    # ---------------------------------------------------------------- #

    def run_one(self, sample: PURESample, batch_id: str) -> BatchResult:
        """
        Run the full RAMA pipeline on a single PURESample.
        Exceptions are caught and recorded in BatchResult.error.
        """
        t0 = time.perf_counter()
        try:
            result = self._runner.run_sync(sample.raw_text)
            duration = round(time.perf_counter() - t0, 2)

            return BatchResult(
                batch_id=batch_id,
                doc_id=sample.doc_id,
                domain=sample.domain,
                word_count=sample.word_count,
                source=sample.source,
                run_id=result.metrics.run_id,
                timestamp=result.metrics.timestamp,
                mode=result.metrics.mode,
                parse_method=result.metrics.parse_method,
                synthesis_method=result.metrics.synthesis_method,
                pre_score=result.metrics.pre_score,
                pre_weighted_score=result.metrics.pre_weighted_score,
                post_score=result.metrics.post_score,
                post_weighted_score=result.metrics.post_weighted_score,
                score_improvement=result.score_improvement,
                pre_coverage_level=result.pre_report.coverage_level(),
                post_coverage_level=result.post_report.coverage_level(),
                critical_gaps_before=result.metrics.critical_gaps_before,
                critical_gaps_after=result.metrics.critical_gaps_after,
                questions_asked=result.metrics.questions_asked,
                answers_collected=result.metrics.answers_collected,
                duration_seconds=duration,
                error="",
            )

        except Exception as exc:
            duration = round(time.perf_counter() - t0, 2)
            err_msg  = f"{type(exc).__name__}: {exc}"
            if self.verbose:
                print(f"  [BatchRunner] ERROR on {sample.doc_id}: {err_msg}")
            return BatchResult(
                batch_id=batch_id,
                doc_id=sample.doc_id,
                domain=sample.domain,
                word_count=sample.word_count,
                source=sample.source,
                run_id="",
                timestamp=datetime.now().isoformat(),
                mode=self.mode,
                parse_method="",
                synthesis_method="",
                pre_score=0.0,
                pre_weighted_score=0.0,
                post_score=0.0,
                post_weighted_score=0.0,
                score_improvement=0.0,
                pre_coverage_level="POOR",
                post_coverage_level="POOR",
                critical_gaps_before=0,
                critical_gaps_after=0,
                questions_asked=0,
                answers_collected=0,
                duration_seconds=duration,
                error=err_msg,
            )

    def run_dataset(self, samples: List[PURESample]) -> List["BatchResult"]:
        """
        Run all samples sequentially.  Returns one BatchResult per sample.
        Failed samples produce a BatchResult with error set (not skipped).
        """
        batch_id = BatchResult.make_batch_id()
        results: List[BatchResult] = []

        if self.verbose:
            print(f"\n[BatchRunner] Starting batch {batch_id[:8]}…")
            print(f"  mode={self.mode}  docs={len(samples)}\n")

        for i, sample in enumerate(samples, 1):
            if self.verbose:
                print(f"  [{i:>3}/{len(samples)}] {sample.doc_id:<14} "
                      f"({sample.word_count} words) … ", end="", flush=True)

            br = self.run_one(sample, batch_id)
            results.append(br)

            if self.verbose:
                status = f"pre={br.pre_score:.2f}  post={br.post_score:.2f}  "
                status += f"Δ={br.score_improvement:+.2f}"
                if br.error:
                    status = f"ERROR: {br.error[:40]}"
                print(status)

        if self.verbose:
            successful = sum(1 for r in results if not r.error)
            mean_pre   = (sum(r.pre_score  for r in results if not r.error) /
                          max(successful, 1))
            mean_post  = (sum(r.post_score for r in results if not r.error) /
                          max(successful, 1))
            print(f"\n[BatchRunner] Done. {successful}/{len(samples)} successful")
            print(f"  mean pre={mean_pre:.3f}  mean post={mean_post:.3f}  "
                  f"mean Δ={mean_post - mean_pre:+.3f}")

        return results

    # ---------------------------------------------------------------- #
    #  Persistence                                                      #
    # ---------------------------------------------------------------- #

    @staticmethod
    def save_results(
        results: List["BatchResult"],
        path: Optional[Path] = None,
    ) -> Path:
        """
        Save BatchResult list to CSV.
        Default path: evaluation_logs/batch_results.csv
        Returns the path written.
        """
        if path is None:
            path = _RESULTS_DIR / "batch_results.csv"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        write_header = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_BATCH_CSV_FIELDS)
            if write_header:
                writer.writeheader()
            for r in results:
                writer.writerow(r.to_row())

        return path

    @staticmethod
    def load_results(path: Optional[Path] = None) -> List["BatchResult"]:
        """Load BatchResult rows from CSV."""
        if path is None:
            path = _RESULTS_DIR / "batch_results.csv"
        path = Path(path)
        if not path.exists():
            return []
        with open(path, "r", newline="", encoding="utf-8") as f:
            return [BatchResult.from_row(row) for row in csv.DictReader(f)]

    @staticmethod
    def clear_results(path: Optional[Path] = None) -> None:
        """Delete the batch results CSV (used in tests)."""
        if path is None:
            path = _RESULTS_DIR / "batch_results.csv"
        path = Path(path)
        if path.exists():
            path.unlink()


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from pure_dataset import PUREDatasetLoader

    samples = PUREDatasetLoader.load_builtin()
    runner  = BatchRunner(mode="silent", verbose=True)
    results = runner.run_dataset(samples)
    out     = BatchRunner.save_results(results)
    print(f"\nResults saved to: {out}")
