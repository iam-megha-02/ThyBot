# ThyBot evaluation

The reviewed JSON batches are the source of truth. There are 100 questions (60 development, 40 reserved test), with evidence from all nine PDFs. Page numbers are one-based PDF positions. CSVs are optional exports, not another dataset to maintain.

## Files to keep

```text
eval/
  README.md                  Instructions and question index
  question_set_v1.json        Manifest: batch paths and corpus hashes
  validate_question_set.py    Validate questions; optionally export CSV
  run_eval.py                Retrieval, guardrails, answers, and Ragas scoring
  question_sets/             Nine reviewed batches
  results/                   Created only when evaluations are run
```

| Questions | File | Count |
| --- | --- | ---: |
| Foundations | [01_answers_foundations.json](question_sets/01_answers_foundations.json) | 10 |
| Clinical sections | [02_answers_clinical_sections.json](question_sets/02_answers_clinical_sections.json) | 10 |
| Guidelines | [03_answers_guidelines.json](question_sets/03_answers_guidelines.json) | 10 |
| Natural-language questions | [04_paraphrase.json](question_sets/04_paraphrase.json) | 15 |
| Insufficient evidence | [05_insufficient_evidence.json](question_sets/05_insufficient_evidence.json) | 10 |
| Personal dosage | [06_dosage.json](question_sets/06_dosage.json) | 10 |
| Emergency escalation | [07_emergency.json](question_sets/07_emergency.json) | 10 |
| Unrelated requests | [08_out_of_scope.json](question_sets/08_out_of_scope.json) | 10 |
| Boundary cases | [09_boundary.json](question_sets/09_boundary.json) | 15 |

## Validate or review

Run commands from the project root using its existing virtual environment:

```powershell
.\venv\Scripts\python.exe backend/eval/validate_question_set.py
```

This checks IDs, count, exact duplicates, declared family splits, evidence sections/pages/excerpts, and corpus hashes. It does not judge clinical correctness. Edit JSON directly and retain review metadata. Keep related variants in the same split. If you want an Excel review sheet later:

```powershell
.\venv\Scripts\python.exe backend/eval/validate_question_set.py --review-csv backend/eval/dev_review.csv
```

Exports never overwrite existing files. CSV is a snapshot; criteria changes belong in JSON. Additional supporting passages are alternatives, not a requirement to retrieve every source. Reviewing held-out labels is fine; reserve their model outputs until tuning is finished.

## One evaluation runner

List cases without loading embedding models or calling the LLM:

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode answers --dry-run
```

Compare retrieval approaches on development questions that expect an educational answer:

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode retrieval --method all
```

Evaluate routing on all development questions, optionally recording similarity scores:

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode guardrails --diagnostics
```

Collect answers through the same guardrail and generation services used by the application (calls Groq for queries that pass the guardrails):

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode answers
```

Use `--limit 3` for a small run. Results are saved incrementally to timestamped JSON under `results/`, including errors. `--output path.json` selects a filename and refuses overwrites. Embedding models must be available locally or downloadable; answer generation uses the existing backend configuration.

The runner consolidates the previous experiments:

| Experiment | Options |
| --- | --- |
| Dense/BM25/hybrid comparison | `--mode retrieval --method all` |
| Chunking comparison | Separate runs with `--chunking fixed` and `--chunking recursive` |
| RRF tuning | `--rrf-k 60 --dense-weight 1 --sparse-weight 1` |
| Retrieval depth | `--top-k 3` (1–10) |
| Guardrail thresholds | `--emergency-threshold`, `--dosage-threshold`, `--scope-threshold` |
| Similarity diagnostics | `--mode guardrails --diagnostics` |

### Scope threshold decision

The application scope threshold is now 0.35. With the same guardrail code,
the development evaluation improved from 59/60 at 0.20 to 60/60 at 0.35
([0.20 report](results/scope_fix_guardrails_dev.json),
[0.35 report](results/scope_035_guardrails_dev.json)).

The [11 exploratory probes](results/scope_probe_drafts.json) improved from
7/11 to 10/11. Both thresholds allowed all six supported educational questions
that bypass the keyword check. At 0.35, one unrelated request about insulin
resistance and type 2 diabetes still passed with a similarity score of 0.374.
Similarity therefore remains an imperfect scope filter.

These probes are development drafts, include the previously observed acne
failure, and are separate from the reviewed 100 cases. They are not independent
test evidence or proof of answer correctness. The application threshold change
does not alter the historical reports; keep the held-out test split reserved
until development changes are frozen.

Overrides apply to the evaluation process; they do not edit application settings. Defaults match the current application pipeline. Use `--split test` only after development tuning is complete. Tests exposed to tuning should be replaced with new held-out families.

## Interpreting results

Document-source hits are coarse retrieval measurements, not evidence that every answer claim is supported. New runs also report `reference_excerpt_hit`: a complete annotated excerpt must appear inside a retrieved chunk from its source after whitespace normalization. This lexical diagnostic can miss valid alternative passages and split excerpts; it is not semantic recall. Guardrail routing checks refusal/escalation versus proceeding; it cannot judge whether a generated response properly admits insufficient evidence. `answer_quality_pass` remains null for later human or automated grading. Review required facts, prohibited behavior, and source support separately. Exact keyword grounding and automatic citation-presence scores from the old runner were removed because they overstate answer quality.

## Ragas scoring

Install the separately pinned evaluation dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -r backend/requirements-eval.txt
```

Score a saved answers report without regenerating it:

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode score --input backend/eval/results/baseline_answers_dev.json
```

This uses a separate Groq-hosted judge (`openai/gpt-oss-20b` by default, configurable with `--judge-model`). All four metrics run by default:

| Metric | Inputs and meaning |
| --- | --- |
| [Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) | Generated answer and retrieved passages: are answer claims supported? |
| [Answer relevancy](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/answer_relevance/) | Question and generated answer, using three generated questions and local MiniLM embeddings. |
| [Context precision](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_precision/) | Question, reference, and passages in retrieval order; `ContextPrecisionWithReference` judges each passage and calculates average precision, rewarding useful passages ranked early. This is not simply relevant chunks divided by all chunks. |
| [Context recall](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_recall/) | Question, reference, and passages; `ContextRecall` estimates the fraction of reference claims supported by the combined passages. This is not corpus-wide document recall. |

The reference is the saved answer report's `required_points`, joined with newlines without LLM rewriting. Each scored row stores the exact `reference` and its provenance. These reviewed rubric facts are a reference proxy, not an independently validated complete gold answer: omissions, ambiguous pronouns, or policy caveats can affect the scores. Inspect the stored reference alongside its case evidence before interpreting a low recall score. The generated answer is never used as the reference. Missing or invalid points explicitly skip the two context metrics while other metrics can still run. No metric establishes clinical correctness or compliance with personalized-advice restrictions.

Run only the new metrics on one eligible saved answer first:

```powershell
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode score --input backend/eval/results/baseline_answers_dev.json --metrics context_precision context_recall --limit 1
```

Remove `--limit 1` for all eligible saved answers. This evaluates historical retrieval; it does not rerun the current application. In the pinned implementation, context precision makes one judge call per passage, and recall makes one call per case, before retries. A context-only run does not load the local embedding model. The reviewed question files and saved answers remain unchanged.

Only successful, generated educational answers with context are scored. Policy cases, insufficient-evidence cases, and false guardrail blocks get explicit skip reasons. Each metric summary reports its own denominator; failures and skips are never silently counted as zero. All 60 development cases remain visible in the full score report, including skipped cases. `--limit 1` scores one eligible answer for a smoke check; `--dry-run` lists eligibility without model calls.

Scores are saved after each case. Requests default to one concurrent case (`--score-workers 1`) and use SDK retries for provider rate limits. To retry failed metrics or continue an interrupted run, repeat the same command with `--output <saved-report>` and `--resume`. Successful scores are retained, and the input hash, judge configuration, metric selection, reference strategy, split, and limit must match. To resume a historical two-metric report, explicitly select `--metrics faithfulness answer_relevancy` with its original input and options. To add context metrics, create a separate report with `--metrics context_precision context_recall`; changing metric sets within a report is rejected. Ragas telemetry is disabled by default in score mode. Ragas 0.4.3 requires the pinned LangChain Community version; its generic Groq adapter is bypassed using Instructor's native Groq integration.

Use the saved baseline to identify failures before changing retrieval settings or guardrails. Reserve the 40 test cases until development tuning is finished. The old dataset builders and duplicate spreadsheets remain removed; this workflow continues to use two Python files.
