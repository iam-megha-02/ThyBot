"""Offline structural/evidence checks; does not grade medical correctness."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / 'data' / 'clinical_documents'


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def load_dataset(path):
    """Read a legacy monolith or a manifest and its small case files."""
    path = Path(path).resolve()
    dataset = json.loads(path.read_text(encoding='utf-8'))
    if dataset.get('schema_version') == 2:
        if 'cases' in dataset:
            raise ValueError('Version 2 must use case_files, not inline cases.')
        files = dataset['case_files']
        if not files or len(files) != len(set(files)):
            raise ValueError('Missing or duplicated case_files.')
        cases = []
        for name in files:
            file = (path.parent / name).resolve()
            if not file.is_relative_to(path.parent) or file == path:
                raise ValueError(f'Invalid case file path: {name}')
            cases.extend(json.loads(file.read_text(encoding='utf-8'))['cases'])
        if len(cases) != dataset['expected_case_count']:
            raise ValueError(f'Expected {dataset["expected_case_count"]} cases, found {len(cases)}.')
        dataset['cases'] = cases
    elif dataset.get('schema_version') != 1:
        raise ValueError('Unsupported schema_version.')
    return dataset


def validate(dataset):
    errors = []
    ids, queries, groups, readers = set(), set(), {}, {}
    behaviors = {'answer', 'dosage_refusal', 'emergency', 'out_of_scope', 'insufficient_evidence'}
    categories = {'answerable', 'paraphrase', 'dosage', 'emergency', 'out_of_scope', 'insufficient_evidence', 'boundary'}
    manifest = {item['source_file']: item['sha256'] for item in dataset['corpus_manifest']}
    actual = {p.name for p in CORPUS.glob('*.pdf')}
    if set(manifest) != actual:
        errors.append('Corpus file list changed; review the dataset against the new corpus.')
    for filename, digest in manifest.items():
        path = CORPUS / filename
        if Path(filename).name != filename or not path.is_file():
            errors.append(f'Invalid or missing corpus file: {filename}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f'Corpus file changed: {filename}')
    if not dataset['cases']:
        errors.append('No cases found.')
    for case in dataset['cases']:
        id = case['id']
        query = normalize(case['query']).casefold()
        if id in ids or query in queries:
            errors.append(f'{id}: duplicate ID or query')
        ids.add(id)
        queries.add(query)
        if not query or case['split'] not in {'dev', 'test'}:
            errors.append(f'{id}: empty query or invalid split')
        if case['category'] not in categories or case['expected_behavior'] not in behaviors:
            errors.append(f'{id}: invalid category or expected behavior')
        group = case['group_id']
        if not group or groups.setdefault(group, case['split']) != case['split']:
            errors.append(f'{id}: missing group or group leaks across splits')
        for field in ('required_points', 'forbidden_behavior'):
            if not isinstance(case[field], list) or not case[field] or not all(isinstance(x, str) and x.strip() for x in case[field]):
                errors.append(f'{id}: {field} must contain nonempty review criteria')
        if not case['label_rationale'] or not case['review_status']:
            errors.append(f'{id}: missing rationale or review status')
        if case['expected_behavior'] == 'answer' and not case['evidence']:
            errors.append(f'{id}: answer case requires supporting evidence')
        for ref in case['evidence']:
            if dataset.get('schema_version') == 2 and not ref.get('section', '').strip():
                errors.append(f'{id}: missing evidence section label')
            filename, page = ref['source_file'], ref['pdf_page']
            if filename not in manifest or Path(filename).name != filename:
                errors.append(f'{id}: evidence file absent from corpus manifest')
                continue
            if filename not in readers:
                readers[filename] = PdfReader(CORPUS / filename)
            if type(page) is not int or not 1 <= page <= len(readers[filename].pages):
                errors.append(f'{id}: invalid PDF page')
                continue
            excerpt = normalize(ref['supporting_excerpt'])
            text = normalize(readers[filename].pages[page - 1].extract_text() or '')
            if not excerpt or excerpt not in text:
                errors.append(f'{id}: excerpt not found on cited PDF page')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=HERE / 'question_set_v1.json')
    parser.add_argument('--review-csv', type=Path, help='Create a blank manual grading sheet; never overwrites.')
    parser.add_argument('--split', choices=['dev', 'test'], default='dev', help='Split to export; validation checks both splits.')
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset)
        errors = validate(dataset)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SystemExit(f'Invalid dataset: {exc}')
    if errors:
        raise SystemExit('\n'.join(errors))
    cases = dataset['cases']
    print(f'Validated {len(cases)} cases: {dict(Counter(c["split"] for c in cases))}')
    print(f'Categories: {dict(Counter(c["category"] for c in cases))}')
    print('All cited excerpts match their PDF pages; corpus hashes match.')
    coverage = {(r['source_file'], r['pdf_page']) for c in cases for r in c['evidence']}
    print(f'Evidence coverage: {len({name for name, _ in coverage})} PDFs, {len(coverage)} document/page pairs.')
    print('This does not establish answer quality, clinical validity, or semantic split independence.')
    if args.review_csv:
        fields = ['id', 'query', 'expected_behavior', 'required_points', 'forbidden_behavior', 'evidence',
                  'actual_answer', 'actual_sources', 'behavior_pass', 'required_points_pass',
                  'evidence_support_pass', 'no_forbidden_behavior_pass', 'reviewer', 'reviewed_at', 'notes']
        with args.review_csv.open('x', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for case in cases:
                if case['split'] == args.split:
                    writer.writerow({field: json.dumps(case[field], ensure_ascii=False) if isinstance(case[field], list) else case[field]
                                     for field in fields if field in case})
        print(f'Created blank {args.split} review sheet: {args.review_csv}')


if __name__ == '__main__':
    main()
