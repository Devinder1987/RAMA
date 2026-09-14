"""
Elicitation Runner (W6b)
-------------------------
End-to-end RAMA pipeline orchestrator.

Chains W2 → W3 → W4 → W5 → metrics log in a single async call.

    raw SRS text
        │
        ▼  W2: SRSParser
        ParsedSRS
        │
        ▼  W3: CompletenessAnalyser
        CompletenessReport  (pre_score)
        │
        ▼  W4: ElicitationDialogue
        ElicitationSession
        │
        ▼  W5: SRSSynthesiser
        SynthesisResult  (enriched_srs)
        │
        ▼  W3 again: re-score enriched SRS
        CompletenessReport  (post_score)
        │
        ▼  W6a: MetricsLogger
        RunMetrics  → evaluation_logs/runs.csv

Three run modes:
  interactive — terminal Q&A  (thesis live demo)
  llm         — Gemini answers questions automatically  (PURE dataset eval)
  silent      — no dialogue, measures pre/post on unchanged SRS  (ablation)

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------ #
#  Local module imports                                                #
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


_parser_mod     = _load(_ELICITATION / "parser"      / "srs_parser.py",            "srs_parser")
_analyser_mod   = _load(_ELICITATION / "analyser"    / "completeness_analyser.py", "completeness_analyser")
_dialogue_mod   = _load(_ELICITATION / "dialogue"    / "elicitation_dialogue.py",  "elicitation_dialogue")
_synth_mod      = _load(_ELICITATION / "synthesiser" / "srs_synthesiser.py",       "srs_synthesiser")
_logger_mod     = _load(_BASE        / "metrics_logger.py",                        "metrics_logger")

SRSParser            = _parser_mod.SRSParser
CompletenessAnalyser = _analyser_mod.CompletenessAnalyser
ElicitationDialogue  = _dialogue_mod.ElicitationDialogue
SRSSynthesiser       = _synth_mod.SRSSynthesiser
MetricsLogger        = _logger_mod.MetricsLogger
RunMetrics           = _logger_mod.RunMetrics


# ------------------------------------------------------------------ #
#  RunResult                                                           #
# ------------------------------------------------------------------ #

@dataclass
class RunResult:
    """
    Complete output of one ElicitationRunner.run() call.
    Contains every intermediate artifact plus the final metrics row.
    """
    original_srs:   str
    enriched_srs:   str
    pre_report:     object   # CompletenessReport before elicitation
    post_report:    object   # CompletenessReport after (on enriched SRS)
    session:        object   # ElicitationSession from W4
    synthesis:      object   # SynthesisResult from W5
    metrics:        RunMetrics
    token_usage:    dict = field(default_factory=dict)   # per-stage Gemini tokens
    stage_timings:  dict = field(default_factory=dict)   # per-stage wall-clock (s)

    @property
    def score_improvement(self) -> float:
        return round(self.post_report.raw_score - self.pre_report.raw_score, 4)

    def summary(self) -> str:
        lines = [
            "=" * 55,
            " RAMA Elicitation Run Summary",
            "=" * 55,
            f"Run ID       : {self.metrics.run_id}",
            f"Mode         : {self.metrics.mode}",
            "",
            "Completeness scores:",
            f"  Before     : {self.pre_report.raw_score:.2f}  "
            f"({len(self.pre_report.covered_categories)}/24 categories)",
            f"  After      : {self.post_report.raw_score:.2f}  "
            f"({len(self.post_report.covered_categories)}/24 categories)",
            f"  Improvement: +{self.score_improvement:.2f}",
            "",
            f"Questions asked   : {self.metrics.questions_asked}",
            f"Answers collected : {self.metrics.answers_collected}",
            f"Synthesis method  : {self.metrics.synthesis_method}",
            f"Duration          : {self.metrics.duration_seconds:.1f}s",
            "",
            "Critical gaps remaining after elicitation:",
            f"  {self.post_report.critical_gaps or 'none'}",
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Runner                                                              #
# ------------------------------------------------------------------ #

class ElicitationRunner:
    """
    Orchestrates the full RAMA pipeline for a single SRS input.

    Usage:
        runner = ElicitationRunner(mode="llm", max_questions=10)
        result = runner.run_sync("Build a fast, modern shop...")

    Args:
        mode          : "interactive" | "llm" | "silent"
        max_questions : cap on how many questions W4 will ask
        log_file      : path to evaluation_logs/runs.csv
                        (pass None to disable logging)

    Ablation switches (all default True = full RAMA):
        use_llm_parse     : False → W2 uses the keyword/regex fallback parser
        use_rag           : False → W4 questions carry no W1 knowledge-base hints
        use_llm_synthesis : False → W5 uses template synthesis, never the LLM
    """

    def __init__(
        self,
        mode: str = "llm",
        max_questions: int = 10,
        log_file: Optional[Path] = None,
        use_llm_parse: bool = True,
        use_rag: bool = True,
        use_llm_synthesis: bool = True,
        random_questions: bool = False,
    ):
        self.mode              = mode
        self.use_llm_parse     = use_llm_parse
        self.parser            = SRSParser()
        self.analyser          = CompletenessAnalyser()
        self.dialogue          = ElicitationDialogue(
            max_questions=max_questions, use_rag=use_rag,
            random_questions=random_questions,
        )
        self.synthesiser       = SRSSynthesiser(use_llm=use_llm_synthesis)
        self.logger            = MetricsLogger(log_file) if log_file is not None else MetricsLogger()

    # ---------------------------------------------------------------- #
    #  Public API                                                        #
    # ---------------------------------------------------------------- #

    async def run(self, requirement: str) -> RunResult:
        """
        Execute the full pipeline and return a RunResult.
        Metrics are automatically appended to evaluation_logs/runs.csv.
        """
        run_id    = RunMetrics.make_run_id()
        timestamp = RunMetrics.now_iso()
        t_start   = time.perf_counter()

        # ── W2: parse original SRS ───────────────────────────────── #
        _t = time.perf_counter()
        if self.use_llm_parse:
            parsed = await self.parser.parse(requirement)
        else:
            parsed = self.parser.parse_fallback(requirement)   # ablation: no LLM
        t_parse = time.perf_counter() - _t

        # ── W3: score original SRS ───────────────────────────────── #
        pre_report = self.analyser.analyse(parsed)

        # ── W4: elicitation dialogue ─────────────────────────────── #
        _t = time.perf_counter()
        session = await self.dialogue.run(requirement, pre_report, mode=self.mode)
        t_dialogue = time.perf_counter() - _t

        # ── W5: synthesise enriched SRS ──────────────────────────── #
        _t = time.perf_counter()
        synthesis = await self.synthesiser.synthesise(session)
        t_synth = time.perf_counter() - _t

        # ── W3 again: score enriched SRS ────────────────────────── #
        if synthesis.enriched_srs.strip() == requirement.strip():
            # No clarifications were added — the pipeline is a no-op, so the
            # post-score must equal the pre-score (avoids the asymmetry of
            # scoring identical text with LLM parse pre vs fallback parse post)
            post_report = pre_report
        else:
            enriched_parsed = self.parser.parse_fallback(synthesis.enriched_srs)
            post_report     = self.analyser.analyse(enriched_parsed)

        duration = round(time.perf_counter() - t_start, 2)

        # ── W6a: log metrics ─────────────────────────────────────── #
        metrics = RunMetrics(
            run_id=run_id,
            timestamp=timestamp,
            mode=self.mode,
            parse_method=parsed.parse_method,
            synthesis_method=synthesis.synthesis_method,
            pre_score=round(pre_report.raw_score, 4),
            pre_weighted_score=round(pre_report.weighted_score, 4),
            post_score=round(post_report.raw_score, 4),
            post_weighted_score=round(post_report.weighted_score, 4),
            questions_asked=len(session.questions_asked),
            answers_collected=len(session.answers),
            critical_gaps_before=len(pre_report.critical_gaps),
            critical_gaps_after=len(post_report.critical_gaps),
            duration_seconds=duration,
            original_srs_excerpt=requirement[:120],
        )
        self.logger.log(metrics)

        # ── Per-stage token usage (Gemini) and timings ───────────── #
        def _stage(component):
            return {
                "prompt": component.prompt_tokens,
                "completion": component.completion_tokens,
                "total": component.prompt_tokens + component.completion_tokens,
                "calls": component.llm_calls,
            }

        parse_t = _stage(self.parser)
        dlg_t   = _stage(self.dialogue)
        syn_t   = _stage(self.synthesiser)
        token_usage = {
            "parse":     parse_t,
            "dialogue":  dlg_t,
            "synthesis": syn_t,
            "total_prompt":     parse_t["prompt"] + dlg_t["prompt"] + syn_t["prompt"],
            "total_completion": parse_t["completion"] + dlg_t["completion"] + syn_t["completion"],
            "total":            parse_t["total"] + dlg_t["total"] + syn_t["total"],
        }
        stage_timings = {
            "parse":     round(t_parse, 2),
            "dialogue":  round(t_dialogue, 2),
            "synthesis": round(t_synth, 2),
            "total":     duration,
        }

        return RunResult(
            original_srs=requirement,
            enriched_srs=synthesis.enriched_srs,
            pre_report=pre_report,
            post_report=post_report,
            session=session,
            synthesis=synthesis,
            metrics=metrics,
            token_usage=token_usage,
            stage_timings=stage_timings,
        )

    def run_sync(self, requirement: str) -> RunResult:
        """Synchronous wrapper around run()."""
        return asyncio.run(self.run(requirement))


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."
    SRS_RICH  = (
        "Build a B2C e-commerce platform where customers can register, "
        "login, browse a product catalog with search and filter, add items "
        "to their cart, and checkout using Stripe or PayPal. "
        "Admins can manage products, view orders, and issue refunds. "
        "The system should handle 5000 concurrent users with <2s response time. "
        "GDPR and PCI-DSS compliance are required."
    )

    runner = ElicitationRunner(mode="llm", max_questions=5)

    for label, srs in [("VAGUE", SRS_VAGUE), ("RICH", SRS_RICH)]:
        print(f"\nRunning on SRS_{label} ...")
        result = runner.run_sync(srs)
        print(result.summary())
        print("\n--- Enriched SRS ---")
        print(result.enriched_srs[:600])
        print()

    stats = runner.logger.summary_stats()
    print("\n=== Aggregate Stats ===")
    for k, v in stats.items():
        print(f"  {k:<30}: {v}")
