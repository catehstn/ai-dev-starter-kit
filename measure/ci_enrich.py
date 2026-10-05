#!/usr/bin/env python3
"""Step 2: add CI effort columns to prs.csv.

    python3 ci_enrich.py --repo owner/name [--csv prs.csv] [--only 12,34] [--refresh] [--check]

For each PR: one call for its commits and changed files, then one call per commit for
the number of check runs on it. Paced at ~1s per call, so a few thousand calls is an
hour or so. Progress is saved every 10 PRs; re-running picks up where it stopped (only
rows without ci_status=ok are fetched, unless --refresh or --only).

A failed call marks the row `ci_status=error: ...`. It never writes a zero in place of
missing data. At the end every problem row is listed and the exit code is 1 if any
remain, so re-run (or --only the listed numbers) before reading the numbers.
"""
import argparse
import sys

import prdata


def enrich(api, repo, row):
    view = api.gh_json('pr', 'view', row['number'], '--repo', repo, '--json', 'commits,files')
    shas = [c['oid'] for c in view.get('commits', [])]
    test_files = sum(1 for f in view.get('files', []) if prdata.is_test_path(f.get('path')))
    if not shas:
        raise RuntimeError('gh returned 0 commits')
    counts = []
    for sha in shas:
        out = api.gh('api', f'repos/{repo}/commits/{sha}/check-runs?per_page=1', '--jq', '.total_count')
        counts.append(int(out.strip()))
    final, total = counts[-1], sum(counts)
    churn = total - final
    row.update({
        'commits': str(len(shas)),
        'final_checks': str(final),
        'total_checks': str(total),
        'rerun_churn': str(churn),
        'rerun_rounds': f'{churn / final:.2f}' if final else '',
        'contains_tests': '1' if test_files else '0',
        'test_files_touched': str(test_files),
        'ci_status': 'ok',
    })


def report(rows):
    errors, warnings = prdata.problems(rows)
    for n, why in warnings:
        print(f'  warn  #{n}: {why}')
    for n, why in errors:
        print(f'  ERROR #{n}: {why}')
    ok = len(rows) - len(errors)
    print(f'{ok}/{len(rows)} rows complete, {len(errors)} errors, {len(warnings)} warnings.')
    if errors:
        print('Re-run with --only ' + ','.join(n for n, _ in errors))
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True, help='owner/name')
    ap.add_argument('--csv', default='prs.csv')
    ap.add_argument('--only', help='comma-separated PR numbers to (re)fetch')
    ap.add_argument('--refresh', action='store_true', help='re-fetch every row (check counts drift up; see README)')
    ap.add_argument('--check', action='store_true', help='only validate the CSV, no API calls')
    ap.add_argument('--pace', type=float, default=prdata.DEFAULT_PACE, help='seconds between API calls')
    a = ap.parse_args()

    rows = prdata.read_prs(a.csv)
    if a.check:
        sys.exit(report(rows))

    if a.only:
        want = {s.strip().lstrip('#') for s in a.only.split(',') if s.strip()}
        todo = [r for r in rows if r['number'] in want]
    elif a.refresh:
        todo = rows
    else:
        todo = [r for r in rows if r['ci_status'] != 'ok']
    print(f'Enriching {len(todo)} of {len(rows)} PRs at {a.pace}s/call...')

    api = prdata.Paced(a.pace)
    try:
        for i, row in enumerate(todo, 1):
            try:
                enrich(api, a.repo, row)
            except Exception as e:  # noqa: BLE001 - record it on the row, keep going
                for c in prdata.CI_COLUMNS:
                    row[c] = ''
                row['ci_status'] = f'error: {e}'[:200]
            if i % 10 == 0:
                prdata.write_prs(a.csv, rows)
                print(f'  ...{i}/{len(todo)}')
    finally:
        prdata.write_prs(a.csv, rows)
    sys.exit(report(rows))


if __name__ == '__main__':
    main()
