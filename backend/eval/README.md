# ThyBot evaluation

This folder checks whether ThyBot actually works, not just whether it runs.

100 hand-written, hand-reviewed questions: 60 for development (tune against these) and 40 reserved for a final test (don't touch until development is done). Each question is backed by evidence from one of the 9 PDFs. JSON is the source of truth; CSV is just an optional export for reviewing in a spreadsheet.

## What's in here

```text
eval/
  question_set_v1.json        list of question files + a hash of the PDFs
  validate_question_set.py    sanity-checks the questions (not the AI's answers)
  run_eval.py                 the test runner: retrieval, guardrails, answers, scoring
  question_sets/              the 9 files of reviewed questions
  results/                    test output lands here once you run something
```

| Questions | File | Count |
| --- | --- | ---: |
| Foundations | [01_answers_foundations.json](question_sets/01_answers_foundations.json) | 10 |
| Clinical sections | [02_answers_clinical_sections.json](question_sets/02_answers_clinical_sections.json) | 10 |
| Guidelines | [03_answers_guidelines.json](question_sets/03_answers_guidelines.json) | 10 |
| Reworded questions | [04_paraphrase.json](question_sets/04_paraphrase.json) | 15 |
| Not enough evidence | [05_insufficient_evidence.json](question_sets/05_insufficient_evidence.json) | 10 |
| Personal dosage | [06_dosage.json](question_sets/06_dosage.json) | 10 |
| Emergencies | [07_emergency.json](question_sets/07_emergency.json) | 10 |
| Off-topic | [08_out_of_scope.json](question_sets/08_out_of_scope.json) | 10 |
| Tricky edge cases | [09_boundary.json](question_sets/09_boundary.json) | 15 |

## Validate the question set

Checks IDs, duplicates, and that every claimed piece of evidence actually points to a real section/page/quote, not whether the medical content is correct:

```powershell
.\venv\Scripts\python.exe backend/eval/validate_question_set.py
```

## Run an evaluation

One script, different modes:

```powershell
# dry run, no models loaded, no AI calls
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode answers --dry-run

# compare meaning-based / keyword / combined retrieval
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode retrieval --method all

# check guardrails route each question correctly
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode guardrails --diagnostics

# generate real answers (calls Groq)
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode answers
```

Add `--limit 3` to try a handful first. Results save as timestamped JSON under `results/`, including errors. `--output path.json` picks a filename (won't overwrite).

| What you're testing | How |
| --- | --- |
| Retrieval method | `--mode retrieval --method all` |
| Chunking strategy | `--chunking fixed` vs `--chunking recursive` |
| How rankings combine | `--rrf-k`, `--dense-weight`, `--sparse-weight` |
| Chunks retrieved | `--top-k 3` (try 1-10) |
| Guardrail sensitivity | `--emergency-threshold`, `--dosage-threshold`, `--scope-threshold` |

Overrides only affect this script, not the real app. Only run against the 40 reserved questions once development tuning is finished.

**Why the scope threshold is 0.35:** at 0.20 the guardrail got 59/60 dev questions right; at 0.35 it got 60/60 ([0.20](results/scope_fix_guardrails_dev.json), [0.35](results/scope_035_guardrails_dev.json)). Not perfect, one unrelated diabetes question still slipped through at 0.35, but the best tradeoff found so far.

## Reading the results

A document "hit" doesn't mean the right sentence was found or the answer was correct, just a rough signal. `reference_excerpt_hit` is stricter (looks for the exact expected quote) but can miss valid answers phrased differently. Guardrail routing only checks answer/refuse/escalate, not whether the generated answer itself was good.

## Scoring answers with Ragas

Separate library, separate AI judge, separate dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -r backend/requirements-eval.txt
.\venv\Scripts\python.exe backend/eval/run_eval.py --mode score --input backend/eval/results/baseline_answers_dev.json
```

| Metric | What it checks |
| --- | --- |
| [Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) | Is the answer backed by the retrieved text? |
| [Answer relevancy](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/answer_relevance/) | Does it address the actual question? |
| [Context precision](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_precision/) | Were the useful chunks ranked near the top? |
| [Context recall](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_recall/) | Do the chunks together cover what's needed? |

Test on one case first: add `--metrics context_precision context_recall --limit 1`. Scores save after every case, so an interrupted run can resume with `--resume` (same input, judge, and metrics).

## Bottom line

Use the saved baseline to spot problems before changing retrieval or guardrail settings. Keep the 40 test questions untouched until development tuning is actually finished.
