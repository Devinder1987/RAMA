"""
Analysis Writer (W10b)
-----------------------
Records one RAMA/MetaGPT run's Cost, Latency, Token usage, and Completeness
into  workspace/<project>/docs/analysis.txt.

Why a temp file:
    MetaGPT's PrepareDocuments wipes workspace/<project>/ (shutil.rmtree) at the
    START of its run. So the elicitation-stage numbers are stashed in a temp
    JSON UNDER evaluation_logs/ — outside the workspace — the moment elicitation
    finishes. After MetaGPT rebuilds docs/, the temp data is merged with the
    MetaGPT-stage numbers and rendered as the final analysis.txt.

Data captured:
    1. Tokens used by the Elicitation Layer   (Gemini usage_metadata, per stage)
    2. Tokens consumed by MetaGPT             (ctx.cost_manager)
    3. Total run time                         (elicitation + MetaGPT wall-clock)
    4. Completeness of RAW SRS vs Final Synthesis SRS   (Formula 1)
    + ACQS of the generated system design, and per-stage breakdowns.

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent


# ------------------------------------------------------------------ #
#  Temp-file (survives MetaGPT's workspace wipe)                       #
# ------------------------------------------------------------------ #

def temp_path_for(project_name: str, logs_dir: Path) -> Path:
    safe = (project_name or "rama_project").replace("/", "_").replace("\\", "_")
    return logs_dir / f"_analysis_{safe}.tmp.json"


def stash(temp_path: Path, data: dict) -> None:
    """Persist intermediate (elicitation-stage) data outside the workspace."""
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_stash(temp_path: Path) -> dict:
    if temp_path.exists():
        try:
            return json.loads(temp_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ------------------------------------------------------------------ #
#  ACQS (optional — scores the just-generated system design)          #
# ------------------------------------------------------------------ #

def _acqs_for_design(docs_dir: Path) -> Optional[dict]:
    try:
        if "acqs_scorer" in sys.modules:
            mod = sys.modules["acqs_scorer"]
        else:
            spec = importlib.util.spec_from_file_location(
                "acqs_scorer", _HERE / "acqs_scorer.py"
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules["acqs_scorer"] = mod   # required before exec so @dataclass resolves
            spec.loader.exec_module(mod)
    except Exception:
        return None

    sd_dir = docs_dir / "system_design"
    files = sorted(sd_dir.glob("*.json")) if sd_dir.exists() else []
    if not files:
        return None
    try:
        report = mod.ACQSScorer().score_files(files)
        return {
            "acqs": report.acqs,
            "attributes": {k: v.score for k, v in report.attributes.items()},
        }
    except Exception:
        return None


# ------------------------------------------------------------------ #
#  Rendering                                                           #
# ------------------------------------------------------------------ #

def _fmt(v, nd=2, na="N/A"):
    return na if v is None else f"{v:.{nd}f}"


def render(data: dict) -> str:
    W = 66
    L = ["=" * W,
         " RAMA — Run Analysis (Cost · Latency · Tokens · Completeness)",
         "=" * W,
         f" Project    : {data.get('project_name', '?')}",
         f" Timestamp  : {data.get('timestamp', '?')}",
         ]

    sc = data.get("scenario", {})
    L += [f" Scenario   : mode={sc.get('mode')}  skip_elicitation={sc.get('skip_elicitation')}"
          f"  docs_only={sc.get('docs_only')}"]
    abl = sc.get("ablations") or []
    L += [f"              ablations={', '.join(abl) if abl else 'none'}"
          f"  random_questions={sc.get('random_questions')}"
          f"  max_questions={sc.get('max_questions')}  n_round={sc.get('n_round')}"]
    L.append("")

    # 4. Completeness
    c = data.get("completeness", {})
    L += ["-" * W,
          " 4. COMPLETENESS SCORE (Formula 1, 0-1)",
          "-" * W,
          f"   RAW SRS            : {_fmt(c.get('raw_score'))}  "
          f"({c.get('raw_covered','?')}/24 categories)",
          f"   Final Synthesis   : {_fmt(c.get('final_score'))}  "
          f"({c.get('final_covered','?')}/24 categories)",
          f"   Improvement (Δ)   : {_fmt(c.get('improvement'), 4)}",
          f"   Critical gaps     : before={c.get('critical_gaps_before','?')}  "
          f"after={c.get('critical_gaps_after','?')}",
          ""]

    # 1. Elicitation tokens
    e = data.get("elicitation", {})
    et = e.get("tokens", {})
    L += ["-" * W,
          " 1. TOKENS — ELICITATION LAYER (Gemini)",
          "-" * W,
          f"   {'stage':<12}{'prompt':>10}{'completion':>12}{'total':>10}{'calls':>8}"]
    for stage in ("parse", "dialogue", "synthesis"):
        s = et.get(stage, {})
        L.append(f"   {stage:<12}{s.get('prompt',0):>10}{s.get('completion',0):>12}"
                 f"{s.get('total',0):>10}{s.get('calls',0):>8}")
    L += [f"   {'TOTAL':<12}{et.get('total_prompt',0):>10}"
          f"{et.get('total_completion',0):>12}{et.get('total',0):>10}",
          f"   questions_asked={e.get('questions_asked','?')}  "
          f"answers={e.get('answers_collected','?')}  "
          f"synthesis={e.get('synthesis_method','?')}",
          ""]

    # 2. MetaGPT tokens
    m = data.get("metagpt", {})
    L += ["-" * W,
          " 2. TOKENS — METAGPT",
          "-" * W,
          f"   prompt={m.get('prompt_tokens','?')}  "
          f"completion={m.get('completion_tokens','?')}  "
          f"total={m.get('total_tokens','?')}",
          f"   cost_usd={_fmt(m.get('cost_usd'), 4)}  rounds_used={m.get('rounds','?')}",
          ""]

    # Grand total tokens
    tot = data.get("totals", {})
    L += ["-" * W,
          " TOTAL TOKENS (elicitation + MetaGPT, both Gemini)",
          "-" * W,
          f"   {tot.get('tokens','?')} tokens",
          ""]

    # 3. Latency
    et_t = e.get("timings", {})
    L += ["-" * W,
          " 3. LATENCY / RUN TIME (seconds)",
          "-" * W,
          f"   elicitation : parse={_fmt(et_t.get('parse'))}  "
          f"dialogue={_fmt(et_t.get('dialogue'))}  synthesis={_fmt(et_t.get('synthesis'))}  "
          f"(sub-total={_fmt(et_t.get('total'))})",
          f"   metagpt     : {_fmt(m.get('seconds'))}",
          f"   TOTAL       : {_fmt(tot.get('seconds'))}",
          ""]

    # ACQS (bonus)
    a = data.get("acqs")
    if a:
        L += ["-" * W,
              " ACQS — Architecture Coverage Quality Score (system_design, 0-1)",
              "-" * W,
              f"   ACQS = {_fmt(a.get('acqs'), 3)}"]
        for attr, sc_ in (a.get("attributes") or {}).items():
            L.append(f"     {attr:<16}{_fmt(sc_)}")
        L.append("")

    L.append("=" * W)
    return "\n".join(L)


# ------------------------------------------------------------------ #
#  Final write                                                        #
# ------------------------------------------------------------------ #

def write_analysis(docs_dir: Path, data: dict, compute_acqs: bool = True) -> Path:
    """Render data to docs_dir/analysis.txt (creating docs_dir if needed)."""
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    if compute_acqs and "acqs" not in data:
        acqs = _acqs_for_design(docs_dir)
        if acqs:
            data["acqs"] = acqs
    out = docs_dir / "analysis.txt"
    out.write_text(render(data), encoding="utf-8")
    return out


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
