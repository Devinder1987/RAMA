# RAMA — Requirement-Aware MetaGPT

**RAMA Thesis — Devinder Shuthwal, LJMU 2026**

RAMA prepends a **Requirement Elicitation Layer** to an otherwise unmodified
[MetaGPT](https://github.com/geekan/MetaGPT) pipeline. A vague one-line idea is
parsed, scored for completeness, clarified through a short Q&A dialogue, and
rewritten into an enriched SRS _before_ MetaGPT's agent team generates the PRD,
system design, task list and code. Every run also writes a per-run
`analysis.txt` with completeness, token, cost and latency figures.

- Source: <https://github.com/Devinder1987/RAMA.git>
- Full algorithm listing: [RAMA_PSEUDOCODE_CLEAN.md](RAMA_PSEUDOCODE_CLEAN.md)
- Experiment scripts (S0, S1, A1–A4, C1, D1, E1, R1, R2): [RAMA_SCENARIOS.md](RAMA_SCENARIOS.md)

---

## Pipeline overview

| Component             | What it does                                                                               |
| --------------------- | ------------------------------------------------------------------------------------------ |
| RAG knowledge base    | Retrieves e-commerce domain hints used to enrich clarifying questions                      |
| SRS parser            | LLM extraction of the raw idea into a structured schema (keyword/regex fallback available) |
| Completeness analyser | Scores the parsed SRS against the domain schema (pre-score)                                |
| Dialogue              | Selects the highest-weight gaps and asks up to _N_ clarifying questions                    |
| Synthesiser           | Rewrites the idea plus answers into an enriched SRS (LLM or template append)               |
| Metrics logger        | Re-scores the enriched SRS (post-score) and appends the run to `evaluation_logs/runs.csv`  |
| MetaGPT               | Consumes the enriched SRS and produces `workspace/<project>/` (docs + code)                |

---

## Setup

Requirements: Python **3.9 – 3.11**, a Gemini API key.

```bash
git clone https://github.com/Devinder1987/RAMA.git
cd RAMA
pip install -r requirements.txt
pip install -e .
```

Copy the example config and add your key:

```bash
cp config/config2.example.yaml config/config2.yaml
```

```yaml
# config/config2.yaml
llm:
  api_type: "gemini"
  api_key: "<your-key>"
  model: "gemini-2.5-flash"
```

All reported runs use `gemini-2.5-flash` for both the elicitation layer and
MetaGPT.

---

## Running the project

Example requirement used throughout the thesis:

```
Build an online shop for customers to buy products with email and password
as login, Guest user allow to shop, Credit card and paypal as payment
options, around 100 site visits per day
```

Pass it as the first (quoted) argument to `rama.py`. If omitted you are
prompted for it.

### S0 — MetaGPT only (baseline)

```bash
python rama.py "<idea>" --skip-elicitation --n-round 10 \
  --project-name own_shop_S0_metagpt_only
```

### S1 — Full RAMA, interactive (you answer the questions)

```bash
python rama.py "<idea>" --mode interactive --n-round 10 \
  --project-name own_shop_S1_full_rama
```

### Other useful invocations

```bash
# Elicitation only — print the enriched SRS, don't launch MetaGPT
python rama.py "<idea>" --dry-run

# Save the enriched SRS to a file
python rama.py "<idea>" --mode llm --save-srs enriched.txt

# Docs only — PRD + system design + task list, no source code
python rama.py "<idea>" --mode llm --n-round 10 --docs-only --project-name shop_docs

# Ablation: no RAG hints, template synthesis
python rama.py "<idea>" --mode llm --no-rag --no-llm-synthesis --n-round 10 \
  --project-name own_shop_ablation
```

Run `python rama.py --help` for the full option list.

---

## Command-line switches

| Switch                                  | Effect when set                                                                                |
| --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `--skip-elicitation`                    | Bypass the RAMA layer entirely; the raw requirement is passed straight to MetaGPT              |
| `--no-llm-parse`                        | Disable the LLM extraction pass; use the keyword and regex fallback only                       |
| `--no-rag`                              | Disable knowledge-base retrieval; questions are not enriched with domain hints                 |
| `--no-llm-synthesis`                    | Disable LLM rewriting; assemble the enriched specification by template append                  |
| `--random-questions`                    | Select gaps for questioning uniformly at random instead of by severity weight                  |
| `--mode {interactive \| llm \| silent}` | Source of dialogue answers: human, simulated stakeholder, or none (pre-score only)             |
| `--n-round N`                           | MetaGPT round limit (CLI default 5; **fixed at 10 in all reported runs**)                      |
| `--max-questions N`                     | Dialogue question budget (default 10; **fixed at 10 in all reported runs**, varied only in D1) |

| Switch                | Effect                                                            |
| --------------------- | ----------------------------------------------------------------- |
| `--dry-run`           | Run elicitation only; print the enriched SRS and stop             |
| `--save-srs FILE`     | Write the enriched SRS to `FILE`                                  |
| `--docs-only`         | Stop MetaGPT after the documentation stage (no Engineer, no code) |
| `--project-name NAME` | Name of the `workspace/` folder for this run                      |
| `--investment $`      | Dollar budget for the MetaGPT agent team (default 3.0)            |
| `--no-code-review`    | Disable MetaGPT's code-review step                                |

---

## Outputs

Each run writes to `workspace/<project-name>/` (key files shown; MetaGPT also emits `class_view/`, `code_summary/`, `graph_repo/` and `tests/`):

```
workspace/<project-name>/
├── docs/
│   ├── prd/                # Product requirement document
│   ├── system_design/      # Architecture JSON (scored by ACQS)
│   ├── task/               # Task list
│   └── analysis.txt        # Per-run report: pre/post completeness, tokens, latency, ACQS
├── resources/
└── <project-name>/         # Generated source code (omitted with --docs-only)
```

Cross-run metrics are appended to `evaluation_logs/runs.csv`.

To score a generated architecture deterministically:

```bash
python metagpt/elicitation/evaluation/acqs_scorer.py \
  workspace/own_shop_S1_full_rama/docs/system_design/*.json
```

To run the PURE-corpus batch (scenario E1):

```bash
python run_pure_baseline.py     # writes evaluation_logs/batch_results_llm.csv
```

---

## Repository layout

```
rama.py                         # RAMA CLI entry point
run_pure_baseline.py            # Batch runner over the PURE corpus
metagpt/elicitation/
├── schema/                     # E-commerce requirement schema
├── parser/                     # W2 SRS parser (LLM + fallback)
├── analyser/                   # W3 completeness analyser
├── rag/                        # W1 knowledge-base retrieval
├── dialogue/                   # W4 question selection and answer sources
├── synthesiser/                # W5 enriched-SRS synthesis
└── evaluation/                 # W6 metrics logger, ACQS scorer
rag_store/                      # Domain knowledge base index
config/config2.yaml             # LLM configuration
evaluation_logs/                # runs.csv, batch results
workspace/                      # MetaGPT outputs, one folder per run
RAMA_PSEUDOCODE_CLEAN.md        # Algorithm listings (thesis appendix)
RAMA_SCENARIOS.md               # Reproducible experiment commands
```

---

## Reproducibility notes

- Use the same idea string and `--n-round 10` across every MetaGPT-producing
  scenario so outputs are comparable.
- To compare architecture only (ACQS on `docs/system_design`), add
  `--docs-only` uniformly to all scenarios.
- LLM output is non-deterministic; repeat each scenario several times and
  report mean ± SD.
