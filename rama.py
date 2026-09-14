#!/usr/bin/env python
"""
RAMA CLI  — Requirement-Aware MetaGPT
---------------------------------------
Enriches a vague software requirement through the RAMA Elicitation Layer
(W1–W6) before passing the structured SRS to MetaGPT.

Usage:
  python rama.py "Build an online shop"
  python rama.py "Build an online shop" --mode llm
  python rama.py "Build an online shop" --dry-run
  python rama.py "Build an online shop" --skip-elicitation
  python rama.py "Build an online shop" --max-questions 5 --n-round 3
  python rama.py --save-srs enriched.txt "Build an online shop"

Modes:
  interactive  (default)  You type answers in the terminal
  llm                     Gemini auto-answers each question
  silent                  No dialogue; measures pre-score only

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------ #
#  RAMA module loader (bypasses metagpt.__init__ import chain)        #
# ------------------------------------------------------------------ #

_BASE        = Path(__file__).parent
_ELICITATION = _BASE / "metagpt" / "elicitation"
_EVAL        = _ELICITATION / "evaluation"


def _load(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_rama_modules():
    """Load all RAMA elicitation modules in dependency order."""
    _load(_ELICITATION / "schema"      / "ecommerce_schema.py",         "ecommerce_schema")
    _load(_ELICITATION / "rag"         / "knowledge_base.py",           "knowledge_base")
    _load(_ELICITATION / "parser"      / "srs_parser.py",               "srs_parser")
    _load(_ELICITATION / "analyser"    / "completeness_analyser.py",    "completeness_analyser")
    _load(_ELICITATION / "dialogue"    / "question_prioritiser.py",     "question_prioritiser")
    _load(_ELICITATION / "dialogue"    / "elicitation_dialogue.py",     "elicitation_dialogue")
    _load(_ELICITATION / "synthesiser" / "srs_synthesiser.py",          "srs_synthesiser")
    _load(_EVAL        / "metrics_logger.py",                           "metrics_logger")
    runner_mod = _load(_EVAL / "elicitation_runner.py",                 "elicitation_runner")
    return runner_mod.ElicitationRunner


def _load_analysis_writer():
    """Load the analysis-writer module (records cost/latency/tokens/completeness)."""
    return _load(_EVAL / "analysis_writer.py", "analysis_writer")


# ------------------------------------------------------------------ #
#  Terminal formatting helpers                                         #
# ------------------------------------------------------------------ #

_W = 64   # display width


def _hr(char="─"):
    print(char * _W)


def _box(title: str):
    print("┌" + "─" * (_W - 2) + "┐")
    pad = (_W - 2 - len(title)) // 2
    print("│" + " " * pad + title + " " * (_W - 2 - pad - len(title)) + "│")
    print("└" + "─" * (_W - 2) + "┘")


def _section(title: str):
    print()
    print(f"  ┌─ {title} " + "─" * max(0, _W - 6 - len(title)) + "┐")


def _info(label: str, value: str):
    print(f"  │  {label:<22} {value}")


def _end_section():
    print("  └" + "─" * (_W - 3) + "┘")


def _score_bar(score: float, width: int = 30) -> str:
    filled = int(score * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:.2f}"


def _level_tag(level: str) -> str:
    tags = {
        "POOR":     "  POOR  ",
        "PARTIAL":  "PARTIAL ",
        "GOOD":     "  GOOD  ",
        "COMPLETE": "COMPLETE",
    }
    return tags.get(level, level)


def _banner():
    print()
    print("╔" + "═" * (_W - 2) + "╗")
    title = "RAMA — Requirement-Aware MetaGPT"
    pad   = (_W - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (_W - 2 - pad - len(title)) + "║")
    sub   = "Elicitation Layer → MetaGPT Pipeline"
    pad2  = (_W - 2 - len(sub)) // 2
    print("║" + " " * pad2 + sub + " " * (_W - 2 - pad2 - len(sub)) + "║")
    print("╚" + "═" * (_W - 2) + "╝")
    print()


# ------------------------------------------------------------------ #
#  Elicitation step                                                    #
# ------------------------------------------------------------------ #

def run_elicitation(
    idea: str,
    mode: str,
    max_questions: int,
    save_srs: Path | None,
    use_llm_parse: bool = True,
    use_rag: bool = True,
    use_llm_synthesis: bool = True,
    random_questions: bool = False,
):
    """Run RAMA W2–W6 and return (enriched_srs, run_result)."""
    ElicitationRunner = _load_rama_modules()

    _section("STEP 1 — RAMA Elicitation Layer")
    print(f"  │  Mode      : {mode}")
    print(f"  │  Max Q&A   : {max_questions}")
    print(f"  │  Modules   : W2 SRS Parser  →  W3 Analyser  →")
    print(f"  │              W4 Dialogue    →  W5 Synthesiser")
    ablated = []
    if not use_llm_parse:     ablated.append("LLM parse (W2→fallback)")
    if not use_rag:           ablated.append("RAG knowledge base (W1)")
    if not use_llm_synthesis: ablated.append("LLM synthesis (W5→template)")
    if ablated:
        print(f"  │  Ablated   : {', '.join(ablated)}")
    if random_questions:
        print(f"  │  Questions : RANDOM selection (C1 control — prioritisation OFF)")
    _end_section()

    runner = ElicitationRunner(
        mode=mode,
        max_questions=max_questions,
        use_llm_parse=use_llm_parse,
        use_rag=use_rag,
        use_llm_synthesis=use_llm_synthesis,
        random_questions=random_questions,
    )

    print()
    print("  Parsing your requirement (W2)…")
    print("  Scoring completeness   (W3)…")
    if mode != "silent":
        print(f"  Starting {'interactive ' if mode == 'interactive' else 'LLM-driven '}Q&A  (W4)…")
        print()

    result = runner.run_sync(idea)

    # ── Post-elicitation summary ──────────────────────────────────── #
    pre  = result.pre_report
    post = result.post_report

    print()
    _section("Completeness Scores")
    _info("Before elicitation:",
          f"{_score_bar(pre.raw_score)}  [{_level_tag(pre.coverage_level())}]  "
          f"({len(pre.covered_categories)}/24 categories)")
    _info("After  elicitation:",
          f"{_score_bar(post.raw_score)}  [{_level_tag(post.coverage_level())}]  "
          f"({len(post.covered_categories)}/24 categories)")
    improvement = result.score_improvement
    sign        = "+" if improvement >= 0 else ""
    _info("Score improvement:",
          f"{sign}{improvement:.4f}  "
          f"({sign}{improvement / max(pre.raw_score, 0.0001) * 100:.1f}% relative)")
    _info("Critical gaps before:", str(result.metrics.critical_gaps_before))
    _info("Critical gaps after: ", str(result.metrics.critical_gaps_after))
    _info("Questions asked:    ", str(result.metrics.questions_asked))
    _info("Answers collected:  ", str(result.metrics.answers_collected))
    _info("Synthesis method:   ", result.metrics.synthesis_method)
    _end_section()

    # ── Show enriched SRS preview ─────────────────────────────────── #
    enriched = result.enriched_srs
    print()
    _section("Enriched SRS  (will be passed to MetaGPT as 'idea')")
    preview = enriched[:500].replace("\n", "\n  │  ")
    print(f"  │  {preview}")
    if len(enriched) > 500:
        print(f"  │  … ({len(enriched)} chars total)")
    _end_section()

    # ── Save to file if requested ─────────────────────────────────── #
    if save_srs:
        save_srs.write_text(enriched, encoding="utf-8")
        print()
        print(f"  Enriched SRS saved to: {save_srs}")

    return enriched, result


# ------------------------------------------------------------------ #
#  MetaGPT step                                                        #
# ------------------------------------------------------------------ #

def run_metagpt(
    idea: str,
    n_round: int,
    investment: float,
    project_name: str,
    code_review: bool,
    docs_only: bool = False,
):
    _section("STEP 2 — MetaGPT Pipeline")
    if docs_only:
        print(f"  │  Roles    : ProductManager → Architect → ProjectManager")
        print(f"  │  Output   : docs only (PRD, design, tasks) — NO code")
    else:
        print(f"  │  Roles    : ProductManager → Architect → ProjectManager → Engineer")
    print(f"  │  Rounds   : {n_round}")
    print(f"  │  Budget   : ${investment:.2f}")
    if project_name:
        print(f"  │  Project  : {project_name}")
    if not docs_only:
        print(f"  │  Code rev : {'yes' if code_review else 'no'}")
    _end_section()
    print()
    print("  Launching MetaGPT…")
    _hr("=")
    print()

    import asyncio
    from metagpt.config2 import config
    from metagpt.const import DEFAULT_WORKSPACE_ROOT
    from metagpt.context import Context
    from metagpt.roles import ProductManager, Architect, ProjectManager, Engineer
    from metagpt.team import Team

    # Set project_path explicitly so PrepareDocuments skips its LLM parse_resources call
    # (the call asks the LLM to return JSON but Gemini returns prose when the SRS is rich)
    _pname = project_name or "rama_project"
    _project_path = str(DEFAULT_WORKSPACE_ROOT / _pname)
    config.update_via_cli(_project_path, _pname, False, "", 0)
    ctx = Context(config=config)
    company = Team(context=ctx, use_mgx=False)
    roles = [
        ProductManager(use_fixed_sop=True),
        Architect(use_fixed_sop=True),
        ProjectManager(use_fixed_sop=True),
    ]
    if not docs_only:
        # Engineer watches WriteTasks and writes the source files; without it
        # the run stops after docs/prd, docs/system_design, docs/task
        roles.append(Engineer(n_borg=5, use_code_review=code_review))
    company.hire(roles)
    company.invest(investment)

    _t = time.perf_counter()
    asyncio.run(company.run(n_round=n_round, idea=idea))
    metagpt_seconds = round(time.perf_counter() - _t, 2)

    # Capture MetaGPT-stage token/cost totals from the cost manager
    cm = ctx.cost_manager
    return {
        "prompt_tokens":     cm.total_prompt_tokens,
        "completion_tokens": cm.total_completion_tokens,
        "total_tokens":      cm.total_prompt_tokens + cm.total_completion_tokens,
        "cost_usd":          round(cm.total_cost, 6),
        "seconds":           metagpt_seconds,
        "rounds":            n_round,
        "project_path":      _project_path,
    }


# ------------------------------------------------------------------ #
#  Confirmation prompt                                                  #
# ------------------------------------------------------------------ #

def _confirm(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"\n  {prompt} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if ans == "":
        return default
    return ans.startswith("y")


# ------------------------------------------------------------------ #
#  Idea input helpers                                                   #
# ------------------------------------------------------------------ #

def _prompt_for_idea() -> str:
    print("  Enter your software requirement.")
    print("  (multiple lines OK — press Enter on a blank line to submit)\n")
    lines = []
    first = True
    while True:
        try:
            line = input("  > " if first else "    ")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if line.strip() == "" and lines:
            break
        if line.strip():
            lines.append(line)
            first = False
    return " ".join(lines).strip()


# ------------------------------------------------------------------ #
#  CLI                                                                  #
# ------------------------------------------------------------------ #

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python rama.py",
        description=(
            "RAMA CLI — Elicits missing requirements interactively, "
            "then launches MetaGPT with the enriched SRS."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive Q&A, then MetaGPT:
  python rama.py "Build an online shop"

  # Gemini auto-answers, then MetaGPT:
  python rama.py "Build an online shop" --mode llm

  # Elicitation only — don't launch MetaGPT:
  python rama.py "Build an online shop" --dry-run

  # Skip elicitation — go straight to MetaGPT:
  python rama.py "Build an online shop" --skip-elicitation

  # Save the enriched SRS to a file:
  python rama.py "Build an online shop" --save-srs enriched.txt

  # Fewer questions, more MetaGPT rounds:
  python rama.py "Build an online shop" --max-questions 5 --n-round 8

  # Ablation: no RAG hints, template synthesis (component study):
  python rama.py "Build an online shop" --mode llm --no-rag --no-llm-synthesis --dry-run

  # Docs only — PRD + design + tasks, no source code:
  python rama.py "Build an online shop" --docs-only --project-name shop_docs
        """,
    )

    p.add_argument(
        "idea",
        nargs="?",
        default=None,
        metavar="IDEA",
        help="Your software requirement (quoted string). "
             "If omitted you will be prompted.",
    )

    # ── Elicitation options ──────────────────────────────────────── #
    elicit = p.add_argument_group("Elicitation options")
    elicit.add_argument(
        "--mode",
        choices=["interactive", "llm", "silent"],
        default="interactive",
        help="interactive: you type answers (default); "
             "llm: Gemini auto-answers; "
             "silent: no Q&A, baseline score only.",
    )
    elicit.add_argument(
        "--max-questions",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of clarifying questions (default: 10).",
    )
    elicit.add_argument(
        "--skip-elicitation",
        action="store_true",
        help="Skip the RAMA layer and pass the raw idea directly to MetaGPT.",
    )
    elicit.add_argument(
        "--dry-run",
        action="store_true",
        help="Run elicitation only. Print enriched SRS but do not launch MetaGPT.",
    )
    elicit.add_argument(
        "--save-srs",
        type=Path,
        default=None,
        metavar="FILE",
        help="Save the enriched SRS to this file (e.g. enriched.txt).",
    )

    # ── Ablation options (W9 study) ──────────────────────────────── #
    ablation = p.add_argument_group(
        "Ablation options",
        "Disable individual RAMA components to measure their contribution. "
        "All components are ON by default (full RAMA).",
    )
    ablation.add_argument(
        "--no-rag",
        action="store_true",
        help="Disable the W1 RAG knowledge base: questions carry no "
             "domain-knowledge hints (tests the KB's contribution).",
    )
    ablation.add_argument(
        "--no-llm-parse",
        action="store_true",
        help="Disable W2 LLM extraction: use the keyword/regex fallback "
             "parser only (tests the LLM parser's contribution).",
    )
    ablation.add_argument(
        "--no-llm-synthesis",
        action="store_true",
        help="Disable W5 LLM synthesis: append clarifications with the "
             "template instead of LLM rewriting (tests synthesis quality).",
    )
    ablation.add_argument(
        "--random-questions",
        action="store_true",
        help="C1 control: select clarifying questions uniformly at random "
             "instead of by weight priority (tests whether prioritisation, "
             "not just asking questions, drives the gain).",
    )

    # ── MetaGPT options ──────────────────────────────────────────── #
    mg = p.add_argument_group("MetaGPT options")
    mg.add_argument(
        "--n-round",
        type=int,
        default=5,
        metavar="N",
        help="Number of MetaGPT simulation rounds (default: 5).",
    )
    mg.add_argument(
        "--investment",
        type=float,
        default=3.0,
        metavar="$",
        help="Dollar budget for the MetaGPT agent team (default: 3.0).",
    )
    mg.add_argument(
        "--project-name",
        default="",
        metavar="NAME",
        help="Optional project name for the MetaGPT workspace folder.",
    )
    mg.add_argument(
        "--no-code-review",
        action="store_true",
        help="Disable code review in MetaGPT (faster but lower quality).",
    )
    mg.add_argument(
        "--docs-only",
        action="store_true",
        help="Stop after the documentation stage: write only "
             "workspace/<name>/docs (PRD, system design, task list) and "
             "resources. No Engineer is hired, no source code is written.",
    )

    return p


def _raw_completeness(idea: str) -> dict:
    """Score the raw idea's completeness without any LLM (for S0 baseline)."""
    _load(_ELICITATION / "schema"   / "ecommerce_schema.py",      "ecommerce_schema")
    srs_parser = _load(_ELICITATION / "parser" / "srs_parser.py", "srs_parser")
    analyser_m = _load(_ELICITATION / "analyser" / "completeness_analyser.py",
                       "completeness_analyser")
    parsed = srs_parser.SRSParser().parse_fallback(idea)
    rep    = analyser_m.CompletenessAnalyser().analyse(parsed)
    return {
        "raw_score": round(rep.raw_score, 4),
        "covered":   len(rep.covered_categories),
        "critical":  len(rep.critical_gaps),
    }


def _build_analysis_data(args, idea: str, result, pname: str, aw) -> dict:
    """Assemble the elicitation-stage analysis record (result=None for S0)."""
    scenario = {
        "mode": args.mode,
        "skip_elicitation": args.skip_elicitation,
        "docs_only": args.docs_only,
        "random_questions": args.random_questions,
        "max_questions": args.max_questions,
        "n_round": args.n_round,
        "ablations": [name for name, on in [
            ("no_rag", args.no_rag),
            ("no_llm_parse", args.no_llm_parse),
            ("no_llm_synthesis", args.no_llm_synthesis),
        ] if on],
    }

    if result is not None:
        pre, post = result.pre_report, result.post_report
        completeness = {
            "raw_score":            round(pre.raw_score, 4),
            "final_score":          round(post.raw_score, 4),
            "improvement":          result.score_improvement,
            "raw_covered":          len(pre.covered_categories),
            "final_covered":        len(post.covered_categories),
            "critical_gaps_before": len(pre.critical_gaps),
            "critical_gaps_after":  len(post.critical_gaps),
        }
        elicitation = {
            "questions_asked":   result.metrics.questions_asked,
            "answers_collected": result.metrics.answers_collected,
            "synthesis_method":  result.metrics.synthesis_method,
            "tokens":            result.token_usage,
            "timings":           result.stage_timings,
        }
    else:
        raw = _raw_completeness(idea)
        completeness = {
            "raw_score":            raw["raw_score"],
            "final_score":          None,
            "improvement":          None,
            "raw_covered":          raw["covered"],
            "final_covered":        None,
            "critical_gaps_before": raw["critical"],
            "critical_gaps_after":  None,
        }
        elicitation = {
            "questions_asked": 0, "answers_collected": 0,
            "synthesis_method": "none (skipped)",
            "tokens": {"parse": {}, "dialogue": {}, "synthesis": {},
                       "total_prompt": 0, "total_completion": 0, "total": 0},
            "timings": {"parse": 0, "dialogue": 0, "synthesis": 0, "total": 0},
        }

    return {
        "project_name": pname,
        "timestamp":    aw.now_iso(),
        "scenario":     scenario,
        "completeness": completeness,
        "elicitation":  elicitation,
    }


def main():
    parser = _build_parser()
    args   = parser.parse_args()

    _banner()

    # ── Get idea ─────────────────────────────────────────────────── #
    idea = args.idea
    if not idea:
        idea = _prompt_for_idea()
    if not idea.strip():
        print("  No requirement provided. Exiting.")
        sys.exit(1)

    print()
    print("  Your requirement:")
    _hr()
    wrapped = idea if len(idea) <= _W - 4 else idea[:_W - 7] + "..."
    print(f"  {wrapped}")
    _hr()

    # ── Analysis recorder setup ──────────────────────────────────── #
    aw        = _load_analysis_writer()
    pname     = args.project_name or "rama_project"
    logs_dir  = _BASE / "evaluation_logs"
    temp_path = aw.temp_path_for(pname, logs_dir)

    # ── Elicitation ──────────────────────────────────────────────── #
    if args.skip_elicitation:
        print()
        print("  [--skip-elicitation]  Bypassing RAMA layer.")
        enriched = idea
        result   = None
    else:
        enriched, result = run_elicitation(
            idea=idea,
            mode=args.mode,
            max_questions=args.max_questions,
            save_srs=args.save_srs,
            use_llm_parse=not args.no_llm_parse,
            use_rag=not args.no_rag,
            use_llm_synthesis=not args.no_llm_synthesis,
            random_questions=args.random_questions,
        )

    # ── Stash elicitation-stage data to temp (survives MetaGPT wipe) ─ #
    analysis = _build_analysis_data(args, idea, result, pname, aw)
    aw.stash(temp_path, analysis)

    # ── Dry-run exit ─────────────────────────────────────────────── #
    if args.dry_run:
        out = aw.write_analysis(logs_dir / pname / "docs", analysis, compute_acqs=False)
        print()
        print("  [--dry-run]  Elicitation complete. MetaGPT not launched.")
        print(f"  Partial analysis written to: {out}")
        print()
        sys.exit(0)

    # ── Confirm MetaGPT launch ────────────────────────────────────── #
    if not args.skip_elicitation:
        proceed = _confirm("Proceed to MetaGPT with the enriched SRS?", default=True)
    else:
        proceed = True

    if not proceed:
        print()
        print("  Cancelled. The enriched SRS was NOT passed to MetaGPT.")
        if args.save_srs:
            print(f"  It was saved to: {args.save_srs}")
        print()
        sys.exit(0)

    # ── MetaGPT ──────────────────────────────────────────────────── #
    mg = run_metagpt(
        idea=enriched,
        n_round=args.n_round,
        investment=args.investment,
        project_name=args.project_name,
        code_review=not args.no_code_review,
        docs_only=args.docs_only,
    )

    # ── Consolidate: merge MetaGPT numbers, write docs/analysis.txt ── #
    analysis = aw.load_stash(temp_path) or analysis
    analysis["metagpt"] = mg
    elic_total = analysis.get("elicitation", {}).get("tokens", {}).get("total", 0)
    elic_secs  = analysis.get("elicitation", {}).get("timings", {}).get("total", 0)
    analysis["totals"] = {
        "tokens":  elic_total + mg["total_tokens"],
        "seconds": round(elic_secs + mg["seconds"], 2),
    }
    docs_dir = Path(mg["project_path"]) / "docs"
    out = aw.write_analysis(docs_dir, analysis, compute_acqs=True)
    try:
        temp_path.unlink()   # clean the temp only after the final write succeeds
    except OSError:
        pass

    # ── Done ─────────────────────────────────────────────────────── #
    print()
    _hr("═")
    print()
    print("  RAMA + MetaGPT pipeline complete.")
    print(f"  Run analysis written to: {out}")
    if args.save_srs:
        print(f"  Enriched SRS was saved to: {args.save_srs}")
    print()


if __name__ == "__main__":
    main()
