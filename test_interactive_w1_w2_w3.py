"""
Interactive Test — W1 (Schema + RAG) + W2 (SRS Parser) + W3 (Completeness Analyser)
-------------------------------------------------------------------------------------
YOU type a real software requirement and watch it flow through the pipeline:

    your text
        -> W2 SRSParser.parse()              (LLM extraction + keyword scan)
        -> W3 CompletenessAnalyser.analyse()  (coverage score + gaps)
        -> W1 EcommerceKnowledgeBase.query()  (domain hints for your biggest gaps)

Run this yourself in a terminal (it needs your live keyboard input):

    python test_interactive_w1_w2_w3.py

Type your requirement, then press Enter on a BLANK line to submit.
Type 'quit' on a blank prompt to exit.

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import importlib.util
import sys
from pathlib import Path


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_BASE = Path(__file__).parent / "metagpt" / "elicitation"

schema_mod   = _load(_BASE / "schema"   / "ecommerce_schema.py",         "ecommerce_schema")
kb_mod       = _load(_BASE / "rag"      / "knowledge_base.py",           "knowledge_base")
parser_mod   = _load(_BASE / "parser"   / "srs_parser.py",               "srs_parser")
analyser_mod = _load(_BASE / "analyser" / "completeness_analyser.py",    "completeness_analyser")

SRSParser             = parser_mod.SRSParser
CompletenessAnalyser  = analyser_mod.CompletenessAnalyser
EcommerceKnowledgeBase = kb_mod.EcommerceKnowledgeBase


def read_multiline_input() -> str:
    print("\nType your requirement (multiple lines OK). Press Enter on a blank line to submit,")
    print("or just type 'quit' and Enter to exit.\n")
    lines = []
    first = True
    while True:
        line = input("  " if not first else "> ")
        if first and line.strip().lower() == "quit":
            return "__QUIT__"
        if line == "":
            break
        lines.append(line)
        first = False
    return " ".join(lines).strip()


def run_once(requirement: str, parser, analyser, kb) -> None:
    # ---- W2: Parse ----
    print("\n" + "-" * 60)
    print(" W2 -- Parsing your requirement (calling Gemini)...")
    print("-" * 60)
    parsed = parser.parse_sync(requirement)
    print(parsed.summary())

    # ---- W3: Completeness ----
    print("\n" + "-" * 60)
    print(" W3 -- Completeness Analysis")
    print("-" * 60)
    report = analyser.analyse(parsed)
    print(report.summary())

    # ---- W1: RAG hints for the biggest gaps ----
    print("\n" + "-" * 60)
    print(" W1 -- RAG Knowledge Base hints for your top gaps")
    print("-" * 60)
    if kb.count() == 0:
        print("  Knowledge base is empty. Run:")
        print("    python -m metagpt.elicitation.rag.seed_knowledge")
        print("  then try again.")
    else:
        priority_gaps = report.critical_gaps[:3] or report.missing_categories[:3]
        if not priority_gaps:
            print("  No gaps found — requirement is fully covered!")
        for cat in priority_gaps:
            cat_obj = report.gap_details[cat]
            print(f"\n  Category : {cat}  (weight={cat_obj.weight})")
            print(f"  Question : {cat_obj.question}")
            hits = kb.query(cat_obj.description, n_results=2, category_filter=cat)
            if not hits:
                print("    (no matching RAG documents for this category yet)")
            for h in hits:
                snippet = h[:150].replace("\n", " ")
                print(f"    - {snippet}...")


def main():
    print("=" * 60)
    print(" RAMA Elicitation -- Interactive W1 + W2 + W3 Test")
    print("=" * 60)

    parser   = SRSParser()
    analyser = CompletenessAnalyser()
    kb       = EcommerceKnowledgeBase()

    if not parser._api_key:
        print("\n[!] No Gemini API key found in config/config2.yaml.")
        print("    W2 will run in keyword-only fallback mode.")

    while True:
        requirement = read_multiline_input()

        if requirement == "__QUIT__":
            break
        if not requirement:
            print("  (empty input, try again)")
            continue

        run_once(requirement, parser, analyser, kb)

        print("\n" + "=" * 60)

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
