# RAMA — Experimental Scenario Scripts

RAMA Thesis — Devinder Shuthwal, LJMU 2026

Single worked example (`own_shop`). Same idea string across all scenarios so
outputs are comparable. Each scenario writes to a unique `--project-name`.
For automated reproducibility, elicitation scenarios use `--mode llm`
(Gemini auto-answers); `R1` deliberately switches to `--mode interactive`.

Constant idea:
"Build an online shop for customers to buy products with email and password
as login, Guest user allow to shop, Credit card and paypal as payment
options, around 100 site visits per day"

Fair-comparison note: every MetaGPT-producing scenario uses `--n-round 10`.
To compare architecture only (ACQS on `docs/system_design`), add `--docs-only`
uniformly to all of them.

---

## S0 — MetaGPT only (baseline, RQ2 lower bound)

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --skip-elicitation --n-round 10 --project-name own_shop_S0_metagpt_only
```

## S1 — Full RAMA (RQ2 treatment)

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --n-round 10 --project-name own_shop_S1_full_rama
```

## A1 — RAMA − RAG/Knowledge base

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --no-rag --n-round 10 --project-name own_shop_A1_no_rag
```

## A2 — RAMA − LLM parse (W2 → fallback)

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --no-llm-parse --n-round 10 --project-name own_shop_A2_no_llm_parse
```

## A3 — RAMA − LLM synthesis (W5 → template)

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --no-llm-synthesis --n-round 10 --project-name own_shop_A3_no_llm_synth
```

## A4 — RAMA − all three (ablation floor)

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --no-rag --no-llm-parse --no-llm-synthesis --n-round 10 --project-name own_shop_A4_no_all
```

## C1 — Prioritised vs RANDOM questions (control for RQ1)

Status: implemented (`--random-questions`), runnable via `rama.py` and in batch
(`BatchRunner(random_questions=True)`). Verified: prioritised picks the weight-3
critical gap first; random picks a low-priority gap instead.

Run S1 (prioritised) above, then this random-selection twin; compare their
post-scores / ACQS. Repeat several times (random seed varies each run).

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --random-questions --n-round 10 --project-name own_shop_C1_random_q
```

## D1 — Question-count sweep (RQ2 cost vs completeness curve)

Four runs; only `--max-questions` varies. Plot completeness gain + tokens per level.

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --max-questions 1  --n-round 10 --project-name own_shop_D1_q01
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --max-questions 3  --n-round 10 --project-name own_shop_D1_q03
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --max-questions 5  --n-round 10 --project-name own_shop_D1_q05
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode llm --max-questions 10 --n-round 10 --project-name own_shop_D1_q10
```

## E1 — Improvement Δ vs continuous pre-score (0–1)

Not a single-idea run — needs the PURE corpus to get a spread of pre-scores.
Generates per-doc pre/post scores; then correlate.

```
python run_pure_baseline.py                 # writes evaluation_logs/batch_results_llm.csv
```

Then, from `batch_results_llm.csv`: x = `pre_score` (0–1), y = `score_improvement`
(= post − pre); report Pearson r + linear-fit slope (expect negative — larger
gains at lower pre-scores).

## R1 — Answer source ≠ generator (self-answer confound)

Same config as S1 but a human answers the questions instead of the LLM.
Compare against S1 (`own_shop_S1_full_rama`).

```
python rama.py "Build an online shop for customers to buy products with email and password as login, Guest user allow to shop, Credit card and paypal as payment options, around 100 site visits per day" --mode interactive --n-round 10 --project-name own_shop_R1_human_answers
```

## R2 — Judge robustness (metric validity)

No new pipeline run. Score the SAME design with two independent judges and
report agreement (Cohen's κ, §7.4.2).

Layer 1 (deterministic, runnable now — one number, no judge variance):
```
python metagpt/elicitation/evaluation/acqs_scorer.py workspace/own_shop_S1_full_rama/docs/system_design/*.json
python metagpt/elicitation/evaluation/acqs_scorer.py workspace/own_shop_S0_metagpt_only/docs/system_design/*.json
```

Layer 2 (LLM-as-judge ×2 models — BLOCKED until the Gemini spending cap resets;
use a second free provider as the second judge). Pending implementation in the
W10 MAAD rubric.

---

## Metrics per scenario (proposal §7.4)

For every scenario above, collect:
1. Completeness score (Formula 1) — pre & post
2. ACQS / quality-attribute rubric — score `docs/system_design`
3. Cost + latency — tokens & wall-clock

Repeat each N× and report mean ± SD (LLM output is non-deterministic).
