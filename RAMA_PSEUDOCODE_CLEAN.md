# RAMA — Full-System Pseudocode (Clean)

RAMA Thesis — Devinder Shuthwal, LJMU 2026

Main logic only. No module/week labels, no error handling. Organised as:
orchestration → elicitation → retrieval → generation → measurement → experiments.

---

## Section 1 — Main Pipeline

```
FUNCTION run_rama(requirement, config):
    IF config.skip_elicitation:                       # baseline: no elicitation
        enriched_srs ← requirement
        result       ← NULL
    ELSE:
        (enriched_srs, result) ← elicit(requirement, config)
        display_completeness(result.pre, result.post)
        IF NOT user_confirms(): RETURN

    metagpt_stats ← generate_architecture(enriched_srs, config)
    write_analysis_report(project, requirement, result, metagpt_stats)
```

---

## Section 2 — Requirement Elicitation

```
FUNCTION elicit(requirement, config):
    parsed   ← parse(requirement, config.use_llm_parse)
    pre      ← analyse_completeness(parsed)
    session  ← run_dialogue(requirement, pre, config)
    enriched ← synthesise(requirement, session, config.use_llm_synthesis)

    IF enriched = requirement:                        # no answers → no change
        post ← pre
    ELSE:
        post ← analyse_completeness(parse(enriched, use_llm = FALSE))

    log_metrics(pre, post, session)
    RETURN (enriched, RunResult(pre, post, session, tokens, timings))
```

### Parser

```
FUNCTION parse(requirement, use_llm):
    hints ← scan requirement for each schema category's keywords
    IF use_llm:
        fields ← LLM_extract(requirement)             # actors, entities, intents, NFRs
    ELSE:
        fields ← regex_extract(requirement)           # deterministic heuristics
    RETURN ParsedSRS(fields, hints)
```

### Completeness Analyser

```
FUNCTION analyse_completeness(parsed):
    FOR each category IN SCHEMA:                       # 24 categories
        covered[category] ← parsed.hints[category]
                            OR any category.keyword appears in parsed.text
    covered_set   ← categories where covered
    missing_set   ← remaining categories
    raw_score     ← |covered_set| / 24
    weighted      ← Σ weight(covered_set) / 58
    critical_gaps ← missing categories with weight = 3
    RETURN Report(raw_score, weighted, covered_set, missing_set, critical_gaps)
```

### Question Prioritisation & Dialogue

```
FUNCTION run_dialogue(requirement, report, config):
    gaps ← report.missing_set
    IF config.random_questions:                        # control condition
        questions ← random_sample(gaps, config.max_questions)
    ELSE:                                              # prioritised
        questions ← sort gaps by (weight DESC, group order)
                    then take top config.max_questions

    IF config.use_rag:
        FOR each q IN questions:
            q.hints ← knowledge_base_query(q.text, q.category)

    session ← new Session(requirement)
    FOR each q IN questions:
        answer ← get_answer(q, config.mode)
        IF answer valid:
            session.answers[q.category] ← answer
    RETURN session


FUNCTION get_answer(question, mode):
    SWITCH mode:
        silent:      RETURN none                       # measure only, no answers
        interactive: RETURN human_selects_or_types(question)
        llm:         RETURN LLM_answer_as_stakeholder(question)
```

### Synthesiser

```
FUNCTION synthesise(requirement, session, use_llm):
    clarifications ← session.answers
    IF clarifications empty:
        RETURN requirement
    IF use_llm:
        RETURN LLM_rewrite(requirement, clarifications)     # one coherent SRS
    ELSE:
        RETURN requirement + bullet_list(clarifications)    # template append
```

---

## Section 3 — Domain Knowledge Base (Retrieval)

```
FUNCTION knowledge_base_query(text, category):
    embedding ← embed(text)
    RETURN vector_store.search(embedding, filter = category, top_k = 2)
```

---

## Section 4 — Architecture Generation

```
FUNCTION generate_architecture(enriched_srs, config):
    set_workspace_path(project)
    team ← [ ProductManager, Architect, ProjectManager ]
    IF NOT config.docs_only:
        team ← team + [ Engineer ]

    publish(enriched_srs) AS user_requirement
    start ← now
    REPEAT config.n_round TIMES:
        IF all agents idle: BREAK
        FOR each agent IN team:
            agent_react(agent)
    RETURN cost_stats(prompt_tokens, completion_tokens, cost, now − start)


FUNCTION agent_react(agent):
    news ← observe(agent.watched_messages)
    IF no news: RETURN idle
    action ← agent.decide_next_action()
    output ← run(action)                # writes PRD / design / tasks / code
    publish(output)                     # wakes the next agent in the chain
```

Agent collaboration is watch-driven — each artefact triggers the next stage:

```
requirement ─▶ PRD ─▶ system design ─▶ task list ─▶ [ code ]
```

---

## Section 5 — Measurement & Analysis

```
FUNCTION write_analysis_report(project, requirement, result, metagpt_stats):
    IF result = NULL:                                  # baseline
        raw_score          ← analyse_completeness(parse(requirement, FALSE)).raw
        final_score        ← N/A
        elicitation_tokens ← 0
    ELSE:
        raw_score          ← result.pre.raw
        final_score        ← result.post.raw
        elicitation_tokens ← result.tokens

    acqs ← score_acqs(project.system_design)

    emit report:
        completeness : raw_score, final_score, (final − raw), critical_gaps
        tokens       : elicitation_tokens, metagpt_stats.tokens, total
        latency      : elicitation stages, metagpt, total
        acqs         : overall + per attribute
```

### ACQS — Architecture Coverage Quality Score

```
FUNCTION score_acqs(system_design):
    text ← contents of system_design
    FOR each attribute IN {security, scalability, cost,
                           performance, availability, modifiability}:
        FOR each indicator_group OF attribute:
            covered[group] ← any indicator pattern matches text
        attribute_score[attribute] ← |covered groups| / |groups|
    ACQS ← mean(attribute_score)                       # 0–1
    RETURN (ACQS, attribute_score)
```

---

## Section 6 — Experiment Configurations

Each experiment is one setting of the config switches over the same input:

```
Baseline        : skip_elicitation = TRUE
Full system     : all switches ON
− Retrieval     : use_rag = FALSE
− LLM parse     : use_llm_parse = FALSE
− LLM synthesis : use_llm_synthesis = FALSE
− All three     : the three above OFF together
Random control  : random_questions = TRUE
Question sweep  : vary max_questions
Answer source   : mode = interactive  vs  mode = llm
```

---

## Reference constants

```
SCHEMA               : 24 categories
  groups             : FUNCTIONAL (12), NON_FUNCTIONAL (4), DOMAIN (8)
  weights            : critical=3 (10 categories), important=2 (14), Σ = 58
completeness (raw)   : |covered| / 24
completeness (wtd)   : Σ weight(covered) / 58
ACQS attributes      : security, scalability, cost, performance,
                       availability, modifiability
```
