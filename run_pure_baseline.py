"""
RAMA PURE Baseline Evaluation Script
--------------------------------------
Runs the full RAMA evaluation on the PURE dataset (or built-in samples)
in two passes and produces thesis evaluation tables.

Pass 1 — Silent (baseline):
    Measures the raw completeness score of each SRS document AS-IS,
    before any elicitation.  This establishes the PURE baseline.

Pass 2 — LLM (RAMA full pipeline):
    Runs the complete W2→W3→W4→W5→W3 pipeline on each document,
    measuring post-elicitation completeness.  Demonstrates RAMA's uplift.

Usage:
    python run_pure_baseline.py                   # built-in 10-sample corpus
    python run_pure_baseline.py --dir pure_data/srs   # real PURE dataset

Output:
    evaluation_logs/batch_results.csv       (silent pass results)
    evaluation_logs/batch_results_llm.csv   (llm pass results)

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------ #
#  Module loading                                                      #
# ------------------------------------------------------------------ #

def _load(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_BASE        = Path(__file__).parent
_ELICITATION = _BASE / "metagpt" / "elicitation"
_EVAL        = _ELICITATION / "evaluation"

_load(_ELICITATION / "schema"      / "ecommerce_schema.py",         "ecommerce_schema")
_load(_ELICITATION / "parser"      / "srs_parser.py",               "srs_parser")
_load(_ELICITATION / "analyser"    / "completeness_analyser.py",    "completeness_analyser")
_load(_ELICITATION / "dialogue"    / "question_prioritiser.py",     "question_prioritiser")
_load(_ELICITATION / "dialogue"    / "elicitation_dialogue.py",     "elicitation_dialogue")
_load(_ELICITATION / "synthesiser" / "srs_synthesiser.py",          "srs_synthesiser")
_load(_EVAL        / "metrics_logger.py",                           "metrics_logger")
_load(_EVAL        / "elicitation_runner.py",                       "elicitation_runner")

dataset_mod   = _load(_EVAL / "pure_dataset.py",    "pure_dataset")
batch_mod     = _load(_EVAL / "batch_runner.py",    "batch_runner")
analyser_mod  = _load(_EVAL / "results_analyser.py","results_analyser")

PUREDatasetLoader = dataset_mod.PUREDatasetLoader
BatchRunner       = batch_mod.BatchRunner
ResultsAnalyser   = analyser_mod.ResultsAnalyser

_RESULTS_DIR   = _BASE / "evaluation_logs"
_SILENT_CSV    = _RESULTS_DIR / "batch_results.csv"
_LLM_CSV       = _RESULTS_DIR / "batch_results_llm.csv"


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAMA PURE baseline evaluation"
    )
    parser.add_argument(
        "--dir", type=Path, default=None,
        help="Directory of .txt SRS files (default: use built-in 10 samples)",
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="Only run the silent baseline pass (no LLM calls)",
    )
    parser.add_argument(
        "--max-questions", type=int, default=10,
        help="Max elicitation questions per document (default: 10)",
    )
    args = parser.parse_args()

    # -- Load dataset ------------------------------------------------- #
    samples = PUREDatasetLoader.load(path=args.dir)
    source_label = (
        f"{args.dir}" if args.dir and Path(args.dir).exists()
        else "built-in 10-sample corpus"
    )
    print(f"\n[RAMA] Loaded {len(samples)} SRS documents from: {source_label}")

    analyser = ResultsAnalyser()

    # ================================================================ #
    #  Pass 1 — Silent (baseline)                                      #
    # ================================================================ #
    print("\n" + "=" * 62)
    print(" Pass 1: Silent Baseline (no elicitation)")
    print("=" * 62)

    silent_runner  = BatchRunner(mode="silent", verbose=True)
    silent_results = silent_runner.run_dataset(samples)
    BatchRunner.save_results(silent_results, _SILENT_CSV)
    print(f"\n[RAMA] Silent results saved to: {_SILENT_CSV}")

    silent_stats = analyser.analyse(silent_results)
    print()
    print(analyser.format_summary(silent_stats, label="Silent Baseline"))

    if args.skip_llm:
        print("\n[RAMA] --skip-llm flag set; skipping LLM pass.")
        return

    # ================================================================ #
    #  Pass 2 — LLM (full RAMA elicitation)                            #
    # ================================================================ #
    print("\n" + "=" * 62)
    print(" Pass 2: LLM Elicitation (full RAMA pipeline)")
    print("=" * 62)

    llm_runner  = BatchRunner(
        mode="llm",
        max_questions=args.max_questions,
        verbose=True,
    )
    llm_results = llm_runner.run_dataset(samples)
    BatchRunner.save_results(llm_results, _LLM_CSV)
    print(f"\n[RAMA] LLM results saved to: {_LLM_CSV}")

    llm_stats = analyser.analyse(llm_results)
    print()
    print(analyser.format_summary(llm_stats, label="LLM Elicitation"))

    # ================================================================ #
    #  Comparison table                                                 #
    # ================================================================ #
    print()
    print(analyser.compare(
        silent_results, llm_results,
        label_a="Silent (Baseline)",
        label_b="LLM (RAMA)",
    ))

    print("\n[RAMA] Evaluation complete.")
    print(f"  Silent CSV : {_SILENT_CSV}")
    print(f"  LLM CSV    : {_LLM_CSV}")
    print("\nUse results_analyser.py to generate further thesis tables.")


if __name__ == "__main__":
    main()
