"""Evaluate reviewed cases; retrieval/guardrails are local, answers calls the LLM."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter

from validate_question_set import HERE, CORPUS, load_dataset, validate, normalize

SCORE_METRICS = ('faithfulness', 'answer_relevancy', 'context_precision', 'context_recall')


def reference_answer(row):
    """Use saved rubric facts, never generated answers, as a reference proxy."""
    points = row.get('required_points')
    if not isinstance(points, list) or not points or not all(
        isinstance(point, str) and point.strip() for point in points
    ):
        return None
    return '\n'.join(point.strip() for point in points)


def scoring_inputs(name, row):
    if name in ('context_precision', 'context_recall'):
        reference = reference_answer(row)
        if reference is None:
            return None
        return dict(user_input=row['query'], reference=reference,
                    retrieved_contexts=row['retrieved_contexts'])
    inputs = dict(user_input=row['query'], response=row['answer'])
    if name == 'faithfulness':
        inputs['retrieved_contexts'] = row['retrieved_contexts']
    return inputs


def scoring_skip_reason(row):
    if row.get('status') != 'ok':
        return 'generation_error'
    if row.get('expected_behavior') != 'answer':
        return 'policy_or_insufficient_evidence_case'
    if row.get('guardrail_route') != 'proceed':
        return 'blocked_by_guardrail'
    if not row.get('answer') or not row.get('retrieved_contexts'):
        return 'missing_answer_or_context'
    return None


def summarize_scores(rows, metric_names=SCORE_METRICS):
    summary = dict(total=len(rows), skipped=sum(r['status'] == 'skipped' for r in rows),
                   errors=sum(r['status'] == 'error' for r in rows))
    for name in metric_names:
        values = [r['metrics'][name]['value'] for r in rows
                  if r.get('metrics', {}).get(name, {}).get('status') == 'ok']
        summary[name] = dict(mean=sum(values)/len(values) if values else None, evaluated=len(values),
                            skipped=sum(r.get('metrics', {}).get(name, {}).get('status') == 'skipped' for r in rows))
    summary['note'] = 'Judge estimates for generated educational answers only. Skips/errors are not zero scores. These metrics do not grade diagnosis/dosage policy, clinical correctness, or missing-information refusals.'
    return summary


def runtime_metadata():
    """Record implementation/dependency versions without reading credential files."""
    from importlib.metadata import version, PackageNotFoundError
    versions = {}
    for name in ('groq', 'sentence-transformers', 'faiss-cpu', 'rank-bm25', 'pypdf'):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    sources = {}
    for name in ('llm_service.py', 'guardrails.py', 'semantic_guardrails.py', 'chunking.py',
                 'dense_retrieval.py', 'sparse_retrieval.py', 'hybrid_retrieval.py'):
        path = HERE.parent / 'app' / 'services' / name
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(python=sys.version.split()[0], packages=versions, service_sha256=sources)


async def score_saved_answers(args):
    """Score saved outputs independently, without regenerating answers or reading test cases."""
    if not args.input:
        raise SystemExit('--mode score requires --input <answers.json>')
    source_bytes = args.input.read_bytes()
    source = json.loads(source_bytes)
    if source.get('configuration', {}).get('mode') != 'answers':
        raise SystemExit('Input must be an answers-mode report.')
    if source['configuration']['split'] != args.split:
        raise SystemExit('Input split differs from --split; test scoring must be explicit.')
    rows = source['results']
    if len({r['id'] for r in rows}) != len(rows):
        raise SystemExit('Duplicate case IDs in input.')
    selected = []
    eligible = 0
    for row in rows:
        if scoring_skip_reason(row) is None:
            if args.limit is not None and eligible >= args.limit:
                continue
            eligible += 1
        selected.append(row)
    if args.dry_run:
        print(f'{len(selected)} input rows; {eligible} educational answers eligible for Ragas.')
        print(f'Metrics: {", ".join(args.metrics)}')
        if any(name.startswith('context_') for name in args.metrics):
            missing = [r['id'] for r in selected if scoring_skip_reason(r) is None and reference_answer(r) is None]
            print(f'Missing references (context metrics will skip): {missing}')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output or HERE / 'results' / f'ragas_{args.split}_{stamp}.json'
    fingerprint = hashlib.sha256(source_bytes).hexdigest()
    config = dict(judge_model=args.judge_model, embedding_model='all-MiniLM-L6-v2',
                  strictness=3, input_sha256=fingerprint, split=args.split, limit=args.limit,
                  metrics=args.metrics, reference_strategy='saved_required_points_joined_v1')
    if args.resume:
        if not args.output or not output.exists():
            raise SystemExit('--resume requires an existing --output.')
        report = json.loads(output.read_text(encoding='utf-8'))
        # Old reports contain only the original two metrics. Resume them only
        # when those metrics are explicitly selected; never mix metric sets.
        if 'metrics' not in report['configuration'] and args.metrics == list(SCORE_METRICS[:2]):
            report['configuration'].update(metrics=args.metrics,
                                           reference_strategy=config['reference_strategy'])
        if report['configuration'] != config:
            raise SystemExit('Cannot resume: input or scoring configuration changed.')
    else:
        if output.exists():
            raise SystemExit(f'Refusing to overwrite {output}; use --resume to continue it.')
        report = dict(created_at=datetime.now(timezone.utc).isoformat(), configuration=config,
                      input_file=str(args.input), results=[])
    os.environ.setdefault('RAGAS_DO_NOT_TRACK', 'true')
    from importlib.metadata import version
    from groq import AsyncGroq
    import instructor
    from ragas.llms import InstructorLLM
    from ragas.embeddings.huggingface_provider import HuggingFaceEmbeddings
    from ragas.metrics.collections import (Faithfulness, AnswerRelevancy,
                                          ContextPrecisionWithReference, ContextRecall)
    sys.path.insert(0, str(HERE.parent))
    from app.core.config import settings
    if not settings.groq_api_key:
        raise SystemExit('GROQ_API_KEY is not configured in backend/.env.')
    report['ragas_version'] = version('ragas')
    embeddings = (HuggingFaceEmbeddings(model=config['embedding_model'], use_api=False)
                  if 'answer_relevancy' in args.metrics else None)
    # Groq's SDK honors Retry-After for 429s; leave time for those waits.
    async with AsyncGroq(api_key=settings.groq_api_key, timeout=45, max_retries=6) as client:
        # Ragas 0.4.3's generic Groq factory expects a messages API that Groq lacks.
        patched_client = instructor.from_groq(client, mode=instructor.Mode.JSON)
        llm = InstructorLLM(model=args.judge_model, provider='groq', client=patched_client,
                            temperature=0, max_tokens=4096)
        factories = dict(faithfulness=lambda: Faithfulness(llm=llm),
                         answer_relevancy=lambda: AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=3),
                         context_precision=lambda: ContextPrecisionWithReference(llm=llm),
                         context_recall=lambda: ContextRecall(llm=llm))
        metrics = {name: factories[name]() for name in args.metrics}
        existing = {r['id']: r for r in report['results']}
        output.parent.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(args.score_workers)
        report['execution'] = dict(workers=args.score_workers)
        order = {row['id']: i for i, row in enumerate(selected)}
        with output.open('r+' if args.resume else 'x', encoding='utf-8') as handle:
            async def process(row):
                async with semaphore:
                    previous = existing.get(row['id'])
                    if previous and previous['status'] in {'ok', 'skipped'}:
                        return
                    result = dict(id=row['id'], category=row['category'], query=row['query'],
                                  metrics=dict(previous.get('metrics', {})) if previous else {})
                    skip = scoring_skip_reason(row)
                    if skip:
                        result.update(status='skipped', reason=skip)
                    else:
                        result['status'] = 'ok'
                        if any(name.startswith('context_') for name in metrics):
                            result['reference'] = reference_answer(row)
                            result['reference_source'] = 'saved_input.required_points'
                        for name, metric in metrics.items():
                            if result['metrics'].get(name, {}).get('status') == 'ok':
                                continue
                            kwargs = scoring_inputs(name, row)
                            if kwargs is None:
                                result['metrics'][name] = dict(status='skipped', value=None,
                                                              reason='missing_reference_points')
                                continue
                            started = perf_counter()
                            try:
                                score = await asyncio.wait_for(metric.ascore(**kwargs), timeout=300)
                                value = float(score.value)
                                if not math.isfinite(value):
                                    raise ValueError('Metric returned a nonfinite score.')
                                result['metrics'][name] = dict(status='ok', value=value, reason=score.reason)
                            except Exception as exc:
                                result['metrics'][name] = dict(status='error', value=None, error=f'{type(exc).__name__}: {exc}')
                                result['status'] = 'error'
                            result['metrics'][name]['elapsed_seconds'] = round(perf_counter()-started, 3)
                            await asyncio.sleep(1)
                    existing[row['id']] = result
                    report['results'] = sorted(existing.values(), key=lambda r: order[r['id']])
                    report['summary'] = summarize_scores(report['results'], args.metrics)
                    # No awaits during the write: completed rows alone are checkpointed.
                    handle.seek(0)
                    json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
                    handle.truncate()
                    handle.flush()
                    print(f'{row["id"]}: {result["status"]}', flush=True)
            await asyncio.gather(*(process(row) for row in selected))
    print(json.dumps(report['summary'], indent=2))
    print(f'Saved {output}')
    if report['summary']['errors']:
        raise SystemExit(1)


def evaluate_case(case, args, dense, sparse, fusion, guards=None, generate=None):
    """Record evidence and routing separately; never infer grounding from keywords."""
    started = perf_counter()
    row = {key: case[key] for key in ('id', 'category', 'query', 'expected_behavior',
                                      'required_points', 'forbidden_behavior', 'evidence')}
    row['status'] = 'ok'
    row['answer_quality_pass'] = None
    try:
        if args.mode != 'retrieval':
            response = guards.check_guardrails(case['query'], dense_index=dense)
            labels = {guards.EMERGENCY_RESPONSE: 'emergency',
                      guards.DOSAGE_REFUSAL_RESPONSE: 'dosage_refusal',
                      guards.OUT_OF_SCOPE_RESPONSE: 'out_of_scope'}
            observed = labels.get(response, 'proceed')
            expected = case['expected_behavior']
            expected_route = 'proceed' if expected in {'answer', 'insufficient_evidence'} else expected
            row.update(guardrail_route=observed, expected_guardrail_route=expected_route,
                       guardrail_route_pass=observed == expected_route)
            if args.diagnostics:
                row['scores'] = dict(
                    emergency=guards.semantic_emergency_score(case['query']),
                    dosage=guards.semantic_dosage_score(case['query']),
                    scope=dense.search_with_scores(case['query'], top_k=1)[0][1])
            if response is not None:
                row.update(answer=response, sources=[], retrieved_contexts=[])
                return row
            if args.mode == 'guardrails':
                return row

        pool = min(10, len(dense.chunks))
        dense_results = dense.search(case['query'], top_k=pool)
        sparse_results = sparse.search(case['query'], top_k=pool)
        results = dict(dense=dense_results[:args.top_k], bm25=sparse_results[:args.top_k],
                       hybrid=fusion(dense_results, sparse_results, k=args.rrf_k,
                                     dense_weight=args.dense_weight, sparse_weight=args.sparse_weight,
                                     top_k=args.top_k))
        methods = list(results) if args.method == 'all' else [args.method]
        row['retrieval'] = {}
        for method in methods:
            chunks = results[method]
            expected_sources = {r['source_file'] for r in case['evidence']}
            row['retrieval'][method] = dict(
                source_hit=bool(expected_sources & {c.source_file for c in chunks}) if expected_sources else None,
                reference_excerpt_hit=any(
                    e['source_file'] == c.source_file and normalize(e['supporting_excerpt']) in normalize(c.text)
                    for e in case['evidence'] for c in chunks) if expected_sources else None,
                chunks=[dict(source_file=c.source_file, chunk_index=c.chunk_index, text=c.text) for c in chunks])
        if args.mode == 'answers':
            chunks = results[args.method]
            row.update(generate(case['query'], chunks))
            row['retrieved_contexts'] = [c.text for c in chunks]
    except Exception as exc:
        row.update(status='error', error=f'{type(exc).__name__}: {exc}')
    finally:
        row['elapsed_seconds'] = round(perf_counter() - started, 3)
    return row


def summarize(rows):
    summary = dict(total=len(rows), errors=sum(r['status'] == 'error' for r in rows))
    routes = [r['guardrail_route_pass'] for r in rows if 'guardrail_route_pass' in r]
    summary['guardrail_routing'] = dict(passed=sum(routes), evaluated=len(routes))
    summary['retrieval_source_hits'] = {}
    summary['retrieval_reference_excerpt_hits'] = {}
    for method in ('dense', 'bm25', 'hybrid'):
        hits = [r['retrieval'][method]['source_hit'] for r in rows
                if method in r.get('retrieval', {}) and r['retrieval'][method]['source_hit'] is not None]
        if hits:
            summary['retrieval_source_hits'][method] = dict(hits=sum(hits), evaluated=len(hits))
        excerpts = [r['retrieval'][method]['reference_excerpt_hit'] for r in rows
                    if r.get('retrieval', {}).get(method, {}).get('reference_excerpt_hit') is not None]
        if excerpts:
            summary['retrieval_reference_excerpt_hits'][method] = dict(hits=sum(excerpts), evaluated=len(excerpts))
    summary['note'] = 'Source hits measure document retrieval, not passage support. Routing is not answer correctness; insufficient-evidence responses and answer quality need separate grading.'
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=HERE / 'question_set_v1.json')
    parser.add_argument('--mode', choices=['retrieval', 'guardrails', 'answers', 'score'], default='retrieval')
    parser.add_argument('--input', type=Path, help='Saved answers JSON for score mode.')
    parser.add_argument('--judge-model', default='openai/gpt-oss-20b', help='Groq-hosted Ragas judge; separate from the answering model.')
    parser.add_argument('--score-workers', type=int, default=1, help='Concurrent Ragas cases (1-4); default 1 suits limited provider quotas.')
    parser.add_argument('--metrics', nargs='+', choices=SCORE_METRICS, default=list(SCORE_METRICS),
                        help='Ragas metrics to run in score mode; defaults to all four.')
    parser.add_argument('--resume', action='store_true', help='Continue a matching score report, retrying failed metrics only.')
    parser.add_argument('--split', choices=['dev', 'test'], default='dev')
    parser.add_argument('--method', choices=['dense', 'bm25', 'hybrid', 'all'], default='hybrid')
    parser.add_argument('--chunking', choices=['fixed', 'recursive'], default='recursive')
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--rrf-k', type=int, default=60)
    parser.add_argument('--dense-weight', type=float, default=1.0)
    parser.add_argument('--sparse-weight', type=float, default=1.0)
    parser.add_argument('--emergency-threshold', type=float)
    parser.add_argument('--dosage-threshold', type=float)
    parser.add_argument('--scope-threshold', type=float)
    parser.add_argument('--diagnostics', action='store_true', help='Record similarity scores in guardrails/answers modes.')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', type=Path, help='JSON results file; never overwrites. Defaults to results/<timestamp>.json.')
    parser.add_argument('--dry-run', action='store_true', help='Validate and list selected IDs without loading models or calling APIs.')
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10 or args.rrf_k <= 0:
        parser.error('top-k must be 1-10 and rrf-k must be positive.')
    if args.dense_weight < 0 or args.sparse_weight < 0 or args.dense_weight + args.sparse_weight <= 0:
        parser.error('Weights must be nonnegative with at least one positive weight.')
    if args.limit is not None and args.limit <= 0:
        parser.error('limit must be positive.')
    if not 1 <= args.score_workers <= 4:
        parser.error('score-workers must be between 1 and 4.')
    if args.mode == 'score':
        asyncio.run(score_saved_answers(args))
        return
    if args.resume or args.input:
        parser.error('--resume and --input are only supported in score mode.')
    if args.method == 'all' and args.mode != 'retrieval':
        parser.error('--method all is only supported for retrieval comparisons.')
    for value in (args.emergency_threshold, args.dosage_threshold, args.scope_threshold):
        if value is not None and not -1 <= value <= 1:
            parser.error('Similarity thresholds must be between -1 and 1.')
    dataset = load_dataset(args.dataset)
    errors = validate(dataset)
    if errors:
        raise SystemExit('\n'.join(errors))
    cases = [c for c in dataset['cases'] if c['split'] == args.split
             and (args.mode != 'retrieval' or c['expected_behavior'] == 'answer')]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        raise SystemExit('No matching cases.')
    if args.dry_run:
        print(f'{args.mode}: {len(cases)} {args.split} cases: ' + ', '.join(c['id'] for c in cases))
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output or HERE / 'results' / f'{args.mode}_{args.split}_{stamp}.json'
    if output.exists():
        raise SystemExit(f'Refusing to overwrite {output}')
    sys.path.insert(0, str(HERE.parent))
    from app.services.document_loader import load_all_documents
    from app.services.chunking import chunk_all_documents, recursive_chunk_all_documents
    from app.services.dense_retrieval import DenseIndex
    from app.services.sparse_retrieval import BM25Index
    from app.services.hybrid_retrieval import reciprocal_rank_fusion
    documents = load_all_documents(CORPUS)
    chunker = chunk_all_documents if args.chunking == 'fixed' else recursive_chunk_all_documents
    chunks = chunker(documents)
    if not chunks:
        raise SystemExit('Corpus contains no readable chunks.')
    dense, sparse = DenseIndex(chunks), BM25Index(chunks)
    guards = generate = None
    if args.mode != 'retrieval':
        from app.services import guardrails as guards
        for option, constant in [('emergency_threshold', 'EMERGENCY_SIMILARITY_THRESHOLD'),
                                 ('dosage_threshold', 'DOSAGE_SIMILARITY_THRESHOLD'),
                                 ('scope_threshold', 'SCOPE_SIMILARITY_THRESHOLD')]:
            if getattr(args, option) is not None:
                setattr(guards, constant, getattr(args, option))
    if args.mode == 'answers':
        from app.services.llm_service import generate_grounded_answer as generate
    report = dict(created_at=datetime.now(timezone.utc).isoformat(),
                  configuration={k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
                  dataset_sha256=hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest(),
                  corpus_manifest=dataset['corpus_manifest'], runtime=runtime_metadata(), results=[])
    if guards:
        report['thresholds'] = {k: getattr(guards, k) for k in
                                ['EMERGENCY_SIMILARITY_THRESHOLD', 'DOSAGE_SIMILARITY_THRESHOLD', 'SCOPE_SIMILARITY_THRESHOLD']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        for case in cases:
            row = evaluate_case(case,args,dense,sparse,reciprocal_rank_fusion,guards,generate)
            report['results'].append(row)
            report['summary'] = summarize(report['results'])
            handle.seek(0)
            json.dump(report,handle,indent=2,ensure_ascii=False)
            handle.truncate()
            handle.flush()
            print(f'{case["id"]}: {row["status"]}', flush=True)
    print(json.dumps(report['summary'],indent=2))
    print(f'Saved {output}')
    if report['summary']['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
