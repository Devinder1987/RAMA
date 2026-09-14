# RAMA + MetaGPT — Full-System Pseudocode

RAMA Thesis — Devinder Shuthwal, LJMU 2026
Covers the complete current system: Elicitation Layer (W1–W8), the MetaGPT
generation pipeline, ablation switches, token/cost/latency accounting, the
per-run analysis.txt report, and the ACQS architecture-coverage metric.

Legend of run-configurable switches (from the CLI):
skip_elicitation bypass the RAMA layer entirely (S0)
use_llm_parse W2 LLM extraction vs keyword fallback (A2 off)
use_rag W1 knowledge-base hints on questions (A1 off)
use_llm_synthesis W5 LLM rewrite vs template append (A3 off)
random_questions random gap selection vs weight-priority (C1)
docs_only stop after task list, write no code
mode interactive | llm | silent (answer source)

---

## Algorithm 1 — RAMA Main Pipeline (`rama.py`)

```
Input : R (requirement), switches above, n_round, project_name
Output: architecture artefacts + workspace/<project>/docs/analysis.txt

 1  pname     ← project_name or "rama_project"
 2  temp_path ← evaluation_logs/_analysis_<pname>.tmp.json   ▷ OUTSIDE workspace

 3  if skip_elicitation:                                     ▷ S0 baseline
 4      enriched ← R ; result ← ∅
 5  else:
 6      (enriched, result) ← ELICIT(R, switches)             ▷ Algorithm 2
 7      show pre/post completeness bars

 8  analysis ← BUILD_ANALYSIS(R, result, switches, pname)    ▷ completeness+tokens
 9  STASH(temp_path, analysis)               ▷ survives MetaGPT's workspace wipe

10  if dry_run:
11      write partial analysis → evaluation_logs/<pname>/docs ; stop
12  if not skip_elicitation and not user_confirms(): stop

13  mg ← RUN_METAGPT(enriched, n_round, pname, docs_only)    ▷ Algorithm 7
14  analysis ← LOAD(temp_path)                               ▷ reload after wipe
15  analysis.metagpt ← mg
16  analysis.totals  ← { tokens : elic_tokens + mg.tokens,
17                       seconds: elic_secs   + mg.seconds }
18  WRITE_ANALYSIS(workspace/<pname>/docs, analysis)         ▷ Algorithm 10
19  delete temp_path        ▷ only after the final write succeeds (crash-safe)
```

---

## Algorithm 2 — Elicitation Pipeline (W2–W6, `ElicitationRunner.run`)

```
ELICIT(R, switches):
 1  t0 ← now
 2  parsed ← use_llm_parse ? PARSE(R) : PARSE_FALLBACK(R)    ▷ Algorithm 3 (W2)
 3  pre    ← ANALYSE(parsed)                                 ▷ Algorithm 4 (W3)
 4  session ← DIALOGUE(R, pre, mode, use_rag, random_questions) ▷ Algorithm 5 (W4)
 5  synth  ← SYNTHESISE(R, session, use_llm_synthesis)       ▷ Algorithm 6 (W5)
 6  if synth.enriched = R:  post ← pre           ▷ no-op guard (0 answers → Δ=0)
 7  else:                   post ← ANALYSE(PARSE_FALLBACK(synth.enriched))
 8  duration ← now − t0
 9  LOG_METRICS(pre, post, session, duration)               ▷ W6 → runs.csv
10  token_usage   ← collect per-stage {prompt,completion,total,calls}
                     from parser, dialogue, synthesiser      ▷ Algorithm 3a
11  stage_timings ← {parse, dialogue, synthesis, total}
12  return (synth.enriched,
            RunResult(pre, post, session, synth, token_usage, stage_timings))
```

---

## Algorithm 3 — SRS Parser (W2, `srs_parser.py`)

```
PARSE(R):
 1  hints ← keyword scan of R over ECOMMERCE_SCHEMA (24 categories)
 2  try:
 3      response ← LLM("extract actors/entities/intents/NFRs as JSON", R)
 4      RECORD_USAGE(response)                               ▷ Algorithm 3a
 5      return ParsedSRS(fields=parse_json(response), hints, method="llm")
 6  catch: return PARSE_FALLBACK(R)

PARSE_FALLBACK(R):                                           ▷ deterministic, no LLM
 1  actors,entities ← regex heuristics ; hints ← keyword scan
 2  return ParsedSRS(actors, entities, hints, method="fallback")

Algorithm 3a — RECORD_USAGE(response):   ▷ same helper in parser/dialogue/synth
 1  um ← response.usage_metadata
 2  self.prompt_tokens     += um.prompt_token_count
 3  self.completion_tokens += um.candidates_token_count
 4  self.llm_calls         += 1
```

---

## Algorithm 4 — Completeness Analyser (W3, `completeness_analyser.py`)

```
ANALYSE(P):
 1  for each category c in ECOMMERCE_SCHEMA:
 2      coverage[c] ← P.schema_hints[c]
                      OR ∃ kw ∈ c.keywords : kw ⊆ P.combined_text()
 3  covered  ← {c : coverage[c]} ; missing ← rest
 4  raw      ← |covered| / 24                                ▷ Formula 1
 5  weighted ← Σ_{c∈covered} w_c / Σ_all w_c                 ▷ Formula 2 (Σw=58)
 6  critical ← {c ∈ missing : w_c = 3}
 7  per_group[g] ← |covered ∩ g| / |g|   for g ∈ {FUNC,NON_FUNC,DOMAIN}
 8  level ← POOR<0.3 | PARTIAL<0.6 | GOOD<0.9 | COMPLETE≥0.9
 9  return Report(raw, weighted, covered, missing, critical, per_group, level)
```

---

## Algorithm 5 — Elicitation Dialogue (W4 + W1 RAG, `elicitation_dialogue.py`)

```
DIALOGUE(R, report, mode, use_rag, random_questions):
 1  gaps ← report.missing categories
 2  if random_questions:                                     ▷ C1 control
 3      Q ← random.sample(gaps, max_questions)               ▷ ignore weight
 4  else:
 5      Q ← top max_questions of gaps by (weight desc, group order)  ▷ prioritise
 6  if use_rag and mode ≠ silent:                            ▷ W1 enrichment
 7      for q in Q: q.rag_hints ← KB.query(q.question, category=q, k=2)
 8  session ← new Session(R, Q, mode)
 9  for q in Q:
10      switch mode:
11          silent      : a ← ∅                              ▷ baseline, no answers
12          interactive : a ← human types answer             ▷ 0 LLM tokens
13          llm         : a ← LLM("answer as stakeholder", R, q, q.rag_hints)
14                        RECORD_USAGE(response)             ▷ Algorithm 3a
15      if a valid: session.answers[q.category] ← a
16  return session
```

---

## Algorithm 6 — SRS Synthesiser (W5, `srs_synthesiser.py`)

```
SYNTHESISE(R, session, use_llm_synthesis):
 1  clars ← session.answers
 2  if clars = ∅: return R                                   ▷ no-op
 3  if use_llm_synthesis and api_key:
 4      response ← LLM("rewrite as one coherent SRS; integrate every
                        clarification; invent nothing", R, clars)
 5      RECORD_USAGE(response)                               ▷ Algorithm 3a
 6      if response non-empty: return enriched   (method="llm")
 7  return R + "Additional requirements clarified:" + bullets  (method="template")
```

---

## Algorithm 7 — MetaGPT Pipeline (`rama.py run_metagpt`)

```
RUN_METAGPT(R′, n_round, pname, docs_only):
 1  config.project_path ← workspace/pname     ▷ MOD-3: skips PrepareDocuments'
                                                fragile parse_resources LLM call
 2  ctx  ← Context(config) ; team ← Team(ctx, use_mgx=False)
 3  roles ← [ ProductManager(use_fixed_sop),  ▷ classic SOP roles, no TeamLeader
             Architect(use_fixed_sop),
             ProjectManager(use_fixed_sop) ]
 4  if not docs_only: roles += Engineer(n_borg=5)   ▷ omit → docs only, no code
 5  team.hire(roles) ; team.invest(budget)
 6  t0 ← now
 7  for round ← 1 .. n_round:
 8      if every role idle: break
 9      for each role: role.RUN()                            ▷ Algorithm 8
10  return { prompt_tokens, completion_tokens, total_tokens,   ▷ from
             cost_usd, seconds: now−t0, rounds, project_path } ▷ ctx.cost_manager
```

---

## Algorithm 8 — Role Reaction Loop (`RoleZero._react`, RAMA-modified)

```
ROLE.RUN():
 1  news ← observe(msg_buffer ∩ watched causes)
 2  if news = ∅: return idle
 3  if use_fixed_sop:                                        ▷ MOD-1
 4      max_react_loop ← 1        ▷ one action/observation; else RoleZero's
                                    default 50 repeats WritePRD dozens of times
 5  else:
 6      if QUICK_THINK(news)=QUICK: return text answer  ▷ bypassed for SOP roles
                                                          (text answer = no files)
 7  while actions_taken < max_react_loop:
 8      todo ← THINK()   ▷ PM: PrepareDocuments if no workspace else WritePRD
 9      if todo = ∅: break
10      msg ← ACT(todo)  ▷ runs the Action; writes files; accrues ctx.cost_manager
11  publish(msg)         ▷ wakes the next role in the SOP chain
```

---

## Algorithm 9 — MetaGPT SOP Action Chain (watch-driven)

```
UserRequirement ─▶ ProductManager : PrepareDocuments → WritePRD  → docs/prd/*.json
                        ▼ watched by
                   Architect      : WriteDesign  → docs/system_design/*.json
                        ▼ watched by
                   ProjectManager : WriteTasks   → docs/task/*.json
                        ▼ watched by       (skipped when docs_only)
                   Engineer       : WriteCodePlanAndChange → docs/code_plan_and_change/
                                    WriteCode (per task file) → workspace/<pname>/<pname>/*
```

---

## Algorithm 10 — Analysis Writer (`analysis_writer.py`)

```
STASH(temp_path, analysis):        write analysis as JSON to temp_path (outside
                                   workspace, so MetaGPT's rmtree cannot delete it)

WRITE_ANALYSIS(docs_dir, analysis):
 1  analysis.acqs ← ACQS(docs_dir/system_design)             ▷ Algorithm 11
 2  render human-readable report with sections:
      · Scenario (mode, ablations, random_questions, n_round …)
      · Completeness: RAW vs Final (Formula 1), Δ, critical gaps
      · Tokens — Elicitation (parse/dialogue/synthesis, per Algorithm 3a)
      · Tokens — MetaGPT (prompt/completion/total, cost)
      · Total tokens (both Gemini → additive)
      · Latency: per-stage elicitation + MetaGPT + total
      · ACQS (overall + 6 attributes)
 3  write docs_dir/analysis.txt
```

Baseline note: for S0 (skip_elicitation) the Final-Synthesis score and
elicitation tokens are N/A / 0; RAW completeness is still computed from the raw
idea via PARSE_FALLBACK so S0 and S1 reports stay comparable.

---

## Algorithm 11 — ACQS Scorer (`acqs_scorer.py`)

```
ACQS(system_design_files):
 1  text ← concat(design JSON docs)
 2  for each attribute a in {security, scalability, cost,
                             performance, availability, modifiability}:
 3      for each indicator group g of a (5–6 groups):
 4          covered[g] ← ∃ pattern ∈ g : regex_match(pattern, text)
 5      a_score ← |covered groups| / |groups of a|
 6  ACQS ← mean(a_score over the 6 attributes)               ▷ 0–1
 7  return { ACQS, per-attribute scores }
```

---

## Algorithm 12 — Evaluation Harness & Scenarios (W7–W8)

```
BATCH_EVAL(dataset, switches):                               ▷ W7 batch_runner
 1  samples ← PURE_LOADER.load(dataset)     ▷ 79 PURE docs or 10 built-in
 2  for each doc: try ELICIT(doc, switches) → batch_results.csv
                  catch → error row, continue                ▷ per-doc isolation

ANALYSE_RESULTS(results):                                    ▷ W8 results_analyser
 1  mean/std/median of pre, post, Δ; % improved/unchanged/regressed
 2  coverage distribution POOR/PARTIAL/GOOD/COMPLETE, pre vs post
 3  COMPARE(A, B) → ablation table

Experimental scenarios (each = one switch configuration):
    S0  skip_elicitation                         baseline (MetaGPT only)
    S1  full RAMA (all switches on)              treatment
    A1  use_rag=off                              − RAG/KB
    A2  use_llm_parse=off                        − LLM parse
    A3  use_llm_synthesis=off                    − LLM synthesis
    A4  A1+A2+A3                                  ablation floor
    C1  random_questions=on                      prioritised-vs-random control
    D1  sweep max_questions ∈ {1,3,5,10}         cost vs completeness curve
    E1  batch over PURE; regress Δ on pre-score  conditional effect
    R1  mode=interactive vs llm                  answer-source confound
    R2  ACQS/rubric scored by two judges         metric validity
Metrics per scenario: completeness (Formula 1), ACQS (Algorithm 11),
tokens + latency (analysis.txt).
```

---

## MetaGPT-core modifications (methodology chapter)

| #     | File                    | Change                                                                               | Reason                                                                                   |
| ----- | ----------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| MOD-1 | `roles/di/role_zero.py` | `_react()`: when `use_fixed_sop`, skip `_quick_think()` and set `max_react_loop = 1` | QuickThink answers rich SRSs as text (no files); loop=50 repeats WritePRD ~50×           |
| MOD-2 | `tools/libs/editor.py`  | `create_file(filename)` → `create_file(file_path)`                                   | LLM emits `file_path=` keyword; tool schema exposes the parameter name                   |
| MOD-3 | `rama.py` (caller)      | classic role lineup instead of `generate_repo()`; preset `config.project_path`       | avoids TeamLeader/QuickThink; skips a fragile JSON-extraction call in `PrepareDocuments` |

```

```
