"""
SRS Synthesiser (W5)
---------------------
Converts an ElicitationSession (W4 output) into a single enriched SRS
string that incorporates the original requirement and all clarification
answers gathered during the dialogue.

Two synthesis modes:
  llm      — Gemini 2.5 Flash rewrites the requirement as coherent prose,
              naturally embedding all clarifications.  Produces the highest-
              quality enriched SRS and is used during real RAMA runs.
  template — Rule-based string assembly (no LLM).  Used when no API key is
              available and as the fast fallback during batch evaluation.

Output (SynthesisResult.enriched_srs) is passed directly to MetaGPT's
Team.run() as the enriched requirement string.

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ------------------------------------------------------------------ #
#  Local module imports via importlib.util                             #
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


# ------------------------------------------------------------------ #
#  Config loader                                                       #
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

_SYNTHESIS_PROMPT = """\
You are a senior software requirements engineer specialising in e-commerce systems.

A product owner submitted this initial requirement:
---
{original_requirement}
---

After a structured elicitation session, the following clarifications were obtained:
{clarification_lines}

Task:
Rewrite the above into a single, complete Software Requirements Specification (SRS) \
that naturally incorporates all clarifications into fluent prose.

Rules:
- Write 2-4 paragraphs of plain English
- Embed ALL clarifications naturally — do not list them as bullet points
- Replace every vague term (fast, modern, secure, scalable) with the specific \
  clarification provided
- Do not invent features absent from both the original and clarifications
- Output ONLY the enriched SRS text — no headings, no meta-commentary
"""


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class SynthesisResult:
    """
    Output of W5.  enriched_srs is passed to MetaGPT Team.run().
    """
    enriched_srs: str               # the final enriched requirement text
    original_srs: str               # original raw input
    clarifications_applied: int     # how many answer pairs were incorporated
    synthesis_method: str           # "llm" | "template"

    def improvement_summary(self) -> str:
        return (
            f"Synthesis method      : {self.synthesis_method}\n"
            f"Clarifications applied: {self.clarifications_applied}\n"
            f"Original length       : {len(self.original_srs)} chars\n"
            f"Enriched length       : {len(self.enriched_srs)} chars\n"
        )


# ------------------------------------------------------------------ #
#  Synthesiser                                                         #
# ------------------------------------------------------------------ #

class SRSSynthesiser:
    """
    Produces an enriched SRS from an ElicitationSession.

    Usage (async):
        synth  = SRSSynthesiser()
        result = await synth.synthesise(session)

    Usage (sync):
        result = synth.synthesise_sync(session)
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm  = use_llm   # False → always use template synthesis (ablation)
        self._api_key = _load_api_key()
        self._client  = None   # lazy Gemini client
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

    async def synthesise(self, session) -> SynthesisResult:
        """
        Primary entry point.  Tries LLM synthesis first; falls back to
        template if the API key is absent or the call fails.
        """
        ctx = session.to_context_dict()
        original   = ctx["original_requirement"]
        clars: Dict[str, str] = ctx["clarifications"]

        if self.use_llm and self._api_key and clars:
            enriched = await self._synthesise_llm(original, clars)
            if enriched:
                return SynthesisResult(
                    enriched_srs=enriched,
                    original_srs=original,
                    clarifications_applied=len(clars),
                    synthesis_method="llm",
                )

        # Fallback
        enriched = self._synthesise_template(original, clars)
        return SynthesisResult(
            enriched_srs=enriched,
            original_srs=original,
            clarifications_applied=len(clars),
            synthesis_method="template",
        )

    def synthesise_sync(self, session) -> SynthesisResult:
        """Synchronous wrapper around synthesise()."""
        return asyncio.run(self.synthesise(session))

    def synthesise_from_dict(
        self,
        original_srs: str,
        clarifications: Dict[str, str],
    ) -> SynthesisResult:
        """
        Convenience: build a minimal session-like context directly from
        raw strings.  Used in unit tests and standalone scripts.
        Always uses template mode (no async).
        """
        enriched = self._synthesise_template(original_srs, clarifications)
        return SynthesisResult(
            enriched_srs=enriched,
            original_srs=original_srs,
            clarifications_applied=len(clarifications),
            synthesis_method="template",
        )

    # ---------------------------------------------------------------- #
    #  LLM mode                                                          #
    # ---------------------------------------------------------------- #

    async def _synthesise_llm(
        self,
        original: str,
        clars: Dict[str, str],
    ) -> Optional[str]:
        try:
            from google import genai
            from google.genai import types

            if self._client is None:
                self._client = genai.Client(api_key=self._api_key)

            clar_lines = "\n".join(
                f"- {cat.replace('_', ' ').title()}: {answer}"
                for cat, answer in clars.items()
            )
            prompt = _SYNTHESIS_PROMPT.format(
                original_requirement=original,
                clarification_lines=clar_lines,
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
            text = response.text.strip()
            return text if text else None

        except Exception as exc:
            print(f"  [SRSSynthesiser] LLM call failed ({exc}) — using template.")
            return None

    # ---------------------------------------------------------------- #
    #  Template mode (no LLM)                                           #
    # ---------------------------------------------------------------- #

    def _synthesise_template(
        self,
        original: str,
        clars: Dict[str, str],
    ) -> str:
        """
        Assembles enriched SRS by appending clarifications to the original.
        Produces readable prose without requiring an LLM call.
        Groups clarifications by area for readability.
        """
        if not clars:
            return original

        lines = [original.rstrip(".") + "."]
        lines.append("")
        lines.append("Additional requirements clarified during elicitation:")

        for cat, answer in clars.items():
            label = cat.replace("_", " ").title()
            lines.append(f"  - {label}: {answer}.")

        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Load dialogue module to build a sample session
    _dialogue_mod = _load(
        _ELICITATION / "dialogue" / "elicitation_dialogue.py",
        "elicitation_dialogue",
    )
    _analyser_mod = _load(
        _ELICITATION / "analyser" / "completeness_analyser.py",
        "completeness_analyser",
    )

    SRS_VAGUE = "Build a fast, modern, secure online shop for users to buy things."

    analyser  = _analyser_mod.CompletenessAnalyser()
    report    = analyser.analyse_text(SRS_VAGUE)

    dialogue  = _dialogue_mod.ElicitationDialogue(max_questions=3)
    session   = dialogue.run_sync(SRS_VAGUE, report, mode="llm")

    synth     = SRSSynthesiser()
    result    = synth.synthesise_sync(session)

    print("\n=== SynthesisResult ===")
    print(result.improvement_summary())
    print("\n--- Enriched SRS ---")
    print(result.enriched_srs)
